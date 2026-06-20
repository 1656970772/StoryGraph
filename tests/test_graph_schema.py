import pytest

from storygraph_lib.graph_schema import merge_template_supplements, validate_canonical_graph
from storygraph_lib.ids import (
    stable_edge_id,
    stable_event_id,
    stable_evidence_id,
    stable_node_id,
)


def test_stable_ids_are_repeatable_and_type_scoped():
    assert stable_node_id("凡人修仙传", "韩立", "person") == stable_node_id(
        "凡人修仙传", "韩立", "person"
    )
    assert stable_node_id("凡人修仙传", "韩立", "person") != stable_node_id(
        "凡人修仙传", "韩立", "faction"
    )
    assert stable_edge_id("凡人修仙传", "node:a", "node:b", "owns").startswith(
        "edge:owns:"
    )
    assert stable_event_id("凡人修仙传", "resource_gain", "韩立", [0, 12]).startswith(
        "event:resource_gain:"
    )
    assert stable_evidence_id("凡人修仙传", "chunk-0001", [0, 12]).startswith(
        "evidence:"
    )


def test_deep_validation_rejects_missing_evidence_and_bad_status():
    graph = {
        "nodes": [
            {
                "id": "node:person:abc",
                "label": "韩立",
                "node_type": "person",
                "source_range": [0, 2],
                "evidence_ids": [],
                "supports_templates": [
                    {
                        "template_name": "法宝分析",
                        "requirement_id": "法宝分析.required_fields.法宝",
                        "status": "maybe",
                    }
                ],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
            }
        ],
        "edges": [],
        "hyperedges": [],
        "events": [],
        "evidence_index": [],
        "metadata": {},
    }

    result = validate_canonical_graph(graph)

    assert result.ok is False
    assert "missing:schema_version" in result.errors
    assert "missing:graphify_schema_version" in result.errors
    assert "missing:storygraph_schema_version" in result.errors
    assert "bad_requirement_status:maybe" in result.errors
    assert "node_without_evidence:node:person:abc" in result.errors


def test_deep_validation_requires_top_level_schema_versions():
    graph = {
        "nodes": [],
        "edges": [],
        "hyperedges": [],
        "events": [],
        "evidence_index": [],
        "metadata": {"graphify_schema_version": "x"},
    }

    errors = validate_canonical_graph(graph).errors

    assert "missing:schema_version" in errors
    assert "missing:graphify_schema_version" in errors
    assert "missing:storygraph_schema_version" in errors


def test_deep_validation_reports_malformed_collections_without_throwing():
    graph = {
        "schema_version": "1.0",
        "graphify_schema_version": "x",
        "storygraph_schema_version": "1.0",
        "nodes": {},
        "edges": None,
        "hyperedges": "bad",
        "events": 1,
        "evidence_index": None,
        "metadata": {},
    }

    result = validate_canonical_graph(graph)

    assert result.ok is False
    assert "bad_graph_collection:nodes" in result.errors
    assert "bad_graph_collection:edges" in result.errors
    assert "bad_graph_collection:hyperedges" in result.errors
    assert "bad_graph_collection:events" in result.errors
    assert "bad_graph_collection:evidence_index" in result.errors


def test_deep_validation_reports_malformed_status_enums_without_throwing():
    graph = {
        "schema_version": "1.0",
        "graphify_schema_version": "x",
        "storygraph_schema_version": "1.0",
        "nodes": [],
        "edges": [],
        "hyperedges": [],
        "events": [],
        "evidence_index": [],
        "metadata": {},
    }

    result = validate_canonical_graph(graph, {"verification_statuses": 1})

    assert result.ok is False
    assert "bad_status_enum:verification_statuses" in result.errors


