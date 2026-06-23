import json
from pathlib import Path

from storygraph_lib.stage2_query import (
    query_stage2_cases,
    query_template_candidates,
    write_query_result,
    write_stage2_query_result,
)


def _query_parameters() -> dict:
    return {
        "template_name": "丹药分析",
        "template_file": "丹药分析模板.md",
        "template_path": "templates/丹药分析模板.md",
        "query_terms": ["丹药", "药液", "筑基丹"],
        "target_types": ["item"],
        "required_fields": ["name", "usage", "formula"],
        "rough_filter": {
            "text_fields": ["label", "description", "fact_summary", "support"],
            "min_term_matches": 1,
            "include_graph_links": True,
        },
    }


def _general_query_parameters() -> dict:
    return {
        "template_name": "丹药分析",
        "template_file": "丹药分析模板.md",
        "include_terms": ["丹药", "丹方", "筑基丹", "服用"],
        "exclude_terms": ["法宝", "人物"],
        "target_kinds": ["item"],
        "require_any_term": ["筑基丹", "丹方", "服用"],
        "limit": 5,
        "field_alias": {
            "evidence_text": ["fact_summary", "support", "quote", "source_excerpt"],
            "graph_text": ["label", "name", "description", "summary"],
        },
        "rough_filter_rules": {
            "include_graph_links": True,
            "min_term_matches": 1,
        },
    }


