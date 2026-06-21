def _reviewed_bundle(**overrides):
    bundle = {
        "chunk_id": "chunk-0001",
        "ready_for_merge": True,
        "reviewer_status": "passed",
        "lane_output_paths": [
            "intermediate/lane-outputs/chunk-0001/entities_resources/run-001.json"
        ],
        "normalized_nodes": [],
        "normalized_edges": [],
        "normalized_events": [],
        "normalized_evidence": [],
    }
    bundle.update(overrides)
    return bundle


def test_canonical_writer_rejects_unreviewed_lane_outputs():
    from storygraph_lib.canonical_writer import build_canonical_graph_from_bundles

    bundle = {
        "chunk_id": "chunk-0001",
        "ready_for_merge": False,
        "reviewer_status": "pending",
        "normalized_nodes": [],
        "normalized_edges": [],
        "normalized_events": [],
        "normalized_evidence": [],
    }

    result = build_canonical_graph_from_bundles([bundle], novel_name="book", status_enums={})

    assert result.ok is False
    assert "bundle_not_reviewed:chunk-0001" in result.errors


def test_canonical_writer_defaults_to_passed_only_for_default_reviewer_status_enum():
    from storygraph_lib.canonical_writer import build_canonical_graph_from_bundles

    status_enums = {"reviewer_statuses": ["pending", "passed", "failed", "blocked"]}

    for status in ["pending", "failed", "blocked"]:
        result = build_canonical_graph_from_bundles(
            [_reviewed_bundle(reviewer_status=status)],
            novel_name="book",
            status_enums=status_enums,
        )

        assert result.ok is False
        assert result.errors == ["bundle_not_reviewed:chunk-0001"]

    result = build_canonical_graph_from_bundles(
        [_reviewed_bundle(reviewer_status="passed")],
        novel_name="book",
        status_enums=status_enums,
    )

    assert result.ok is True
    assert result.errors == []


def test_canonical_writer_accepts_configured_unreviewed_merge_gate_status():
    from storygraph_lib.canonical_writer import build_canonical_graph_from_bundles

    bundle = _reviewed_bundle(
        reviewer_status=None,
        merge_gate_status="unreviewed_usable",
        review_state="unreviewed_usable",
    )

    result = build_canonical_graph_from_bundles(
        [bundle],
        novel_name="book",
        status_enums={
            "bundle_review_statuses": [
                "reviewed_passed",
                "unreviewed_usable",
                "needs_incremental_review",
                "review_failed",
            ]
        },
    )

    assert result.ok is True
    assert result.errors == []
    assert result.graph["metadata"]["review_status"] == "unreviewed_usable"
    assert result.graph["metadata"]["unreviewed_bundle_count"] == 1


def test_canonical_writer_rejects_passed_reviewer_status_without_merge_gate():
    from storygraph_lib.canonical_writer import build_canonical_graph_from_bundles

    bundle = _reviewed_bundle()

    result = build_canonical_graph_from_bundles(
        [bundle],
        novel_name="book",
        status_enums={
            "bundle_review_statuses": [
                "reviewed_passed",
                "unreviewed_usable",
                "needs_incremental_review",
                "review_failed",
            ]
        },
    )

    assert result.ok is False
    assert result.errors == ["bundle_not_merge_gated:chunk-0001"]


