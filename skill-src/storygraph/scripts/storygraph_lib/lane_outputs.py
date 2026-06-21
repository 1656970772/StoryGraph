from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


DEFAULT_ALLOWED_OUTPUT_STATUSES = ("pending", "completed", "blocked", "failed", "needs_repair")

REQUIRED_STRING_FIELDS = (
    "run_id",
    "task_packet_id",
    "chunk_id",
    "lane_id",
    "agent_role",
    "model_or_agent_identity",
    "output_status",
    "produced_at",
)

LANE_OUTPUT_LIST_FIELDS = (
    "extracted_nodes",
    "extracted_edges",
    "extracted_events",
    "extracted_evidence",
    "supports_templates",
    "uncertainties",
    "rejected_candidates",
    "structured_failures",
)

OBJECT_ITEM_LIST_FIELDS = frozenset(
    (
        "extracted_nodes",
        "extracted_edges",
        "extracted_events",
        "extracted_evidence",
    )
)

STRUCTURED_FAILURE_STATUS = "structured_failure"
LEGACY_SEMANTIC_PRODUCER_EXACT = frozenset({"python", "legacy", "python-template-aware"})
LEGACY_SEMANTIC_PRODUCER_TOKENS = frozenset({"python-template-aware"})
LEGACY_SEMANTIC_PRODUCER_TOKEN_PREFIXES = frozenset({"python", "legacy"})


@dataclass(frozen=True)
class LaneOutputValidation:
    ok: bool
    errors: list[str]


def validate_lane_output(
    output: Any,
    *,
    allowed_lane_ids: list[str] | set[str],
    allowed_statuses: list[str] | set[str] | None = None,
    chunk_source_range: Any = None,
) -> LaneOutputValidation:
    errors: list[str] = []
    allowed_lanes = _allowed_values(
        allowed_lane_ids,
        "allowed_lane_ids_not_list_or_set",
        "allowed_lane_ids_item_not_string",
        errors,
    )
    configured_statuses = (
        set(DEFAULT_ALLOWED_OUTPUT_STATUSES)
        if allowed_statuses is None
        else _allowed_values(
            allowed_statuses,
            "allowed_statuses_not_list_or_set",
            "allowed_statuses_item_not_string",
            errors,
        )
    )
    chunk_range = (
        _validated_source_range(chunk_source_range, "chunk_source_range", errors)
        if chunk_source_range is not None
        else None
    )

    if not isinstance(output, dict):
        errors.append("lane_output_not_object")
        return LaneOutputValidation(ok=False, errors=_dedupe(errors))

    for field in REQUIRED_STRING_FIELDS:
        _validate_required_string(output, field, errors)

    lane_id = output.get("lane_id")
    if isinstance(lane_id, str) and allowed_lanes is not None and lane_id not in allowed_lanes:
        errors.append(f"lane_not_configured:{lane_id}")

    output_status = output.get("output_status")
    if (
        isinstance(output_status, str)
        and configured_statuses is not None
        and output_status not in configured_statuses
    ):
        errors.append(f"output_status_not_allowed:{output_status}")

    _validate_agent_producer(output, errors)
    list_values = _validate_list_fields(output, errors)
    _validate_source_ranges(list_values, chunk_range, errors)
    _validate_structured_failures(list_values.get("structured_failures"), output_status, errors)

    return LaneOutputValidation(ok=not errors, errors=_dedupe(errors))


def _allowed_values(
    values: Any,
    shape_error: str,
    item_error: str,
    errors: list[str],
) -> set[str] | None:
    if not isinstance(values, (list, set)):
        errors.append(shape_error)
        return None

    allowed: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value:
            errors.append(item_error)
            continue
        allowed.add(value)
    return allowed


def _validate_required_string(output: dict, field: str, errors: list[str]) -> None:
    if field not in output:
        errors.append(f"missing:{field}")
        return
    value = output[field]
    if not isinstance(value, str):
        errors.append(f"field_not_string:{field}")
        return
    if not value:
        errors.append(f"field_empty:{field}")


