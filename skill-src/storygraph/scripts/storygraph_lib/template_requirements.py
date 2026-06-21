from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_REQUIRED_LIST_FIELDS = (
    "required_fields",
    "required_tables",
    "required_cards",
    "required_case_patterns",
    "required_evidence_fields",
    "graph_node_mapping",
    "graph_event_mapping",
    "graph_relation_mapping",
)

_REQUIRED_TEMPLATE_FIELDS = ("template_name", "template_file", *_REQUIRED_LIST_FIELDS, "coverage_rules")


@dataclass(frozen=True)
class TemplateRequirementsValidationResult:
    ok: bool
    errors: list[str]


def validate_template_requirements_payload(
    payload: Any,
    expected_template_names: list[str] | tuple[str, ...] | None = None,
) -> TemplateRequirementsValidationResult:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return TemplateRequirementsValidationResult(
            ok=False, errors=["template_requirements_payload_not_object"]
        )

    producer = payload.get("producer")
    if producer is not None and (
        not isinstance(producer, str) or not producer or _is_legacy_producer(producer)
    ):
        errors.append("template_requirements_not_agent_produced")

    templates = payload.get("templates")
    if not isinstance(templates, list):
        errors.append("template_requirements_templates_not_list")
        return TemplateRequirementsValidationResult(ok=False, errors=errors)
    template_count = payload.get("template_count")
    if template_count is not None:
        if type(template_count) is not int:
            errors.append("template_requirements_template_count_not_int")
        elif template_count != len(templates):
            errors.append("template_requirements_template_count_mismatch")

    actual_names: list[str] = []
    seen_names: set[str] = set()
    for index, template in enumerate(templates):
        if not isinstance(template, dict):
            errors.append(f"template_requirements_template_not_object:{index}")
            continue
        template_name = template.get("template_name")
        name = template_name if isinstance(template_name, str) and template_name else f"index_{index}"
        if not isinstance(template_name, str) or not template_name:
            errors.append(f"template_requirements_missing_template_name:{index}")
        else:
            if template_name in seen_names:
                errors.append(f"template_requirements_duplicate_template_name:{template_name}")
            seen_names.add(template_name)
            actual_names.append(template_name)

        mapping_source = template.get("mapping_source")
        if mapping_source:
            errors.append(f"legacy_mapping_source:{name}:{mapping_source}")

        for field in _REQUIRED_TEMPLATE_FIELDS:
            if field not in template:
                errors.append(f"template_requirements_missing_field:{name}:{field}")
                continue
            value = template[field]
            if field == "template_file" and not isinstance(value, str):
                errors.append(f"template_requirements_field_not_string:{name}:{field}")
            if field in _REQUIRED_LIST_FIELDS:
                if not isinstance(value, list):
                    errors.append(f"template_requirements_field_not_list:{name}:{field}")
                    continue
                for item in value:
                    if not isinstance(item, str):
                        errors.append(f"template_requirements_item_not_string:{name}:{field}")

        coverage_rules = template.get("coverage_rules")
        if isinstance(coverage_rules, dict):
            statuses = coverage_rules.get("requirement_statuses")
            if not isinstance(statuses, list):
                errors.append(f"template_requirements_statuses_not_list:{name}")
            else:
                for status in statuses:
                    if not isinstance(status, str):
                        errors.append(f"template_requirements_status_not_string:{name}")
        elif "coverage_rules" in template:
            errors.append(f"template_requirements_coverage_rules_not_object:{name}")

    for expected_name in expected_template_names or []:
        if expected_name not in actual_names:
            errors.append(f"template_requirements_missing_expected_template:{expected_name}")
    for actual_name in actual_names:
        if expected_template_names is not None and actual_name not in expected_template_names:
            errors.append(f"template_requirements_unexpected_template:{actual_name}")
    if expected_template_names is not None and actual_names != list(expected_template_names):
        errors.append("template_requirements_template_names_mismatch")

    return TemplateRequirementsValidationResult(ok=not errors, errors=errors)


def _is_legacy_producer(value: str) -> bool:
    normalized = value.strip().lower().replace("_", "-")
    return normalized in {"python", "legacy"} or normalized.startswith(
        ("python-", "legacy-")
    )
