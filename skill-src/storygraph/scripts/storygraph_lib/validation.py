from dataclasses import dataclass
import json
from pathlib import Path

from .agent_ledger import validate_single_writer
from .graph_schema import DEFAULT_STATUS_ENUMS, validate_canonical_graph
from .state import REQUIRED_STAGE1_FILES


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    missing: list[str]


@dataclass(frozen=True)
class GraphDirValidation:
    ok: bool
    errors: list[str]


DEFAULT_REQUIREMENT_STATUSES = DEFAULT_STATUS_ENUMS["requirement_statuses"]
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
    errors.extend(_validate_evidence_links(graph, coverage_evidence, status_enums))
    errors.extend(_validate_readiness_references(graph, coverage_evidence, readiness))

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
    template_count = requirements.get("template_count")
    if not _is_non_negative_int(template_count):
        errors.append("bad_requirements_template_count")
    elif template_count != len(requirement_records):
        errors.append("requirements_template_count_mismatch")
    requirement_templates = _template_name_set(requirement_records, errors, "bad_requirement_template_name")
    readiness_templates = _template_name_set(readiness, errors, "bad_readiness_template_name")
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
                if not isinstance(item, str):
                    errors.append(f"bad_requirement_item:{template_name}:{key}")
                    continue
                marker = (kind, item)
                if marker in seen:
                    continue
                seen.add(marker)
                expected_ids.add(f"{template_name}.{key}.{item}")

    actual_ids = set()
    for record in readiness:
        if not isinstance(record, dict):
            continue
        for status in _safe_statuses(record.get("requirement_statuses")):
            if not isinstance(status, dict):
                continue
            requirement_id = status.get("requirement_id")
            if not isinstance(requirement_id, str):
                errors.append(f"bad_readiness_requirement_id:{record.get('template_name')}")
                continue
            actual_ids.add(requirement_id)
    if expected_ids != actual_ids:
        errors.append("requirements_readiness_id_mismatch")

    allowed_statuses = _allowed_status_values(status_enums, "requirement_statuses", errors)
    for record in readiness:
        if not isinstance(record, dict):
            errors.append("bad_readiness_record")
            continue
        _validate_readiness_summary_shape(record, errors)
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
            status_value = status.get("status")
            if not isinstance(status_value, str) or status_value not in allowed_statuses:
                errors.append(f"bad_readiness_status:{status_value}")
            _validate_readiness_status_shape(status, record.get("template_name"), errors)
    return errors


def _template_name_set(records: list, errors: list[str], error_code: str) -> set[str]:
    names = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        template_name = record.get("template_name")
        if not isinstance(template_name, str):
            errors.append(error_code)
            continue
        names.add(template_name)
    return names


def _safe_string_set(values: list, errors: list[str], error_code: str) -> set[str]:
    strings = set()
    for value in values:
        if not isinstance(value, str):
            errors.append(error_code)
            continue
        strings.add(value)
    return strings


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
        _validate_chunk_shape(chunk, errors)
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


def _validate_evidence_links(
    graph: dict, coverage_evidence: list[dict], status_enums: dict | None
) -> list[str]:
    errors: list[str] = []
    graph_evidence = graph.get("evidence_index", [])
    if not isinstance(graph_evidence, list):
        errors.append("bad_graph_collection:evidence_index")
        graph_evidence = []
    graph_evidence_ids = _evidence_id_set(graph_evidence)
    coverage_evidence_ids = _coverage_evidence_id_set(coverage_evidence, status_enums, errors)
    for evidence in graph_evidence:
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
            if not isinstance(evidence_id, str) or evidence_id not in graph_evidence_ids:
                errors.append(f"unknown_evidence_reference:{item.get('id')}")
    return errors


def _evidence_id_set(records: list) -> set[str]:
    ids = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        evidence_id = record.get("evidence_id")
        if isinstance(evidence_id, str):
            ids.add(evidence_id)
    return ids


def _coverage_evidence_id_set(
    records: list, status_enums: dict | None, errors: list[str]
) -> set[str]:
    ids = set()
    for record in records:
        if not isinstance(record, dict):
            errors.append("bad_coverage_evidence_record")
            continue
        evidence_id = record.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id:
            errors.append("bad_coverage_evidence_id")
            continue
        ids.add(evidence_id)
        _validate_coverage_evidence_shape(record, evidence_id, status_enums, errors)
    return ids


