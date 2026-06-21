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
_SUMMARY_SCHEMA_VERSION = "storygraph.template-requirements-summary.v1"


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


def validate_template_requirements_summary_payload(
    payload: Any,
    expected_template_names: list[str] | tuple[str, ...] | None = None,
) -> TemplateRequirementsValidationResult:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return TemplateRequirementsValidationResult(
            ok=False, errors=["template_requirements_summary_payload_not_object"]
        )

    if payload.get("schema_version") != _SUMMARY_SCHEMA_VERSION:
        errors.append("template_requirements_summary_schema_version_invalid")
    if payload.get("summary_passes") != 3:
        errors.append("template_requirements_summary_passes_invalid")

    source_template_count = payload.get("source_template_count")
    if type(source_template_count) is not int or source_template_count < 0:
        errors.append("template_requirements_summary_source_template_count_invalid")

    categories = payload.get("categories")
    covered_names: list[str] = []
    if not isinstance(categories, list) or not categories:
        errors.append("template_requirements_summary_categories_invalid")
    else:
        seen_categories: set[str] = set()
        for index, category in enumerate(categories):
            if not isinstance(category, dict):
                errors.append(f"template_requirements_summary_category_not_object:{index}")
                continue
            category_id = category.get("category_id")
            name = category_id if isinstance(category_id, str) and category_id else f"index_{index}"
            if not isinstance(category_id, str) or not category_id:
                errors.append(f"template_requirements_summary_category_id_invalid:{index}")
            elif category_id in seen_categories:
                errors.append(f"template_requirements_summary_duplicate_category:{category_id}")
            else:
                seen_categories.add(category_id)
            for field in (
                "category_name",
                "purpose",
                "required_extraction_targets",
                "evidence_requirements",
                "graph_mapping_summary",
                "template_coverage",
            ):
                if field not in category:
                    errors.append(f"template_requirements_summary_missing_field:{name}:{field}")
            _extend_string_list_errors(
                category.get("required_extraction_targets"),
                f"template_requirements_summary_targets_invalid:{name}",
                errors,
            )
            _extend_string_list_errors(
                category.get("evidence_requirements"),
                f"template_requirements_summary_evidence_invalid:{name}",
                errors,
            )
            mapping = category.get("graph_mapping_summary")
            if not isinstance(mapping, dict):
                errors.append(f"template_requirements_summary_mapping_invalid:{name}")
            coverage = category.get("template_coverage")
            if not isinstance(coverage, list):
                errors.append(f"template_requirements_summary_template_coverage_invalid:{name}")
            else:
                for item in coverage:
                    if isinstance(item, str) and item:
                        covered_names.append(item)
                    else:
                        errors.append(
                            f"template_requirements_summary_template_coverage_item_invalid:{name}"
                        )

    global_rules = payload.get("global_rules")
    if not isinstance(global_rules, dict):
        errors.append("template_requirements_summary_global_rules_invalid")
    else:
        statuses = global_rules.get("requirement_statuses")
        _extend_string_list_errors(
            statuses,
            "template_requirements_summary_requirement_statuses_invalid",
            errors,
        )

    _extend_string_list_errors(
        payload.get("refinement_notes"),
        "template_requirements_summary_refinement_notes_invalid",
        errors,
    )

    source_coverage = payload.get("source_coverage")
    source_names: list[str] = []
    if not isinstance(source_coverage, dict):
        errors.append("template_requirements_summary_source_coverage_invalid")
    else:
        template_names = source_coverage.get("template_names")
        if not isinstance(template_names, list):
            errors.append("template_requirements_summary_source_template_names_invalid")
        else:
            for item in template_names:
                if isinstance(item, str) and item:
                    source_names.append(item)
                else:
                    errors.append(
                        "template_requirements_summary_source_template_name_invalid"
                    )
        covered_count = source_coverage.get("covered_template_count")
        if type(covered_count) is not int:
            errors.append("template_requirements_summary_covered_template_count_invalid")
        elif covered_count != len(set(source_names)):
            errors.append("template_requirements_summary_covered_template_count_mismatch")

    unique_covered = set(covered_names)
    unique_source = set(source_names)
    if unique_source and not unique_source.issubset(unique_covered):
        errors.append("template_requirements_summary_category_coverage_mismatch")
    if type(source_template_count) is int and source_template_count != len(unique_source):
        errors.append("template_requirements_summary_source_template_count_mismatch")

    if expected_template_names is not None:
        expected = list(expected_template_names)
        for expected_name in expected:
            if expected_name not in unique_source or expected_name not in unique_covered:
                errors.append(
                    f"template_requirements_summary_missing_expected_template:{expected_name}"
                )
        for actual_name in unique_source:
            if actual_name not in expected:
                errors.append(
                    f"template_requirements_summary_unexpected_template:{actual_name}"
                )
        if source_names != expected:
            errors.append("template_requirements_summary_template_names_mismatch")

    return TemplateRequirementsValidationResult(ok=not errors, errors=errors)


def _extend_string_list_errors(value: Any, code: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(code)
        return
    for item in value:
        if not isinstance(item, str):
            errors.append(code)
            return


def _is_legacy_producer(value: str) -> bool:
    normalized = value.strip().lower().replace("_", "-")
    return normalized in {"python", "legacy"} or normalized.startswith(
        ("python-", "legacy-")
    )
