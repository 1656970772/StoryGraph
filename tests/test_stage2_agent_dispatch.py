"""Tests for stage2_agent_dispatch module."""

import json
import pytest
from pathlib import Path
from storygraph_lib.stage2_agent_dispatch import (
    prepare_query_task_packet,
    prepare_draft_task_packet,
    prepare_final_task_packet,
    collect_query_results,
    collect_draft_results,
    collect_final_results,
)


class TestPrepareQueryTaskPacket:
    def test_basic_packet(self, tmp_path):
        template = {
            "template_name": "丹药分析",
            "template_path": "templates/pill.md",
            "query_hints": {
                "target_node_types": ["pill", "ingredient"],
                "context_filter": ["effect", "material"],
            }
        }
        packet = prepare_query_task_packet(template, tmp_path)

        assert packet["task_type"] == "stage2_query"
        assert packet["template_name"] == "丹药分析"
        assert "instructions" in packet
        assert "graph_dir" in packet

    def test_packet_contains_hints(self, tmp_path):
        template = {
            "template_name": "test",
            "query_hints": {
                "target_node_types": ["type1", "type2"],
            }
        }
        packet = prepare_query_task_packet(template, tmp_path)
        assert "type1" in packet["instructions"]


class TestPrepareDraftTaskPacket:
    def test_basic_packet(self, tmp_path):
        template = {
            "template_name": "丹药分析",
            "template_path": str(tmp_path / "template.md"),
        }
        query_result = {
            "nodes_found": 10,
            "text": "NODE ...",
        }

        # Create template file
        (tmp_path / "template.md").write_text("# 丹药分析", encoding="utf-8")

        packet = prepare_draft_task_packet(template, query_result, tmp_path)

        assert packet["task_type"] == "stage2_draft"
        assert packet["template_name"] == "丹药分析"
        assert packet["query_result"] == query_result
        assert "# 丹药分析" in packet["template_markdown"]

    def test_packet_missing_template_file(self, tmp_path):
        template = {
            "template_name": "test",
            "template_path": str(tmp_path / "nonexistent.md"),
        }
        query_result = {}

        # Should not raise, just use empty template
        packet = prepare_draft_task_packet(template, query_result, tmp_path)
        assert packet["template_markdown"] == ""


class TestPrepareFinalTaskPacket:
    def test_basic_packet(self, tmp_path):
        template = {
            "template_name": "丹药分析",
            "template_path": str(tmp_path / "template.md"),
            "render_policy": {
                "dedup_strategy": "by_label",
                "merge_strategy": "conservative",
            }
        }
        draft_cases = [
            {"case_id": "1", "title": "case1"},
        ]

        (tmp_path / "template.md").write_text("# 丹药分析", encoding="utf-8")

        packet = prepare_final_task_packet(template, draft_cases, tmp_path)

        assert packet["task_type"] == "stage2_final"
        assert packet["template_name"] == "丹药分析"
        assert packet["draft_cases"] == draft_cases
        assert "dedup_strategy" in packet["render_policy"]


class TestCollectQueryResults:
    def test_collect_single_result(self):
        agent_results = [
            {
                "task_type": "query_agent",
                "template_name": "丹药分析",
                "agent_result": {
                    "question": "what pills help breakthrough",
                    "mode": "bfs",
                }
            }
        ]
        results = collect_query_results(agent_results)

        assert "丹药分析" in results
        assert results["丹药分析"]["question"] == "what pills help breakthrough"

    def test_collect_json_string_result(self):
        agent_results = [
            {
                "task_type": "query_agent",
                "template_name": "test",
                "agent_result": '{"question": "test"}'
            }
        ]
        results = collect_query_results(agent_results)

        assert "test" in results
        assert results["test"]["question"] == "test"

    def test_skip_non_query_results(self):
        agent_results = [
            {
                "task_type": "draft_agent",
                "template_name": "test",
                "agent_result": {}
            }
        ]
        results = collect_query_results(agent_results)

        assert len(results) == 0


class TestCollectDraftResults:
    def test_collect_single_result(self):
        agent_results = [
            {
                "task_type": "draft_agent",
                "template_name": "丹药分析",
                "agent_result": [
                    {"case_id": "1", "title": "case1"}
                ]
            }
        ]
        results = collect_draft_results(agent_results)

        assert "丹药分析" in results
        assert len(results["丹药分析"]) == 1

    def test_collect_dict_result(self):
        agent_results = [
            {
                "task_type": "draft_agent",
                "template_name": "test",
                "agent_result": {
                    "cases": [
                        {"case_id": "1"}
                    ]
                }
            }
        ]
        results = collect_draft_results(agent_results)

        assert "test" in results
        assert len(results["test"]) == 1

    def test_collect_json_string_result(self):
        agent_results = [
            {
                "task_type": "draft_agent",
                "template_name": "test",
                "agent_result": '[{"case_id": "1"}]'
            }
        ]
        results = collect_draft_results(agent_results)

        assert "test" in results
        assert len(results["test"]) == 1


class TestCollectFinalResults:
    def test_collect_markdown_result(self):
        agent_results = [
            {
                "task_type": "final_agent",
                "template_name": "丹药分析",
                "agent_result": "# 丹药分析\n\n这是最终文档"
            }
        ]
        results = collect_final_results(agent_results)

        assert "丹药分析" in results
        assert "这是最终文档" in results["丹药分析"]

    def test_skip_non_final_results(self):
        agent_results = [
            {
                "task_type": "draft_agent",
                "template_name": "test",
                "agent_result": "some text"
            }
        ]
        results = collect_final_results(agent_results)

        assert len(results) == 0
