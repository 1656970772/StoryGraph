from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from .review_findings import (
    DEFAULT_ALLOWED_FINDING_SEVERITIES,
    DEFAULT_ALLOWED_FINDING_STATUSES,
    validate_review_finding,
)


OPEN_STATUS = "open"
CLOSED_STATUS = "closed"
MUST_FIX_SEVERITY = "must_fix"
COMPLETED_OUTPUT_STATUS = "completed"
STRUCTURED_FAILURE_STATUSES = frozenset(("blocked", "failed", "needs_repair", "structured_failure"))


@dataclass(frozen=True)
class BundleMergeValidation:
    ok: bool
    errors: list[str]


def make_chunk_bundle(
    *,
    chunk_id: str,
    source_range: Any,
    lane_outputs: Any,
    review_findings: Any | None = None,
) -> dict:
    errors: list[str] = []
    normalized_lane_outputs: list[dict] = []

    if not isinstance(lane_outputs, list):
        errors.append("lane_outputs_not_list")
    else:
        for index, lane_output in enumerate(lane_outputs):
            if not isinstance(lane_output, dict):
                errors.append(f"lane_output_not_object:{index}")
                continue
            output_chunk_id = lane_output.get("chunk_id")
            if not isinstance(output_chunk_id, str) or not output_chunk_id:
                errors.append(f"lane_output_bad_chunk_id:{index}")
                continue
            if output_chunk_id != chunk_id:
                errors.append(f"lane_output_chunk_mismatch:{index}")
                continue
            normalized_lane_outputs.append(copy.deepcopy(lane_output))

    normalized_findings: list[Any] = []
    if review_findings is None:
        normalized_findings = []
    elif not isinstance(review_findings, list):
        errors.append("review_findings_not_list")
    else:
        normalized_findings = copy.deepcopy(review_findings)

    return {
        "chunk_id": chunk_id,
        "source_range": copy.deepcopy(source_range),
        "lane_outputs": normalized_lane_outputs,
        "review_findings": normalized_findings,
        "errors": _dedupe(errors),
    }


def validate_bundle_ready_for_merge(
    bundle: Any,
    require_review_before_merge: bool = True,
    required_lane_ids: list[str] | set[str] | tuple[str, ...] | None = None,
    *,
    allowed_finding_severities: list[str] | set[str] | tuple[str, ...] | None = None,
    allowed_finding_statuses: list[str] | set[str] | tuple[str, ...] | None = None,
) -> BundleMergeValidation:
    errors: list[str] = []
    required_lanes = _required_lane_ids(required_lane_ids, errors)

    if not isinstance(require_review_before_merge, bool):
        errors.append("require_review_before_merge_not_bool")

    if not isinstance(bundle, dict):
        errors.append("bundle_not_object")
        return BundleMergeValidation(ok=False, errors=_dedupe(errors))

    _extend_bundle_errors(bundle.get("errors", []), errors)
    chunk_id = _validate_bundle_string(bundle, "chunk_id", errors)
    _validate_source_range(bundle.get("source_range"), "source_range", errors)

    lane_outputs = _validate_lane_outputs(bundle, chunk_id, errors)
    review_findings = _validate_review_findings(
        bundle,
        chunk_id,
        require_review_before_merge=require_review_before_merge,
        allowed_finding_severities=(
            DEFAULT_ALLOWED_FINDING_SEVERITIES
            if allowed_finding_severities is None
            else allowed_finding_severities
        ),
        allowed_finding_statuses=(
            DEFAULT_ALLOWED_FINDING_STATUSES
            if allowed_finding_statuses is None
            else allowed_finding_statuses
        ),
        errors=errors,
    )
    _validate_required_lanes(required_lanes, lane_outputs, review_findings, errors)

    return BundleMergeValidation(ok=not errors, errors=_dedupe(errors))


def _extend_bundle_errors(values: Any, errors: list[str]) -> None:
    if values is None:
        return
    if not isinstance(values, list):
        errors.append("bundle_errors_not_list")
        return
    for value in values:
        if isinstance(value, str) and value:
            errors.append(value)
        else:
            errors.append("bundle_error_not_string")


def _validate_bundle_string(bundle: dict, field: str, errors: list[str]) -> str | None:
    if field not in bundle:
        errors.append(f"missing:{field}")
        return None
    value = bundle.get(field)
    if not isinstance(value, str):
        errors.append(f"field_not_string:{field}")
        return None
    if not value:
        errors.append(f"field_empty:{field}")
        return None
    return value


def _validate_source_range(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        errors.append(f"source_range_invalid:{label}")
        return
    start, end = value
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
        or start < 0
        or end < 0
    ):
        errors.append(f"source_range_invalid:{label}")
        return
    if start > end:
        errors.append(f"source_range_order_invalid:{label}")


def _validate_lane_outputs(
    bundle: dict, bundle_chunk_id: str | None, errors: list[str]
) -> list[dict]:
    if "lane_outputs" not in bundle:
        errors.append("missing:lane_outputs")
        return []
    lane_outputs = bundle.get("lane_outputs")
    if not isinstance(lane_outputs, list):
        errors.append("lane_outputs_not_list")
        return []

    valid_outputs: list[dict] = []
    for index, lane_output in enumerate(lane_outputs):
        if not isinstance(lane_output, dict):
            errors.append(f"lane_output_not_object:{index}")
            continue
        output_chunk_id = lane_output.get("chunk_id")
        if not isinstance(output_chunk_id, str) or not output_chunk_id:
            errors.append(f"lane_output_bad_chunk_id:{index}")
        elif bundle_chunk_id is not None and output_chunk_id != bundle_chunk_id:
            errors.append(f"lane_output_chunk_mismatch:{index}")
        lane_id = lane_output.get("lane_id")
        if not isinstance(lane_id, str) or not lane_id:
            errors.append(f"lane_output_bad_lane_id:{index}")
        output_status = lane_output.get("output_status")
        if output_status is not None and not isinstance(output_status, str):
            errors.append(f"lane_output_bad_status:{index}")
        structured_failures = lane_output.get("structured_failures", [])
        if not isinstance(structured_failures, list):
            errors.append(f"structured_failures_not_list:{index}")
        else:
            for failure_index, failure in enumerate(structured_failures):
                if not isinstance(failure, dict):
                    errors.append(
                        f"structured_failure_not_object:{index}:{failure_index}"
                    )
        valid_outputs.append(lane_output)
    return valid_outputs


