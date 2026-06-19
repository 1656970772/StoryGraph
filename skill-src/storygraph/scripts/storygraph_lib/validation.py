from dataclasses import dataclass
import json
from pathlib import Path

from .agent_ledger import validate_single_writer
from .graph_schema import validate_canonical_graph
from .state import REQUIRED_STAGE1_FILES


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    missing: list[str]


@dataclass(frozen=True)
class GraphDirValidation:
    ok: bool
    errors: list[str]


def validate_skill_tree(root: Path) -> ValidationResult:
    required = [
        "SKILL.md",
        "agents/openai.yaml",
        "config/storygraph.default.json",
        "references/workflow.md",
        "references/graph-schema.md",
        "references/extraction-workflow.md",
        "scripts/storygraph.py",
        "scripts/sync-skill.ps1",
    ]
    missing = [item for item in required if not (root / item).exists()]
    return ValidationResult(ok=not missing, missing=missing)


def validate_graph_dir(graph_dir: Path) -> GraphDirValidation:
    graph_dir = Path(graph_dir)
    errors = [f"missing:{item}" for item in REQUIRED_STAGE1_FILES if not (graph_dir / item).exists()]
    agent_ledger = _read_json(graph_dir / "coverage" / "agent-run-ledger.json", default=[])
    if not isinstance(agent_ledger, list):
        errors.append("bad_json:coverage/agent-run-ledger.json")
        agent_ledger = []

    for record in agent_ledger:
        if not isinstance(record, dict) or record.get("status") != "failed":
            continue
        record_errors = record.get("errors") or [{"code": "unknown"}]
        for error in record_errors:
            code = error.get("code", "unknown") if isinstance(error, dict) else "unknown"
            errors.append(f"blocking_ledger:{code}")

    if errors:
        return GraphDirValidation(False, _dedupe(errors))

    manifest = _read_json(graph_dir / "manifest.json", default={})
    graph = _read_json(graph_dir / "graphify-out" / "graph.json", default={})
    requirements = _read_json(graph_dir / "requirements" / "template-requirements.json", default={})
    chunks = _read_json(graph_dir / "coverage" / "chunk-ledger.json", default=[])
    coverage_evidence = _read_json(graph_dir / "coverage" / "evidence-index.json", default=[])
    readiness = _read_json(graph_dir / "coverage" / "template-readiness.json", default=[])

    if not isinstance(manifest, dict):
        errors.append("bad_json:manifest.json")
        manifest = {}
    if not isinstance(graph, dict):
        errors.append("bad_json:graphify-out/graph.json")
        graph = {}
    if not isinstance(requirements, dict):
        errors.append("bad_json:requirements/template-requirements.json")
        requirements = {}
    if not isinstance(chunks, list):
        errors.append("bad_json:coverage/chunk-ledger.json")
        chunks = []
    if not isinstance(coverage_evidence, list):
        errors.append("bad_json:coverage/evidence-index.json")
        coverage_evidence = []
    if not isinstance(readiness, list):
        errors.append("bad_json:coverage/template-readiness.json")
        readiness = []

    single_writer = validate_single_writer(agent_ledger)
    if not single_writer.ok:
        errors.extend(single_writer.errors)

    schema = validate_canonical_graph(graph, requirements.get("status_enums"))
    errors.extend(schema.errors)
    errors.extend(_validate_requirements_readiness(requirements, readiness))
    errors.extend(_validate_chunks(manifest, chunks))
    errors.extend(_validate_evidence_links(graph, coverage_evidence))

    stage1_status = manifest.get("stage_status", {}).get("stage1")
    if stage1_status != "success":
        errors.append(f"stage1_not_success:{stage1_status}")
    if stage1_status == "success" and any(record.get("status") != "completed" for record in agent_ledger):
        errors.append("agent_run_not_completed")

    return GraphDirValidation(ok=not errors, errors=_dedupe(errors))