def _validate_coverage_evidence_shape(
    record: dict, evidence_id: str, status_enums: dict | None, errors: list[str]
) -> None:
    if "source_path" in record and not isinstance(record.get("source_path"), str):
        errors.append(f"bad_coverage_source_path:{evidence_id}")
    source_location = record.get("source_location")
    if "source_location" in record and not _valid_coverage_source_location(source_location):
        errors.append(f"bad_coverage_source_location:{evidence_id}")
    if "chunk_id" in record and not isinstance(record.get("chunk_id"), str):
        errors.append(f"bad_coverage_chunk_id:{evidence_id}")
    if "chapter_hint" in record and not _is_optional_str(record.get("chapter_hint")):
        errors.append(f"bad_coverage_chapter_hint:{evidence_id}")
    if "support" in record and not isinstance(record.get("support"), str):
        errors.append(f"bad_coverage_support:{evidence_id}")
    for key in ["linked_node_ids", "linked_edge_ids", "linked_event_ids"]:
        if key in record and not _is_string_list(record.get(key)):
            errors.append(f"bad_coverage_{key}:{evidence_id}")
    source_range = record.get("source_range")
    if source_range is not None and _valid_source_range(source_range) is None:
        errors.append(f"bad_evidence_source_range:{evidence_id}")
    if "fact_summary" in record and not isinstance(record.get("fact_summary"), str):
        errors.append("bad_coverage_evidence_record")
    confidence = record.get("confidence")
    if "confidence" in record and (
        not isinstance(confidence, str)
        or confidence not in _allowed_status_values(status_enums, "confidence_levels", errors)
    ):
        errors.append(f"bad_confidence:{confidence}")
    verification_status = record.get("verification_status")
    if "verification_status" in record and (
        not isinstance(verification_status, str)
        or verification_status
        not in _allowed_status_values(status_enums, "verification_statuses", errors)
    ):
        errors.append(f"bad_verification_status:{verification_status}")
    if "supports_templates" in record and not isinstance(record.get("supports_templates"), list):
        errors.append("bad_coverage_evidence_record")
    if isinstance(record.get("supports_templates"), list):
        _validate_supports_shape(
            "evidence",
            evidence_id,
            record.get("supports_templates"),
            _allowed_status_values(status_enums, "requirement_statuses", errors),
            errors,
        )


def _validate_supports_shape(
    owner: str,
    owner_id: object,
    supports: list,
    allowed_statuses: set[str],
    errors: list[str],
) -> None:
    if not supports:
        errors.append(f"{owner}_without_supports:{owner_id}")
        return
    for support in supports:
        if not isinstance(support, dict):
            errors.append(f"{owner}_bad_support:{owner_id}")
            continue
        for key in ["template_name", "requirement_id", "status"]:
            if key not in support:
                errors.append(f"{owner}_support_missing:{owner_id}:{key}")
        status = support.get("status")
        if not isinstance(status, str) or status not in allowed_statuses:
            errors.append(f"bad_requirement_status:{status}")


def _validate_readiness_status_shape(
    status: dict, template_name: object, errors: list[str]
) -> None:
    requirement_id = status.get("requirement_id")
    owner = requirement_id if isinstance(requirement_id, str) else template_name
    for key in ["linked_node_ids", "linked_edge_ids", "linked_event_ids", "evidence_ids"]:
        if key in status and not _is_string_list(status.get(key)):
            errors.append(f"bad_readiness_{key}:{owner}")
    if "notes" in status and not _is_string_list(status.get("notes")):
        errors.append(f"bad_readiness_notes:{owner}")


def _validate_readiness_summary_shape(record: dict, errors: list[str]) -> None:
    template_name = record.get("template_name")
    if "readiness_score" in record and not _is_non_negative_number(
        record.get("readiness_score")
    ):
        errors.append(f"bad_readiness_score:{template_name}")
    for key in [
        "supporting_node_count",
        "supporting_edge_count",
        "supporting_event_count",
        "evidence_count",
    ]:
        if key in record and not _is_non_negative_int(record.get(key)):
            errors.append(f"bad_readiness_{key}:{template_name}")
    if "missing_requirement_types" in record and not _is_string_list(
        record.get("missing_requirement_types")
    ):
        errors.append(f"bad_readiness_missing_requirement_types:{template_name}")
    if "notes" in record and not _is_string_list(record.get("notes")):
        errors.append(f"bad_readiness_notes:{template_name}")


