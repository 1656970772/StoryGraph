def test_template_requirements_must_come_from_agent_payload():
    from storygraph_lib.template_requirements import validate_template_requirements_payload

    payload = {
        "producer": "template-requirements-analysis-agent",
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
        "producer": "template-requirements-analysis-agent",
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