def test_canonical_writer_preserves_agent_output_provenance():
    from storygraph_lib.canonical_writer import build_canonical_graph_from_bundles

    bundle = {
        "chunk_id": "chunk-0001",
        "ready_for_merge": True,
        "reviewer_status": "passed",
        "lane_output_paths": [
            "intermediate/lane-outputs/chunk-0001/entities_resources/run-001.json"
        ],
        "normalized_nodes": [
            {
                "id": "node:artifact:x",
                "label": "小瓶",
                "node_type": "artifact",
                "evidence_ids": ["evidence:1"],
                "source_locator": "tests/fixtures/mini_novel.txt#char=3-5",
                "supports_templates": [
                    {"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}
                ],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
            }
        ],
        "normalized_edges": [],
        "normalized_events": [],
        "normalized_evidence": [
            {
                "evidence_id": "evidence:1",
                "source_range": [3, 5],
                "source_locator": "tests/fixtures/mini_novel.txt#char=3-5",
                "chunk_id": "chunk-0001",
                "fact_summary": "韩立获得小瓶",
                "supports_templates": [
                    {"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}
                ],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
            }
        ],
    }

    result = build_canonical_graph_from_bundles([bundle], novel_name="book", status_enums={})

    assert result.ok is True
    assert result.graph["nodes"][0]["provenance"]["lane_output_paths"]
    assert result.graph["evidence_index"][0]["provenance"]["lane_output_paths"]
    assert result.graph["metadata"]["semantic_generation"] == "agent-produced"
    assert result.graph["metadata"]["canonical_writer_version"]
    assert result.graph["metadata"]["source_bundle_paths"] == []


def test_canonical_writer_uses_stable_ids_and_dedupes_duplicate_items():
    from storygraph_lib.canonical_writer import build_canonical_graph_from_bundles

    node = {
        "label": "小瓶",
        "node_type": "artifact",
        "source_range": [3, 5],
        "evidence_ids": ["evidence:1"],
        "supports_templates": [
            {"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}
        ],
        "confidence": "EXTRACTED",
        "verification_status": "verified",
    }
    evidence = {
        "evidence_id": "evidence:1",
        "source_range": [3, 5],
        "chunk_id": "chunk-0001",
        "fact_summary": "韩立获得小瓶",
        "supports_templates": [
            {"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}
        ],
        "confidence": "EXTRACTED",
        "verification_status": "verified",
    }
    first = _reviewed_bundle(normalized_nodes=[node], normalized_evidence=[evidence])
    second = _reviewed_bundle(
        chunk_id="chunk-0002",
        lane_output_paths=[
            "intermediate/lane-outputs/chunk-0002/entities_resources/run-001.json"
        ],
        normalized_nodes=[dict(node)],
        normalized_evidence=[dict(evidence, chunk_id="chunk-0002")],
    )

    result = build_canonical_graph_from_bundles([first, second], novel_name="book", status_enums={})

    assert result.ok is True
    assert len(result.graph["nodes"]) == 1
    assert result.graph["nodes"][0]["id"].startswith("node:artifact:")
    assert result.graph["nodes"][0]["provenance"]["chunk_ids"] == ["chunk-0001", "chunk-0002"]
    assert result.graph["nodes"][0]["provenance"]["lane_output_paths"] == [
        "intermediate/lane-outputs/chunk-0001/entities_resources/run-001.json",
        "intermediate/lane-outputs/chunk-0002/entities_resources/run-001.json",
    ]


def test_canonical_writer_preserves_conflicting_duplicate_ids():
    from storygraph_lib.canonical_writer import build_canonical_graph_from_bundles

    first = _reviewed_bundle(
        normalized_nodes=[
            {
                "id": "node:artifact:x",
                "label": "小瓶",
                "node_type": "artifact",
                "source_range": [3, 5],
                "evidence_ids": ["evidence:1"],
                "supports_templates": [
                    {"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}
                ],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
            }
        ],
        normalized_evidence=[
            {
                "evidence_id": "evidence:1",
                "source_range": [3, 5],
                "chunk_id": "chunk-0001",
                "fact_summary": "韩立获得小瓶",
                "supports_templates": [
                    {"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}
                ],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
            }
        ],
    )
    second = _reviewed_bundle(
        chunk_id="chunk-0002",
        lane_output_paths=[
            "intermediate/lane-outputs/chunk-0002/entities_resources/run-001.json"
        ],
        normalized_nodes=[
            {
                "id": "node:artifact:x",
                "label": "掌天瓶",
                "node_type": "artifact",
                "source_range": [10, 13],
                "evidence_ids": ["evidence:2"],
                "supports_templates": [
                    {"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}
                ],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
            }
        ],
        normalized_evidence=[
            {
                "evidence_id": "evidence:2",
                "source_range": [10, 13],
                "chunk_id": "chunk-0002",
                "fact_summary": "韩立持有掌天瓶",
                "supports_templates": [
                    {"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}
                ],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
            }
        ],
    )

    result = build_canonical_graph_from_bundles([first, second], novel_name="book", status_enums={})

    assert result.ok is True
    assert len(result.graph["nodes"]) == 1
    assert result.graph["metadata"]["conflicts"] == [
        {
            "collection": "nodes",
            "id": "node:artifact:x",
            "kept_chunk_id": "chunk-0001",
            "conflicting_chunk_id": "chunk-0002",
            "reason": "duplicate_id_conflict",
        }
    ]
    assert result.graph["nodes"][0]["provenance"]["conflicts"][0]["chunk_id"] == "chunk-0002"


def test_canonical_writer_fails_closed_for_bad_boundary_shapes_without_repr():
    from storygraph_lib.canonical_writer import build_canonical_graph_from_bundles

    result = build_canonical_graph_from_bundles(
        [
            "not-object",
            _reviewed_bundle(chunk_id="chunk-0002", normalized_nodes={}),
            _reviewed_bundle(chunk_id="chunk-0003", normalized_nodes=[object()]),
            _reviewed_bundle(chunk_id="chunk-0004", lane_output_paths=[object()]),
            _reviewed_bundle(
                chunk_id="chunk-0005",
                normalized_nodes=[
                    {
                        "id": "node:artifact:bad-provenance",
                        "label": "小瓶",
                        "node_type": "artifact",
                        "source_range": [3, 5],
                        "evidence_ids": ["evidence:bad-provenance"],
                        "supports_templates": [
                            {
                                "template_name": "法宝分析",
                                "requirement_id": "r1",
                                "status": "covered",
                            }
                        ],
                        "confidence": "EXTRACTED",
                        "verification_status": "verified",
                        "provenance": {"chunk_ids": "bad"},
                    }
                ],
                normalized_evidence=[
                    {
                        "evidence_id": "evidence:bad-provenance",
                        "source_range": [3, 5],
                        "chunk_id": "chunk-0005",
                        "fact_summary": "韩立获得小瓶",
                        "supports_templates": [
                            {
                                "template_name": "法宝分析",
                                "requirement_id": "r1",
                                "status": "covered",
                            }
                        ],
                        "confidence": "EXTRACTED",
                        "verification_status": "verified",
                    }
                ],
            ),
        ],
        novel_name="book",
        status_enums={"verification_statuses": 1},
        source_bundle_paths=[object()],
    )

    assert result.ok is False
    assert "bad_status_enum:verification_statuses" in result.errors
    assert "source_bundle_path_not_string:0" in result.errors
    assert "bundle_not_object:0" in result.errors
    assert "normalized_nodes_not_list:chunk-0002" in result.errors
    assert "normalized_node_not_object:chunk-0003:0" in result.errors
    assert "lane_output_path_not_string:chunk-0004:0" in result.errors
    assert "bad_provenance_chunk_ids:node:artifact:bad-provenance" in result.errors
    assert all("object at" not in error for error in result.errors)


def test_canonical_writer_rejects_bundles_argument_that_is_not_a_list():
    from storygraph_lib.canonical_writer import build_canonical_graph_from_bundles

    result = build_canonical_graph_from_bundles(
        {"chunk_id": "chunk-0001"},
        novel_name="book",
        status_enums={},
    )

    assert result.ok is False
    assert result.errors == ["bundles_not_list"]


def test_canonical_writer_reports_deep_json_values_without_throwing():
    from storygraph_lib.canonical_writer import build_canonical_graph_from_bundles

    deep = []
    current = deep
    for _ in range(1500):
        child = []
        current.append(child)
        current = child

    node = {
        "id": "node:artifact:x",
        "label": "小瓶",
        "node_type": "artifact",
        "source_range": [3, 5],
        "evidence_ids": ["evidence:1"],
        "supports_templates": [
            {"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}
        ],
        "confidence": "EXTRACTED",
        "verification_status": "verified",
        "extra": deep,
    }
    evidence = {
        "evidence_id": "evidence:1",
        "source_range": [3, 5],
        "fact_summary": "韩立获得小瓶",
        "supports_templates": [
            {"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}
        ],
        "confidence": "EXTRACTED",
        "verification_status": "verified",
    }

    result = build_canonical_graph_from_bundles(
        [_reviewed_bundle(normalized_nodes=[node], normalized_evidence=[evidence])],
        novel_name="book",
        status_enums={},
    )

    assert result.ok is False
    assert result.errors == ["json_depth_exceeded:nodes:chunk-0001:0"]


def test_canonical_writer_rejects_intermediate_deep_json_without_throwing():
    from storygraph_lib.canonical_writer import build_canonical_graph_from_bundles

    deep = []
    current = deep
    for _ in range(500):
        child = []
        current.append(child)
        current = child

    node = {
        "id": "node:artifact:x",
        "label": "小瓶",
        "node_type": "artifact",
        "source_range": [3, 5],
        "evidence_ids": ["evidence:1"],
        "supports_templates": [
            {"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}
        ],
        "confidence": "EXTRACTED",
        "verification_status": "verified",
        "extra": deep,
    }

    result = build_canonical_graph_from_bundles(
        [_reviewed_bundle(normalized_nodes=[node])],
        novel_name="book",
        status_enums={},
    )

    assert result.ok is False
    assert "json_depth_exceeded:nodes:chunk-0001:0" in result.errors


def test_canonical_writer_rejects_bad_existing_provenance_conflicts_without_throwing():
    from storygraph_lib.canonical_writer import build_canonical_graph_from_bundles

    first = _reviewed_bundle(
        normalized_nodes=[
            {
                "id": "node:artifact:x",
                "label": "小瓶",
                "node_type": "artifact",
                "source_range": [3, 5],
                "evidence_ids": ["evidence:1"],
                "supports_templates": [
                    {"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}
                ],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
                "provenance": {"conflicts": {"bad": True}},
            }
        ],
    )
    second = _reviewed_bundle(
        chunk_id="chunk-0002",
        lane_output_paths=[
            "intermediate/lane-outputs/chunk-0002/entities_resources/run-001.json"
        ],
        normalized_nodes=[
            {
                "id": "node:artifact:x",
                "label": "掌天瓶",
                "node_type": "artifact",
                "source_range": [10, 13],
                "evidence_ids": ["evidence:2"],
                "supports_templates": [
                    {"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}
                ],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
            }
        ],
    )

    result = build_canonical_graph_from_bundles([first, second], novel_name="book", status_enums={})

    assert result.ok is False
    assert "bad_provenance_conflicts:node:artifact:x" in result.errors
