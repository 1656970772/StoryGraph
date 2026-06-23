from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
import shutil

from .output_writer import OutputWriteError, OutputWriter, normalize_relative_output_path
from .stage2_schema import (
    TEMPLATE_EVIDENCE_USAGE,
    TEMPLATE_GAP_REPORT,
    TEMPLATE_RUN_LEDGER,
    resolve_render_target,
    validate_extraction_record,
)
from .stage2_templates import (
    assert_templates_match_stage1_cache,
    discover_stage2_templates,
)
from .stage2_graph_query import query_graph, normalize_query_params
from .stage2_agent_dispatch import (
    prepare_query_task_packet,
    prepare_draft_task_packet,
    prepare_final_task_packet,
    save_draft,
    save_final_markdown,
)


DEFAULT_STAGE2_ARTIFACTS = {
    "task_packet_dir": "intermediate/stage2/task-packets",
    "dispatch_state": "intermediate/stage2/dispatch-state.json",
    "extraction_record_dir": "intermediate/stage2/extraction-records",
}


class Stage2ArtifactError(ValueError):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}")


def prepare_stage2(
    graph_dir: str | Path,
    template_dir: str | Path,
    config: dict,
    *,
    overwrite_policy: str | None = None,
    selection: str | None = None,
) -> dict:
    graph_dir = Path(graph_dir)
    template_dir = Path(template_dir)
    artifacts = _stage2_artifacts(config)
    writer = _writer(graph_dir, config)
    grouping_strategy = config.get("stage2_agent_orchestration", {}).get(
        "grouping_strategy", "by_template_document"
    )
    if grouping_strategy != "by_template_document":
        return {
            "status": "failed",
            "error": "unsupported_stage2_grouping_strategy",
            "grouping_strategy": grouping_strategy,
        }
    resolved_selection = _stage2_selection(config, selection)
    if resolved_selection not in {"all", "changed-or-missing"}:
        return {
            "status": "failed",
            "error": "unsupported_stage2_selection",
            "selection": resolved_selection,
        }
    requirements = _read_json(graph_dir / "requirements" / "template-requirements.json")
    stage1_cache = _read_json(graph_dir / "intermediate" / "stage1-input-cache.json")
    evidence_index = _read_json(graph_dir / "coverage" / "evidence-index.json")
    templates = discover_stage2_templates(template_dir, config)
    template_errors = assert_templates_match_stage1_cache(templates, stage1_cache)
    if template_errors:
        return {"status": "failed", "error": "template_cache_mismatch", "errors": template_errors}

    templates_by_name = {template["template_name"]: template for template in templates}
    categories = requirements.get("categories", []) if isinstance(requirements, dict) else []
    categories_by_template: dict[str, list[dict]] = {}
    for category in categories:
        for template_name in category.get("template_coverage", []):
            if template_name in templates_by_name:
                categories_by_template.setdefault(template_name, []).append(category)

    batches = []
    record_root = artifacts["extraction_record_dir"]
    covered_templates = []
    previous_tasks = (
        _previous_stage2_tasks(graph_dir)
        if resolved_selection == "changed-or-missing"
        else {}
    )
    for template in templates:
        template_name = template["template_name"]
        template_categories = categories_by_template.get(template_name, [])
        if not template_categories:
            continue
        category_ids = [category.get("category_id") for category in template_categories]
        category_ids = [category_id for category_id in category_ids if category_id]
        if not category_ids:
            continue
        if resolved_selection == "changed-or-missing" and not _template_needs_stage2_batch(
            graph_dir,
            template,
            previous_tasks.get(template_name),
            config,
            overwrite_policy or config.get("overwrite_policy", "draft"),
        ):
            continue
        covered_templates.append(template)
        expected_rel_paths = [f"{record_root}/{template_name}/run-001.json"]
        batch_index = len(batches) + 1
        batch_id = _stage2_template_batch_id(batch_index, template)
        batches.append(
            {
                "batch_id": batch_id,
                "grouping_strategy": "by_template_document",
                "category_id": category_ids[0],
                "category_name": template_categories[0].get("category_name"),
                "requirement_categories": [
                    {
                        "category_id": category.get("category_id"),
                        "category_name": category.get("category_name"),
                    }
                    for category in template_categories
                    if category.get("category_id")
                ],
                "agent_role": config.get("stage2_agent_orchestration", {}).get(
                    "agent_role", "stage2-template-document-agent"
                ),
                "status": "pending",
                "templates": [template],
                "requirements": {
                    "required_extraction_targets": _unique_in_order(
                        target
                        for category in template_categories
                        for target in category.get("required_extraction_targets", [])
                    ),
                    "evidence_requirements": _unique_in_order(
                        requirement
                        for category in template_categories
                        for requirement in category.get("evidence_requirements", [])
                    ),
                },
                "evidence_ids": [],  # Evidence lookup now done by agents during query
                "expected_output_rel_paths": expected_rel_paths,
                "expected_output_paths": [
                    str((graph_dir / Path(*rel.split("/"))).resolve())
                    for rel in expected_rel_paths
                ],
                # New: agent selector for dynamic agent selection
                "agent_selector": {
                    "stage": "stage2",
                    "lane_id": "template_document",
                    "required_schema": "stage2-task-packet.v1",
                    "preferred_agents": config.get("stage2_agent_orchestration", {}).get("preferred_agents"),
                },
                "selected_agent_info": None,  # Will be filled by claim_stage2_batches
            }
        )

    for batch in batches:
        packet = dict(batch)
        packet["schema"] = "stage2-task-packet.v1"
        packet["overwrite_policy"] = overwrite_policy or config.get("overwrite_policy", "draft")
        packet["stage2_policy"] = {
            "stage2_categories": config.get("stage2_categories", {}),
            "stage2_output_policy": config.get("stage2_output_policy", {}),
            "stage2_render_policy": config.get("stage2_render_policy", {}),
        }
        writer.write_json(f"{artifacts['task_packet_dir']}/{batch['batch_id']}.json", packet)

    state = _dispatch_state(batches)
    writer.write_json(artifacts["dispatch_state"], state)
    writer.write_json(TEMPLATE_RUN_LEDGER, _template_run_ledger(covered_templates, batches))
    writer.write_json(TEMPLATE_EVIDENCE_USAGE, _template_evidence_usage(batches))
    writer.write_text(TEMPLATE_GAP_REPORT, "# Stage 2 Template Gap Report\n\n")
    _update_manifest_stage2(graph_dir, "prepared")
    return {
        "status": "prepared",
        "batch_count": len(batches),
        "template_count": len(covered_templates),
        "overwrite_policy": overwrite_policy or config.get("overwrite_policy", "draft"),
        "selection": resolved_selection,
    }


