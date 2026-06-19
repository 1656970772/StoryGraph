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


DEFAULT_REQUIREMENT_STATUSES = ["covered", "needs_review", "not_found_in_source"]
REQUIRED_STAGE1_AGENT_ROLES = ["模板需求分析", "图抽取", "覆盖审查", "质量审查"]


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
    agent_ledger = _read_json(
        graph_dir, "coverage/agent-run-ledger.json", default=[], errors=errors
    )
    if not isinstance(agent_ledger, list):
        errors.append("bad_shape:coverage/agent-run-ledger.json")
        agent_ledger = []

    for record in agent_ledger:
        if not isinstance(record, dict) or record.get("status") != "failed":
            continue
        record_errors = _safe_agent_ledger_errors(record, errors)
        for error in record_errors:
            code = error.get("code", "unknown") if isinstance(error, dict) else "unknown"
            errors.append(f"blocking_ledger:{code}")

    if errors:
        return GraphDirValidation(False, _dedupe(errors))

    manifest = _read_json(graph_dir, "manifest.json", default={}, errors=errors)
    graph = _read_json(graph_dir, "graphify-out/graph.json", default={}, errors=errors)
    requirements = _read_json(
        graph_dir, "requirements/template-requirements.json", default={}, errors=errors
    )
    chunks = _read_json(graph_dir, "coverage/chunk-ledger.json", default=[], errors=errors)
    coverage_evidence = _read_json(
        graph_dir, "coverage/evidence-index.json", default=[], errors=errors
    )
    readiness = _read_json(
        graph_dir, "coverage/template-readiness.json", default=[], errors=errors
    )

    if not isinstance(manifest, dict):
        errors.append("bad_shape:manifest.json")
        manifest = {}
    if not isinstance(graph, dict):
        errors.append("bad_shape:graphify-out/graph.json")
        graph = {}
    if not isinstance(requirements, dict):
        errors.append("bad_shape:requirements/template-requirements.json")
        requirements = {}
    if not isinstance(chunks, list):
        errors.append("bad_shape:coverage/chunk-ledger.json")
        chunks = []
    if not isinstance(coverage_evidence, list):
        errors.append("bad_shape:coverage/evidence-index.json")
        coverage_evidence = []
    if not isinstance(readiness, list):
        errors.append("bad_shape:coverage/template-readiness.json")
        readiness = []

    single_writer = validate_single_writer(agent_ledger)
    if not single_writer.ok:
        errors.extend(single_writer.errors)

    status_enums = _normalized_status_enums(requirements, errors)
    schema = validate_canonical_graph(graph, status_enums)
    errors.extend(schema.errors)
    errors.extend(_validate_requirements_readiness(requirements, readiness, status_enums))
    errors.extend(_validate_chunks(manifest, chunks))
    errors.extend(_validate_evidence_links(graph, coverage_evidence))

    stage1_status = _stage1_status(manifest, errors)
    if stage1_status != "success":
        errors.append(f"stage1_not_success:{stage1_status}")
    if stage1_status == "success":
        errors.extend(_validate_required_agent_roles(agent_ledger))
    if stage1_status == "success" and any(
        not isinstance(record, dict) or record.get("status") != "completed"
        for record in agent_ledger
    ):
        errors.append("agent_run_not_completed")

    return GraphDirValidation(ok=not errors, errors=_dedupe(errors))


def _safe_agent_ledger_errors(record: dict, errors: list[str]) -> list:
    record_errors = record.get("errors")
    if record_errors in (None, []):
        return [{"code": "unknown"}]
    if not isinstance(record_errors, list):
        errors.append(f"bad_agent_ledger_errors:{_agent_record_owner(record)}")
        return [{"code": "unknown"}]
    return record_errors


def _agent_record_owner(record: dict) -> str:
    return str(record.get("run_id") or record.get("agent_role") or "unknown")


def _stage1_status(manifest: dict, errors: list[str]):
    stage_status = manifest.get("stage_status", {})
    if not isinstance(stage_status, dict):
        errors.append("bad_manifest_stage_status")
        return None
    return stage_status.get("stage1")


def _validate_requirements_readiness(
    requirements: dict, readiness: list[dict], status_enums: dict | None
) -> list[str]:
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
            items = record.get(key, [])
            if not isinstance(items, list):
                errors.append(f"bad_requirement_list:{template_name}:{key}")
                continue
            for item in items:
                marker = (kind, item)
                if marker in seen:
                    continue
                seen.add(marker)
                expected_ids.add(f"{template_name}.{key}.{item}")

    actual_ids = {
        status.get("requirement_id")
        for record in readiness
        if isinstance(record, dict)
        for status in _safe_statuses(record.get("requirement_statuses"))
        if isinstance(status, dict)
    }
    if expected_ids != actual_ids:
        errors.append("requirements_readiness_id_mismatch")

    configured_statuses = (
        status_enums.get("requirement_statuses", DEFAULT_REQUIREMENT_STATUSES)
        if status_enums
        else DEFAULT_REQUIREMENT_STATUSES
    )
    if not isinstance(configured_statuses, list):
        errors.append("bad_status_enum:requirement_statuses")
        configured_statuses = DEFAULT_REQUIREMENT_STATUSES
    allowed_statuses = set(configured_statuses)
    for record in readiness:
        if not isinstance(record, dict):
            errors.append("bad_readiness_record")
            continue
        statuses = record.get("requirement_statuses")
        if not isinstance(statuses, list):
            errors.append(f"bad_readiness_requirement_statuses:{record.get('template_name')}")
            continue
        if not statuses:
            errors.append("readiness_without_requirement_statuses")
        for status in statuses:
            if not isinstance(status, dict):
                errors.append(f"bad_readiness_status_record:{record.get('template_name')}")
                continue
            if status.get("status") not in allowed_statuses:
                errors.append(f"bad_readiness_status:{status.get('status')}")
    return errors


