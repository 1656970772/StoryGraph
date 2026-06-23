"""Stage 2 agent dispatch system - Query → Draft → Final pipeline.

Orchestrates agent-driven workflow:
- Stage 2a: Query agents (parameter generation + graph query)
- Stage 2b: Draft agents (extract & structure + source annotation)
- Stage 2c: Final agents (render markdown + no source annotation)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# ============================================================================
# Query Agent Dispatch (Step 1: Parameter Generation)
# ============================================================================

def prepare_query_task_packet(
    template: dict,
    graph_dir: Path,
) -> dict:
    """Prepare task packet for query agent.

    Query agent receives template definition and generates query parameters
    for the specific template's requirements.
    """
    template_name = template.get("template_name", "")
    template_path = template.get("template_path", "")

    # Extract query hints from template
    query_hints = template.get("query_hints", {})
    node_types = query_hints.get("target_node_types", [])
    context_types = query_hints.get("context_filter", [])

    return {
        "task_type": "stage2_query",
        "template_name": template_name,
        "template_path": template_path,
        "template_definition": template,
        "graph_dir": str(graph_dir),
        "instructions": f"""
You are a StoryGraph query parameter generator.

Template: {template_name}

Based on the template definition provided, your task is to generate query parameters
that will find relevant nodes and relationships in the knowledge graph.

Generate a JSON object with these fields:
{{
    "question": "natural language query that captures template intent",
    "mode": "bfs or dfs",
    "depth": 1-6,
    "token_budget": 1000-5000,
    "target_node_types": {node_types},
    "context_filter": {context_types},
    "include_terms": ["term1", "term2", ...],
    "exclude_terms": ["term1", "term2", ...],
    "limit": 30
}}

Guidelines:
1. The question should be specific to what the template is looking for
2. Use BFS for broad context discovery
3. Use DFS to trace specific relationships/hierarchies
4. Include terms that are central to the template domain
5. Exclude terms that would bring in noise
6. target_node_types should match the entity types the template cares about
7. context_filter should focus on relevant relationship types
""",
    }


def dispatch_query_agent(
    template: dict,
    graph_dir: Path,
    agent_tool_fn: Any | None = None,
) -> dict:
    """Dispatch a query parameter generation agent.

    Returns the agent job ID or result (depending on execution model).
    """
    task_packet = prepare_query_task_packet(template, graph_dir)

    if agent_tool_fn is None:
        # Dry run: just return the task packet
        return {
            "status": "pending",
            "task_type": "query_agent",
            "template_name": task_packet["template_name"],
            "task_packet": task_packet,
        }

    # Actual dispatch: call agent tool
    result = agent_tool_fn(
        description=f"Generate query parameters for template: {task_packet['template_name']}",
        prompt=task_packet["instructions"],
    )

    return {
        "status": "dispatched",
        "task_type": "query_agent",
        "template_name": task_packet["template_name"],
        "agent_result": result,
    }


# ============================================================================
# Draft Agent Dispatch (Step 3: Query Results → Draft)
# ============================================================================

def prepare_draft_task_packet(
    template: dict,
    query_result: dict,
    graph_dir: Path,
) -> dict:
    """Prepare task packet for draft generation agent.

    Draft agent receives query results and template definition,
    then generates structured draft with source annotations.
    """
    template_name = template.get("template_name", "")

    # Read template markdown for context
    template_path = template.get("template_path")
    template_md = ""
    if template_path:
        try:
            template_md = Path(template_path).read_text(encoding="utf-8")
        except Exception:
            pass

    return {
        "task_type": "stage2_draft",
        "template_name": template_name,
        "template_definition": template,
        "template_markdown": template_md,
        "query_result": query_result,
        "graph_dir": str(graph_dir),
        "instructions": f"""
You are a StoryGraph draft generation agent.

Template: {template_name}

Your task is to take the query results and generate a structured draft
with source annotations.

## Input
- Template definition (what fields to extract)
- Query results (nodes and edges from the graph)
- Original template markdown (structure reference)

## Output
Generate a JSON array of draft cases:
[
  {{
    "case_id": "unique_id",
    "title": "case title",
    "fields": {{
      "field1": "value with context",
      "field2": "...",
      ...
    }},
    "source_nodes": ["node_id_1", "node_id_2"],
    "source_evidence": ["evidence_id_1", ...],
    "coverage": "complete|partial|missing",
    "notes": "any special notes"
  }},
  ...
]