def inspect_stage2_dispatch(graph_dir: str | Path, config: dict | None = None) -> dict:
    graph_dir = Path(graph_dir)
    artifacts = _stage2_artifacts(config or {})
    return _read_json(graph_dir / Path(*artifacts["dispatch_state"].split("/")))


def claim_stage2_batches(
    graph_dir: str | Path,
    limit: int,
    config: dict | None = None,
    agent_type: str | None = None,
) -> dict:
    graph_dir = Path(graph_dir)
    artifacts = _stage2_artifacts(config or {})
    state_path = graph_dir / Path(*artifacts["dispatch_state"].split("/"))
    state = _read_json(state_path)
    writer = _writer(graph_dir, config or {})

    # Initialize agent registry if config provided
    agent_registry = None
    if config:
        try:
            from .config import load_agent_adapters
            agent_registry = load_agent_adapters(config)
        except (ImportError, ValueError):
            # Silently continue if agent registry loading fails
            pass

    for batch in state.get("batches", []):
        if batch.get("status") == "running":
            outputs_valid, output_errors = _batch_outputs_valid(
                graph_dir,
                batch,
            )
            if outputs_valid:
                batch["status"] = "completed"
                batch["errors"] = []
            elif output_errors:
                batch["errors"] = output_errors

    # Group batches by agent type for per-agent parallelism window
    running_by_agent = _group_stage2_batches_by_agent(state.get("batches", []))

    # Calculate available slots respecting per-agent max_parallel_tasks
    available_slots = _claim_available_slots_stage2_per_agent(
        limit, running_by_agent, agent_registry, agent_type
    )

    # Count pending batches
    pending_count = sum(
        1 for batch in state.get("batches", []) if batch.get("status") == "pending"
    )
    available_slots = min(available_slots, pending_count)

    claimed = []
    for batch in state.get("batches", []):
        if available_slots <= 0:
            break
        if batch.get("status") == "pending":
            batch["status"] = "running"

            # Apply agent selection to batch
            if agent_registry:
                selected_agent_type = _apply_stage2_agent_selection(
                    batch, agent_registry, agent_type
                )
                if selected_agent_type:
                    batch["selected_agent_type"] = selected_agent_type

            claimed.append(batch)
            available_slots -= 1

    _refresh_state_counts(state)
    writer.write_json(artifacts["dispatch_state"], state)
    return {
        "status": "stage2_batches_claimed",
        "claimed_count": len(claimed),
        "in_flight_count": state["in_flight_count"],
        "pending_count": state["pending_count"],
        "completed_count": state["completed_count"],
        "batches": claimed,
    }


