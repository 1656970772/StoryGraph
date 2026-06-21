import pytest


def _agent_output(**overrides):
    output = {
        "run_id": "run-001",
        "task_packet_id": "stage1:chunk-0001:entities_resources",
        "chunk_id": "chunk-0001",
        "lane_id": "entities_resources",
        "agent_role": "实体道具资源抽取 agent",
        "model_or_agent_identity": "codex-subagent",
        "extracted_nodes": [],
        "extracted_edges": [],
        "extracted_events": [],
        "extracted_evidence": [],
        "supports_templates": [],
        "uncertainties": [],
        "rejected_candidates": [],
        "structured_failures": [],
        "output_status": "completed",
        "produced_at": "2026-06-20T00:00:00Z",
    }
    output.update(overrides)
    return output


def test_validate_lane_output_accepts_agent_produced_json():
    from storygraph_lib.lane_outputs import validate_lane_output

    result = validate_lane_output(
        _agent_output(),
        allowed_lane_ids=["entities_resources"],
    )

    assert result.ok is True
    assert result.errors == []


def test_validate_lane_output_allows_agent_role_that_mentions_template_aware():
    from storygraph_lib.lane_outputs import validate_lane_output

    result = validate_lane_output(
        _agent_output(agent_role="template-aware lane extraction agent"),
        allowed_lane_ids=["entities_resources"],
    )

    assert result.ok is True
    assert result.errors == []


@pytest.mark.parametrize(
    "producer",
    [
        "python-producer",
        "python_producer",
        "legacy-producer",
        "python-template-aware-producer",
    ],
)
def test_validate_lane_output_rejects_separator_variants_of_legacy_producers(producer):
    from storygraph_lib.lane_outputs import validate_lane_output

    result = validate_lane_output(
        _agent_output(agent_role=producer),
        allowed_lane_ids=["entities_resources"],
    )

    assert result.ok is False
    assert "semantic_output_not_agent_produced" in result.errors


def test_validate_lane_output_rejects_python_producer_and_bad_lane():
    from storygraph_lib.lane_outputs import validate_lane_output

    output = {
        "run_id": "run-001",
        "chunk_id": "chunk-0001",
        "lane_id": "python_template_aware",
        "agent_role": "python",
        "model_or_agent_identity": "python-template-aware",
        "output_status": "completed",
    }

    result = validate_lane_output(output, allowed_lane_ids=["entities_resources"])

    assert result.ok is False
    assert "lane_not_configured:python_template_aware" in result.errors
    assert "semantic_output_not_agent_produced" in result.errors


def test_validate_lane_output_checks_source_ranges_against_chunk_range():
    from storygraph_lib.lane_outputs import validate_lane_output

    valid = _agent_output(
        extracted_evidence=[
            {"evidence_id": "ev-1", "source_range": [12, 18]},
        ]
    )
    invalid = _agent_output(
        extracted_evidence=[
            {"evidence_id": "ev-2", "source_range": [9, 18]},
            {"evidence_id": "ev-3", "source_range": [18, 21]},
        ]
    )

    valid_result = validate_lane_output(
        valid,
        allowed_lane_ids=["entities_resources"],
        chunk_source_range=[10, 20],
    )
    invalid_result = validate_lane_output(
        invalid,
        allowed_lane_ids=["entities_resources"],
        chunk_source_range=[10, 20],
    )

    assert valid_result.ok is True
    assert valid_result.errors == []
    assert invalid_result.ok is False
    assert "source_range_outside_chunk:extracted_evidence[0]" in invalid_result.errors
    assert "source_range_outside_chunk:extracted_evidence[1]" in invalid_result.errors


@pytest.mark.parametrize(
    "source_range, expected_error",
    [
        ("1-2", "source_range_invalid:extracted_evidence[0]"),
        ([2], "source_range_invalid:extracted_evidence[0]"),
        ([5, 3], "source_range_order_invalid:extracted_evidence[0]"),
        ([False, 3], "source_range_invalid:extracted_evidence[0]"),
    ],
)
def test_validate_lane_output_fails_closed_for_bad_source_range(source_range, expected_error):
    from storygraph_lib.lane_outputs import validate_lane_output

    output = _agent_output(
        extracted_evidence=[
            {"evidence_id": "ev-bad", "source_range": source_range},
        ]
    )

    result = validate_lane_output(
        output,
        allowed_lane_ids=["entities_resources"],
        chunk_source_range=[1, 10],
    )

    assert result.ok is False
    assert expected_error in result.errors