Guidelines:
1. Each case should map to one or more query result nodes
2. Extract fields based on the template definition
3. Annotate every field with source node IDs
4. Mark coverage as complete if all template fields found, partial if some missing
5. Include evidence IDs that support each case
6. Preserve all source information for traceability
7. Do NOT write the final prose yet - just structure the data
""",
    }


def dispatch_draft_agent(
    template: dict,
    query_result: dict,
    graph_dir: Path,
    agent_tool_fn: Any | None = None,
) -> dict:
    """Dispatch a draft generation agent."""
    task_packet = prepare_draft_task_packet(template, query_result, graph_dir)

    if agent_tool_fn is None:
        return {
            "status": "pending",
            "task_type": "draft_agent",
            "template_name": task_packet["template_name"],
            "task_packet": task_packet,
        }

    result = agent_tool_fn(
        description=f"Generate draft for template: {task_packet['template_name']}",
        prompt=task_packet["instructions"],
    )

    return {
        "status": "dispatched",
        "task_type": "draft_agent",
        "template_name": task_packet["template_name"],
        "agent_result": result,
    }


def save_draft(
    template_name: str,
    draft_content: list[dict],
    graph_dir: Path,
) -> Path:
    """Save draft to graph_dir/drafts/<template>.draft.json."""
    draft_dir = graph_dir / "drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)

    draft_file = draft_dir / f"{template_name}.draft.json"
    draft_file.write_text(
        json.dumps(
            {
                "template_name": template_name,
                "cases": draft_content,
                "version": "1.0",
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return draft_file


# ============================================================================
# Final Agent Dispatch (Step 4: Draft → Final Markdown)
# ============================================================================

def prepare_final_task_packet(
    template: dict,
    draft_content: list[dict],
    graph_dir: Path,
) -> dict:
    """Prepare task packet for final markdown generation agent.

    Final agent receives draft and original template,
    then generates clean markdown without source annotations.
    """
    template_name = template.get("template_name", "")

    # Read template markdown
    template_path = template.get("template_path")
    template_md = ""
    if template_path:
        try:
            template_md = Path(template_path).read_text(encoding="utf-8")
        except Exception:
            pass

    # Get render policy
    render_policy = template.get("render_policy", {})
    dedup_strategy = render_policy.get("dedup_strategy", "by_label")
    merge_strategy = render_policy.get("merge_strategy", "conservative")
    sort_strategy = render_policy.get("sort_strategy", "by_relevance")

    return {
        "task_type": "stage2_final",
        "template_name": template_name,
        "template_definition": template,
        "template_markdown": template_md,
        "draft_cases": draft_content,
        "render_policy": {
            "dedup_strategy": dedup_strategy,
            "merge_strategy": merge_strategy,
            "sort_strategy": sort_strategy,
        },
        "instructions": f"""
You are a StoryGraph final document generation agent.

Template: {template_name}

Your task is to take the draft cases and generate a clean, final markdown document
that follows the template structure.

## Input
- Template markdown (structure, sections, format)
- Draft cases (structured data with source annotations)
- Render policy (dedup, merge, sort strategies)

## Output
Generate clean Markdown text WITHOUT source annotations.
Format should follow the original template structure.

## Process
1. Dedup: Remove duplicate cases (same label or very similar content)
   - Strategy: {dedup_strategy}
2. Merge: Combine related cases if render policy says so
   - Strategy: {merge_strategy}
3. Sort: Order cases by relevance
   - Strategy: {sort_strategy}
4. Render: Write final markdown following template structure

Guidelines:
1. Do NOT include source node IDs, evidence IDs, or coverage markers
2. Write only the final prose/cases
3. Follow the template markdown structure exactly
4. Each case should be compelling and complete
5. Remove any placeholder text or TODO markers
6. Ensure consistency in formatting and tone
7. If some fields are missing from draft, omit that case or mark clearly