def _apply_stage2_agent_selection(
    batch: dict,
    agent_registry,
    forced_agent_type: str | None = None,
) -> str | None:
    """Apply agent selection to a Stage 2 batch.

    Updates batch with selected_agent_info based on agent selector.
    Returns the selected agent type.
    """
    # Get agent selector from batch
    selector = batch.get("agent_selector")
    if not selector:
        return None

    # Determine which agent to use
    stage = selector.get("stage", "stage2")
    lane_id = selector.get("lane_id", "template_document")
    preferred = selector.get("preferred_agents")

    # Use forced agent_type if provided, otherwise use registry selection
    if forced_agent_type:
        selected_type = forced_agent_type
        adapter = agent_registry.get_adapter(forced_agent_type)
    else:
        result = agent_registry.select_best_adapter(stage, lane_id, preferred)
        if not result:
            return None
        selected_type, adapter = result

    # Update batch with selected agent info
    batch["selected_agent_info"] = {
        "agent_type": selected_type,
        "agent_role": batch.get("agent_role", ""),
        "adapter_version": adapter.get_capabilities().get("version", "1.0.0"),
    }

    return selected_type


def _group_stage2_batches_by_agent(batches: list[dict]) -> dict[str, int]:
    """Count running batches by selected agent type."""
    by_agent = {}
    for batch in batches:
        if batch.get("status") != "running":
            continue
        agent_type = batch.get("selected_agent_type", "unknown")
        by_agent[agent_type] = by_agent.get(agent_type, 0) + 1
    return by_agent


def _claim_available_slots_stage2_per_agent(
    limit: int,
    running_by_agent: dict[str, int],
    agent_registry,
    forced_agent_type: str | None,
) -> int:
    """Calculate available slots respecting per-agent max_parallel_tasks for Stage 2."""
    if not agent_registry:
        # Fallback to simple limit-based
        total_running = sum(running_by_agent.values())
        return max(0, limit - total_running)

    # Determine the agent type that will be used for next batch
    if forced_agent_type:
        adapter = agent_registry.get_adapter(forced_agent_type)
        if not adapter:
            # Fallback
            total_running = sum(running_by_agent.values())
            return max(0, limit - total_running)
        max_parallel = adapter.get_capabilities()["max_parallel_tasks"]
        running_for_agent = running_by_agent.get(forced_agent_type, 0)
    else:
        # For auto-selection, estimate using default agent (codex)
        adapter = agent_registry.get_adapter("codex")
        if not adapter:
            # Fallback
            total_running = sum(running_by_agent.values())
            return max(0, limit - total_running)
        max_parallel = adapter.get_capabilities()["max_parallel_tasks"]
        running_for_agent = sum(running_by_agent.values())

    # Calculate slots: min of (per-agent window, limit)
    per_agent_slots = max(0, max_parallel - running_for_agent)
    return min(per_agent_slots, limit)


