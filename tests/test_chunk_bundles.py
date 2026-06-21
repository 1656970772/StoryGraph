def _lane_output(**overrides):
    output = {
        "chunk_id": "chunk-0001",
        "lane_id": "entities_resources",
        "output_status": "completed",
        "structured_failures": [],
    }
    output.update(overrides)
    return output


def test_open_required_review_finding_blocks_chunk_bundle_merge():
    from storygraph_lib.chunk_bundles import make_chunk_bundle, validate_bundle_ready_for_merge

    bundle = make_chunk_bundle(
        chunk_id="chunk-0001",
        source_range=[0, 20],
        lane_outputs=[{"chunk_id": "chunk-0001", "lane_id": "entities_resources", "output_status": "completed"}],
        review_findings=[{"finding_id": "finding-001", "severity": "must_fix", "status": "open"}],
    )

    result = validate_bundle_ready_for_merge(bundle, require_review_before_merge=True)

    assert result.ok is False
    assert "open_must_fix_finding:finding-001" in result.errors


def test_closed_finding_with_fresh_repair_allows_bundle_merge():
    from storygraph_lib.chunk_bundles import make_chunk_bundle, validate_bundle_ready_for_merge

    bundle = make_chunk_bundle(
        chunk_id="chunk-0001",
        source_range=[0, 20],
        lane_outputs=[{"chunk_id": "chunk-0001", "lane_id": "entities_resources", "output_status": "completed"}],
        review_findings=[
            {
                "finding_id": "finding-001",
                "severity": "must_fix",
                "status": "closed",
                "repair_agent_run_id": "run-002",
                "repair_of": "run-001",
            }
        ],
    )

    result = validate_bundle_ready_for_merge(bundle, require_review_before_merge=True)

    assert result.ok is True
    assert result.errors == []


def test_make_chunk_bundle_fails_closed_for_cross_chunk_lane_output():
    from storygraph_lib.chunk_bundles import make_chunk_bundle, validate_bundle_ready_for_merge

    bundle = make_chunk_bundle(
        chunk_id="chunk-0001",
        source_range=[0, 20],
        lane_outputs=[
            _lane_output(chunk_id="chunk-0001", lane_id="entities_resources"),
            _lane_output(chunk_id="chunk-0002", lane_id="events"),
        ],
        review_findings=[],
    )

    result = validate_bundle_ready_for_merge(bundle, require_review_before_merge=False)

    assert bundle["lane_outputs"] == [_lane_output(chunk_id="chunk-0001", lane_id="entities_resources")]
    assert result.ok is False
    assert "lane_output_chunk_mismatch:1" in result.errors


def test_make_chunk_bundle_snapshots_mutable_inputs():
    from storygraph_lib.chunk_bundles import make_chunk_bundle

    source_range = [0, 20]
    lane_output = _lane_output()
    review_finding = {
        "finding_id": "finding-001",
        "severity": "note",
        "status": "closed",
    }

    bundle = make_chunk_bundle(
        chunk_id="chunk-0001",
        source_range=source_range,
        lane_outputs=[lane_output],
        review_findings=[review_finding],
    )
    source_range[0] = 99
    lane_output["lane_id"] = "events"
    lane_output["structured_failures"].append({"code": "late_mutation"})
    review_finding["status"] = "open"

    assert bundle["source_range"] == [0, 20]
    assert bundle["lane_outputs"] == [_lane_output()]
    assert bundle["review_findings"] == [
        {"finding_id": "finding-001", "severity": "note", "status": "closed"}
    ]


def test_missing_required_lane_blocks_merge_with_structured_error():
    from storygraph_lib.chunk_bundles import make_chunk_bundle, validate_bundle_ready_for_merge

    bundle = make_chunk_bundle(
        chunk_id="chunk-0001",
        source_range=[0, 20],
        lane_outputs=[_lane_output(lane_id="entities_resources")],
        review_findings=[],
    )

    result = validate_bundle_ready_for_merge(
        bundle,
        require_review_before_merge=True,
        required_lane_ids=["entities_resources", "events"],
    )

    assert result.ok is False
    assert "missing_required_lane:events" in result.errors


def test_missing_required_lane_can_be_explained_by_open_finding_but_still_blocks():
    from storygraph_lib.chunk_bundles import make_chunk_bundle, validate_bundle_ready_for_merge

    bundle = make_chunk_bundle(
        chunk_id="chunk-0001",
        source_range=[0, 20],
        lane_outputs=[_lane_output(lane_id="entities_resources")],
        review_findings=[
            {
                "finding_id": "finding-002",
                "chunk_id": "chunk-0001",
                "lane_id": "events",
                "severity": "must_fix",
                "status": "open",
            }
        ],
    )

    result = validate_bundle_ready_for_merge(
        bundle,
        require_review_before_merge=True,
        required_lane_ids=["entities_resources", "events"],
    )

    assert result.ok is False
    assert "open_must_fix_finding:finding-002" in result.errors
    assert "missing_required_lane:events" not in result.errors


def test_validate_bundle_ready_for_merge_fails_closed_for_bad_shapes_without_repr():
    from storygraph_lib.chunk_bundles import validate_bundle_ready_for_merge

    not_object = validate_bundle_ready_for_merge([], require_review_before_merge=True)
    bad_lane_outputs = validate_bundle_ready_for_merge(
        {
            "chunk_id": "chunk-0001",
            "source_range": [0, 20],
            "lane_outputs": {"bad": "shape"},
            "review_findings": [],
        },
        require_review_before_merge=True,
    )
    bad_review_findings = validate_bundle_ready_for_merge(
        {
            "chunk_id": "chunk-0001",
            "source_range": [0, 20],
            "lane_outputs": [],
            "review_findings": [object()],
        },
        require_review_before_merge=True,
    )
    bad_required_lanes = validate_bundle_ready_for_merge(
        {
            "chunk_id": "chunk-0001",
            "source_range": [0, 20],
            "lane_outputs": [],
            "review_findings": [],
        },
        require_review_before_merge=True,
        required_lane_ids="events",
    )

    assert not_object.ok is False
    assert "bundle_not_object" in not_object.errors
    assert bad_lane_outputs.ok is False
    assert "lane_outputs_not_list" in bad_lane_outputs.errors
    assert bad_review_findings.ok is False
    assert "review_finding_not_object:0" in bad_review_findings.errors
    assert bad_required_lanes.ok is False
    assert "required_lane_ids_not_list_or_set" in bad_required_lanes.errors
    assert all("object at" not in error for error in bad_review_findings.errors)
