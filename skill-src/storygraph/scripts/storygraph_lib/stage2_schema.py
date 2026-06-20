from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath


STAGE1_CHUNK_LEDGER = "coverage/chunk-ledger.json"
TEMPLATE_RUN_LEDGER = "coverage/template-run-ledger.json"
TEMPLATE_EVIDENCE_USAGE = "coverage/template-evidence-usage.json"
TEMPLATE_GAP_REPORT = "coverage/template-gap-report.md"

STAGE2_CATEGORY_KEYS = (
    "facts",
    "judgments",
    "pending_verifications",
    "not_found_items",
)


@dataclass(frozen=True)
class ExtractionValidation:
    ok: bool
    errors: list[str]


def make_extraction_record(
    template_name,
    template_file,
    source_graph,
    source_novel,
    requirement_id,
    evidence_id,
    policy,
):
    categories = _required_policy_dict(policy, "stage2_categories")
    output_policy = _required_policy_dict(policy, "stage2_output_policy")
    _require_category_keys(categories)

    fulfilled = {
        "requirement_id": requirement_id,
        "requirement_kind": "field",
        "status": "covered",
        "linked_node_ids": [],
        "linked_edge_ids": [],
        "linked_event_ids": [],
        "evidence_ids": [evidence_id],
        "notes": [],
    }

    return {
        "schema": "stage2-extraction-record.v1",
        "template_name": template_name,
        "template_file": template_file,
        "source_graph": source_graph,
        "source_novel": source_novel,
        "output_language": policy.get("output_language"),
        "stage2_policy": {
            "stage2_categories": deepcopy(categories),
            "stage2_output_policy": deepcopy(output_policy),
        },
        "coverage_scope": _coverage_scope([]),
        "fulfilled_sections": [deepcopy(fulfilled)],
        "fulfilled_fields": [deepcopy(fulfilled)],
        "fulfilled_tables": [],
        "fulfilled_cards": [],
        "fulfilled_cases": [],
        "facts": [
            {
                "content": "source fact placeholder",
                "category": categories["facts"],
                "evidence_ids": [evidence_id],
                "source_locations": [],
                "confidence": "EXTRACTED",
            }
        ],
        "judgments": [
            {
                "content": "evidence-backed judgment placeholder",
                "category": categories["judgments"],
                "evidence_ids": [evidence_id],
                "source_locations": [],
                "confidence": "INFERRED",
            }
        ],
        "pending_verifications": [
            {
                "content": "pending verification placeholder",
                "category": categories["pending_verifications"],
                "evidence_ids": [],
                "source_locations": [],
                "confidence": "AMBIGUOUS",
            }
        ],
        "not_found_items": [
            {
                "content": "not found in reliable evidence placeholder",
                "category": categories["not_found_items"],
                "evidence_ids": [],
                "source_locations": [],
                "confidence": "AMBIGUOUS",
            }
        ],
        "evidence_citations": [evidence_id],
        "gap_items": [],
        "render_target": output_policy.get("default_dir"),
        "overwrite_policy": policy.get("overwrite_policy", "draft"),
    }


def make_template_run_ledger(template_names, chunk_ranges):
    chunk_ranges = list(chunk_ranges or [])
    return {
        "schema": "template-run-ledger.v1",
        "artifact_paths": _artifact_paths(),
        "coverage_scope": _coverage_scope(chunk_ranges),
        "template_tasks": [
            {
                "template_name": name,
                "status": "pending",
                "assigned_chunks": [
                    chunk["chunk_id"]
                    for chunk in chunk_ranges
                    if isinstance(chunk, dict) and "chunk_id" in chunk
                ],
                "output_record": None,
                "errors": [],
            }
            for name in template_names
        ],
    }


def make_template_evidence_usage(template_name, evidence_id, chunk_id, source_range):
    return {
        "schema": "template-evidence-usage.v1",
        "artifact_path": TEMPLATE_EVIDENCE_USAGE,
        "template_name": template_name,
        "evidence_id": evidence_id,
        "chunk_id": chunk_id,
        "source_range": source_range,
        "used_by_fields": [],
        "used_by_sections": [],
    }


def make_template_gap_report(template_name, requirement_id, status):
    return {
        "schema": "template-gap-report.v1",
        "artifact_path": TEMPLATE_GAP_REPORT,
        "gaps": [
            {
                "template_name": template_name,
                "requirement_id": requirement_id,
                "status": status,
                "evidence_ids": [],
                "notes": [],
            }
        ],
    }


def resolve_render_target(
    graph_dir: Path,
    novel_dir: Path,
    template_name: str,
    output_policy: dict,
    overwrite_policy: str = "draft",
) -> dict:
    allowed_policies = output_policy.get("allowed_policies", [])
    if overwrite_policy not in allowed_policies:
        raise ValueError(f"unsupported overwrite_policy: {overwrite_policy}")

    filename = f"{_safe_template_name(template_name)}.md"
    default_dir = _safe_relative_dir(output_policy["default_dir"])
    graph_root = Path(graph_dir).resolve()
    novel_root = Path(novel_dir).resolve()
    formal = (novel_root / filename).resolve()
    draft = (graph_root / default_dir / filename).resolve()
    _ensure_inside(draft, graph_root, "draft target")
    _ensure_inside(formal, novel_root, "formal target")

    if overwrite_policy == "draft":
        return {
            "target_path": str(draft),
            "formal_target_path": str(formal),
            "backup_path": None,
            "action": output_policy.get("draft_action", "write_draft"),
            "will_overwrite": False,
        }

    if overwrite_policy == "backup-and-overwrite":
        backup = formal.with_name(f"{formal.name}.bak")
        return {
            "target_path": str(formal),
            "formal_target_path": str(formal),
            "backup_path": str(backup),
            "action": "backup_and_overwrite" if formal.exists() else "write_new_formal",
            "will_overwrite": formal.exists(),
        }

    if overwrite_policy == "merge":
        return {
            "target_path": str(formal),
            "formal_target_path": str(formal),
            "backup_path": None,
            "action": "merge_existing" if formal.exists() else "write_new_formal",
            "will_overwrite": formal.exists(),
        }

    raise ValueError(f"unsupported overwrite_policy: {overwrite_policy}")


