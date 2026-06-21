from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


DEFAULT_ALLOWED_FINDING_STATUSES = ("open", "closed", "waived")
DEFAULT_ALLOWED_FINDING_SEVERITIES = ("must_fix", "should_fix", "note")

REQUIRED_SCHEMA_STRING_FIELDS = (
    "finding_id",
    "reviewer_role",
    "stage",
    "chunk_id",
    "lane_id",
    "severity",
    "status",
)
REQUIRED_SCHEMA_JSON_FIELDS = (
    "probe_or_sample",
    "actual_output",
    "expected_output",
)
MERGE_REQUIRED_STRING_FIELDS = ("finding_id", "severity", "status")
OPTIONAL_STRING_OR_NONE_FIELDS = ("repair_agent_run_id", "repair_of")


@dataclass(frozen=True)
class ReviewFindingValidation:
    ok: bool
    errors: list[str]


def make_review_finding(
    *,
    finding_id: str,
    reviewer_role: str,
    stage: str,
    chunk_id: str,
    lane_id: str,
    probe_or_sample: Any,
    actual_output: Any,
    expected_output: Any,
    severity: str,
    status: str,
    repair_required: bool,
    repair_agent_run_id: str | None,
    repair_of: str | None = None,
) -> dict:
    return {
        "finding_id": finding_id,
        "reviewer_role": reviewer_role,
        "stage": stage,
        "chunk_id": chunk_id,
        "lane_id": lane_id,
        "probe_or_sample": probe_or_sample,
        "actual_output": actual_output,
        "expected_output": expected_output,
        "severity": severity,
        "status": status,
        "repair_required": repair_required,
        "repair_agent_run_id": repair_agent_run_id,
        "repair_of": repair_of,
    }


def validate_review_finding(
    finding: Any,
    *,
    allowed_severities: list[str] | set[str] | tuple[str, ...] | None = None,
    allowed_statuses: list[str] | set[str] | tuple[str, ...] | None = None,
    require_full_schema: bool = True,
) -> ReviewFindingValidation:
    errors: list[str] = []
    severities = _allowed_values(
        DEFAULT_ALLOWED_FINDING_SEVERITIES
        if allowed_severities is None
        else allowed_severities,
        "allowed_finding_severities_not_list_or_set",
        "allowed_finding_severities_item_not_string",
        errors,
    )
    statuses = _allowed_values(
        DEFAULT_ALLOWED_FINDING_STATUSES if allowed_statuses is None else allowed_statuses,
        "allowed_finding_statuses_not_list_or_set",
        "allowed_finding_statuses_item_not_string",
        errors,
    )

    if not isinstance(finding, dict):
        errors.append("review_finding_not_object")
        return ReviewFindingValidation(ok=False, errors=_dedupe(errors))

    string_fields = (
        REQUIRED_SCHEMA_STRING_FIELDS
        if require_full_schema
        else MERGE_REQUIRED_STRING_FIELDS
    )
    for field in string_fields:
        _validate_required_string(finding, field, errors)

    if not require_full_schema:
        for field in ("reviewer_role", "stage", "chunk_id", "lane_id"):
            if field in finding:
                _validate_optional_string(finding, field, errors)

    if require_full_schema:
        for field in REQUIRED_SCHEMA_JSON_FIELDS:
            _validate_required_json_like(finding, field, errors)
        _validate_required_bool(finding, "repair_required", errors)
        if "repair_agent_run_id" not in finding:
            errors.append("missing:repair_agent_run_id")

    if "repair_required" in finding:
        _validate_optional_bool(finding, "repair_required", errors)
    for field in OPTIONAL_STRING_OR_NONE_FIELDS:
        if field in finding:
            _validate_optional_string_or_none(finding, field, errors)

    severity = finding.get("severity")
    if isinstance(severity, str) and severities is not None and severity not in severities:
        errors.append(f"finding_severity_not_allowed:{severity}")

    status = finding.get("status")
    if isinstance(status, str) and statuses is not None and status not in statuses:
        errors.append(f"finding_status_not_allowed:{status}")

    return ReviewFindingValidation(ok=not errors, errors=_dedupe(errors))


def _allowed_values(
    values: Any,
    shape_error: str,
    item_error: str,
    errors: list[str],
) -> set[str] | None:
    if not isinstance(values, (list, set, tuple)):
        errors.append(shape_error)
        return None
    allowed: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value:
            errors.append(item_error)
            continue
        allowed.add(value)
    return allowed


def _validate_required_string(record: dict, field: str, errors: list[str]) -> None:
    if field not in record:
        errors.append(f"missing:{field}")
        return
    _validate_optional_string(record, field, errors)


def _validate_optional_string(record: dict, field: str, errors: list[str]) -> None:
    value = record.get(field)
    if not isinstance(value, str):
        errors.append(f"field_not_string:{field}")
        return
    if not value:
        errors.append(f"field_empty:{field}")


def _validate_required_json_like(record: dict, field: str, errors: list[str]) -> None:
    if field not in record:
        errors.append(f"missing:{field}")
        return
    if not _is_json_like(record.get(field)):
        errors.append(f"field_not_json_like:{field}")


def _validate_required_bool(record: dict, field: str, errors: list[str]) -> None:
    if field not in record:
        errors.append(f"missing:{field}")
        return
    _validate_optional_bool(record, field, errors)


def _validate_optional_bool(record: dict, field: str, errors: list[str]) -> None:
    if not isinstance(record.get(field), bool):
        errors.append(f"field_not_bool:{field}")


def _validate_optional_string_or_none(
    record: dict, field: str, errors: list[str]
) -> None:
    value = record.get(field)
    if value is not None and not isinstance(value, str):
        errors.append(f"field_not_string_or_none:{field}")
    elif isinstance(value, str) and not value:
        errors.append(f"field_empty:{field}")


def _is_json_like(value: Any, depth: int = 0) -> bool:
    if depth > 20:
        return False
    if value is None or isinstance(value, (str, int, bool)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_json_like(item, depth + 1) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_json_like(item, depth + 1)
            for key, item in value.items()
        )
    return False


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
