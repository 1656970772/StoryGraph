def _review_finding(**overrides):
    finding = {
        "finding_id": "finding-001",
        "reviewer_role": "chunk-lane-reviewer",
        "stage": "stage1",
        "chunk_id": "chunk-0001",
        "lane_id": "entities_resources",
        "probe_or_sample": "pytest tests/test_stage1.py::test_probe -v",
        "actual_output": "failed",
        "expected_output": "passed",
        "severity": "must_fix",
        "status": "open",
        "repair_required": True,
        "repair_agent_run_id": None,
    }
    finding.update(overrides)
    return finding


def test_make_review_finding_includes_task7_schema_fields():
    from storygraph_lib.review_findings import make_review_finding, validate_review_finding

    finding = make_review_finding(
        finding_id="finding-001",
        reviewer_role="chunk-lane-reviewer",
        stage="stage1",
        chunk_id="chunk-0001",
        lane_id="entities_resources",
        probe_or_sample="pytest tests/test_stage1.py::test_probe -v",
        actual_output="failed",
        expected_output="passed",
        severity="must_fix",
        status="open",
        repair_required=True,
        repair_agent_run_id=None,
    )

    assert {
        "reviewer_role",
        "stage",
        "chunk_id",
        "lane_id",
        "probe_or_sample",
        "actual_output",
        "expected_output",
        "severity",
        "status",
        "repair_required",
        "repair_agent_run_id",
    } <= finding.keys()
    assert validate_review_finding(finding).ok is True


def test_validate_review_finding_uses_explicit_allowed_enums():
    from storygraph_lib.review_findings import validate_review_finding

    accepted = validate_review_finding(
        _review_finding(severity="critical", status="triaged"),
        allowed_severities=["critical"],
        allowed_statuses=["triaged"],
    )
    rejected = validate_review_finding(
        _review_finding(severity="critical", status="triaged"),
        allowed_severities=["must_fix"],
        allowed_statuses=["open"],
    )

    assert accepted.ok is True
    assert accepted.errors == []
    assert rejected.ok is False
    assert "finding_severity_not_allowed:critical" in rejected.errors
    assert "finding_status_not_allowed:triaged" in rejected.errors


def test_validate_review_finding_fails_closed_for_missing_and_bad_fields():
    from storygraph_lib.review_findings import validate_review_finding

    finding = _review_finding(
        reviewer_role="",
        actual_output=object(),
        repair_required="yes",
        repair_agent_run_id=object(),
    )
    finding.pop("expected_output")

    result = validate_review_finding(finding)

    assert result.ok is False
    assert "field_empty:reviewer_role" in result.errors
    assert "missing:expected_output" in result.errors
    assert "field_not_json_like:actual_output" in result.errors
    assert "field_not_bool:repair_required" in result.errors
    assert "field_not_string_or_none:repair_agent_run_id" in result.errors
    assert all("object at" not in error for error in result.errors)


def test_validate_review_finding_rejects_non_finite_json_numbers():
    import math

    from storygraph_lib.review_findings import validate_review_finding

    result = validate_review_finding(
        _review_finding(
            probe_or_sample={"value": math.nan},
            actual_output={"value": math.inf},
            expected_output={"value": -math.inf},
        )
    )

    assert result.ok is False
    assert "field_not_json_like:probe_or_sample" in result.errors
    assert "field_not_json_like:actual_output" in result.errors
    assert "field_not_json_like:expected_output" in result.errors
    assert all("nan" not in error.lower() for error in result.errors)
    assert all("inf" not in error.lower() for error in result.errors)


def test_validate_review_finding_rejects_bad_shape_status_and_severity():
    from storygraph_lib.review_findings import validate_review_finding

    not_object = validate_review_finding([])
    bad_enums = validate_review_finding(
        _review_finding(severity="critical", status="blocked")
    )

    assert not_object.ok is False
    assert "review_finding_not_object" in not_object.errors
    assert bad_enums.ok is False
    assert "finding_severity_not_allowed:critical" in bad_enums.errors
    assert "finding_status_not_allowed:blocked" in bad_enums.errors