def test_validate_lane_output_rejects_negative_source_ranges():
    from storygraph_lib.lane_outputs import validate_lane_output

    item_range = _agent_output(
        extracted_evidence=[
            {"evidence_id": "ev-neg", "source_range": [-1, 3]},
        ]
    )
    chunk_range = _agent_output()

    item_result = validate_lane_output(
        item_range,
        allowed_lane_ids=["entities_resources"],
        chunk_source_range=[-10, 10],
    )
    chunk_result = validate_lane_output(
        chunk_range,
        allowed_lane_ids=["entities_resources"],
        chunk_source_range=[-1, 10],
    )

    assert item_result.ok is False
    assert "source_range_invalid:extracted_evidence[0]" in item_result.errors
    assert chunk_result.ok is False
    assert "source_range_invalid:chunk_source_range" in chunk_result.errors


@pytest.mark.parametrize(
    "field",
    [
        "extracted_nodes",
        "extracted_edges",
        "extracted_events",
        "extracted_evidence",
    ],
)
def test_validate_lane_output_rejects_non_object_items_in_object_lists(field):
    from storygraph_lib.lane_outputs import validate_lane_output

    result = validate_lane_output(
        _agent_output(**{field: ["bad"]}),
        allowed_lane_ids=["entities_resources"],
    )

    assert result.ok is False
    assert f"field_item_not_object:{field}[0]" in result.errors


def test_validate_lane_output_default_statuses_match_configured_lane_statuses():
    from storygraph_lib.lane_outputs import validate_lane_output

    pending = validate_lane_output(
        _agent_output(output_status="pending"),
        allowed_lane_ids=["entities_resources"],
    )
    structured_failure = validate_lane_output(
        _agent_output(
            output_status="structured_failure",
            structured_failures=[
                {
                    "code": "source_unreadable",
                    "message": "chunk text could not be decoded",
                    "attempt": 1,
                }
            ],
        ),
        allowed_lane_ids=["entities_resources"],
    )

    assert pending.ok is True
    assert pending.errors == []
    assert structured_failure.ok is False
    assert "output_status_not_allowed:structured_failure" in structured_failure.errors


def test_validate_lane_output_allows_structured_failure_with_complete_failure_record():
    from storygraph_lib.lane_outputs import validate_lane_output

    output = _agent_output(
        extracted_nodes=[],
        extracted_edges=[],
        extracted_events=[],
        extracted_evidence=[],
        output_status="structured_failure",
        structured_failures=[
            {
                "code": "source_unreadable",
                "message": "chunk text could not be decoded",
                "attempt": 1,
            }
        ],
    )

    result = validate_lane_output(
        output,
        allowed_lane_ids={"entities_resources"},
        allowed_statuses=["structured_failure"],
    )

    assert result.ok is True
    assert result.errors == []


@pytest.mark.parametrize("missing_key", ["code", "message", "attempt"])
def test_validate_lane_output_requires_complete_structured_failure_records(missing_key):
    from storygraph_lib.lane_outputs import validate_lane_output

    failure = {
        "code": "source_unreadable",
        "message": "chunk text could not be decoded",
        "attempt": 1,
    }
    failure.pop(missing_key)
    output = _agent_output(
        output_status="structured_failure",
        structured_failures=[failure],
    )

    result = validate_lane_output(
        output,
        allowed_lane_ids=["entities_resources"],
        allowed_statuses=["structured_failure"],
    )

    assert result.ok is False
    assert f"structured_failure_missing:{missing_key}:0" in result.errors


def test_validate_lane_output_uses_explicit_allowed_statuses():
    from storygraph_lib.lane_outputs import validate_lane_output

    accepted = _agent_output(output_status="reviewed")
    rejected = _agent_output(output_status="reviewed")

    accepted_result = validate_lane_output(
        accepted,
        allowed_lane_ids=["entities_resources"],
        allowed_statuses=["reviewed"],
    )
    rejected_result = validate_lane_output(
        rejected,
        allowed_lane_ids=["entities_resources"],
        allowed_statuses=["completed"],
    )

    assert accepted_result.ok is True
    assert accepted_result.errors == []
    assert rejected_result.ok is False
    assert "output_status_not_allowed:reviewed" in rejected_result.errors


def test_validate_lane_output_fails_closed_for_bad_shapes_and_list_fields():
    from storygraph_lib.lane_outputs import validate_lane_output

    not_object = validate_lane_output([], allowed_lane_ids=["entities_resources"])
    bad_allowed_lanes = validate_lane_output(_agent_output(), allowed_lane_ids="entities_resources")
    bad_list_field = validate_lane_output(
        _agent_output(extracted_nodes={"bad": "shape"}),
        allowed_lane_ids=["entities_resources"],
    )
    bad_required_field = validate_lane_output(
        _agent_output(run_id={"bad": "shape"}),
        allowed_lane_ids=["entities_resources"],
    )

    assert not_object.ok is False
    assert "lane_output_not_object" in not_object.errors
    assert bad_allowed_lanes.ok is False
    assert "allowed_lane_ids_not_list_or_set" in bad_allowed_lanes.errors
    assert bad_list_field.ok is False
    assert "field_not_list:extracted_nodes" in bad_list_field.errors
    assert bad_required_field.ok is False
    assert "field_not_string:run_id" in bad_required_field.errors