def ingest_stage2(graph_dir: str | Path, config: dict) -> dict:
    graph_dir = Path(graph_dir)
    writer = _writer(graph_dir, config)
    state = inspect_stage2_dispatch(graph_dir, config)
    records = []
    errors = []
    for batch in state.get("batches", []):
        for rel_path in batch.get("expected_output_rel_paths", []):
            try:
                normalized_rel_path, path = _resolve_graph_relative_path(
                    graph_dir,
                    rel_path,
                    "expected_output_path",
                )
            except Stage2ArtifactError as exc:
                errors.append(f"{exc.code}:{exc.detail}")
                continue
            if not path.exists():
                errors.append(f"missing_stage2_record:{normalized_rel_path}")
                continue
            try:
                record = _read_json(path)
            except Stage2ArtifactError as exc:
                errors.append(f"{normalized_rel_path}:{exc.code}:{exc.detail}")
                continue
            result = validate_extraction_record(
                record,
                evidence_ids=None,  # Skip evidence validation
                require_document_sections=True,
            )
            if not result.ok:
                errors.extend(f"{normalized_rel_path}:{error}" for error in result.errors)
            else:
                records.append((normalized_rel_path, record))
    if errors:
        return {"status": "failed", "error": "stage2_record_validation_failed", "errors": errors}

    ledger = _read_json(graph_dir / TEMPLATE_RUN_LEDGER)
    tasks_by_name = {
        task.get("template_name"): task
        for task in ledger.get("template_tasks", [])
        if isinstance(task, dict)
    }
    for rel_path, record in records:
        task = tasks_by_name.get(record.get("template_name"))
        if task:
            task["status"] = "completed"
            task["output_record"] = rel_path
            task["errors"] = []
    writer.write_json(TEMPLATE_RUN_LEDGER, ledger)
    writer.write_json(TEMPLATE_EVIDENCE_USAGE, _records_evidence_usage(records))
    writer.write_text(TEMPLATE_GAP_REPORT, _gap_report(records))
    _update_manifest_stage2(graph_dir, "ingested")
    return {"status": "ingested", "record_count": len(records)}


def render_stage2(graph_dir: str | Path, config: dict) -> dict:
    """Render Stage 2 documents using agent-driven pipeline.

    New pipeline (agent-driven):
    1. Query Agent: Generates query parameters for each template
    2. Query Engine: Executes Graphify-style query on the graph
    3. Draft Agent: Generates structured draft with source annotations
    4. Final Agent: Renders clean markdown from draft
    """
    graph_dir = Path(graph_dir)
    writer = _writer(graph_dir, config)
    ledger = _read_json(graph_dir / TEMPLATE_RUN_LEDGER)
    graph_json_path = graph_dir / "graphify-out" / "graph.json"

    if not graph_json_path.exists():
        return {
            "status": "failed",
            "error": "graph_json_missing",
            "detail": "Cannot render Stage 2 without graph.json"
        }

    graph = _read_json(graph_json_path)
    rendered = []
    record_errors = []

    for task in ledger.get("template_tasks", []):
        rel_path = task.get("output_record")
        if task.get("status") != "completed" or not rel_path:
            continue

        try:
            normalized_rel_path, record_path = _resolve_graph_relative_path(
                graph_dir,
                rel_path,
                "output_record_path",
            )
            record = _read_json(record_path)
        except Stage2ArtifactError as exc:
            record_errors.append(f"{exc.code}:{exc.detail}")
            continue

        template_name = record.get("template_name")

        # Find template definition
        template_def = None
        for task_def in ledger.get("template_tasks", []):
            if task_def.get("template_name") == template_name:
                template_def = task_def
                break

        if not template_def:
            record_errors.append(f"template_definition_missing:{template_name}")
            continue

        overwrite_policy = record.get("overwrite_policy", config.get("overwrite_policy", "draft"))
        decision = resolve_render_target(
            graph_dir,
            _novel_dir(graph_dir),
            template_name,
            config.get("stage2_output_policy", {}),
            overwrite_policy,
        )

        if overwrite_policy == "merge":
            record_errors.append(f"stage2_merge_contract_required:{template_name}")
            continue

        # Generate query parameters (Query Agent would do this, but we approximate)
        query_params = _generate_query_params_from_record(record, config)

        # Execute query on graph
        try:
            query_result = query_graph(graph, query_params)
        except Exception as e:
            record_errors.append(f"query_failed:{template_name}:{str(e)}")
            continue

        # In full implementation, Draft and Final agents would run here.
        # For now, we generate markdown from the query result.
        # This is a simplified version that bypasses agent dispatch for MVP.

        if overwrite_policy == "backup-and-overwrite":
            text = _render_markdown_from_query_result(query_result, template_def, record)
            write_error = _write_formal_stage2_document(
                graph_dir,
                _novel_dir(graph_dir),
                decision,
                text,
            )
            if write_error:
                record_errors.append(f"render_failed:{template_name}:{write_error.get('error')}")
                continue
            relative_target = _display_rendered_path(graph_dir, Path(decision["target_path"]))
        else:
            text = _render_markdown_from_query_result(query_result, template_def, record)
            relative_target = _relative_to_graph(graph_dir, Path(decision["target_path"]))
            writer.write_text(relative_target, text)

        rendered.append(relative_target)

    if record_errors:
        return {
            "status": "partial",
            "error": "stage2_render_errors",
            "errors": record_errors,
            "rendered_count": len(rendered),
            "rendered": rendered,
        }

    if not rendered:
        return {"status": "failed", "error": "no_stage2_records_to_render", "rendered_count": 0}

    _update_manifest_stage2(graph_dir, "rendered")
    return {"status": "rendered", "rendered_count": len(rendered), "rendered": rendered}