def validate_extraction_record(record):
    errors = []
    if not isinstance(record, dict):
        return ExtractionValidation(ok=False, errors=["record.must_be_object"])

    required = [
        "template_name",
        "template_file",
        "source_graph",
        "source_novel",
        "stage2_policy",
        "coverage_scope",
        "fulfilled_sections",
        "facts",
        "judgments",
        "pending_verifications",
        "not_found_items",
        "evidence_citations",
        "overwrite_policy",
    ]
    for key in required:
        if key not in record:
            errors.append(f"missing:{key}")

    _validate_coverage_scope(record.get("coverage_scope"), errors)
    categories = _validate_stage2_policy(record.get("stage2_policy"), record, errors)
    _validate_category_sections(record, categories, errors)
    _validate_facts(record.get("facts"), errors)

    return ExtractionValidation(ok=not errors, errors=errors)


def _coverage_scope(chunk_ranges):
    return {
        "scope": "whole_novel",
        "stage1_chunk_ledger": STAGE1_CHUNK_LEDGER,
        "chunk_ranges": chunk_ranges,
        "ledger_path": TEMPLATE_RUN_LEDGER,
    }


def _artifact_paths():
    return {
        "template_run_ledger": TEMPLATE_RUN_LEDGER,
        "template_evidence_usage": TEMPLATE_EVIDENCE_USAGE,
        "template_gap_report": TEMPLATE_GAP_REPORT,
    }


def _required_policy_dict(policy, key):
    value = policy.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"policy.{key}_required")
    return value


def _require_category_keys(categories):
    missing = [key for key in STAGE2_CATEGORY_KEYS if key not in categories]
    if missing:
        raise ValueError(f"policy.stage2_categories_missing:{','.join(missing)}")


def _validate_coverage_scope(scope, errors):
    if not isinstance(scope, dict):
        errors.append("coverage_scope.invalid")
        return
    if scope.get("stage1_chunk_ledger") != STAGE1_CHUNK_LEDGER:
        errors.append("coverage_scope.stage1_chunk_ledger_invalid")
    if not isinstance(scope.get("chunk_ranges"), list):
        errors.append("coverage_scope.chunk_ranges_must_be_list")


def _validate_stage2_policy(stage2_policy, record, errors):
    if not isinstance(stage2_policy, dict):
        return {}

    categories = stage2_policy.get("stage2_categories")
    if not isinstance(categories, dict):
        errors.append("stage2_policy.stage2_categories_required")
        categories = {}
    else:
        for key in STAGE2_CATEGORY_KEYS:
            if key not in categories:
                errors.append(f"stage2_policy.stage2_categories.missing:{key}")

    output_policy = stage2_policy.get("stage2_output_policy")
    if not isinstance(output_policy, dict):
        errors.append("stage2_policy.stage2_output_policy_required")
    else:
        allowed = output_policy.get("allowed_policies")
        if not isinstance(allowed, list):
            errors.append("stage2_policy.stage2_output_policy.allowed_policies_must_be_list")
            errors.append("overwrite_policy.unsupported")
        elif record.get("overwrite_policy") not in allowed:
            errors.append("overwrite_policy.unsupported")

    return categories


def _validate_category_sections(record, categories, errors):
    for section in STAGE2_CATEGORY_KEYS:
        items = record.get(section)
        if not isinstance(items, list):
            errors.append(f"{section}.must_be_list")
            continue
        expected_category = categories.get(section)
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"{section}[{index}].must_be_object")
                continue
            category = item.get("category")
            if not category:
                errors.append(f"{section}[{index}].category_required")
            elif expected_category and category != expected_category:
                errors.append(f"{section}[{index}].category_invalid")


def _validate_facts(facts, errors):
    if not isinstance(facts, list):
        return
    for index, fact in enumerate(facts):
        if isinstance(fact, dict) and not fact.get("evidence_ids"):
            errors.append(f"facts[{index}].evidence_ids_required")


def _safe_template_name(template_name):
    if not isinstance(template_name, str):
        raise ValueError("unsafe template_name: must be a string")
    if not template_name or not template_name.strip() or "\x00" in template_name:
        raise ValueError("unsafe template_name")
    path = Path(template_name)
    if path.is_absolute() or path.name != template_name or template_name in {".", ".."}:
        raise ValueError("unsafe template_name")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("unsafe template_name")
    if ":" in template_name:
        raise ValueError("unsafe template_name")
    return template_name


def _safe_relative_dir(path_value):
    if not isinstance(path_value, str) or not path_value or "\x00" in path_value:
        raise ValueError("unsafe output_policy.default_dir")
    path = Path(path_value)
    windows_path = PureWindowsPath(path_value)
    if (
        ":" in path_value
        or windows_path.drive
        or windows_path.is_absolute()
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("unsafe output_policy.default_dir")
    return path


def _ensure_inside(path, root, label):
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes configured root") from exc