def _validate_review_findings(
    bundle: dict,
    bundle_chunk_id: str | None,
    *,
    require_review_before_merge: bool,
    allowed_finding_severities: Any,
    allowed_finding_statuses: Any,
    errors: list[str],
) -> list[dict]:
    if "review_findings" not in bundle:
        errors.append("missing:review_findings")
        return []
    review_findings = bundle.get("review_findings")
    if not isinstance(review_findings, list):
        errors.append("review_findings_not_list")
        return []

    valid_findings: list[dict] = []
    for index, finding in enumerate(review_findings):
        if not isinstance(finding, dict):
            errors.append(f"review_finding_not_object:{index}")
            continue
        finding_validation = validate_review_finding(
            finding,
            allowed_severities=allowed_finding_severities,
            allowed_statuses=allowed_finding_statuses,
            require_full_schema=False,
        )
        errors.extend(finding_validation.errors)
        _validate_finding_chunk(finding, bundle_chunk_id, errors)
        valid_findings.append(finding)
        if require_review_before_merge:
            _validate_finding_gate(finding, errors)
    return valid_findings


def _validate_finding_chunk(
    finding: dict, bundle_chunk_id: str | None, errors: list[str]
) -> None:
    if bundle_chunk_id is None or "chunk_id" not in finding:
        return
    finding_chunk_id = finding.get("chunk_id")
    finding_id = _finding_id(finding)
    if isinstance(finding_chunk_id, str) and finding_chunk_id != bundle_chunk_id:
        errors.append(f"review_finding_chunk_mismatch:{finding_id}")


def _validate_finding_gate(finding: dict, errors: list[str]) -> None:
    finding_id = _finding_id(finding)
    severity = finding.get("severity")
    status = finding.get("status")
    if severity == MUST_FIX_SEVERITY and status == OPEN_STATUS:
        errors.append(f"open_must_fix_finding:{finding_id}")
        return
    if severity == MUST_FIX_SEVERITY and status == CLOSED_STATUS:
        repair_agent_run_id = finding.get("repair_agent_run_id")
        repair_of = finding.get("repair_of")
        if (
            not isinstance(repair_agent_run_id, str)
            or not repair_agent_run_id
            or not isinstance(repair_of, str)
            or not repair_of
            or repair_agent_run_id == repair_of
        ):
            errors.append(f"closed_must_fix_finding_without_fresh_repair:{finding_id}")


def _validate_required_lanes(
    required_lanes: list[str] | None,
    lane_outputs: list[dict],
    review_findings: list[dict],
    errors: list[str],
) -> None:
    if required_lanes is None:
        return
    completed_lane_ids = {
        lane_output.get("lane_id")
        for lane_output in lane_outputs
        if lane_output.get("output_status") == COMPLETED_OUTPUT_STATUS
        and isinstance(lane_output.get("lane_id"), str)
    }
    known_lane_ids = {
        lane_output.get("lane_id")
        for lane_output in lane_outputs
        if isinstance(lane_output.get("lane_id"), str)
    }

    for lane_id in required_lanes:
        if lane_id in completed_lane_ids:
            continue
        if _has_open_finding_for_lane(review_findings, lane_id):
            errors.append(f"required_lane_blocked_by_open_finding:{lane_id}")
        elif _has_structured_failure_for_lane(lane_outputs, lane_id):
            errors.append(f"required_lane_structured_failure:{lane_id}")
        elif lane_id in known_lane_ids:
            errors.append(f"required_lane_not_completed:{lane_id}")
        else:
            errors.append(f"missing_required_lane:{lane_id}")


def _required_lane_ids(values: Any, errors: list[str]) -> list[str] | None:
    if values is None:
        return None
    if not isinstance(values, (list, set, tuple)):
        errors.append("required_lane_ids_not_list_or_set")
        return None
    lane_ids: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            errors.append("required_lane_ids_item_not_string")
            continue
        if value not in lane_ids:
            lane_ids.append(value)
    return lane_ids


def _has_open_finding_for_lane(findings: list[dict], lane_id: str) -> bool:
    for finding in findings:
        if finding.get("status") != OPEN_STATUS:
            continue
        finding_lane_id = finding.get("lane_id")
        if finding_lane_id == lane_id:
            return True
    return False


def _has_structured_failure_for_lane(lane_outputs: list[dict], lane_id: str) -> bool:
    for lane_output in lane_outputs:
        if lane_output.get("lane_id") != lane_id:
            continue
        structured_failures = lane_output.get("structured_failures", [])
        if isinstance(structured_failures, list) and structured_failures:
            return True
        if lane_output.get("output_status") in STRUCTURED_FAILURE_STATUSES:
            return True
    return False


def _finding_id(finding: dict) -> str:
    finding_id = finding.get("finding_id")
    if isinstance(finding_id, str) and finding_id:
        return finding_id
    return "unknown"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