def validate_stage2(graph_dir: str | Path) -> dict:
    graph_dir = Path(graph_dir)
    errors = []
    try:
        ledger = _read_json(graph_dir / TEMPLATE_RUN_LEDGER)
    except FileNotFoundError:
        return {"ok": False, "errors": ["template_run_ledger_missing"]}
    except Stage2ArtifactError as exc:
        return {"ok": False, "errors": [f"template_run_ledger_invalid:{exc.code}:{exc.detail}"]}

    for task in ledger.get("template_tasks", []):
        template_name = task.get("template_name")
        if task.get("status") != "completed":
            errors.append(f"template_not_completed:{template_name}")
            continue
        output_record = task.get("output_record")
        if not output_record:
            errors.append(f"output_record_required:{template_name}")
            continue
        try:
            normalized_output_record, record_path = _resolve_graph_relative_path(
                graph_dir,
                output_record,
                "output_record_path",
            )
        except Stage2ArtifactError as exc:
            errors.append(f"{exc.code}:{exc.detail}")
            continue
        if not record_path.exists():
            errors.append(f"output_record_missing:{normalized_output_record}")
            continue
        try:
            record = _read_json(record_path)
        except Stage2ArtifactError as exc:
            errors.append(f"{normalized_output_record}:{exc.code}:{exc.detail}")
            continue
        result = validate_extraction_record(
            record,
            evidence_ids=None,  # Skip evidence validation
            require_document_sections=True,
        )
        if not result.ok:
            errors.extend(f"{normalized_output_record}:{error}" for error in result.errors)
    return {"ok": not errors, "errors": errors}


def _stage2_artifacts(config: dict) -> dict:
    artifacts = dict(DEFAULT_STAGE2_ARTIFACTS)
    artifacts.update(config.get("stage2_artifacts", {}))
    return {
        key: normalize_relative_output_path(value)
        for key, value in artifacts.items()
    }


def _stage2_selection(config: dict, selection: str | None) -> str:
    if isinstance(selection, str) and selection:
        return selection
    policy = config.get("stage2_incremental_policy")
    if isinstance(policy, dict):
        configured = policy.get("selection")
        if isinstance(configured, str) and configured:
            return configured
    return "all"