def _validate_chunk_shape(chunk: dict, errors: list[str]) -> None:
    owner = _chunk_owner(chunk)
    if not isinstance(chunk.get("chunk_id"), str):
        errors.append("bad_chunk_id")
    if "source_path" in chunk and not isinstance(chunk.get("source_path"), str):
        errors.append(f"bad_chunk_source_path:{owner}")
    if "chapter_hint" in chunk and not _is_optional_str(chunk.get("chapter_hint")):
        errors.append(f"bad_chunk_chapter_hint:{owner}")
    if "hash" in chunk and not _is_optional_str(chunk.get("hash")):
        errors.append(f"bad_chunk_hash:{owner}")
    if "scanned_at" in chunk and not _is_optional_str(chunk.get("scanned_at")):
        errors.append(f"bad_chunk_scanned_at:{owner}")
    if "processor" in chunk and not isinstance(chunk.get("processor"), str):
        errors.append(f"bad_chunk_processor:{owner}")
    if "failure" in chunk and not (
        isinstance(chunk.get("failure"), dict) or chunk.get("failure") is None
    ):
        errors.append(f"bad_chunk_failure:{owner}")
    if "retry_count" in chunk and not _is_non_negative_int(chunk.get("retry_count")):
        errors.append(f"bad_chunk_retry_count:{owner}")
    if "text" in chunk and not isinstance(chunk.get("text"), str):
        errors.append(f"bad_chunk_text:{owner}")


def _chunk_owner(chunk: dict) -> str:
    chunk_id = chunk.get("chunk_id")
    return chunk_id if isinstance(chunk_id, str) else "unknown"


def _validate_readiness_references(
    graph: dict, coverage_evidence: list[dict], readiness: list[dict]
) -> list[str]:
    errors: list[str] = []
    node_ids = _graph_item_id_set(graph, "nodes")
    edge_ids = _graph_item_id_set(graph, "edges")
    event_ids = _graph_item_id_set(graph, "events")
    evidence_ids = _evidence_id_set(_safe_list(graph.get("evidence_index"))) | _raw_evidence_id_set(
        coverage_evidence
    )
    ref_fields = [
        ("linked_node_ids", node_ids, "unknown_readiness_node"),
        ("linked_edge_ids", edge_ids, "unknown_readiness_edge"),
        ("linked_event_ids", event_ids, "unknown_readiness_event"),
        ("evidence_ids", evidence_ids, "unknown_readiness_evidence"),
    ]
    for record in readiness:
        if not isinstance(record, dict):
            continue
        for status in _safe_statuses(record.get("requirement_statuses")):
            if not isinstance(status, dict):
                continue
            for key, known_ids, error_code in ref_fields:
                refs = status.get(key)
                if refs is None or not _is_string_list(refs):
                    continue
                for ref in refs:
                    if ref not in known_ids:
                        errors.append(f"{error_code}:{ref}")
    return errors


def _graph_item_id_set(graph: dict, key: str) -> set[str]:
    ids = set()
    for record in _safe_list(graph.get(key)):
        if not isinstance(record, dict):
            continue
        item_id = record.get("id")
        if isinstance(item_id, str):
            ids.add(item_id)
    return ids


def _raw_evidence_id_set(records: list) -> set[str]:
    ids = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        evidence_id = record.get("evidence_id")
        if isinstance(evidence_id, str):
            ids.add(evidence_id)
    return ids


def _safe_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _allowed_status_values(
    status_enums: dict | None, key: str, errors: list[str]
) -> set[str]:
    configured = (
        status_enums.get(key, DEFAULT_STATUS_ENUMS[key])
        if status_enums
        else DEFAULT_STATUS_ENUMS[key]
    )
    if not isinstance(configured, list):
        errors.append(f"bad_status_enum:{key}")
        configured = DEFAULT_STATUS_ENUMS[key]
    return _safe_string_set(configured, errors, f"bad_status_enum_item:{key}")


def _is_string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_non_negative_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value >= 0
    )


def _is_optional_str(value: object) -> bool:
    return value is None or isinstance(value, str)


def _valid_coverage_source_location(value: object) -> bool:
    if isinstance(value, str):
        return True
    if isinstance(value, dict):
        if "source_range" in value and _valid_source_range(value.get("source_range")) is None:
            return False
        return True
    return isinstance(value, list) and _valid_source_range(value) is not None


def _validate_required_agent_roles(agent_ledger: list[dict]) -> list[str]:
    seen_roles = {
        record.get("agent_role")
        for record in agent_ledger
        if isinstance(record, dict) and isinstance(record.get("agent_role"), str)
    }
    return [
        f"missing_agent_role:{role}"
        for role in REQUIRED_STAGE1_AGENT_ROLES
        if role not in seen_roles
    ]


def _expected_source_length(manifest: dict, errors: list[str]) -> int:
    source_path = manifest.get("source_path")
    if source_path not in (None, ""):
        try:
            path = Path(source_path)
        except TypeError:
            errors.append("bad_manifest_source_path")
        else:
            try:
                return len(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                pass
    source_size = manifest.get("source_size")
    if source_size is None:
        return 0
    if not _is_non_negative_int(source_size):
        errors.append("bad_manifest_source_size")
        return 0
    return source_size


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