def test_deep_validation_handles_unhashable_nested_refs_and_statuses_without_throwing():
    graph = {
        "schema_version": "1.0",
        "graphify_schema_version": "x",
        "storygraph_schema_version": "1.0",
        "nodes": [
            {
                "id": "node:item:bad",
                "label": "坏引用",
                "node_type": "artifact",
                "source_range": [0, 1],
                "evidence_ids": [["nested"]],
                "supports_templates": [
                    {
                        "template_name": "法宝分析",
                        "requirement_id": "r1",
                        "status": ["covered"],
                    }
                ],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
            }
        ],
        "edges": [],
        "hyperedges": [],
        "events": [
            {
                "id": "event:bad",
                "event_type": "gain",
                "source_range": [0, 1],
                "participants": [["nested"]],
                "evidence_ids": ["evidence:valid"],
                "supports_templates": [
                    {
                        "template_name": "事件分析",
                        "requirement_id": "r2",
                        "status": ["covered"],
                    }
                ],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
            }
        ],
        "evidence_index": [
            {
                "evidence_id": "evidence:valid",
                "source_range": [0, 1],
                "fact_summary": "valid",
                "confidence": "EXTRACTED",
                "verification_status": "verified",
                "supports_templates": [
                    {
                        "template_name": "法宝分析",
                        "requirement_id": "r3",
                        "status": ["covered"],
                    }
                ],
            }
        ],
        "metadata": {},
    }

    result = validate_canonical_graph(graph)

    assert result.ok is False
    assert "node_unknown_evidence:node:item:bad" in result.errors
    assert "event_unknown_node:event:bad" in result.errors
    assert "bad_requirement_status:['covered']" in result.errors


def test_merge_template_supplements_preserves_graphify_fields_and_requires_non_empty_supports():
    base = {
        "nodes": [{"id": "node:person:abc", "label": "韩立"}],
        "edges": [{"id": "graphify-edge-1", "source": "a", "target": "b"}],
        "hyperedges": [],
        "metadata": {"graphify_schema_version": "x"},
        "graphify_extra": {"kept": True},
    }
    supplement = {
        "nodes": [
            {
                "id": "node:person:abc",
                "node_type": "person",
                "source_range": [0, 8],
                "evidence_ids": ["evidence:1"],
                "supports_templates": [
                    {
                        "template_name": "法宝分析",
                        "requirement_id": "法宝分析.required_fields.法宝",
                        "status": "covered",
                    }
                ],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
            }
        ],
        "edges": [],
        "events": [],
        "evidence_index": [
            {
                "evidence_id": "evidence:1",
                "source_range": [0, 8],
                "fact_summary": "韩立获得小瓶",
                "confidence": "EXTRACTED",
                "verification_status": "verified",
                "supports_templates": [
                    {
                        "template_name": "法宝分析",
                        "requirement_id": "法宝分析.required_fields.法宝",
                        "status": "covered",
                    }
                ],
            }
        ],
    }

    graph = merge_template_supplements(base, supplement)

    assert graph["nodes"][0]["label"] == "韩立"
    assert graph["metadata"]["graphify_schema_version"] == "x"
    assert graph["graphify_extra"] == {"kept": True}
    assert graph["graphify_schema_version"] == "x"
    assert graph["storygraph_schema_version"] == "1.0"
    assert validate_canonical_graph(graph).ok is True


def test_merge_template_supplements_tolerates_malformed_optional_collections():
    base = {
        "nodes": [{"id": ["bad-base"], "label": "bad"}],
        "edges": None,
        "events": None,
        "evidence_index": None,
        "metadata": "bad",
    }
    supplement = {
        "nodes": [{"id": ["bad-supplement"], "label": "bad"}],
        "edges": None,
        "events": None,
        "evidence_index": None,
    }

    graph = merge_template_supplements(base, supplement)

    assert graph["metadata"] == {}
    assert graph["graphify_schema_version"] == "unknown"
    assert graph["nodes"] == [
        {"id": ["bad-base"], "label": "bad"},
        {"id": ["bad-supplement"], "label": "bad"},
    ]
    assert graph["edges"] == []
    assert graph["events"] == []
    assert graph["evidence_index"] == []
    assert graph["hyperedges"] == []