def _previous_stage2_tasks(graph_dir: Path) -> dict[str, dict]:
    ledger_path = graph_dir / TEMPLATE_RUN_LEDGER
    if not ledger_path.exists():
        return {}
    try:
        ledger = _read_json(ledger_path)
    except (FileNotFoundError, Stage2ArtifactError):
        return {}
    tasks = ledger.get("template_tasks")
    if not isinstance(tasks, list):
        return {}
    return {
        task["template_name"]: task
        for task in tasks
        if isinstance(task, dict) and isinstance(task.get("template_name"), str)
    }


def _template_needs_stage2_batch(
    graph_dir: Path,
    template: dict,
    previous_task: dict | None,
    config: dict,
    overwrite_policy: str,
) -> bool:
    if not isinstance(previous_task, dict):
        return True
    if previous_task.get("status") != "completed":
        return True
    if previous_task.get("template_sha256") != template.get("template_sha256"):
        return True
    output_record = previous_task.get("output_record")
    if not isinstance(output_record, str) or not output_record:
        return True
    try:
        _normalized, record_path = _resolve_graph_relative_path(
            graph_dir,
            output_record,
            "output_record_path",
        )
    except Stage2ArtifactError:
        return True
    if not record_path.exists():
        return True
    if not _stage2_render_target_exists(
        graph_dir,
        template.get("template_name"),
        config,
        overwrite_policy,
    ):
        return True
    return False


def _stage2_render_target_exists(
    graph_dir: Path,
    template_name: object,
    config: dict,
    overwrite_policy: str,
) -> bool:
    if not isinstance(template_name, str) or not template_name:
        return False
    if overwrite_policy != "draft":
        return False
    output_policy = config.get("stage2_output_policy", {})
    default_dir = output_policy.get("default_dir", "drafts")
    if not isinstance(default_dir, str) or not default_dir:
        return False
    return (graph_dir / default_dir / f"{template_name}.md").exists()


