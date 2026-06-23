"""Tests for stage2_graph_query module."""

import pytest
from storygraph_lib.stage2_graph_query import (
    normalize_query_params,
    extract_query_terms,
    score_nodes,
    pick_seed_nodes,
    traverse_graph_bfs,
    traverse_graph_dfs,
    render_subgraph_text,
    query_graph,
)


class TestNormalizeQueryParams:
    def test_default_values(self):
        params = normalize_query_params({})
        assert params["mode"] == "bfs"
        assert params["depth"] == 3
        assert params["token_budget"] == 2000
        assert params["limit"] is None

    def test_override_values(self):
        params = normalize_query_params({
            "mode": "dfs",
            "depth": 5,
            "token_budget": 3000,
            "limit": 10,
        })
        assert params["mode"] == "dfs"
        assert params["depth"] == 5
        assert params["token_budget"] == 3000
        assert params["limit"] == 10

    def test_depth_capped(self):
        params = normalize_query_params({"depth": 10})
        assert params["depth"] == 6

    def test_list_conversion(self):
        params = normalize_query_params({
            "include_terms": ["a", "b"],
            "exclude_terms": "c",
        })
        assert isinstance(params["include_terms"], set)
        assert isinstance(params["exclude_terms"], set)
        assert "c" in params["exclude_terms"]


class TestExtractQueryTerms:
    def test_english_terms(self):
        terms = extract_query_terms("what calls error handler")
        # "what" should be filtered (3 chars needed for English)
        assert "calls" in terms
        assert "error" in terms
        assert "handler" in terms

    def test_chinese_terms(self):
        # Skip if jieba not available
        terms = extract_query_terms("丹药分析")
        assert isinstance(terms, list)
        # Should be non-empty if jieba available
        assert len(terms) > 0

    def test_mixed_terms(self):
        terms = extract_query_terms("丹药 and error handler")
        assert isinstance(terms, list)
        assert len(terms) > 0

    def test_empty_input(self):
        terms = extract_query_terms("")
        assert terms == []


class TestScoreNodes:
    def test_score_empty_graph(self):
        G = {"nodes": []}
        scored = score_nodes(G, ["test"])
        assert scored == []

    def test_score_with_terms(self):
        G = {
            "nodes": [
                {"id": "n1", "label": "ErrorHandler", "type": "method"},
                {"id": "n2", "label": "CallFrame", "type": "class"},
                {"id": "n3", "label": "error", "type": "constant"},
            ]
        }
        scored = score_nodes(G, ["error", "handler"], target_types={"method", "class"})
        assert len(scored) > 0
        # ErrorHandler should score higher than CallFrame
        scores = {nid: score for score, nid in scored}
        assert scores.get("n1", 0) > scores.get("n2", 0)

    def test_exact_match_beats_prefix(self):
        G = {
            "nodes": [
                {"id": "n1", "label": "error", "type": "constant"},
                {"id": "n2", "label": "error_handler", "type": "method"},
            ]
        }
        scored = score_nodes(G, ["error"])
        assert scored[0][1] == "n1"  # exact match should come first


class TestPickSeeds:
    def test_pick_from_scored(self):
        scored = [(1000, "a"), (900, "b"), (100, "c"), (10, "d")]
        seeds = pick_seed_nodes(scored)
        assert "a" in seeds
        assert "b" in seeds
        # c and d should not be included (drop threshold)

    def test_max_k_limit(self):
        scored = [(100, "a"), (99, "b"), (98, "c"), (97, "d")]
        seeds = pick_seed_nodes(scored, max_k=2)
        assert len(seeds) <= 2

    def test_empty_scored(self):
        seeds = pick_seed_nodes([])
        assert seeds == []


class TestTraverseGraph:
    def test_bfs_traversal(self):
        G = {
            "nodes": [
                {"id": "n1", "label": "A"},
                {"id": "n2", "label": "B"},
                {"id": "n3", "label": "C"},
            ],
            "links": [
                {"source": "n1", "target": "n2"},
                {"source": "n2", "target": "n3"},
            ]
        }
        visited, edges = traverse_graph_bfs(G, ["n1"], depth=2)
        assert "n1" in visited
        assert "n2" in visited
        assert "n3" in visited
        assert len(edges) > 0

    def test_dfs_traversal(self):
        G = {
            "nodes": [
                {"id": "n1", "label": "A"},
                {"id": "n2", "label": "B"},
                {"id": "n3", "label": "C"},
            ],
            "links": [
                {"source": "n1", "target": "n2"},
                {"source": "n2", "target": "n3"},
            ]
        }
        visited, edges = traverse_graph_dfs(G, ["n1"], depth=2)
        assert "n1" in visited
        assert len(visited) >= 2


class TestRenderSubgraphText:
    def test_render_simple(self):
        G = {
            "nodes": [
                {"id": "n1", "label": "ErrorHandler", "type": "method"},
                {"id": "n2", "label": "CallFrame", "type": "class"},
            ],
            "links": [
                {"source": "n1", "target": "n2", "relation": "calls"},
            ]
        }
        text = render_subgraph_text(G, {"n1", "n2"}, [("n1", "n2")])
        assert "ErrorHandler" in text
        assert "CallFrame" in text
        assert "calls" in text

    def test_render_with_truncation(self):
        # Large graph that will be truncated
        nodes = [{"id": f"n{i}", "label": f"Node{i}", "type": "method"} for i in range(100)]
        text = render_subgraph_text(G={"nodes": nodes}, nodes=set(f"n{i}" for i in range(100)), edges=[], token_budget=10)
        assert "truncated" in text


class TestQueryGraphIntegration:
    def test_full_query_pipeline(self):
        G = {
            "nodes": [
                {"id": "n1", "label": "ErrorHandler", "type": "method"},
                {"id": "n2", "label": "CallFrame", "type": "class"},
                {"id": "n3", "label": "error", "type": "constant"},
            ],
            "links": [
                {"source": "n1", "target": "n2", "relation": "calls"},
            ]
        }
        result = query_graph(G, {
            "question": "ErrorHandler",
            "mode": "bfs",
            "depth": 2,
            "target_node_types": {"method", "class"},
        })
        assert result["nodes_found"] > 0
        assert "ErrorHandler" in result["text"]
