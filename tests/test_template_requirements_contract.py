import pytest


def test_template_requirements_must_come_from_agent_payload():
    from storygraph_lib.template_requirements import validate_template_requirements_payload

    payload = {
        "templates": [
            {
                "template_name": "法宝分析",
                "template_file": "法宝分析模板.md",
                "required_fields": ["法宝"],
                "required_tables": [],
                "required_cards": [],
                "required_case_patterns": [],
                "required_evidence_fields": ["原文位置"],
                "graph_node_mapping": ["artifact"],
                "graph_event_mapping": ["artifact_event"],
                "graph_relation_mapping": ["artifact_relation"],
                "coverage_rules": {
                    "requirement_statuses": ["covered", "needs_review", "not_found_in_source"]
                },
            }
        ],
    }

    result = validate_template_requirements_payload(payload, expected_template_names=["法宝分析"])

    assert result.ok is True
    assert result.errors == []


def test_template_requirements_accepts_arbitrary_non_legacy_agent_producer():
    from storygraph_lib.template_requirements import validate_template_requirements_payload

    payload = {
        "producer": "custom-template-agent",
        "templates": [
            {
                "template_name": "法宝分析",
                "template_file": "法宝分析模板.md",
                "required_fields": ["法宝"],
                "required_tables": [],
                "required_cards": [],
                "required_case_patterns": [],
                "required_evidence_fields": ["原文位置"],
                "graph_node_mapping": ["artifact"],
                "graph_event_mapping": ["artifact_event"],
                "graph_relation_mapping": ["artifact_relation"],
                "coverage_rules": {
                    "requirement_statuses": ["covered", "needs_review", "not_found_in_source"]
                },
            }
        ],
    }

    result = validate_template_requirements_payload(payload, expected_template_names=["法宝分析"])

    assert result.ok is True
    assert result.errors == []


@pytest.mark.parametrize(
    "producer",
    [
        "python-template-parser",
        "python_producer",
        "legacy-template-requirements-agent",
        "legacy",
    ],
)
def test_template_requirements_reject_legacy_producers(producer):
    from storygraph_lib.template_requirements import validate_template_requirements_payload

    payload = {"producer": producer, "templates": []}

    result = validate_template_requirements_payload(payload)

    assert result.ok is False
    assert "template_requirements_not_agent_produced" in result.errors


def test_template_requirements_reject_default_mapping_source():
    from storygraph_lib.template_requirements import validate_template_requirements_payload

    payload = {
        "producer": "python-template-parser",
        "templates": [{"template_name": "法宝分析", "mapping_source": "default_mapping"}],
    }

    result = validate_template_requirements_payload(payload, expected_template_names=["法宝分析"])

    assert result.ok is False
    assert "template_requirements_not_agent_produced" in result.errors
    assert "legacy_mapping_source:法宝分析:default_mapping" in result.errors


def test_template_requirements_reject_non_string_scalar_list_and_status_items():
    from storygraph_lib.template_requirements import validate_template_requirements_payload

    payload = {
        "producer": "custom-template-agent",
        "templates": [
            {
                "template_name": "法宝分析",
                "template_file": 123,
                "required_fields": ["法宝", {"bad": "item"}],
                "required_tables": [],
                "required_cards": [],
                "required_case_patterns": [],
                "required_evidence_fields": [7],
                "graph_node_mapping": [42],
                "graph_event_mapping": ["event"],
                "graph_relation_mapping": [None],
                "coverage_rules": {"requirement_statuses": ["covered", 1]},
            }
        ],
    }

    result = validate_template_requirements_payload(payload, expected_template_names=["法宝分析"])

    assert result.ok is False
    assert "template_requirements_field_not_string:法宝分析:template_file" in result.errors
    assert "template_requirements_item_not_string:法宝分析:required_fields" in result.errors
    assert "template_requirements_item_not_string:法宝分析:required_evidence_fields" in result.errors
    assert "template_requirements_item_not_string:法宝分析:graph_node_mapping" in result.errors
    assert "template_requirements_item_not_string:法宝分析:graph_relation_mapping" in result.errors
    assert "template_requirements_status_not_string:法宝分析" in result.errors