def test_deep_validation_rejects_bad_edges_events_evidence_and_unknown_evidence():
    graph = {
        "schema_version": "1.0",
        "graphify_schema_version": "x",
        "storygraph_schema_version": "1.0",
        "nodes": [
            {
                "id": "node:item:1",
                "label": "小瓶",
                "node_type": "artifact",
                "source_range": [0, 8],
                "evidence_ids": ["evidence:missing"],
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
        "edges": [
            {
                "id": "edge:owns:1",
                "source": "node:item:1",
                "target": "node:missing",
                "edge_type": "owns",
                "source_location": {"chunk_id": "chunk-0001"},
                "evidence_ids": ["evidence:missing"],
                "supports_templates": [
                    {
                        "template_name": "法宝分析",
                        "requirement_id": "r2",
                        "status": "covered",
                    }
                ],
                "confidence": "CERTAIN",
                "verification_status": "verified",
            }
        ],
        "hyperedges": [],
        "events": [
            {
                "id": "event:gain:1",
                "event_type": "gain",
                "source_location": {"chunk_id": "chunk-0001"},
                "participants": ["node:missing"],
                "evidence_ids": [],
                "supports_templates": [
                    {
                        "template_name": "法宝分析",
                        "requirement_id": "r3",
                        "status": "unknown",
                    }
                ],
                "confidence": "EXTRACTED",
                "verification_status": "bad",
            }
        ],
        "evidence_index": [
            {
                "evidence_id": "bad",
                "source_range": [],
                "fact_summary": "",
                "confidence": "EXTRACTED",
                "verification_status": "verified",
                "supports_templates": [],
            }
        ],
        "metadata": {},
    }

    errors = validate_canonical_graph(graph).errors

    assert "node_unknown_evidence:node:item:1" in errors
    assert "edge_unknown_node:edge:owns:1" in errors
    assert "bad_confidence:CERTAIN" in errors
    assert "event_without_evidence:event:gain:1" in errors
    assert "bad_requirement_status:unknown" in errors
    assert "bad_evidence_id:bad" in errors


def test_graphify_native_items_without_storygraph_markers_are_allowed():
    graph = {
        "schema_version": "1.0",
        "graphify_schema_version": "x",
        "storygraph_schema_version": "1.0",
        "nodes": [{"id": "person-1", "label": "韩立"}],
        "edges": [{"id": "rel-1", "source": "person-1", "target": "person-2"}],
        "hyperedges": [],
        "events": [],
        "evidence_index": [],
        "metadata": {},
    }

    assert validate_canonical_graph(graph).ok is True


def test_deep_validation_rejects_storygraph_items_without_source_location():
    graph = {
        "schema_version": "1.0",
        "graphify_schema_version": "x",
        "storygraph_schema_version": "1.0",
        "nodes": [
            {
                "id": "node:person:abc",
                "label": "韩立",
                "node_type": "person",
                "evidence_ids": ["evidence:1"],
                "supports_templates": [
                    {"template_name": "人物分析", "requirement_id": "r1", "status": "covered"}
                ],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
            },
            {
                "id": "node:item:abc",
                "label": "小瓶",
                "node_type": "artifact",
                "source_range": [10, 14],
                "evidence_ids": ["evidence:1"],
                "supports_templates": [
                    {"template_name": "法宝分析", "requirement_id": "r2", "status": "covered"}
                ],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
            },
        ],
        "edges": [
            {
                "id": "edge:owns:abc",
                "source": "node:person:abc",
                "target": "node:item:abc",
                "edge_type": "owns",
                "evidence_ids": ["evidence:1"],
                "supports_templates": [
                    {"template_name": "法宝分析", "requirement_id": "r3", "status": "covered"}
                ],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
            }
        ],
        "hyperedges": [],
        "events": [
            {
                "id": "event:gain:abc",
                "event_type": "gain",
                "participants": ["node:person:abc", "node:item:abc"],
                "evidence_ids": ["evidence:1"],
                "supports_templates": [
                    {"template_name": "法宝分析", "requirement_id": "r4", "status": "covered"}
                ],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
            }
        ],
        "evidence_index": [
            {
                "evidence_id": "evidence:1",
                "source_range": [0, 14],
                "fact_summary": "韩立获得小瓶",
                "confidence": "EXTRACTED",
                "verification_status": "verified",
                "supports_templates": [
                    {"template_name": "法宝分析", "requirement_id": "r5", "status": "covered"}
                ],
            }
        ],
        "metadata": {},
    }

    errors = validate_canonical_graph(graph).errors

    assert "node_without_source_location:node:person:abc" in errors
    assert "edge_without_source_location:edge:owns:abc" in errors
    assert "event_without_source_location:event:gain:abc" in errors


@pytest.mark.parametrize(
    ("owner", "expected_error"),
    [
        ("node", "node_bad_source_range:node:item:float"),
        ("edge", "edge_bad_source_range:edge:owns:float"),
        ("event", "event_bad_source_range:event:gain:float"),
        ("evidence", "evidence_bad_source_range:evidence:float"),
    ],
)
def test_validate_canonical_graph_rejects_float_source_ranges(owner, expected_error):
    graph = {
        "schema_version": "1.0",
        "graphify_schema_version": "x",
        "storygraph_schema_version": "1.0",
        "nodes": [
            {
                "id": "node:item:float",
                "label": "小瓶",
                "node_type": "artifact",
                "source_range": [0, 2],
                "evidence_ids": ["evidence:1"],
                "supports_templates": [
                    {"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}
                ],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
            }
        ],
        "edges": [
            {
                "id": "edge:owns:float",
                "source": "node:item:float",
                "target": "node:item:float",
                "edge_type": "owns",
                "source_range": [0, 2],
                "evidence_ids": ["evidence:1"],
                "supports_templates": [
                    {"template_name": "法宝分析", "requirement_id": "r2", "status": "covered"}
                ],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
            }
        ],
        "hyperedges": [],
        "events": [
            {
                "id": "event:gain:float",
                "event_type": "gain",
                "participants": ["node:item:float"],
                "source_range": [0, 2],
                "evidence_ids": ["evidence:1"],
                "supports_templates": [
                    {"template_name": "法宝分析", "requirement_id": "r3", "status": "covered"}
                ],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
            }
        ],
        "evidence_index": [
            {
                "evidence_id": "evidence:1",
                "source_range": [0, 2],
                "fact_summary": "韩立获得小瓶",
                "confidence": "EXTRACTED",
                "verification_status": "verified",
                "supports_templates": [
                    {"template_name": "法宝分析", "requirement_id": "r4", "status": "covered"}
                ],
            }
        ],
        "metadata": {},
    }
    if owner == "node":
        graph["nodes"][0]["source_range"] = [0.5, 1.5]
    elif owner == "edge":
        graph["edges"][0]["source_range"] = [0.5, 1.5]
    elif owner == "event":
        graph["events"][0]["source_range"] = [0.5, 1.5]
    else:
        graph["evidence_index"][0]["evidence_id"] = "evidence:float"
        graph["nodes"][0]["evidence_ids"] = ["evidence:float"]
        graph["edges"][0]["evidence_ids"] = ["evidence:float"]
        graph["events"][0]["evidence_ids"] = ["evidence:float"]
        graph["evidence_index"][0]["source_range"] = [0.5, 1.5]

    result = validate_canonical_graph(graph)

    assert result.ok is False
    assert expected_error in result.errors


def test_validate_canonical_graph_rejects_bad_source_range_even_with_source_location():
    graph = {
        "schema_version": "1.0",
        "graphify_schema_version": "x",
        "storygraph_schema_version": "1.0",
        "nodes": [
            {
                "id": "node:item:float",
                "label": "小瓶",
                "node_type": "artifact",
                "source_location": {"chapter": "第一章"},
                "source_range": [0.5, 1.5],
                "evidence_ids": ["evidence:1"],
                "supports_templates": [
                    {"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}
                ],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
            }
        ],
        "edges": [],
        "hyperedges": [],
        "events": [],
        "evidence_index": [
            {
                "evidence_id": "evidence:1",
                "source_range": [0, 2],
                "fact_summary": "韩立获得小瓶",
                "confidence": "EXTRACTED",
                "verification_status": "verified",
                "supports_templates": [
                    {"template_name": "法宝分析", "requirement_id": "r2", "status": "covered"}
                ],
            }
        ],
        "metadata": {},
    }

    errors = validate_canonical_graph(graph).errors

    assert "node_bad_source_range:node:item:float" in errors


def test_validate_canonical_graph_accepts_configured_status_enums():
    graph = merge_template_supplements(
        {"nodes": [{"id": "node:person:abc", "label": "韩立"}]},
        {
            "nodes": [
                {
                    "id": "node:person:abc",
                    "node_type": "person",
                    "source_location": {"chapter": "第一章"},
                    "evidence_ids": ["evidence:1"],
                    "supports_templates": [
                        {"template_name": "人物分析", "requirement_id": "r1", "status": "done"}
                    ],
                    "confidence": "HIGH",
                    "verification_status": "checked",
                }
            ],
            "evidence_index": [
                {
                    "evidence_id": "evidence:1",
                    "source_range": [0, 8],
                    "fact_summary": "韩立出场",
                    "confidence": "HIGH",
                    "verification_status": "checked",
                    "supports_templates": [
                        {"template_name": "人物分析", "requirement_id": "r1", "status": "done"}
                    ],
                }
            ],
        },
    )

    result = validate_canonical_graph(
        graph,
        status_enums={
            "requirement_statuses": ["done"],
            "verification_statuses": ["checked"],
            "confidence_levels": ["HIGH"],
        },
    )

    assert result.ok is True