def _normalized_status_enums(requirements: dict, errors: list[str]) -> dict | None:
    status_enums = requirements.get("status_enums")
    if status_enums is None:
        return None
    if not isinstance(status_enums, dict):
        errors.append("bad_status_enums")
        return None
    normalized = {}
    for key, value in status_enums.items():
        if not isinstance(value, list):
            errors.append(f"bad_status_enum:{key}")
            continue
        normalized[key] = value
    return normalized


def _validate_chunks(manifest: dict, chunks: list[dict]) -> list[str]:
    if not chunks:
        return ["chunk_ledger_empty"]
    errors: list[str] = []
    valid_chunks = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            errors.append("bad_chunk_record")
            continue
        source_range = _valid_source_range(chunk.get("source_range"))
        if source_range is None:
            errors.append(f"bad_chunk_source_range:{chunk.get('chunk_id')}")
            continue
        valid_chunks.append((chunk, source_range))
    if not valid_chunks:
        return errors
    ordered = sorted(valid_chunks, key=lambda item: item[1][0])
    expected_length = _expected_source_length(manifest, errors)
    first_range = ordered[0][1]
    last_range = ordered[-1][1]
    if first_range[0] != 0 or last_range[1] != expected_length:
        errors.append("chunk_ledger_does_not_cover_full_source")
    for previous, current in zip(ordered, ordered[1:]):
        previous_end = previous[1][1]
        current_start = current[1][0]
        if current_start > previous_end:
            errors.append("chunk_ledger_has_gap")
    for chunk, _ in ordered:
        if chunk.get("extraction_status") != "completed":
            errors.append(f"chunk_not_completed:{chunk.get('chunk_id')}:{chunk.get('extraction_status')}")
    return errors


def _validate_evidence_links(graph: dict, coverage_evidence: list[dict]) -> list[str]:
    errors: list[str] = []
    graph_evidence = graph.get("evidence_index", [])
    if not isinstance(graph_evidence, list):
        errors.append("bad_graph_collection:evidence_index")
        graph_evidence = []
    graph_evidence_ids = {
        item.get("evidence_id") for item in graph_evidence if isinstance(item, dict)
    }
    coverage_evidence_ids = {
        item.get("evidence_id") for item in coverage_evidence if isinstance(item, dict)
    }
    for evidence in graph_evidence:
        if not isinstance(evidence, dict):
            continue
        source_range = evidence.get("source_range")
        if source_range is not None and _valid_source_range(source_range) is None:
            errors.append(f"bad_evidence_source_range:{evidence.get('evidence_id')}")
    for evidence in coverage_evidence:
        if not isinstance(evidence, dict):
            continue
        source_range = evidence.get("source_range")
        if source_range is not None and _valid_source_range(source_range) is None:
            errors.append(f"bad_evidence_source_range:{evidence.get('evidence_id')}")
    if graph_evidence_ids != coverage_evidence_ids:
        errors.append("graph_coverage_evidence_mismatch")
    graph_items = []
    for key in ["nodes", "edges", "events", "hyperedges"]:
        values = graph.get(key, [])
        if not isinstance(values, list):
            errors.append(f"bad_graph_collection:{key}")
            continue
        graph_items.extend(values)
    for item in graph_items:
        if not isinstance(item, dict):
            continue
        refs = item.get("evidence_ids", [])
        if not isinstance(refs, list):
            errors.append(f"bad_graph_evidence_refs:{item.get('id')}")
            continue
        for evidence_id in refs:
            if evidence_id not in graph_evidence_ids:
                errors.append(f"unknown_evidence_reference:{item.get('id')}")
    return errors


def _validate_required_agent_roles(agent_ledger: list[dict]) -> list[str]:
    seen_roles = {
        record.get("agent_role") for record in agent_ledger if isinstance(record, dict)
    }
    return [
        f"missing_agent_role:{role}"
        for role in REQUIRED_STAGE1_AGENT_ROLES
        if role not in seen_roles
    ]


def _expected_source_length(manifest: dict, errors: list[str]) -> int:
    source_path = manifest.get("source_path")
    if source_path:
        try:
            return len(Path(source_path).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            pass
    source_size = manifest.get("source_size")
    if source_size is None:
        return 0
    if isinstance(source_size, bool):
        errors.append("bad_manifest_source_size")
        return 0
    try:
        return int(source_size)
    except (TypeError, ValueError):
        errors.append("bad_manifest_source_size")
        return 0


def _safe_statuses(value: object) -> list:
    return value if isinstance(value, list) else []


def _valid_source_range(value: object) -> list[int] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    if not all(isinstance(item, int) and not isinstance(item, bool) for item in value):
        return None
    start = value[0]
    end = value[1]
    if start < 0 or end < start:
        return None
    return [start, end]


def _read_json(graph_dir: Path, relative_path: str, default, errors: list[str]):
    path = graph_dir / Path(*relative_path.split("/"))
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        errors.append(f"bad_json:{relative_path}")
        return default


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