def _stage2_template_batch_id(index: int, template: dict) -> str:
    payload = json.dumps(
        {
            "template_name": template.get("template_name"),
            "template_file": template.get("template_file"),
            "template_sha256": template.get("template_sha256"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"template-batch-{index:04d}-{digest}"


def _unique_in_order(values) -> list:
    seen = set()
    unique = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _writer(graph_dir: Path, config: dict) -> OutputWriter:
    managed = list(config.get("writer_policy", {}).get("managed_outputs", []))
    output_policy = config.get("stage2_output_policy", {})
    default_dir = output_policy.get("default_dir")
    if default_dir:
        managed.append(f"{default_dir}/*.md")
    for path in (
        "intermediate/stage2/task-packets/*.json",
        "intermediate/stage2/dispatch-state.json",
        "intermediate/stage2/extraction-records/*/*.json",
        TEMPLATE_RUN_LEDGER,
        TEMPLATE_EVIDENCE_USAGE,
        TEMPLATE_GAP_REPORT,
    ):
        if path not in managed:
            managed.append(path)
    return OutputWriter(graph_dir, managed)


def _read_json(path: Path):
    path = Path(path)
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        raise Stage2ArtifactError("json_utf8_bom", str(path))
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Stage2ArtifactError("json_utf8_decode_failed", f"{path}:{exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise Stage2ArtifactError("json_parse_failed", f"{path}:{exc.msg}") from exc


def _dispatch_state(batches: list[dict]) -> dict:
    state = {"schema": "stage2-dispatch-state.v1", "batches": batches}
    _refresh_state_counts(state)
    return state


def _refresh_state_counts(state: dict) -> None:
    state["pending_count"] = _count_status(state, "pending")
    state["in_flight_count"] = _count_status(state, "running")
    state["completed_count"] = _count_status(state, "completed")


def _count_status(state: dict, status: str) -> int:
    return sum(1 for batch in state.get("batches", []) if batch.get("status") == status)


def _batch_outputs_valid(
    graph_dir: Path,
    batch: dict,
) -> tuple[bool, list[str]]:
    rel_paths = batch.get("expected_output_rel_paths", [])
    if not rel_paths:
        return False, ["expected_output_rel_paths_required"]
    errors = []
    any_missing = False
    for rel_path in rel_paths:
        try:
            normalized_rel_path, path = _resolve_graph_relative_path(
                graph_dir,
                rel_path,
                "expected_output_path",
            )
        except Stage2ArtifactError as exc:
            errors.append(f"{exc.code}:{exc.detail}")
            continue
        if not path.exists():
            any_missing = True
            continue
        try:
            record = _read_json(path)
        except Stage2ArtifactError as exc:
            errors.append(f"{normalized_rel_path}:{exc.code}:{exc.detail}")
            continue
        result = validate_extraction_record(
            record,
            evidence_ids=None,  # Skip evidence validation
            require_document_sections=True,
        )
        if not result.ok:
            errors.extend(f"{normalized_rel_path}:{error}" for error in result.errors)
    return not any_missing and not errors, errors


def _resolve_graph_relative_path(
    graph_dir: Path,
    relative_path: str | Path,
    label: str,
) -> tuple[str, Path]:
    try:
        normalized = normalize_relative_output_path(relative_path)
    except OutputWriteError as exc:
        raise Stage2ArtifactError(f"{label}_invalid", exc.path) from exc
    graph_root = Path(graph_dir).resolve()
    target = (graph_root / Path(*normalized.split("/"))).resolve()
    if not _is_within(target, graph_root):
        raise Stage2ArtifactError(f"{label}_invalid", str(relative_path))
    return normalized, target


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _write_formal_stage2_document(
    graph_dir: Path,
    novel_dir: Path,
    decision: dict,
    text: str,
) -> dict | None:
    graph_root = Path(graph_dir).resolve()
    novel_root = Path(novel_dir).resolve()
    target = Path(decision["target_path"]).resolve()
    if _is_within(target, graph_root) or not _is_within(target, novel_root):
        return {
            "error": "formal_target_path_invalid",
            "target_path": str(target),
        }
    backup_path = decision.get("backup_path")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and backup_path:
            backup = Path(backup_path).resolve()
            if not _is_within(backup, novel_root):
                return {
                    "error": "formal_backup_path_invalid",
                    "target_path": str(target),
                    "backup_path": str(backup),
                }
            shutil.copy2(target, backup)
        target.write_text(text, encoding="utf-8")
    except OSError as exc:
        return {
            "error": "formal_document_write_failed",
            "target_path": str(target),
            "detail": str(exc),
        }
    return None


def _template_run_ledger(templates: list[dict], batches: list[dict]) -> dict:
    batch_by_template = {}
    for batch in batches:
        for template in batch.get("templates", []):
            batch_by_template[template["template_name"]] = batch["batch_id"]
    return {
        "schema": "template-run-ledger.v1",
        "artifact_paths": {
            "template_run_ledger": TEMPLATE_RUN_LEDGER,
            "template_evidence_usage": TEMPLATE_EVIDENCE_USAGE,
            "template_gap_report": TEMPLATE_GAP_REPORT,
        },
        "template_tasks": [
            {
                "template_name": template["template_name"],
                "template_file": template["template_file"],
                "template_path": template.get("template_path"),
                "template_sha256": template.get("template_sha256"),
                "status": "pending",
                "batch_id": batch_by_template.get(template["template_name"]),
                "output_record": None,
                "errors": [],
            }
            for template in templates
        ],
    }


def _template_evidence_usage(batches: list[dict]) -> dict:
    return {
        "schema": "template-evidence-usage.v1",
        "artifact_path": TEMPLATE_EVIDENCE_USAGE,
        "usage": [
            {
                "batch_id": batch["batch_id"],
                "category_id": batch["category_id"],
                "evidence_ids": batch.get("evidence_ids", []),
            }
            for batch in batches
        ],
    }


def _records_evidence_usage(records: list[tuple[str, dict]]) -> dict:
    usage = []
    for rel_path, record in records:
        for section in record.get("document_sections", []):
            usage.append(
                {
                    "template_name": record.get("template_name"),
                    "output_record": rel_path,
                    "section": section.get("heading"),
                    "evidence_ids": section.get("evidence_ids", []),
                    "requirement_ids": section.get("requirement_ids", []),
                }
            )
    return {
        "schema": "template-evidence-usage.v1",
        "artifact_path": TEMPLATE_EVIDENCE_USAGE,
        "usage": usage,
    }


def _gap_report(records: list[tuple[str, dict]]) -> str:
    lines = ["# Stage 2 Template Gap Report", ""]
    for _, record in records:
        gaps = list(record.get("gap_items") or [])
        gaps.extend(item.get("content", "") for item in record.get("not_found_items", []))
        if not gaps:
            continue
        lines.extend([f"## {record.get('template_name')}", ""])
        for gap in gaps:
            if gap:
                lines.append(f"- {gap}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _stage1_review_status(graph_dir: Path) -> str | None:
    graph_path = graph_dir / "graphify-out" / "graph.json"
    if not graph_path.exists():
        return None
    graph = _read_json(graph_path)
    metadata = graph.get("metadata") if isinstance(graph, dict) else None
    if isinstance(metadata, dict):
        return metadata.get("review_status")
    return None


def _read_stage2_template_markdown(task: dict, record: dict) -> str | None:
    del record
    template_path = task.get("template_path")
    if not template_path:
        return None
    path = Path(template_path)
    if not path.is_file():
        return None
    expected_sha256 = task.get("template_sha256")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if expected_sha256 and sha256(text.encode("utf-8")).hexdigest() != expected_sha256:
        return None
    return text


def _novel_dir(graph_dir: Path) -> Path:
    manifest_path = graph_dir / "manifest.json"
    if manifest_path.exists():
        manifest = _read_json(manifest_path)
        source_path = manifest.get("source_path")
        if source_path:
            return Path(source_path).parent
    return graph_dir.parent


def _relative_to_graph(graph_dir: Path, target: Path) -> str:
    return target.resolve().relative_to(graph_dir.resolve()).as_posix()


def _display_rendered_path(graph_dir: Path, target: Path) -> str:
    try:
        return _relative_to_graph(graph_dir, target)
    except ValueError:
        return Path(os.path.relpath(target.resolve(), graph_dir.resolve())).as_posix()


def _update_manifest_stage2(graph_dir: Path, status: str) -> None:
    path = graph_dir / "manifest.json"
    if not path.exists():
        return
    manifest = _read_json(path)
    stage_status = manifest.get("stage_status")
    if not isinstance(stage_status, dict):
        stage_status = {}
    stage_status["stage2"] = status
    manifest["stage_status"] = stage_status
    OutputWriter(graph_dir, ["manifest.json"]).write_json("manifest.json", manifest)


def _generate_query_params_from_record(record: dict, config: dict) -> dict:
    """Generate query parameters from Stage 2 record (simplified version).

    In full implementation, Query Agent would generate these.
    This simplified version creates basic parameters from template hints.
    """
    template_name = record.get("template_name", "")

    # Extract query hints from record or use defaults
    query_hints = record.get("query_hints", {})
    node_types = query_hints.get("target_node_types", [])
    context_types = query_hints.get("context_filter", [])

    return {
        "question": template_name,
        "mode": "bfs",
        "depth": 3,
        "token_budget": 2000,
        "target_node_types": node_types,
        "context_filter": context_types,
        "limit": 30,
    }


def _render_markdown_from_query_result(query_result: dict, template_def: dict, record: dict) -> str:
    """Render markdown from query result (simplified version).

    In full implementation, Final Agent would render clean markdown.
    This simplified version generates basic markdown from query output.
    """
    template_name = template_def.get("template_name", "Unknown")
    query_text = query_result.get("text", "")
    nodes_found = query_result.get("nodes_found", 0)

    lines = [
        f"# {template_name}",
        "",
        f"> Query found {nodes_found} relevant nodes",
        "",
        "## Query Results",
        "",
        "```",
        query_text,
        "```",
        "",
    ]

    return "\n".join(lines)
