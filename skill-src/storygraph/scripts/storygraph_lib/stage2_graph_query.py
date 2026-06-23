"""Stage 2 graph query engine - Graphify-style query pipeline.

Implements 5-step query process:
1. Parameter normalization + term extraction
2. Node scoring (IDF-weighted)
3. Seed selection
4. Graph traversal (BFS/DFS)
5. Text rendering
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any

try:
    import jieba
except ImportError:
    jieba = None


# ============================================================================
# Step 1: Parameter Normalization & Term Extraction
# ============================================================================

def normalize_query_params(params: dict) -> dict:
    """Normalize query parameters to standard form.

    Fills in defaults and validates parameter types.
    """
    normalized = dict(params)

    # Mode: bfs or dfs
    normalized.setdefault("mode", "bfs")
    if normalized["mode"] not in ("bfs", "dfs"):
        normalized["mode"] = "bfs"

    # Depth: 1-6
    depth = normalized.get("depth", 3)
    try:
        depth = int(depth)
    except (ValueError, TypeError):
        depth = 3
    normalized["depth"] = max(1, min(depth, 6))

    # Token budget
    token_budget = normalized.get("token_budget", 2000)
    try:
        token_budget = int(token_budget)
    except (ValueError, TypeError):
        token_budget = 2000
    normalized["token_budget"] = max(100, token_budget)

    # Lists: convert to set for faster lookup
    for key in ["include_terms", "exclude_terms", "target_node_types", "context_filter"]:
        val = normalized.get(key, [])
        if isinstance(val, str):
            val = [val]
        normalized[key] = set(v for v in val if v)

    # Question/query text
    normalized.setdefault("question", "")
    normalized.setdefault("query_text", normalized.get("question", ""))

    # Limit
    limit = normalized.get("limit")
    if limit is not None:
        try:
            limit = int(limit)
            normalized["limit"] = max(1, limit) if limit > 0 else None
        except (ValueError, TypeError):
            normalized["limit"] = None
    else:
        normalized["limit"] = None

    return normalized


def _strip_diacritics(text: str | None) -> str:
    """Remove diacritics from text."""
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _search_tokens(text: str) -> list[str]:
    """Split text into word tokens, stripping punctuation."""
    return re.findall(r"\w+", _strip_diacritics(str(text)).lower())


def _has_chinese(text: str) -> bool:
    """Check if text contains Chinese characters."""
    return any("一" <= ch <= "鿿" for ch in text)


def _segment_chinese(text: str) -> list[str]:
    """Segment Chinese text using jieba or bigrams."""
    if jieba is not None:
        segments = [w for w in jieba.cut(text) if len(w.strip()) > 0]
    else:
        # Fallback: bigrams
        segments = [text[i : i + 2] for i in range(len(text) - 1)] or [text]
    # Keep original term for exact matching
    if len(text) > 1 and text not in segments:
        segments.append(text)
    return segments


def _is_searchable(term: str) -> bool:
    """Check if term is searchable (not noise)."""
    # Chinese or non-ASCII: always searchable
    if all("a" <= ch <= "z" for ch in term):
        # English: only if > 2 chars (filter "is", "in", etc.)
        return len(term) > 2
    return True


def extract_query_terms(question: str) -> list[str]:
    """Extract searchable terms from a question.

    Handles both Chinese (jieba) and English (word tokenization).
    Returns list of lowercase, diacritic-stripped, deduplicated terms.
    """
    terms: list[str] = []
    seen: set[str] = set()

    for raw in question.split():
        if _has_chinese(raw):
            for seg in _segment_chinese(raw.lower().strip()):
                seg = seg.strip()
                if seg and _is_searchable(seg) and seg not in seen:
                    terms.append(seg)
                    seen.add(seg)
        else:
            # ASCII: tokenize by word boundary
            for tok in re.findall(r"\w+", raw.lower()):
                if _is_searchable(tok) and tok not in seen:
                    terms.append(tok)
                    seen.add(tok)

    return terms


# ============================================================================
# Step 2a: Node Scoring with IDF Weighting
# ============================================================================

def _compute_idf(G: dict, terms: list[str], cache: dict | None = None) -> dict[str, float]:
    """Compute IDF weights for query terms.

    IDF = log(1 + N / (1 + document_frequency))
    Common terms get low weight; rare terms get high weight.
    """
    if cache is None:
        cache = {}

    nodes = G.get("nodes", [])
    N = len(nodes) or 1

    uncached = [t for t in terms if t not in cache]
    if not uncached:
        return {t: cache.get(t, math.log(1 + N)) for t in terms}

    # Count document frequency
    df: dict[str, int] = {t: 0 for t in uncached}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        label = node.get("label") or ""
        norm_label = _strip_diacritics(label).lower()
        for t in uncached:
            if t in norm_label:
                df[t] += 1

    # Store in cache
    for t in uncached:
        cache[t] = math.log(1 + N / (1 + df[t]))

    return {t: cache.get(t, math.log(1 + N)) for t in terms}


_EXACT_MATCH_BONUS = 1000.0
_PREFIX_MATCH_BONUS = 100.0
_SUBSTRING_MATCH_BONUS = 1.0
_SOURCE_MATCH_BONUS = 0.5


def score_nodes(
    G: dict,
    terms: list[str],
    target_types: set[str] | list[str] | None = None,
    idf_cache: dict | None = None,
) -> list[tuple[float, str]]:
    """Score all nodes in graph by relevance to query terms.

    Scoring tiers (per term):
    1. Exact match: 1000.0
    2. Prefix match: 100.0
    3. Substring match: 1.0
    4. Source file match: 0.5

    Each score is multiplied by IDF weight. Higher weight = rarer term.

    Returns list of (score, node_id) sorted by score descending.
    """
    if not terms:
        return []

    nodes = G.get("nodes", [])
    if not nodes:
        return []

    # Build node lookup
    nodes_by_id: dict[str, dict] = {}
    for node in nodes:
        if isinstance(node, dict):
            nid = node.get("id") or node.get("_id")
            if nid:
                nodes_by_id[nid] = node

    # Compute IDF weights
    norm_terms = [tok for t in terms for tok in _search_tokens(t)]
    idf = _compute_idf(G, norm_terms, cache=idf_cache)

    # Normalize target_types to set
    if target_types and isinstance(target_types, (list, tuple)):
        target_types = set(target_types)

    # Score nodes
    scored: list[tuple[float, str]] = []
    for nid, node in nodes_by_id.items():
        # Skip if target types specified and node doesn't match
        if target_types:
            node_type = node.get("type") or node.get("node_type") or ""
            if node_type not in target_types:
                continue

        label = node.get("label") or nid
        norm_label = _strip_diacritics(label).lower()
        bare_label = norm_label.rstrip("()")
        source = (node.get("source_file") or "").lower()

        score = 0.0
        for t in norm_terms:
            w = idf.get(t, 1.0)
            # Three-tier precedence: exact > prefix > substring
            if t == norm_label or t == bare_label:
                score += _EXACT_MATCH_BONUS * w
            elif norm_label.startswith(t) or bare_label.startswith(t):
                score += _PREFIX_MATCH_BONUS * w
            elif t in norm_label:
                score += _SUBSTRING_MATCH_BONUS * w
            # Source file bonus
            if t in source:
                score += _SOURCE_MATCH_BONUS * w

        if score > 0:
            scored.append((score, nid))

    # Sort by score desc, break ties on label length
    scored.sort(key=lambda s: (-s[0], len(nodes_by_id[s[1]].get("label") or s[1]), s[1]))
    return scored


# ============================================================================
# Step 2b: Seed Selection
# ============================================================================

def pick_seed_nodes(scored: list[tuple[float, str]], max_k: int = 3, gap_ratio: float = 0.2) -> list[str]:
    """Select seed nodes from scored results.

    Stops when score drops below (top_score * gap_ratio) to avoid
    high-frequency noise stealing seed slots from dominant matches.
    """
    if not scored:
        return []

    top_score = scored[0][0]
    seeds = []

    for score, nid in scored[:max_k]:
        if seeds and score < top_score * gap_ratio:
            break
        seeds.append(nid)

    return seeds


# ============================================================================
# Step 2c: Graph Traversal (BFS/DFS)
# ============================================================================

def _build_adjacency(G: dict) -> dict[str, list[str]]:
    """Build adjacency list from graph edges."""
    adjacency: dict[str, list[str]] = {}
    edges = G.get("links", G.get("edges", []))

    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source = edge.get("source") or edge.get("_source")
        target = edge.get("target") or edge.get("_target")
        if source and target:
            adjacency.setdefault(source, []).append(target)
            adjacency.setdefault(target, []).append(source)

    return adjacency


def _compute_hub_threshold(G: dict) -> int:
    """Compute p99 degree threshold to avoid expanding through hubs."""
    degrees = []
    adjacency = _build_adjacency(G)

    for neighbors in adjacency.values():
        degrees.append(len(neighbors))

    if not degrees:
        return 50

    degrees_sorted = sorted(degrees)
    p99_idx = int(len(degrees_sorted) * 0.99)
    return max(50, degrees_sorted[p99_idx])


def traverse_graph_bfs(
    G: dict,
    start_nodes: list[str],
    depth: int,
    context_filters: set[str] | None = None,
) -> tuple[set[str], list[tuple[str, str]]]:
    """BFS traversal from start nodes.

    Returns (visited_nodes, edges) where edges are only those connecting
    nodes in visited_nodes and matching context_filters.
    """
    adjacency = _build_adjacency(G)
    hub_threshold = _compute_hub_threshold(G)

    seed_set = set(start_nodes)
    visited: set[str] = set(start_nodes)
    frontier = set(start_nodes)
    edges_seen: list[tuple[str, str]] = []

    for _ in range(depth):
        next_frontier: set[str] = set()
        for n in frontier:
            # Don't expand through hubs (except seeds)
            if n not in seed_set and len(adjacency.get(n, [])) >= hub_threshold:
                continue
            for neighbor in adjacency.get(n, []):
                if neighbor not in visited:
                    next_frontier.add(neighbor)
                    edges_seen.append((n, neighbor))
        visited.update(next_frontier)
        frontier = next_frontier

    return visited, edges_seen


def traverse_graph_dfs(
    G: dict,
    start_nodes: list[str],
    depth: int,
    context_filters: set[str] | None = None,
) -> tuple[set[str], list[tuple[str, str]]]:
    """DFS traversal from start nodes.

    Returns (visited_nodes, edges) where edges are only those connecting
    nodes in visited_nodes and matching context_filters.
    """
    adjacency = _build_adjacency(G)
    hub_threshold = _compute_hub_threshold(G)

    seed_set = set(start_nodes)
    visited: set[str] = set()
    edges_seen: list[tuple[str, str]] = []
    stack = [(n, 0) for n in reversed(start_nodes)]

    while stack:
        node, d = stack.pop()
        if node in visited or d > depth:
            continue
        visited.add(node)

        # Don't expand through hubs (except seeds)
        if node not in seed_set and len(adjacency.get(node, [])) >= hub_threshold:
            continue

        for neighbor in adjacency.get(node, []):
            if neighbor not in visited:
                stack.append((neighbor, d + 1))
                edges_seen.append((node, neighbor))

    return visited, edges_seen


# ============================================================================
# Step 2d: Context Filtering
# ============================================================================

def _filter_edges_by_context(
    G: dict,
    edges: list[tuple[str, str]],
    context_filters: set[str] | None = None,
) -> list[tuple[str, str]]:
    """Filter edges to only those matching context types."""
    if not context_filters:
        return edges

    # Build edge lookup for fast filtering
    edge_lookup: dict[tuple[str, str], dict] = {}
    graph_edges = G.get("links", G.get("edges", []))

    for edge in graph_edges:
        if not isinstance(edge, dict):
            continue
        source = edge.get("source") or edge.get("_source")
        target = edge.get("target") or edge.get("_target")
        if source and target:
            key = (source, target)
            edge_lookup[key] = edge

    # Filter
    filtered = []
    for u, v in edges:
        edge_data = edge_lookup.get((u, v)) or edge_lookup.get((v, u)) or {}
        context = edge_data.get("context")
        if context in context_filters:
            filtered.append((u, v))

    return filtered


# ============================================================================
# Step 2e: Text Rendering
# ============================================================================

def render_subgraph_text(
    G: dict,
    nodes: set[str],
    edges: list[tuple[str, str]],
    seed_nodes: list[str] | None = None,
    token_budget: int = 2000,
) -> str:
    """Render subgraph to text format.

    Format:
    Traversal: BFS depth=3 | Start: [node1, node2] | 42 nodes found

    NODE node1 [src=file.txt loc=L123 type=pill]
    EDGE node1 --relation [confidence]--> node2
    ...
    """
    # Build node lookup
    nodes_by_id: dict[str, dict] = {}
    for node in G.get("nodes", []):
        if isinstance(node, dict):
            nid = node.get("id") or node.get("_id")
            if nid:
                nodes_by_id[nid] = node

    char_budget = token_budget * 3
    lines: list[str] = []

    seed_set = set(seed_nodes or [])
    ordered = [n for n in (seed_nodes or []) if n in nodes] + sorted(
        nodes - seed_set,
        key=lambda n: len(nodes_by_id.get(n, {}).get("neighbors", [])),
        reverse=True,
    )

    # Render nodes
    for nid in ordered:
        node_data = nodes_by_id.get(nid, {})
        label = node_data.get("label", nid)
        source_file = node_data.get("source_file", "")
        source_location = node_data.get("source_location", "")
        node_type = node_data.get("type") or node_data.get("node_type", "")

        line = f"NODE {label} [src={source_file} loc={source_location} type={node_type}]"
        lines.append(line)

    # Render edges
    for u, v in edges:
        if u in nodes and v in nodes:
            u_label = nodes_by_id.get(u, {}).get("label", u)
            v_label = nodes_by_id.get(v, {}).get("label", v)

            # Try to find edge data
            edge_data = {}
            for edge in G.get("links", G.get("edges", [])):
                if isinstance(edge, dict):
                    if (edge.get("source") == u and edge.get("target") == v) or \
                       (edge.get("source") == v and edge.get("target") == u):
                        edge_data = edge
                        break

            relation = edge_data.get("relation", "")
            confidence = edge_data.get("confidence", "")
            context = edge_data.get("context", "")

            conf_str = f" [{confidence}]" if confidence else ""
            context_str = f" context={context}" if context else ""

            line = f"EDGE {u_label} --{relation}{conf_str}{context_str}--> {v_label}"
            lines.append(line)

    output = "\n".join(lines)

    # Truncate if over budget
    if len(output) > char_budget:
        cut_at = output[:char_budget].rfind("\n")
        cut_at = cut_at if cut_at > 0 else char_budget
        total_nodes = sum(1 for l in lines if l.startswith("NODE "))
        shown_nodes = output[:cut_at].count("\nNODE ") + (1 if output.startswith("NODE ") else 0)
        cut_count = total_nodes - shown_nodes
        output = (
            output[:cut_at]
            + f"\n... (truncated — {cut_count} more nodes cut by ~{token_budget}-token budget."
            " Narrow with context_filter or use get_node for a specific symbol)"
        )

    return output


# ============================================================================
# Main Query Entry Point
# ============================================================================

def query_graph(
    G: dict,
    query_params: dict,
) -> dict:
    """Execute full query pipeline.

    Input query_params:
    {
        "question": "what calls error handler?",
        "mode": "bfs",
        "depth": 3,
        "token_budget": 2000,
        "target_node_types": {"pill", "method"},
        "context_filter": {"call", "field"},
        "include_terms": [...],
        "exclude_terms": [...],
        "limit": 20
    }

    Returns:
    {
        "question": "...",
        "mode": "bfs",
        "depth": 3,
        "nodes_found": 42,
        "edges_found": 30,
        "text": "NODE ...\nEDGE ...",
        "seeds": ["node1", "node2"]
    }
    """
    # Step 1: Normalize parameters
    params = normalize_query_params(query_params)

    # Extract terms from question
    question_terms = extract_query_terms(params.get("question", ""))
    include_terms = list(params.get("include_terms", []))
    all_terms = list(set(question_terms + include_terms))

    if not all_terms:
        return {
            "question": params.get("question", ""),
            "nodes_found": 0,
            "edges_found": 0,
            "text": "No query terms found.",
            "seeds": [],
        }

    # Step 2a: Score nodes
    target_types = params.get("target_node_types") or None
    scored = score_nodes(G, all_terms, target_types=target_types)

    if not scored:
        return {
            "question": params.get("question", ""),
            "nodes_found": 0,
            "edges_found": 0,
            "text": "No matching nodes found.",
            "seeds": [],
        }

    # Step 2b: Pick seeds
    seeds = pick_seed_nodes(scored)

    # Step 2c: Traverse graph
    mode = params.get("mode", "bfs")
    depth = params.get("depth", 3)
    context_filters = params.get("context_filter") or None

    if mode == "dfs":
        visited, edges = traverse_graph_dfs(G, seeds, depth, context_filters)
    else:
        visited, edges = traverse_graph_bfs(G, seeds, depth, context_filters)

    # Filter edges by context if specified
    if context_filters:
        edges = _filter_edges_by_context(G, edges, context_filters)

    # Step 2e: Render text
    text = render_subgraph_text(
        G,
        visited,
        edges,
        seed_nodes=seeds,
        token_budget=params.get("token_budget", 2000),
    )

    return {
        "question": params.get("question", ""),
        "mode": mode,
        "depth": depth,
        "nodes_found": len(visited),
        "edges_found": len(edges),
        "text": text,
        "seeds": seeds,
        "visited_nodes": list(visited),
    }