Return only the final markdown text, nothing else.
""",
    }


def dispatch_final_agent(
    template: dict,
    draft_content: list[dict],
    graph_dir: Path,
    agent_tool_fn: Any | None = None,
) -> dict:
    """Dispatch a final markdown generation agent."""
    task_packet = prepare_final_task_packet(template, draft_content, graph_dir)

    if agent_tool_fn is None:
        return {
            "status": "pending",
            "task_type": "final_agent",
            "template_name": task_packet["template_name"],
            "task_packet": task_packet,
        }

    result = agent_tool_fn(
        description=f"Generate final markdown for template: {task_packet['template_name']}",
        prompt=task_packet["instructions"],
    )

    return {
        "status": "dispatched",
        "task_type": "final_agent",
        "template_name": task_packet["template_name"],
        "agent_result": result,
    }


def save_final_markdown(
    template_name: str,
    markdown_content: str,
    graph_dir: Path,
) -> Path:
    """Save final markdown to graph_dir/generated/<template>.md."""
    final_dir = graph_dir / "generated"
    final_dir.mkdir(parents=True, exist_ok=True)

    final_file = final_dir / f"{template_name}.md"
    final_file.write_text(markdown_content, encoding="utf-8")

    return final_file


# ============================================================================
# Batch Dispatch (High-level coordination)
# ============================================================================

def prepare_stage2_query_batches(
    templates: list[dict],
    graph_dir: Path,
) -> list[dict]:
    """Prepare all query task packets for batch dispatch."""
    batches = []
    for template in templates:
        batches.append(prepare_query_task_packet(template, graph_dir))
    return batches


def prepare_stage2_draft_batches(
    templates: list[dict],
    query_results: dict[str, dict],  # template_name -> query_result
    graph_dir: Path,
) -> list[dict]:
    """Prepare all draft task packets for batch dispatch."""
    batches = []
    for template in templates:
        template_name = template.get("template_name", "")
        query_result = query_results.get(template_name)
        if query_result:
            batches.append(prepare_draft_task_packet(template, query_result, graph_dir))
    return batches


def prepare_stage2_final_batches(
    templates: list[dict],
    draft_results: dict[str, list[dict]],  # template_name -> draft_cases
    graph_dir: Path,
) -> list[dict]:
    """Prepare all final task packets for batch dispatch."""
    batches = []
    for template in templates:
        template_name = template.get("template_name", "")
        draft_cases = draft_results.get(template_name, [])
        if draft_cases:
            batches.append(prepare_final_task_packet(template, draft_cases, graph_dir))
    return batches


# ============================================================================
# Results Collection
# ============================================================================

def collect_query_results(
    agent_results: list[dict],
) -> dict[str, dict]:
    """Collect query agent results into template_name -> query_params mapping."""
    results = {}
    for result in agent_results:
        if result.get("task_type") == "query_agent":
            template_name = result.get("template_name")
            agent_result = result.get("agent_result")
            if template_name and agent_result:
                # Parse JSON from agent output if needed
                if isinstance(agent_result, str):
                    try:
                        agent_result = json.loads(agent_result)
                    except json.JSONDecodeError:
                        pass
                results[template_name] = agent_result
    return results


def collect_draft_results(
    agent_results: list[dict],
) -> dict[str, list[dict]]:
    """Collect draft agent results into template_name -> draft_cases mapping."""
    results = {}
    for result in agent_results:
        if result.get("task_type") == "draft_agent":
            template_name = result.get("template_name")
            agent_result = result.get("agent_result")
            if template_name and agent_result:
                # Parse JSON from agent output if needed
                if isinstance(agent_result, str):
                    try:
                        agent_result = json.loads(agent_result)
                    except json.JSONDecodeError:
                        pass
                # Handle nested structure
                if isinstance(agent_result, dict):
                    draft_cases = agent_result.get("cases", [agent_result])
                else:
                    draft_cases = agent_result if isinstance(agent_result, list) else [agent_result]
                results[template_name] = draft_cases
    return results


def collect_final_results(
    agent_results: list[dict],
) -> dict[str, str]:
    """Collect final agent results into template_name -> markdown mapping."""
    results = {}
    for result in agent_results:
        if result.get("task_type") == "final_agent":
            template_name = result.get("template_name")
            agent_result = result.get("agent_result")
            if template_name and agent_result:
                # Result should be markdown string
                results[template_name] = agent_result
    return results