def _write_query_inputs(graph_dir: Path) -> None:
    (graph_dir / "graphify-out").mkdir(parents=True)
    (graph_dir / "coverage").mkdir(parents=True)
    (graph_dir / "intermediate" / "chunks").mkdir(parents=True)
    (graph_dir / "graphify-out" / "graph.json").write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": "node:pill",
                        "label": "筑基丹",
                        "node_type": "item",
                        "description": "辅助炼气修士突破筑基的丹药。",
                        "evidence_ids": ["evidence:pill"],
                        "source_location": {
                            "chunk_id": "chunk-0001",
                            "source_range": [10, 22],
                        },
                    },
                {
                    "id": "node:bottle",
                    "label": "掌天瓶",
                    "node_type": "item",
                    "description": "法宝小瓶，能催熟灵草。",
                    "evidence_ids": ["evidence:bottle"],
                },
                    {
                        "id": "node:role",
                        "label": "韩立",
                        "node_type": "character",
                        "description": "角色条目。",
                        "evidence_ids": ["evidence:role"],
                    },
                    {
                        "id": "node:chunk-text",
                        "label": "第二十九章 正文覆盖片段",
                        "node_type": "text_coverage_fragment",
                        "description": "正文覆盖片段。",
                        "evidence_ids": ["evidence:chunk-text"],
                    },
                ],
                "edges": [],
                "events": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (graph_dir / "coverage" / "evidence-index.json").write_text(
        json.dumps(
            [
                {
                    "evidence_id": "evidence:pill",
                    "chunk_id": "chunk-0001",
                    "source_range": [10, 22],
                    "source_location": {
                        "chunk_id": "chunk-0001",
                        "source_range": [10, 22],
                    },
                    "fact_summary": "筑基丹可辅助突破筑基。",
                    "support": "筑基丹是修士重视的丹药，服用后可辅助突破。",
                    "linked_node_ids": ["node:pill"],
                    "confidence": "EXTRACTED",
                    "verification_status": "verified",
                    "supports_templates": [
                        {
                            "template_name": "资源、物品与交易经济",
                            "requirement_id": "resources_items_economy",
                            "status": "covered",
                        }
                    ],
                },
                {
                    "evidence_id": "evidence:bottle",
                    "chunk_id": "chunk-0002",
                    "source_range": [30, 42],
                    "fact_summary": "掌天瓶是法宝。",
                    "support": "法宝小瓶用于催熟药草。",
                    "linked_node_ids": ["node:bottle"],
                    "confidence": "EXTRACTED",
                    "verification_status": "verified",
                    "supports_templates": [],
                },
                {
                    "evidence_id": "evidence:role",
                    "chunk_id": "chunk-0003",
                    "source_range": [50, 64],
                    "fact_summary": "韩立获得机缘。",
                    "support": "角色经历。",
                    "linked_node_ids": ["node:role"],
                    "confidence": "EXTRACTED",
                    "verification_status": "verified",
                    "supports_templates": [],
                },
                {
                    "evidence_id": "evidence:chunk-text",
                    "chunk_id": "chunk-0004",
                    "source_range": [100, 180],
                    "source_location": {
                        "chunk_id": "chunk-0004",
                        "source_range": [100, 180],
                    },
                    "fact_summary": "第二十九章 正文覆盖片段。",
                    "support": "第二十九章 正文覆盖片段已纳入覆盖。",
                    "linked_node_ids": ["node:chunk-text"],
                    "confidence": "EXTRACTED",
                    "verification_status": "needs_review",
                    "supports_templates": [],
                },
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (graph_dir / "intermediate" / "chunks" / "chunk-0004.txt").write_text(
        "黄龙丹、金髓丸和养精丹这些丹药摆在韩立面前，养精丹对内外伤都有奇效。",
        encoding="utf-8",
    )

def test_query_stage2_cases_uses_general_parameters_and_records_rejections(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    _write_query_inputs(graph_dir)

    result = query_stage2_cases(graph_dir, _general_query_parameters())

    assert result["schema"] == "stage2-template-query-result.v1"
    assert result["template_name"] == "丹药分析"
    assert "source_requirements" not in result
    assert "requirement_scope" not in result
    assert result["summary"]["candidate_count"] == 1
    assert result["summary"]["rejected_count"] == 3
    case = result["candidate_cases"][0]
    assert case["candidate_name"] == "筑基丹"
    assert case["item_kind"] == "item"
    assert case["source_kind"] == "evidence"
    assert case["matched_terms"] == ["丹药", "筑基丹", "服用"]
    assert case["evidence_ids"] == ["evidence:pill"]
    assert case["source_excerpt"] == "筑基丹是修士重视的丹药，服用后可辅助突破。"
    assert case["fact_summary"] == "筑基丹可辅助突破筑基。"
    assert case["source_range"] == [10, 22]
    assert case["source_locations"] == [
        {"chunk_id": "chunk-0001", "source_range": [10, 22]}
    ]
    assert case["confidence"] == "EXTRACTED"
    assert case["rough_filter_reason"] == "matched_include_terms:丹药,筑基丹,服用"
    rejected = {item["evidence_id"]: item["reason"] for item in result["rejected_candidates"]}
    assert rejected == {
        "evidence:bottle": "exclude_terms_matched:法宝",
        "evidence:role": "target_kind_mismatch",
        "evidence:chunk-text": "target_kind_mismatch",
    }


def test_write_stage2_query_result_writes_json_without_bom(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    _write_query_inputs(graph_dir)
    result = query_stage2_cases(graph_dir, _general_query_parameters())

    output_path = write_stage2_query_result(
        graph_dir,
        result,
        "intermediate/stage2/query-results/丹药分析.json",
    )

    raw = output_path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    written = json.loads(raw.decode("utf-8"))
    assert written["candidate_cases"][0]["candidate_name"] == "筑基丹"
    assert written["candidate_cases"][0]["source_kind"] == "evidence"


def test_query_template_candidates_filters_evidence_by_configurable_terms(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    _write_query_inputs(graph_dir)

    result = query_template_candidates(graph_dir, _query_parameters())

    assert result["schema"] == "stage2-template-query-result.v1"
    assert result["template_name"] == "丹药分析"
    assert result["source_graph"] == "graphify-out/graph.json"
    assert result["summary"]["candidate_count"] == 1
    assert result["summary"]["rejected_count"] == 3
    case = result["candidate_cases"][0]
    assert case["candidate_name"] == "筑基丹"
    assert case["matched_terms"] == ["丹药", "筑基丹"]
    assert case["evidence_ids"] == ["evidence:pill"]
    assert case["source_excerpt"] == "筑基丹是修士重视的丹药，服用后可辅助突破。"
    assert case["source_range"] == [10, 22]
    assert case["source_locations"] == [
        {"chunk_id": "chunk-0001", "source_range": [10, 22]}
    ]
    assert case["confidence"] == "EXTRACTED"
    assert case["review_status"] == "verified"
    assert "rough_filter_reason" in case
    rejected = {item["evidence_id"]: item["reason"] for item in result["rejected_candidates"]}
    assert rejected == {
        "evidence:bottle": "no_query_terms_matched",
        "evidence:role": "target_type_mismatch",
        "evidence:chunk-text": "target_type_mismatch",
    }


def test_write_query_result_writes_managed_json_without_bom(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    _write_query_inputs(graph_dir)
    result = query_template_candidates(graph_dir, _query_parameters())

    output_path = write_query_result(
        graph_dir,
        result,
        "intermediate/stage2/query-results/丹药分析.json",
    )

    raw = output_path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    written = json.loads(raw.decode("utf-8"))
    assert written["schema"] == "stage2-template-query-result.v1"
    assert written["candidate_cases"][0]["candidate_name"] == "筑基丹"


def test_query_stage2_cases_searches_chunk_text_when_evidence_summary_is_generic(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    _write_query_inputs(graph_dir)
    parameters = {
        "template_name": "丹药分析",
        "include_terms": ["养精丹", "丹药"],
        "target_kinds": ["text_coverage_fragment"],
        "require_any_term": ["养精丹"],
        "rough_filter_rules": {
            "include_graph_links": True,
            "include_source_chunks": True,
            "min_term_matches": 1,
        },
    }

    result = query_stage2_cases(graph_dir, parameters)

    assert result["summary"]["candidate_count"] == 1
    case = result["candidate_cases"][0]
    assert case["candidate_name"] == "第二十九章 正文覆盖片段"
    assert case["evidence_ids"] == ["evidence:chunk-text"]
    assert case["matched_terms"] == ["养精丹", "丹药"]
    assert "养精丹对内外伤都有奇效" in case["source_excerpt"]