def test_template_requirements_reject_template_count_mismatch():
    from storygraph_lib.template_requirements import validate_template_requirements_payload

    payload = {
        "template_count": 2,
        "templates": [
            {
                "template_name": "法宝分析",
                "template_file": "法宝分析模板.md",
                "required_fields": ["法宝"],
                "required_tables": [],
                "required_cards": [],
                "required_case_patterns": [],
                "required_evidence_fields": ["原文位置"],
                "graph_node_mapping": ["artifact"],
                "graph_event_mapping": ["artifact_event"],
                "graph_relation_mapping": ["artifact_relation"],
                "coverage_rules": {
                    "requirement_statuses": ["covered", "needs_review", "not_found_in_source"]
                },
            }
        ],
    }

    result = validate_template_requirements_payload(
        payload, expected_template_names=["法宝分析"]
    )

    assert result.ok is False
    assert "template_requirements_template_count_mismatch" in result.errors


def test_template_requirements_reject_duplicate_template_names():
    from storygraph_lib.template_requirements import validate_template_requirements_payload

    template = {
        "template_name": "法宝分析",
        "template_file": "法宝分析模板.md",
        "required_fields": ["法宝"],
        "required_tables": [],
        "required_cards": [],
        "required_case_patterns": [],
        "required_evidence_fields": ["原文位置"],
        "graph_node_mapping": ["artifact"],
        "graph_event_mapping": ["artifact_event"],
        "graph_relation_mapping": ["artifact_relation"],
        "coverage_rules": {
            "requirement_statuses": ["covered", "needs_review", "not_found_in_source"]
        },
    }
    payload = {"template_count": 2, "templates": [template, dict(template)]}

    result = validate_template_requirements_payload(
        payload, expected_template_names=["法宝分析"]
    )

    assert result.ok is False
    assert "template_requirements_duplicate_template_name:法宝分析" in result.errors


def test_template_requirements_summary_accepts_three_pass_category_payload():
    from storygraph_lib.template_requirements import (
        validate_template_requirements_summary_payload,
    )

    payload = {
        "schema_version": "storygraph.template-requirements-summary.v1",
        "source_template_count": 2,
        "summary_passes": 3,
        "categories": [
            {
                "category_id": "characters_and_artifacts",
                "category_name": "人物与法宝",
                "purpose": "归纳人物、法宝和相关事件的抽取要求。",
                "required_extraction_targets": ["人物", "法宝", "获得事件"],
                "evidence_requirements": ["原文位置", "判断依据"],
                "graph_mapping_summary": {
                    "nodes": ["character", "artifact"],
                    "events": ["artifact_gain"],
                    "relations": ["character_owns_artifact"],
                },
                "template_coverage": ["人物关系", "法宝分析"],
            }
        ],
        "global_rules": {
            "requirement_statuses": ["covered", "needs_review", "not_found_in_source"]
        },
        "refinement_notes": ["三轮归纳后合并同类模板。"],
        "source_coverage": {
            "template_names": ["人物关系", "法宝分析"],
            "covered_template_count": 2,
        },
    }

    result = validate_template_requirements_summary_payload(
        payload, expected_template_names=["人物关系", "法宝分析"]
    )

    assert result.ok is True
    assert result.errors == []


def test_template_requirements_summary_rejects_missing_template_coverage():
    from storygraph_lib.template_requirements import (
        validate_template_requirements_summary_payload,
    )

    payload = {
        "schema_version": "storygraph.template-requirements-summary.v1",
        "source_template_count": 2,
        "summary_passes": 2,
        "categories": [
            {
                "category_id": "artifacts",
                "category_name": "法宝",
                "template_coverage": ["法宝分析"],
            }
        ],
        "global_rules": {
            "requirement_statuses": ["covered", "needs_review", "not_found_in_source"]
        },
        "refinement_notes": [],
        "source_coverage": {
            "template_names": ["法宝分析"],
            "covered_template_count": 1,
        },
    }

    result = validate_template_requirements_summary_payload(
        payload, expected_template_names=["人物关系", "法宝分析"]
    )

    assert result.ok is False
    assert "template_requirements_summary_passes_invalid" in result.errors
    assert "template_requirements_summary_missing_expected_template:人物关系" in result.errors
    assert "template_requirements_summary_source_template_count_mismatch" in result.errors