def _validate_agent_producer(output: dict, errors: list[str]) -> None:
    agent_role = output.get("agent_role")
    identity = output.get("model_or_agent_identity")
    role_text = _normalized_semantic_text(agent_role)
    identity_text = _normalized_semantic_text(identity)
    if _is_legacy_semantic_producer(role_text) or _is_legacy_semantic_producer(identity_text):
        errors.append("semantic_output_not_agent_produced")


def _normalized_semantic_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower().replace("_", "-")


def _is_legacy_semantic_producer(value: str) -> bool:
    if value in LEGACY_SEMANTIC_PRODUCER_EXACT:
        return True
    phrase_tokens = set(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", value))
    if phrase_tokens & LEGACY_SEMANTIC_PRODUCER_TOKENS:
        return True
    separator_tokens = set(re.findall(r"[a-z0-9]+", value))
    return "producer" in separator_tokens and bool(
        separator_tokens & LEGACY_SEMANTIC_PRODUCER_TOKEN_PREFIXES
    )


def _validate_list_fields(output: dict, errors: list[str]) -> dict[str, list]:
    list_values: dict[str, list] = {}
    for field in LANE_OUTPUT_LIST_FIELDS:
        if field not in output:
            errors.append(f"missing:{field}")
            continue
        value = output[field]
        if not isinstance(value, list):
            errors.append(f"field_not_list:{field}")
            continue
        list_values[field] = value
    return list_values


def _validate_source_ranges(
    list_values: dict[str, list],
    chunk_range: tuple[int, int] | None,
    errors: list[str],
) -> None:
    for field, items in list_values.items():
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                if field in OBJECT_ITEM_LIST_FIELDS:
                    errors.append(f"field_item_not_object:{field}[{index}]")
                continue
            _validate_item_source_range(item, f"{field}[{index}]", chunk_range, errors)


def _validate_item_source_range(
    item: dict,
    label: str,
    chunk_range: tuple[int, int] | None,
    errors: list[str],
) -> None:
    if "source_range" not in item:
        return
    source_range = _validated_source_range(item.get("source_range"), label, errors)
    if source_range is None or chunk_range is None:
        return
    if source_range[0] < chunk_range[0] or source_range[1] > chunk_range[1]:
        errors.append(f"source_range_outside_chunk:{label}")


def _validated_source_range(
    value: Any,
    label: str,
    errors: list[str],
) -> tuple[int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        errors.append(f"source_range_invalid:{label}")
        return None
    start, end = value
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
    ):
        errors.append(f"source_range_invalid:{label}")
        return None
    if start < 0 or end < 0:
        errors.append(f"source_range_invalid:{label}")
        return None
    if start > end:
        errors.append(f"source_range_order_invalid:{label}")
        return None
    return start, end


def _validate_structured_failures(
    structured_failures: list | None,
    output_status: Any,
    errors: list[str],
) -> None:
    if structured_failures is None:
        return
    if output_status == STRUCTURED_FAILURE_STATUS and not structured_failures:
        errors.append("structured_failure_required")
    for index, failure in enumerate(structured_failures):
        if not isinstance(failure, dict):
            errors.append(f"structured_failure_not_object:{index}")
            continue
        _validate_structured_failure_field(failure, "code", index, errors, expected=str)
        _validate_structured_failure_field(failure, "message", index, errors, expected=str)
        _validate_structured_failure_field(failure, "attempt", index, errors, expected=int)


def _validate_structured_failure_field(
    failure: dict,
    field: str,
    index: int,
    errors: list[str],
    *,
    expected: type,
) -> None:
    if field not in failure:
        errors.append(f"structured_failure_missing:{field}:{index}")
        return
    value = failure[field]
    if expected is int:
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append(f"structured_failure_field_not_int:{field}:{index}")
        return
    if not isinstance(value, expected) or not value:
        errors.append(f"structured_failure_field_not_string:{field}:{index}")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