def _validate_requirements_readiness(requirements: dict, readiness: list[dict]) -> list[str]:
    errors: list[str] = []
    requirement_records = requirements.get("templates", [])
    if not isinstance(requirement_records, list):
        return ["requirements_templates_not_list"]
    requirement_templates = {
        record.get("template_name") for record in requirement_records if isinstance(record, dict)
    }
    readiness_templates = {
        record.get("template_name") for record in readiness if isinstance(record, dict)
    }
    if requirement_templates != readiness_templates:
        errors.append("requirements_readiness_template_mismatch")

    count_policy = requirements.get("template_count_policy")
    if isinstance(count_policy, dict):
        expected = count_policy.get("expected_existing_templates")
        if count_policy.get("enforce_integration_count") and expected is not None:
            if requirements.get("template_count") != expected or len(readiness) != expected:
                errors.append(f"template_readiness_count_not_{expected}")
    elif requirements.get("template_count") == 37 and len(readiness) != 37:
        errors.append("template_readiness_count_not_37")

    expected_ids = set()
    for record in requirement_records:
        if not isinstance(record, dict):
            continue
        template_name = record.get("template_name")
        seen: set[tuple[str, str]] = set()
        for kind, key in [
            ("fields", "required_fields"),
            ("tables", "required_tables"),
            ("cards", "required_cards"),
            ("cards", "required_card_headings"),
            ("cards", "required_card_fields"),
            ("cases", "required_case_patterns"),
        ]:
            for item in record.get(key, []):
                marker = (kind, item)
                if marker in seen:
                    continue
                seen.add(marker)
                expected_ids.add(f"{template_name}.{key}.{item}")

    actual_ids = {
        status.get("requirement_id")
        for record in readiness
        if isinstance(record, dict)
        for status in record.get("requirement_statuses", [])
        if isinstance(status, dict)
    }
    if expected_ids != actual_ids:
        errors.append("requirements_readiness_id_mismatch")

    allowed_statuses = set(
        requirements.get("status_enums", {}).get(
            "requirement_statuses", ["covered", "needs_review", "not_found_in_source"]
        )
    )
    for record in readiness:
        if not isinstance(record, dict):
            errors.append("bad_readiness_record")
            continue
        if not record.get("requirement_statuses"):
            errors.append("readiness_without_requirement_statuses")
        for status in record.get("requirement_statuses", []):
            if status.get("status") not in allowed_statuses:
                errors.append(f"bad_readiness_status:{status.get('status')}")
    return errors


def _validate_chunks(manifest: dict, chunks: list[dict]) -> list[str]:
    if not chunks:
        return ["chunk_ledger_empty"]
    errors: list[str] = []
    ordered = sorted(chunks, key=lambda chunk: chunk.get("source_range", [0, 0])[0])
    expected_length = _expected_source_length(manifest)
    first_range = ordered[0].get("source_range", [])
    last_range = ordered[-1].get("source_range", [])
    if first_range[:1] != [0] or not last_range or last_range[-1] != expected_length:
        errors.append("chunk_ledger_does_not_cover_full_source")
    for previous, current in zip(ordered, ordered[1:]):
        previous_end = previous.get("source_range", [0, 0])[1]
        current_start = current.get("source_range", [0, 0])[0]
        if current_start > previous_end:
            errors.append("chunk_ledger_has_gap")
    for chunk in ordered:
        if chunk.get("extraction_status") != "completed":
            errors.append(f"chunk_not_completed:{chunk.get('chunk_id')}:{chunk.get('extraction_status')}")
    return errors


def _validate_evidence_links(graph: dict, coverage_evidence: list[dict]) -> list[str]:
    errors: list[str] = []
    graph_evidence_ids = {
        item.get("evidence_id") for item in graph.get("evidence_index", []) if isinstance(item, dict)
    }
    coverage_evidence_ids = {
        item.get("evidence_id") for item in coverage_evidence if isinstance(item, dict)
    }
    if graph_evidence_ids != coverage_evidence_ids:
        errors.append("graph_coverage_evidence_mismatch")
    for item in graph.get("nodes", []) + graph.get("edges", []) + graph.get("events", []):
        if not isinstance(item, dict):
            continue
        for evidence_id in item.get("evidence_ids", []):
            if evidence_id not in graph_evidence_ids:
                errors.append(f"unknown_evidence_reference:{item.get('id')}")
    return errors


def _expected_source_length(manifest: dict) -> int:
    source_path = manifest.get("source_path")
    if source_path:
        try:
            return len(Path(source_path).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            pass
    return int(manifest.get("source_size") or 0)


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"__bad_json__": str(path)}


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
