"""Stage 1 and Stage 2 orchestrator - unified end-to-end pipeline.

Provides a single entry point to execute the complete StoryGraph workflow:
Stage 1: Extract → Prepare → Ingest → Merge
Stage 2: Prepare → Render

This orchestrator handles the full pipeline with automatic progression.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .stage1 import (
    build_stage1_graph,
    claim_agent_batches,
    ingest_stage1,
    ingest_template_requirements,
    merge_stage1,
    prepare_stage1,
)
from .stage2 import (
    claim_stage2_batches,
    ingest_stage2,
    prepare_stage2,
    render_stage2,
    validate_stage2,
)


def execute_complete_pipeline(
    source: str | Path,
    template_dir: str | Path,
    graph_dir: str | Path | None = None,
    config: dict | None = None,
    graphify_repo: str | Path | None = None,
    overwrite_policy: str = "draft",
    selection: str | None = None,
    poll_interval: float = 5.0,
) -> dict:
    """Execute complete StoryGraph pipeline from source to rendered Stage 2 documents.

    This is the unified entry point that orchestrates both Stage 1 and Stage 2.

    Args:
        source: Source code directory to analyze
        template_dir: Directory containing template definitions
        graph_dir: Output directory for graph artifacts (auto-generated if None)
        config: StoryGraph configuration (uses defaults if None)
        graphify_repo: Graphify repository for Stage 1 graph extraction
        overwrite_policy: How to handle existing Stage 2 outputs (draft/backup-and-overwrite/merge)
        selection: Which templates to process (all/changed-or-missing)
        poll_interval: Seconds between polling for agent batch completion

    Returns:
        dict with execution status and results for all stages
    """
    source = Path(source).expanduser().resolve(strict=True)
    template_dir = Path(template_dir).expanduser().resolve(strict=True)
    graph_dir = Path(graph_dir).expanduser().resolve(strict=False) if graph_dir else None

    # Load config if not provided
    if config is None:
        from .config import load_config
        config = load_config(None)

    # Auto-determine graph_dir if not provided
    if graph_dir is None:
        suffix = config.get("graph_dir_suffix", ".storygraph")
        graph_dir = source.parent / f"{source.stem}{suffix}"

    results = {
        "status": "running",
        "stage1": {},
        "stage2": {},
        "pipeline": {
            "source": str(source),
            "template_dir": str(template_dir),
            "graph_dir": str(graph_dir),
            "overwrite_policy": overwrite_policy,
            "selection": selection,
        },
    }

    try:
        # ============================================================================
        # STAGE 1: Extract, Prepare, Ingest, Merge
        # ============================================================================

        # Step 1: Build Stage 1 graph
        results["pipeline"]["step"] = "build-stage1"

        # Add template_dir and graphify_repo to config for build_stage1_graph
        config_with_paths = config.copy()
        if "paths" not in config_with_paths:
            config_with_paths["paths"] = {}
        config_with_paths["paths"]["template_dir"] = str(template_dir)
        if graphify_repo:
            config_with_paths["paths"]["graphify_repo"] = str(graphify_repo)

        build_result = build_stage1_graph(
            source,
            config_with_paths,
        )
        if build_result.get("status") != "success":
            results["status"] = "failed"
            results["stage1"]["build"] = build_result
            return results
        results["stage1"]["build"] = build_result

        # Step 2: Prepare Stage 1
        results["pipeline"]["step"] = "prepare-stage1"
        prepare_result = prepare_stage1(
            source_path=source,
            template_dir=template_dir,
            graph_dir=graph_dir,
            config=config_with_paths,
        )
        if prepare_result.get("status") != "prepared":
            results["status"] = "failed"
            results["stage1"]["prepare"] = prepare_result
            return results
        results["stage1"]["prepare"] = prepare_result

        # Step 3: Ingest template requirements
        results["pipeline"]["step"] = "ingest-template-requirements"
        ingest_req_result = ingest_template_requirements(graph_dir, config)
        if ingest_req_result.get("status") != "ingested":
            results["status"] = "failed"
            results["stage1"]["ingest_requirements"] = ingest_req_result
            return results
        results["stage1"]["ingest_requirements"] = ingest_req_result

        # Step 4: Claim and process Stage 1 agent batches
        results["pipeline"]["step"] = "process-stage1-agents"
        stage1_batches_result = _process_stage1_agent_batches(
            graph_dir, config, poll_interval
        )
        if stage1_batches_result.get("status") != "completed":
            results["status"] = "failed"
            results["stage1"]["process_agents"] = stage1_batches_result
            return results
        results["stage1"]["process_agents"] = stage1_batches_result

        # Step 5: Ingest Stage 1 results
        results["pipeline"]["step"] = "ingest-stage1"
        ingest_stage1_result = ingest_stage1(graph_dir, config)
        if ingest_stage1_result.get("status") != "ingested":
            results["status"] = "failed"
            results["stage1"]["ingest"] = ingest_stage1_result
            return results
        results["stage1"]["ingest"] = ingest_stage1_result

        # Step 6: Merge Stage 1
        results["pipeline"]["step"] = "merge-stage1"
        merge_result = merge_stage1(graph_dir, config)
        if merge_result.get("status") != "merged":
            results["status"] = "failed"
            results["stage1"]["merge"] = merge_result
            return results
        results["stage1"]["merge"] = merge_result

        # ============================================================================
        # STAGE 2: Prepare and Render (fully automated in MVP)
        # ============================================================================

        # Step 7: Prepare Stage 2
        results["pipeline"]["step"] = "prepare-stage2"
        prepare_stage2_result = prepare_stage2(
            graph_dir,
            template_dir,
            config,
            overwrite_policy=overwrite_policy,
            selection=selection,
        )
        if prepare_stage2_result.get("status") != "prepared":
            results["status"] = "failed"
            results["stage2"]["prepare"] = prepare_stage2_result
            return results
        results["stage2"]["prepare"] = prepare_stage2_result

        # Step 8: Process Stage 2 agent batches
        results["pipeline"]["step"] = "process-stage2-agents"
        stage2_batches_result = _process_stage2_agent_batches(
            graph_dir, config, poll_interval
        )
        if stage2_batches_result.get("status") != "completed":
            results["status"] = "failed"
            results["stage2"]["process_agents"] = stage2_batches_result
            return results
        results["stage2"]["process_agents"] = stage2_batches_result

        # Step 9: Ingest Stage 2
        results["pipeline"]["step"] = "ingest-stage2"
        ingest_stage2_result = ingest_stage2(graph_dir, config)
        if ingest_stage2_result.get("status") != "ingested":
            results["status"] = "failed"
            results["stage2"]["ingest"] = ingest_stage2_result
            return results
        results["stage2"]["ingest"] = ingest_stage2_result

        # Step 10: Render Stage 2
        results["pipeline"]["step"] = "render-stage2"
        render_result = render_stage2(graph_dir, config)
        if render_result.get("status") not in ("rendered", "partial"):
            results["status"] = "failed"
            results["stage2"]["render"] = render_result
            return results
        results["stage2"]["render"] = render_result

        # Step 11: Validate Stage 2
        results["pipeline"]["step"] = "validate-stage2"
        validate_result = validate_stage2(graph_dir)
        results["stage2"]["validate"] = validate_result

        # Success!
        results["status"] = "completed"
        results["pipeline"]["completed_at"] = _timestamp()

        return results

    except Exception as e:
        results["status"] = "error"
        results["pipeline"]["error"] = str(e)
        results["pipeline"]["error_type"] = type(e).__name__
        return results


def _process_stage1_agent_batches(
    graph_dir: str | Path,
    config: dict,
    poll_interval: float = 5.0,
) -> dict:
    """Process Stage 1 agent batches (claim and wait for completion).

    This is a simplified version that claims batches but doesn't actually
    wait for agent completion. In a production system, this would poll
    for batch completion and retry.

    Returns:
        dict with status and batch processing results
    """
    graph_dir = Path(graph_dir)
    max_parallel = _agent_capability_limit(
        config,
        stage="stage1",
        lane_id="comprehensive_extraction",
    )

    # Claim initial batches
    claim_result = claim_agent_batches(
        graph_dir=graph_dir,
        phase="lane_extraction",
        limit=max_parallel,
        config=config,
    )

    if claim_result.get("status") != "batches_claimed":
        return {
            "status": "failed",
            "error": "failed_to_claim_batches",
            "detail": claim_result,
        }

    # In MVP, we assume agents complete quickly
    # In production, would poll here for completion
    claimed_count = claim_result.get("claimed_count", 0)

    return {
        "status": "completed",
        "claimed_count": claimed_count,
        "note": "MVP implementation - assumes agent completion",
    }


def _process_stage2_agent_batches(
    graph_dir: str | Path,
    config: dict,
    poll_interval: float = 5.0,
) -> dict:
    """Process Stage 2 agent batches (claim and wait for completion).

    This is a simplified version that claims batches but doesn't actually
    wait for agent completion. In a production system, this would poll
    for batch completion and retry.

    Returns:
        dict with status and batch processing results
    """
    graph_dir = Path(graph_dir)
    max_parallel = _agent_capability_limit(
        config,
        stage="stage2",
        lane_id="template_document",
    )

    # Claim initial batches
    claim_result = claim_stage2_batches(
        graph_dir,
        limit=max_parallel,
        config=config,
    )

    if claim_result.get("status") != "stage2_batches_claimed":
        return {
            "status": "failed",
            "error": "failed_to_claim_batches",
            "detail": claim_result,
        }

    # In MVP, we assume agents complete quickly
    # In production, would poll here for completion
    claimed_count = claim_result.get("claimed_count", 0)

    return {
        "status": "completed",
        "claimed_count": claimed_count,
        "note": "MVP implementation - assumes agent completion",
    }


def _agent_capability_limit(
    config: dict,
    *,
    stage: str,
    lane_id: str,
) -> int:
    try:
        from .config import load_agent_adapters

        registry = load_agent_adapters(config)
        default_agent_type = config.get("agent_platform", {}).get("default_agent_type")
        capability = None
        if isinstance(default_agent_type, str) and default_agent_type:
            capability = registry.resolve_dispatch_capability(
                stage,
                lane_id,
                forced_agent_type=default_agent_type,
            )
        if capability is None:
            capability = registry.resolve_dispatch_capability(stage, lane_id)
        if capability is not None:
            return capability["max_parallel_tasks"]
    except (ImportError, ValueError):
        pass
    return 0


def _timestamp() -> str:
    """Return current timestamp as ISO format string."""
    from datetime import datetime
    return datetime.utcnow().isoformat() + "Z"
