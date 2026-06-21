from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .agent_ledger import (
    make_agent_run_record,
    make_lane_agent_record,
    validate_single_writer,
)
from .canonical_writer import build_canonical_graph_from_bundles
from .chunk_bundles import make_chunk_bundle, validate_bundle_ready_for_merge
from .coverage import make_chunk_ledger, write_coverage_outputs
from .graphify_adapter import GraphifyAdapter
from .lane_outputs import validate_lane_output
from .manifest import write_manifest
from .output_writer import OutputWriteError, OutputWriter, normalize_relative_output_path
from .paths import NovelContext, file_sha256
from .state import compute_stage1_input_hash
from .template_requirements import validate_template_requirements_payload
from .templates import discover_templates


DEFAULT_STAGE1_ARTIFACTS = {
    "requirements": "requirements/template-requirements.json",
    "agent_dispatch_plan": "intermediate/agent-dispatch-plan.json",
    "task_packet_dir": "intermediate/task-packets",
    "chunk_text_dir": "intermediate/chunks",
    "lane_output_dir": "intermediate/lane-outputs",
    "reviewed_bundle_dir": "intermediate/reviewed-bundles",
    "merge_queue": "intermediate/merge-queue.json",
    "review_findings": "coverage/review-findings.json",
    "canonical_graph": "graphify-out/graph.json",
    "agent_run_ledger": "coverage/agent-run-ledger.json",
    "template_requirements_part_dir": "intermediate/template-requirements-parts",
}

def prepare_stage1(
    *,
    source_path: str | Path,
    template_dir: str | Path,
    graph_dir: str | Path,
    config: dict,
) -> dict:
    active_config = _config_with_paths(config, template_dir)
    try:
        ctx = _novel_context(source_path, graph_dir)
    except (OSError, ValueError) as exc:
        return _failure_response(None, _error("source_unreadable", exc), False)

    try:
        discovery = _discover_templates(active_config, template_dir)
        lanes = _configured_lanes(active_config)
        lane_ids = _lane_ids(lanes)
        required_lane_ids = _required_lane_ids(lanes)
        config_hash = stable_stage_input_hash(ctx, active_config, discovery.templates)
        _remove_graphify_artifacts(ctx.graph_dir)
        manifest_path = write_manifest(
            ctx,
            config_hash=config_hash,
            graphify_source=str(active_config.get("paths", {}).get("graphify_repo")),
        )
        writer = OutputWriter(ctx.graph_dir, _managed_outputs(active_config))
        artifacts = _artifact_paths(active_config)
        chunks = make_chunk_ledger(
            ctx.source_path,
            active_config.get("chunk_strategy", {}),
            processor="storygraph-stage1",
            target_lane_ids=lane_ids,
            required_lane_ids=required_lane_ids,
        )
        chunks = _write_chunk_texts(writer, chunks, artifacts["chunk_text_dir"])
        template_requirements_packets = _build_template_requirements_task_packets(
            ctx.source_path,
            chunks,
            discovery.templates,
            artifacts,
            active_config,
        )
        packets = _build_task_packets(
            ctx.source_path,
            chunks,
            lanes,
            artifacts,
            active_config,
        )
        for template_requirements_packet in template_requirements_packets:
            writer.write_json(
                template_requirements_packet["task_packet_path"],
                template_requirements_packet,
            )
        for packet in packets:
            writer.write_json(packet["task_packet_path"], packet)

        agent_runs = _pending_agent_run_ledger(
            chunks,
            template_requirements_packets,
            packets,
            artifacts,
        )
        single_writer = validate_single_writer(agent_runs)
        if not single_writer.ok:
            errors = [{"code": "single_writer_conflict", "detail": item} for item in single_writer.errors]
            write_coverage_outputs(
                writer,
                chunks,
                [],
                [],
                _failed_agent_runs(agent_runs, "single_writer_conflict", errors),
                [f"- single_writer_conflict: {item}" for item in single_writer.errors],
            )
            _update_manifest_stage(manifest_path, "failed")
            return _stage_result(
                "failed",
                ctx.graph_dir,
                discovery.warnings,
                ["single_writer_conflict"],
                errors[0],
                next_action=None,
            )

        dispatch_plan = _build_agent_dispatch_plan(
            template_requirements_packets,
            packets,
            artifacts,
            active_config,
        )
        writer.write_json(artifacts["agent_dispatch_plan"], dispatch_plan)
        write_coverage_outputs(
            writer,
            chunks,
            [],
            [],
            agent_runs,
            ["- pending_agent_outputs: dispatch template requirements agents"],
        )
        _update_manifest_stage(manifest_path, "prepared")
        return _stage_result(
            "prepared",
            ctx.graph_dir,
            discovery.warnings,
            [],
            None,
            next_action="dispatch_template_requirements_agents",
            extra={
                "agent_dispatch": {
                    "dispatch_plan_path": artifacts["agent_dispatch_plan"],
                    "max_parallel": dispatch_plan["max_parallel"],
                    "phases": dispatch_plan["phases"],
                }
            },
        )
    except UnicodeDecodeError as exc:
        return _failure_response(ctx.graph_dir, _error("source_encoding_error", exc), True)
    except Exception as exc:
        code = getattr(exc, "code", None) or _exception_code(exc, "stage1_prepare_failed")
        return _failure_response(ctx.graph_dir, _error(code, exc), (ctx.graph_dir / "manifest.json").exists())


def ingest_stage1(*, graph_dir: str | Path, config: dict) -> dict:
    graph_root = Path(graph_dir)
    artifacts = _artifact_paths(config)
    writer = OutputWriter(graph_root, _managed_outputs(config))

    if _template_requirements_agent_state_exists(graph_root, artifacts):
        aggregate_error = _aggregate_template_requirements_from_parts(
            graph_root, config, writer
        )
        if aggregate_error is not None:
            return _failure_response(
                graph_root,
                aggregate_error,
                _manifest_exists(graph_root),
                validation_errors=aggregate_error.get("validation_errors"),
            )

    requirements_path = _artifact_path(graph_root, artifacts["requirements"])
    requirements, requirements_error = _read_json_artifact(
        requirements_path,
        missing_code="template_requirements_missing",
        bad_code="template_requirements_invalid",
    )
    if requirements_error and requirements_error.get("code") == "template_requirements_missing":
        aggregate_error = _aggregate_template_requirements_from_parts(
            graph_root, config, writer
        )
        if aggregate_error is None:
            requirements, requirements_error = _read_json_artifact(
                requirements_path,
                missing_code="template_requirements_missing",
                bad_code="template_requirements_invalid",
            )
        else:
            return _failure_response(
                graph_root,
                aggregate_error,
                _manifest_exists(graph_root),
                validation_errors=aggregate_error.get("validation_errors"),
            )
    if requirements_error:
        return _failure_response(graph_root, requirements_error, _manifest_exists(graph_root))

    requirement_validation = validate_template_requirements_payload(requirements)
    if not requirement_validation.ok:
        return _failure_response(
            graph_root,
            {
                "code": "template_requirements_invalid",
                "validation_errors": requirement_validation.errors,
            },
            _manifest_exists(graph_root),
            validation_errors=requirement_validation.errors,
        )

    chunks, chunk_error = _read_json_artifact(
        _artifact_path(graph_root, "coverage/chunk-ledger.json"),
        missing_code="chunk_ledger_missing",
        bad_code="chunk_ledger_invalid",
    )
    if chunk_error:
        return _failure_response(graph_root, chunk_error, _manifest_exists(graph_root))
    if not isinstance(chunks, list):
        return _failure_response(
            graph_root,
            {"code": "chunk_ledger_invalid", "message": "chunk ledger must be a list"},
            _manifest_exists(graph_root),
        )

    lane_outputs, lane_output_errors = _read_lane_outputs(graph_root, config)
    if lane_output_errors:
        return _failure_response(
            graph_root,
            {"code": lane_output_errors[0], "validation_errors": lane_output_errors},
            _manifest_exists(graph_root),
            validation_errors=lane_output_errors,
        )
    if not lane_outputs:
        return _failure_response(
            graph_root,
            {"code": "agent_lane_outputs_missing"},
            _manifest_exists(graph_root),
        )

    reviews, review_errors = _read_review_records(graph_root, config)
    if review_errors:
        return _failure_response(
            graph_root,
            {"code": review_errors[0], "validation_errors": review_errors},
            _manifest_exists(graph_root),
            validation_errors=review_errors,
        )

    lanes = _configured_lanes(config)
    required_lane_ids = _required_lane_ids(lanes)
    accepted_review_statuses = _accepted_review_statuses(config)
    bundle_paths: list[str] = []
    validation_errors: list[str] = []

    for chunk in chunks:
        if not isinstance(chunk, dict):
            validation_errors.append("chunk_record_not_object")
            continue
        chunk_id = chunk.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id:
            validation_errors.append("chunk_id_missing")
            continue

        chunk_outputs = lane_outputs.get(chunk_id, [])
        lane_payloads = [record["payload"] for record in chunk_outputs]
        output_paths = [record["relative_path"] for record in chunk_outputs]
        chunk_findings = reviews.findings_by_chunk.get(chunk_id, [])

        chunk_validation_errors: list[str] = []
        chunk_validation_errors.extend(
            _review_gate_errors(
                chunk_id,
                lane_payloads,
                reviews.statuses,
                accepted_review_statuses,
                require_review=_require_review_before_merge(config),
            )
        )
        chunk_validation_errors.extend(_required_lane_errors(required_lane_ids, lane_payloads))

        bundle = make_chunk_bundle(
            chunk_id=chunk_id,
            source_range=chunk.get("source_range"),
            lane_outputs=lane_payloads,
            review_findings=chunk_findings,
        )
        bundle_validation = validate_bundle_ready_for_merge(
            bundle,
            require_review_before_merge=_require_review_before_merge(config),
            allowed_finding_severities=_finding_severities(config),
            allowed_finding_statuses=_finding_statuses(config),
        )
        chunk_validation_errors.extend(bundle_validation.errors)
        if chunk_validation_errors:
            validation_errors.extend(chunk_validation_errors)
            continue

        reviewed_bundle = _reviewed_bundle(
            bundle,
            lane_payloads,
            output_paths,
            reviewer_status="passed" if _require_review_before_merge(config) else None,
            review_state=_bundle_review_state(config, reviewed=_require_review_before_merge(config)),
            review_policy_mode=_review_policy_mode(config),
        )
        bundle_path = _join_artifact(
            artifacts["reviewed_bundle_dir"],
            f"{chunk_id}.json",
        )
        writer.write_json(bundle_path, reviewed_bundle)
        bundle_paths.append(bundle_path)

    validation_errors = _canonical_validation_errors(validation_errors)
    if validation_errors:
        return _failure_response(
            graph_root,
            {"code": validation_errors[0], "validation_errors": validation_errors},
            _manifest_exists(graph_root),
            validation_errors=validation_errors,
        )
    if not bundle_paths:
        return _failure_response(
            graph_root,
            {"code": "required_lane_missing"},
            _manifest_exists(graph_root),
        )

    writer.write_json(
        artifacts["merge_queue"],
        {
            "status": "ready",
            "bundle_paths": bundle_paths,
            "required_lane_ids": required_lane_ids,
            "review_policy_mode": _review_policy_mode(config),
            "review_state_summary": _review_state_summary_from_paths(
                graph_root, bundle_paths
            ),
        },
    )
    return _stage_result(
        "ingested",
        graph_root,
        [],
        [],
        None,
        next_action="merge_stage1",
        extra={"bundle_paths": bundle_paths},
    )


def ingest_template_requirements(*, graph_dir: str | Path, config: dict) -> dict:
    graph_root = Path(graph_dir)
    writer = OutputWriter(graph_root, _managed_outputs(config))
    aggregate_error = _aggregate_template_requirements_from_parts(
        graph_root, config, writer
    )
    if aggregate_error is not None:
        return _failure_response(
            graph_root,
            aggregate_error,
            _manifest_exists(graph_root),
            validation_errors=aggregate_error.get("validation_errors"),
        )
    return _stage_result(
        "requirements_ingested",
        graph_root,
        [],
        [],
        None,
        next_action="dispatch_lane_agents",
    )


def inspect_dispatch(*, graph_dir: str | Path) -> dict:
    graph_root = Path(graph_dir)
    dispatch, error = _read_dispatch_plan(graph_root)
    if error:
        return _failure_response(graph_root, error, _manifest_exists(graph_root))
    phases = []
    for phase in dispatch.get("phases", []):
        if not isinstance(phase, dict):
            continue
        phases.append(
            {
                "phase": phase.get("phase"),
                "task_packet_count": len(phase.get("task_packets", []))
                if isinstance(phase.get("task_packets"), list)
                else 0,
                "execution_batch_count": len(phase.get("execution_batches", []))
                if isinstance(phase.get("execution_batches"), list)
                else 0,
            }
        )
    return {
        "status": "dispatch_ready",
        "graph_dir": str(graph_root),
        "dispatch_plan_path": DEFAULT_STAGE1_ARTIFACTS["agent_dispatch_plan"],
        "max_parallel": dispatch.get("max_parallel"),
        "phases": phases,
    }


def next_agent_batches(
    *, graph_dir: str | Path, phase: str, limit: int | None = None
) -> dict:
    graph_root = Path(graph_dir)
    dispatch, error = _read_dispatch_plan(graph_root)
    if error:
        return _failure_response(graph_root, error, _manifest_exists(graph_root))
    phase_record = _dispatch_phase(dispatch, phase)
    if phase_record is None:
        return _failure_response(
            graph_root,
            {"code": "dispatch_phase_missing", "phase": phase},
            _manifest_exists(graph_root),
        )
    batches = phase_record.get("execution_batches")
    if not isinstance(batches, list):
        return _failure_response(
            graph_root,
            {"code": "dispatch_execution_batches_missing", "phase": phase},
            _manifest_exists(graph_root),
        )
    pending = [
        batch
        for batch in batches
        if isinstance(batch, dict) and not _batch_outputs_exist(graph_root, batch)
    ]
    selected = pending[:limit] if limit is not None and limit >= 0 else pending
    return {
        "status": "pending_agent_batches",
        "graph_dir": str(graph_root),
        "phase": phase,
        "pending_count": len(pending),
        "returned_count": len(selected),
        "batches": selected,
    }


def merge_stage1(*, graph_dir: str | Path, config: dict) -> dict:
    graph_root = Path(graph_dir)
    artifacts = _artifact_paths(config)
    queue_path = _artifact_path(graph_root, artifacts["merge_queue"])
    queue, queue_error = _read_json_artifact(
        queue_path,
        missing_code="missing_reviewed_agent_outputs",
        bad_code="merge_queue_invalid",
    )
    if queue_error:
        validation_errors = [queue_error["code"], "required_lane_missing"]
        return _failure_response(
            graph_root,
            queue_error,
            _manifest_exists(graph_root),
            validation_errors=validation_errors,
        )

    bundle_paths, queue_validation_errors = _validate_merge_queue(queue)
    if queue_validation_errors:
        validation_errors = _canonical_validation_errors(queue_validation_errors)
        return _failure_response(
            graph_root,
            {"code": validation_errors[0], "validation_errors": validation_errors},
            _manifest_exists(graph_root),
            validation_errors=validation_errors,
        )

    try:
        allowed_lane_ids = set(_lane_ids(_configured_lanes(config)))
        allowed_statuses = _lane_output_statuses(config)
        required_lane_ids = _required_lane_ids_with_queue_guard(queue, config)
    except ValueError as exc:
        validation_errors = _canonical_validation_errors([str(exc)])
        return _failure_response(
            graph_root,
            {"code": validation_errors[0], "validation_errors": validation_errors},
            _manifest_exists(graph_root),
            validation_errors=validation_errors,
        )

    bundles: list[dict] = []
    validation_errors: list[str] = []
    for relative_path in bundle_paths:
        path = _artifact_path(graph_root, relative_path)
        bundle, bundle_error = _read_json_artifact(
            path,
            missing_code="missing_reviewed_agent_outputs",
            bad_code="reviewed_bundle_invalid",
        )
        if bundle_error:
            validation_errors.append(bundle_error["code"])
            continue
        if not isinstance(bundle, dict):
            validation_errors.append("reviewed_bundle_invalid")
            continue
        bundle_validation = validate_bundle_ready_for_merge(
            bundle,
            require_review_before_merge=_require_review_before_merge(config),
            required_lane_ids=required_lane_ids,
            allowed_finding_severities=_finding_severities(config),
            allowed_finding_statuses=_finding_statuses(config),
        )
        if not bundle_validation.ok:
            validation_errors.extend(bundle_validation.errors)
            continue
        lane_output_validation_errors = _embedded_lane_output_errors(
            bundle,
            allowed_lane_ids=allowed_lane_ids,
            allowed_statuses=allowed_statuses,
        )
        if lane_output_validation_errors:
            validation_errors.extend(lane_output_validation_errors)
            continue
        bundles.append(bundle)

    if validation_errors:
        validation_errors = _canonical_validation_errors(validation_errors)
        return _failure_response(
            graph_root,
            {"code": validation_errors[0], "validation_errors": validation_errors},
            _manifest_exists(graph_root),
            validation_errors=validation_errors,
        )

    manifest = _read_manifest(graph_root)
    novel_name = _novel_name_from_manifest_or_graph_dir(manifest, graph_root)
    result = build_canonical_graph_from_bundles(
        bundles,
        novel_name=novel_name,
        status_enums=_status_enums_for_merge(config),
        source_bundle_paths=bundle_paths,
    )
    if not result.ok:
        return _failure_response(
            graph_root,
            {"code": "canonical_graph_invalid", "validation_errors": result.errors},
            _manifest_exists(graph_root),
            validation_errors=result.errors,
        )

    writer = OutputWriter(graph_root, _managed_outputs(config))
    canonical_graph = _graph_with_graphify_metadata(result.graph, config)
    metadata = canonical_graph.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["review_policy_mode"] = _review_policy_mode(config)
        metadata.setdefault(
            "incremental_review_queue_path",
            _artifact_paths(config)["review_findings"],
        )
    writer.write_json(artifacts["canonical_graph"], canonical_graph)
    graphify_warnings: list[str] = []
    result_status = "success"

    if _graphify_adapter_enabled(config):
        canonical_graph_path = _artifact_path(graph_root, artifacts["canonical_graph"])
        graphify_result = _graphify_adapter(config).build_graph(
            canonical_graph_path,
            canonical_graph_path.parent,
            graph_dir=graph_root,
        )
        _write_graphify_adapter_ledger(
            graph_root,
            config,
            graphify_result,
            input_path=artifacts["canonical_graph"],
        )
        OutputWriter(graph_root, _managed_outputs(config)).write_json(
            artifacts["canonical_graph"], canonical_graph
        )
        if not graphify_result.ok:
            if _graphify_failure_policy(config) == "degrade-visualization-and-query":
                result_status = "warning"
                graphify_warnings = _dedupe(
                    [
                        "graphify_degraded",
                        *[
                            warning
                            for warning in graphify_result.warnings
                            if isinstance(warning, str)
                        ],
                        _graphify_error_code(graphify_result.error),
                    ]
                )
            else:
                error = graphify_result.error or {"code": "graphify_failed"}
                manifest_path = graph_root / "manifest.json"
                if manifest_path.exists():
                    _update_manifest_stage(manifest_path, "failed")
                return _failure_response(
                    graph_root,
                    error,
                    _manifest_exists(graph_root),
                    validation_errors=_dedupe(
                        ["graphify_adapter_failed", _graphify_error_code(error)]
                    ),
                )
        elif graphify_result.status == "degraded":
            result_status = "warning"
            graphify_warnings = _dedupe(
                [
                    "graphify_degraded",
                    *[
                        warning
                        for warning in graphify_result.warnings
                        if isinstance(warning, str)
                    ],
                ]
            )

    manifest_path = graph_root / "manifest.json"
    if manifest_path.exists():
        _update_manifest_stage(manifest_path, "success")
    return _stage_result(
        result_status,
        graph_root,
        graphify_warnings,
        [],
        None,
        next_action=None,
        extra={"source_bundle_paths": bundle_paths},
    )


def build_stage1_graph(source_path: str | Path, config: dict) -> dict:
    graph_dir = _graph_dir_for_build(source_path, config)
    template_dir = config.get("paths", {}).get("template_dir")
    if template_dir is None:
        return _failure_response(
            graph_dir,
            {"code": "template_dir_missing", "message": "paths.template_dir is required"},
            False,
        )

    prepared = prepare_stage1(
        source_path=source_path,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    if prepared.get("status") != "prepared":
        return prepared
    return prepared


def graphify_source_fingerprint(config: dict) -> dict:
    repo_value = config.get("paths", {}).get("graphify_repo")
    repo = Path(repo_value) if repo_value else None
    repo_content_hash = None
    if repo and repo.exists():
        repo_content_hash = _directory_content_hash(repo)
    adapter_config, adapter_config_error = _graphify_adapter_config(config)
    command = adapter_config.get("command", [])
    return {
        "graphify_repo": str(repo) if repo else None,
        "graphify_content_hash": repo_content_hash,
        "adapter_mode": adapter_config.get("mode"),
        "adapter_command": command,
        "adapter_timeout_seconds": adapter_config.get("timeout_seconds"),
        "adapter_executable": _executable_fingerprint(command),
        "adapter_config_error": adapter_config_error,
    }


def stable_stage_input_hash(
    ctx: NovelContext,
    config: dict,
    templates: list,
    *,
    requirements_hash: str | None = None,
    reviewed_output_manifest_hash: str | None = None,
) -> str:
    return compute_stage1_input_hash(
        source_hash=ctx.source_hash,
        config_hash=_stable_json_hash(config),
        template_inventory_hash=_template_inventory_hash(templates),
        task_packet_schema_hash=_task_packet_schema_hash(config),
        requirements_hash=requirements_hash,
        reviewed_output_manifest_hash=reviewed_output_manifest_hash,
    )


def _build_task_packets(
    source_path: Path,
    chunks: list[dict],
    lanes: list[dict],
    artifacts: dict[str, str],
    config: dict,
) -> list[dict]:
    from .stage1_packets import build_task_packets

    return build_task_packets(
        source_path=source_path,
        chunks=chunks,
        lanes=lanes,
        template_requirements_path=artifacts["requirements"],
        task_packet_dir=artifacts["task_packet_dir"],
        required_evidence_policy=config.get("required_evidence_policy"),
    )


def _build_template_requirements_task_packets(
    source_path: Path,
    chunks: list[dict],
    templates: list,
    artifacts: dict[str, str],
    config: dict,
) -> list[dict]:
    from .stage1_packets import build_template_requirements_task_packets

    return build_template_requirements_task_packets(
        source_path=source_path,
        chunks=chunks,
        templates=templates,
        template_requirements_path=artifacts["requirements"],
        task_packet_dir=artifacts["task_packet_dir"],
        template_requirements_part_dir=artifacts["template_requirements_part_dir"],
        strategy=config.get("template_requirements_strategy"),
    )


def _discover_templates(config: dict, template_dir: str | Path):
    template_config = config.get("template_discovery", {})
    return discover_templates(
        Path(template_dir),
        glob=template_config.get("glob", "*模板.md"),
        readme_index_file=template_config.get("readme_index_file", "README.md"),
        exclude_files=template_config.get("exclude_files", []),
        readme_missing_policy=template_config.get("readme_missing_policy", "warn"),
    )


def _novel_context(source_path: str | Path, graph_dir: str | Path) -> NovelContext:
    source = Path(source_path).expanduser().resolve()
    graph_root = Path(graph_dir).expanduser().resolve()
    graph_root.mkdir(parents=True, exist_ok=True)
    return NovelContext(
        source_path=source,
        source_hash=file_sha256(source),
        source_size=source.stat().st_size,
        novel_name=source.stem,
        novel_dir=source.parent,
        graph_dir=graph_root,
    )


def _config_with_paths(config: dict, template_dir: str | Path) -> dict:
    active_config = dict(config)
    paths = dict(active_config.get("paths", {}))
    paths["template_dir"] = str(template_dir)
    active_config["paths"] = paths
    return active_config


def _graph_dir_for_build(source_path: str | Path, config: dict) -> Path:
    graph_dir = config.get("paths", {}).get("graph_dir")
    if graph_dir:
        return Path(graph_dir)
    suffix = config.get("graph_dir_suffix", ".storygraph")
    source = Path(source_path).expanduser().resolve(strict=False)
    return source.parent / f"{source.stem}{suffix}"


def _configured_lanes(config: dict) -> list[dict]:
    lanes = config.get("element_lanes")
    if not isinstance(lanes, list) or not lanes:
        raise ValueError("element_lanes_missing")
    normalized: list[dict] = []
    for lane in lanes:
        if not isinstance(lane, dict):
            raise ValueError("element_lane_not_object")
        normalized.append(dict(lane))
    return normalized


def _lane_ids(lanes: Iterable[dict]) -> list[str]:
    return [
        lane["lane_id"]
        for lane in lanes
        if isinstance(lane.get("lane_id"), str) and lane.get("lane_id")
    ]


def _required_lane_ids(lanes: Iterable[dict]) -> list[str]:
    return [
        lane["lane_id"]
        for lane in lanes
        if lane.get("required") is True
        and isinstance(lane.get("lane_id"), str)
        and lane.get("lane_id")
    ]


def _write_chunk_texts(
    writer: OutputWriter,
    chunks: list[dict],
    chunk_text_dir: str,
) -> list[dict]:
    prepared_chunks: list[dict] = []
    for chunk in chunks:
        prepared = dict(chunk)
        text = prepared.pop("text", "")
        chunk_text_path = _join_artifact(chunk_text_dir, f"{prepared['chunk_id']}.txt")
        writer.write_text(chunk_text_path, text)
        prepared["chunk_text_path"] = chunk_text_path
        prepared_chunks.append(prepared)
    return prepared_chunks


def _pending_agent_run_ledger(
    chunks: list[dict],
    template_requirements_packets: list[dict],
    packets: list[dict],
    artifacts: dict[str, str],
) -> list[dict]:
    chunk_ids = [chunk["chunk_id"] for chunk in chunks]
    records = []
    for template_requirements_packet in template_requirements_packets:
        template_packet_path = template_requirements_packet["task_packet_path"]
        batch_id = template_requirements_packet["batch_id"]
        template_record = make_agent_run_record(
            f"stage1-template-requirements:{batch_id}",
            template_requirements_packet["agent_role"],
            "stage1",
            chunk_ids,
            template_requirements_packet.get("template_names", []),
            [template_packet_path, "templates"],
            [template_requirements_packet["output_path"]],
            template_requirements_packet["write_scope"],
        )
        template_record["prompt_or_input_packet"] = template_packet_path
        template_record["chunk_id"] = template_requirements_packet["chunk_id"]
        template_record["batch_id"] = batch_id
        template_record["lane_id"] = template_requirements_packet["lane_id"]
        template_record["attempt"] = template_requirements_packet.get("attempt", 1)
        records.append(template_record)
    for packet in packets:
        chunk_id = packet["chunk_id"]
        lane_id = packet["lane_id"]
        attempt = packet.get("attempt", 1)
        output_path = _join_artifact(
            artifacts["lane_output_dir"],
            chunk_id,
            lane_id,
            f"run-{attempt:03d}.json",
        )
        input_paths = [artifacts["requirements"]]
        if packet.get("chunk_text_path"):
            input_paths.append(packet["chunk_text_path"])
        records.append(
            make_lane_agent_record(
                run_id=f"{chunk_id}:{lane_id}:run-{attempt:03d}",
                chunk_id=chunk_id,
                lane_id=lane_id,
                agent_role=packet["agent_role"],
                task_packet_path=packet["task_packet_path"],
                output_path=output_path,
                attempt=attempt,
                input_paths=input_paths,
            )
        )
    return records


def _build_agent_dispatch_plan(
    template_requirements_packets: list[dict],
    lane_packets: list[dict],
    artifacts: dict[str, str],
    config: dict,
) -> dict:
    template_batches = _template_execution_batches(template_requirements_packets)
    lane_batches = _lane_execution_batches(lane_packets, artifacts, config)
    phases = [
        {
            "phase": "template_requirements",
            "next_action": "dispatch_template_requirements_agents",
            "task_packets": [
                _dispatch_task_packet(packet) for packet in template_requirements_packets
            ],
            "execution_batches": template_batches,
            "wait_for_outputs": [
                packet["output_path"] for packet in template_requirements_packets
            ],
        },
        {
            "phase": "lane_extraction",
            "next_action": "dispatch_lane_agents",
            "task_packets": [
                _dispatch_task_packet(packet) for packet in lane_packets
            ],
            "execution_batches": lane_batches,
            "wait_for_outputs_root": artifacts["lane_output_dir"],
        },
    ]
    if _require_review_before_merge(config):
        phases.append(
            {
                "phase": "review",
                "next_action": "dispatch_reviewer_agents",
                "review_findings_path": artifacts["review_findings"],
                "wait_for_outputs": [artifacts["review_findings"]],
            }
        )
    return {
        "schema_version": "storygraph.agent-dispatch.v1",
        "stage": "stage1",
        "max_parallel": _agent_max_parallel(config),
        "review_policy_mode": _review_policy_mode(config),
        "phases": phases,
    }


def _template_execution_batches(packets: list[dict]) -> list[dict]:
    batches = []
    for index, packet in enumerate(packets, start=1):
        output_paths = [packet["output_path"]]
        batches.append(
            {
                "batch_id": f"template-requirements-batch-{index:04d}",
                "phase": "template_requirements",
                "agent_role": packet["agent_role"],
                "lane_id": packet["lane_id"],
                "chunk_ids": packet.get("chunk_ids", []),
                "template_names": packet.get("template_names", []),
                "task_packet_paths": [packet["task_packet_path"]],
                "expected_output_paths": output_paths,
                "write_scope": output_paths,
            }
        )
    return batches


def _lane_execution_batches(
    packets: list[dict], artifacts: dict[str, str], config: dict
) -> list[dict]:
    if _lane_batch_strategy(config) != "by-lane-contiguous-chunks":
        return _lane_execution_batches_by_lane(packets, artifacts, 1)
    return _lane_execution_batches_by_lane(
        packets, artifacts, _lane_chunks_per_agent(config)
    )


def _lane_execution_batches_by_lane(
    packets: list[dict], artifacts: dict[str, str], chunks_per_agent: int
) -> list[dict]:
    lane_order: list[str] = []
    packets_by_lane: dict[str, list[dict]] = {}
    for packet in packets:
        lane_id = packet["lane_id"]
        if lane_id not in packets_by_lane:
            lane_order.append(lane_id)
            packets_by_lane[lane_id] = []
        packets_by_lane[lane_id].append(packet)

    batches: list[dict] = []
    for lane_id in lane_order:
        lane_packets = packets_by_lane[lane_id]
        for index, start in enumerate(range(0, len(lane_packets), chunks_per_agent), start=1):
            batch_packets = lane_packets[start : start + chunks_per_agent]
            output_paths = [
                _lane_packet_output_path(packet, artifacts) for packet in batch_packets
            ]
            batches.append(
                {
                    "batch_id": f"lane-{lane_id}-batch-{index:04d}",
                    "phase": "lane_extraction",
                    "agent_role": batch_packets[0]["agent_role"],
                    "lane_id": lane_id,
                    "chunk_ids": [packet["chunk_id"] for packet in batch_packets],
                    "task_packet_paths": [
                        packet["task_packet_path"] for packet in batch_packets
                    ],
                    "expected_output_paths": output_paths,
                    "write_scope": output_paths,
                }
            )
    return batches


def _lane_packet_output_path(packet: dict, artifacts: dict[str, str]) -> str:
    return _join_artifact(
        artifacts["lane_output_dir"],
        packet["chunk_id"],
        packet["lane_id"],
        f"run-{packet.get('attempt', 1):03d}.json",
    )


def _dispatch_task_packet(packet: dict) -> dict:
    item = {
        "task_packet_path": packet["task_packet_path"],
        "agent_role": packet["agent_role"],
        "stage": packet["stage"],
        "lane_id": packet["lane_id"],
    }
    for field in ("chunk_id", "batch_id", "output_path", "write_scope", "template_names"):
        if field in packet:
            item[field] = packet[field]
    return item


def _agent_max_parallel(config: dict) -> int:
    value = config.get("agent_orchestration", {}).get("max_parallel_agents")
    if type(value) is int and value > 0:
        return value
    value = config.get("agent_policy", {}).get("max_parallel", 1)
    if type(value) is int and value > 0:
        return value
    return 1


def _lane_batch_strategy(config: dict) -> str:
    value = config.get("agent_orchestration", {}).get("lane_batch_strategy")
    if isinstance(value, str) and value:
        return value
    return "by-lane-contiguous-chunks"


def _lane_chunks_per_agent(config: dict) -> int:
    value = config.get("agent_orchestration", {}).get("lane_chunks_per_agent", 1)
    if type(value) is int and value > 0:
        return value
    return 1


def _failed_agent_runs(agent_runs: list[dict], code: str, errors: list[dict]) -> list[dict]:
    failed = [dict(record) for record in agent_runs]
    for record in failed:
        record["status"] = "failed"
        record["errors"] = list(errors)
    return failed


def _template_requirements_agent_state_exists(
    graph_root: Path, artifacts: dict[str, str]
) -> bool:
    try:
        packet_root = _artifact_path(
            graph_root,
            _join_artifact(artifacts["task_packet_dir"], "template-requirements"),
        )
    except OutputWriteError:
        return True
    if packet_root.exists():
        return True

    try:
        ledger_path = _artifact_path(graph_root, artifacts["agent_run_ledger"])
    except OutputWriteError:
        return True
    if not ledger_path.exists():
        return False
    ledger, ledger_error = _read_json_artifact(
        ledger_path,
        missing_code="template_requirements_missing",
        bad_code="template_requirements_part_ledger_invalid",
    )
    if ledger_error:
        return True
    if not isinstance(ledger, list):
        return True
    return any(
        isinstance(record, dict)
        and isinstance(record.get("run_id"), str)
        and record["run_id"].startswith("stage1-template-requirements:")
        for record in ledger
    )


def _aggregate_template_requirements_from_parts(
    graph_root: Path, config: dict, writer: OutputWriter
) -> dict | None:
    artifacts = _artifact_paths(config)
    ledger_path = _artifact_path(graph_root, artifacts["agent_run_ledger"])
    ledger, ledger_error = _read_json_artifact(
        ledger_path,
        missing_code="template_requirements_missing",
        bad_code="template_requirements_part_ledger_invalid",
    )
    if ledger_error:
        return ledger_error
    if not isinstance(ledger, list):
        return {
            "code": "template_requirements_part_ledger_invalid",
            "validation_errors": ["template_requirements_part_ledger_not_list"],
        }

    records = [
        record
        for record in ledger
        if isinstance(record, dict)
        and isinstance(record.get("run_id"), str)
        and record["run_id"].startswith("stage1-template-requirements:")
    ]
    if not records:
        return {"code": "template_requirements_missing"}

    record_by_batch: dict[str, dict] = {}
    validation_errors: list[str] = []
    seen_ledger_output_paths: set[str] = set()
    seen_ledger_write_scope: set[str] = set()
    for record in records:
        batch_id = record.get("batch_id")
        if not isinstance(batch_id, str) or not batch_id:
            validation_errors.append("template_requirements_ledger_batch_id_invalid")
            continue
        if batch_id in record_by_batch:
            validation_errors.append(f"template_requirements_duplicate_ledger_batch:{batch_id}")
            continue
        record_by_batch[batch_id] = record

        output_paths, output_path_errors = _validated_artifact_path_list(
            record.get("output_paths"),
            f"template_requirements_ledger_output_paths:{batch_id}",
        )
        write_scope, write_scope_errors = _validated_artifact_path_list(
            record.get("write_scope"),
            f"template_requirements_ledger_write_scope:{batch_id}",
        )
        validation_errors.extend(output_path_errors)
        validation_errors.extend(write_scope_errors)
        if output_paths is None or len(output_paths) != 1:
            validation_errors.append("template_requirements_part_output_path_invalid")
        if write_scope is None:
            validation_errors.append("template_requirements_part_write_scope_invalid")
        expected_part_path = _join_artifact(
            artifacts["template_requirements_part_dir"], f"{batch_id}.json"
        )
        if output_paths is not None:
            if output_paths != [expected_part_path]:
                validation_errors.append(
                    f"template_requirements_ledger_output_paths_mismatch:{batch_id}"
                )
            for output_path in output_paths:
                if output_path in seen_ledger_output_paths:
                    validation_errors.append(
                        f"template_requirements_duplicate_ledger_output_path:{output_path}"
                    )
                seen_ledger_output_paths.add(output_path)
        if write_scope is not None:
            if write_scope != [expected_part_path]:
                validation_errors.append(
                    f"template_requirements_ledger_write_scope_mismatch:{batch_id}"
                )
            for write_path in write_scope:
                if write_path in seen_ledger_write_scope:
                    validation_errors.append(
                        f"template_requirements_duplicate_ledger_write_scope:{write_path}"
                    )
                seen_ledger_write_scope.add(write_path)
        assigned_names = record.get("assigned_template_names")
        if not isinstance(assigned_names, list) or any(
            not isinstance(name, str) for name in assigned_names
        ):
            validation_errors.append(
                f"template_requirements_ledger_assigned_template_names_invalid:{batch_id}"
            )
        elif not _template_requirements_batch_size_is_valid(assigned_names):
            validation_errors.append(
                f"template_requirements_ledger_template_count_invalid:{batch_id}"
            )

    packets, packet_error = _read_template_requirements_packets(graph_root, artifacts)
    if packet_error:
        validation_errors.extend(
            packet_error.get("validation_errors") or [packet_error["code"]]
        )
        return {
            "code": "template_requirements_part_invalid",
            "validation_errors": validation_errors,
        }
    packet_by_batch = {packet["batch_id"]: packet for packet in packets}

    if set(record_by_batch) != set(packet_by_batch):
        validation_errors.append("template_requirements_ledger_batch_mismatch")

    for batch_id, packet in packet_by_batch.items():
        record = record_by_batch.get(batch_id)
        if record is None:
            continue
        expected_output_paths = [packet["output_path"]]
        expected_write_scope = packet["write_scope"]
        expected_template_names = packet["template_names"]
        if (
            record.get("run_id") != f"stage1-template-requirements:{batch_id}"
            or record.get("output_paths") != expected_output_paths
            or record.get("write_scope") != expected_write_scope
            or record.get("assigned_template_names") != expected_template_names
            or record.get("prompt_or_input_packet") != packet["task_packet_path"]
        ):
            validation_errors.append(
                f"template_requirements_packet_ledger_mismatch:{batch_id}"
            )

    if validation_errors:
        return {
            "code": "template_requirements_part_invalid",
            "validation_errors": validation_errors,
        }

    records = [record_by_batch[packet["batch_id"]] for packet in packets]
    merged_templates: list[dict] = []
    expected_template_names: list[str] = []
    for packet, record in zip(packets, records):
        assigned_names = record["assigned_template_names"]
        part_path = _artifact_path(graph_root, packet["output_path"])
        part, part_error = _read_json_artifact(
            part_path,
            missing_code="template_requirements_part_missing",
            bad_code="template_requirements_part_invalid",
        )
        if part_error:
            return part_error
        validation = validate_template_requirements_payload(
            part, expected_template_names=assigned_names
        )
        if not validation.ok:
            return {
                "code": "template_requirements_part_invalid",
                "validation_errors": validation.errors,
            }
        merged_templates.extend(part["templates"])
        expected_template_names.extend(assigned_names)

    payload = {"template_count": len(merged_templates), "templates": merged_templates}
    validation = validate_template_requirements_payload(
        payload, expected_template_names=expected_template_names
    )
    if not validation.ok:
        return {
            "code": "template_requirements_invalid",
            "validation_errors": validation.errors,
        }
    try:
        writer.write_json(artifacts["requirements"], payload)
    except OutputWriteError as exc:
        return {
            "code": "template_requirements_invalid",
            "validation_errors": [f"{exc.code}:{exc.path}"],
        }
    return None


def _read_template_requirements_packets(
    graph_root: Path, artifacts: dict[str, str]
) -> tuple[list[dict], dict | None]:
    try:
        packet_root = _artifact_path(
            graph_root,
            _join_artifact(artifacts["task_packet_dir"], "template-requirements"),
        )
    except OutputWriteError as exc:
        return [], {
            "code": "template_requirements_part_invalid",
            "validation_errors": [f"{exc.code}:{exc.path}"],
        }
    if not packet_root.exists():
        return [], {
            "code": "template_requirements_part_invalid",
            "validation_errors": ["template_requirements_task_packets_missing"],
        }

    packets: list[dict] = []
    errors: list[str] = []
    seen_batch_ids: set[str] = set()
    seen_output_paths: set[str] = set()
    seen_write_scope_paths: set[str] = set()
    for path in sorted(packet_root.glob("batch-*.json")):
        actual_packet_path = path.relative_to(graph_root).as_posix()
        filename_batch_id = path.stem
        packet, packet_error = _read_json_artifact(
            path,
            missing_code="template_requirements_task_packet_missing",
            bad_code="template_requirements_task_packet_invalid",
        )
        if packet_error:
            errors.append(packet_error["code"])
            continue
        if not isinstance(packet, dict):
            errors.append("template_requirements_task_packet_not_object")
            continue

        batch_id = packet.get("batch_id")
        output_path = packet.get("output_path")
        write_scope = packet.get("write_scope")
        lane_contract = packet.get("lane_contract")
        template_names = packet.get("template_names")
        template_inventory = packet.get("template_inventory")
        task_packet_path = packet.get("task_packet_path")
        packet_errors: list[str] = []
        if not isinstance(batch_id, str) or not batch_id:
            packet_errors.append("template_requirements_task_packet_batch_id_invalid")
        elif batch_id in seen_batch_ids:
            packet_errors.append(f"template_requirements_duplicate_task_packet:{batch_id}")
        elif filename_batch_id != batch_id:
            packet_errors.append(
                f"template_requirements_task_packet_filename_mismatch:{batch_id}"
            )
            seen_batch_ids.add(batch_id)
        else:
            seen_batch_ids.add(batch_id)
        output_paths, output_errors = _validated_artifact_path_list(
            [output_path] if isinstance(output_path, str) else output_path,
            f"template_requirements_packet_output_path:{batch_id}",
        )
        write_scope_paths, write_scope_errors = _validated_artifact_path_list(
            write_scope,
            f"template_requirements_packet_write_scope:{batch_id}",
        )
        packet_errors.extend(output_errors)
        packet_errors.extend(write_scope_errors)
        if output_paths is None or len(output_paths) != 1:
            packet_errors.append("template_requirements_task_packet_output_path_invalid")
        if write_scope_paths is None:
            packet_errors.append("template_requirements_task_packet_write_scope_invalid")
        if isinstance(batch_id, str) and batch_id:
            expected_part_path = _join_artifact(
                artifacts["template_requirements_part_dir"], f"{batch_id}.json"
            )
            if output_paths is not None:
                if output_paths != [expected_part_path]:
                    packet_errors.append(
                        f"template_requirements_task_packet_output_path_mismatch:{batch_id}"
                    )
                for output_item in output_paths:
                    if output_item in seen_output_paths:
                        packet_errors.append(
                            f"template_requirements_duplicate_task_packet_output_path:{output_item}"
                        )
                    seen_output_paths.add(output_item)
            if write_scope_paths is not None:
                if write_scope_paths != [expected_part_path]:
                    packet_errors.append(
                        f"template_requirements_task_packet_write_scope_mismatch:{batch_id}"
                    )
                for write_item in write_scope_paths:
                    if write_item in seen_write_scope_paths:
                        packet_errors.append(
                            f"template_requirements_duplicate_task_packet_write_scope:{write_item}"
                        )
                    seen_write_scope_paths.add(write_item)
            if (
                not isinstance(lane_contract, dict)
                or lane_contract.get("output_path") != expected_part_path
            ):
                packet_errors.append(
                    f"template_requirements_task_packet_lane_contract_output_path_mismatch:{batch_id}"
                )
        if not isinstance(template_names, list) or any(
            not isinstance(name, str) for name in template_names
        ):
            packet_errors.append("template_requirements_task_packet_template_names_invalid")
        elif not _template_requirements_batch_size_is_valid(template_names):
            packet_errors.append(
                f"template_requirements_task_packet_template_count_invalid:{batch_id}"
            )
        if not isinstance(template_inventory, list) or any(
            not isinstance(item, dict) for item in template_inventory
        ):
            packet_errors.append("template_requirements_task_packet_template_inventory_invalid")
        elif not _template_requirements_batch_size_is_valid(template_inventory):
            packet_errors.append(
                f"template_requirements_task_packet_template_inventory_count_invalid:{batch_id}"
            )
        elif isinstance(template_names, list):
            inventory_names = [item.get("template_name") for item in template_inventory]
            if inventory_names != template_names:
                packet_errors.append(
                    f"template_requirements_task_packet_template_inventory_mismatch:{batch_id}"
                )
        if not isinstance(task_packet_path, str):
            packet_errors.append("template_requirements_task_packet_path_invalid")
        else:
            _, task_packet_errors = _validated_artifact_path_list(
                [task_packet_path],
                f"template_requirements_packet_task_path:{batch_id}",
            )
            packet_errors.extend(task_packet_errors)
            if task_packet_path != actual_packet_path:
                packet_errors.append(
                    f"template_requirements_task_packet_path_mismatch:{batch_id}"
                )

        if packet_errors:
            errors.extend(packet_errors)
            continue
        packets.append(packet)

    if errors:
        return [], {"code": "template_requirements_part_invalid", "validation_errors": errors}
    if not packets:
        return [], {
            "code": "template_requirements_part_invalid",
            "validation_errors": ["template_requirements_task_packets_missing"],
        }
    sequence_errors = _template_requirements_batch_sequence_errors(
        [packet["batch_id"] for packet in packets]
    )
    if sequence_errors:
        return [], {
            "code": "template_requirements_part_invalid",
            "validation_errors": sequence_errors,
        }
    return packets, None


def _read_dispatch_plan(graph_root: Path) -> tuple[dict | None, dict | None]:
    path = _artifact_path(graph_root, DEFAULT_STAGE1_ARTIFACTS["agent_dispatch_plan"])
    payload, error = _read_json_artifact(
        path,
        missing_code="dispatch_plan_missing",
        bad_code="dispatch_plan_invalid",
    )
    if error:
        return None, error
    if not isinstance(payload, dict):
        return None, {"code": "dispatch_plan_invalid"}
    return payload, None


def _dispatch_phase(dispatch: dict, phase: str) -> dict | None:
    phases = dispatch.get("phases")
    if not isinstance(phases, list):
        return None
    for item in phases:
        if isinstance(item, dict) and item.get("phase") == phase:
            return item
    return None


def _batch_outputs_exist(graph_root: Path, batch: dict) -> bool:
    output_paths = batch.get("expected_output_paths")
    if not isinstance(output_paths, list) or not output_paths:
        return False
    return all(
        isinstance(path, str) and _artifact_path(graph_root, path).exists()
        for path in output_paths
    )


def _template_requirements_batch_size_is_valid(items: list) -> bool:
    return 1 <= len(items) <= 5


def _template_requirements_batch_sequence_errors(batch_ids: list[str]) -> list[str]:
    batch_numbers: list[int] = []
    for batch_id in batch_ids:
        prefix, _, suffix = batch_id.partition("-")
        if prefix != "batch" or len(suffix) != 4 or not suffix.isdigit():
            return ["template_requirements_batch_sequence_invalid"]
        number = int(suffix)
        if number < 1:
            return ["template_requirements_batch_sequence_invalid"]
        batch_numbers.append(number)

    if sorted(batch_numbers) != list(range(1, max(batch_numbers) + 1)):
        return ["template_requirements_batch_sequence_invalid"]
    return []


def _validated_artifact_path_list(
    values: Any, label: str
) -> tuple[list[str] | None, list[str]]:
    if not isinstance(values, list):
        return None, [f"invalid_path_list:{label}"]
    normalized: list[str] = []
    errors: list[str] = []
    for value in values:
        if not isinstance(value, str):
            errors.append(f"invalid_path_item:{label}")
            continue
        try:
            normalized.append(normalize_relative_output_path(value))
        except OutputWriteError as exc:
            errors.append(f"{exc.code}:{exc.path}")
    return (normalized if not errors else None), errors


def _read_lane_outputs(graph_dir: Path, config: dict) -> tuple[dict[str, list[dict]], list[str]]:
    artifacts = _artifact_paths(config)
    root = _artifact_path(graph_dir, artifacts["lane_output_dir"])
    if not root.exists():
        return {}, []
    allowed_lane_ids = set(_lane_ids(_configured_lanes(config)))
    allowed_statuses = _lane_output_statuses(config)
    chunk_ranges = _chunk_ranges(graph_dir)
    latest_by_lane: dict[tuple[str, str], dict] = {}
    errors: list[str] = []
    for path in sorted(root.glob("*/*/*.json")):
        payload, error = _read_json_artifact(
            path,
            missing_code="lane_output_missing",
            bad_code="lane_output_invalid",
        )
        relative_path = _relative_to_graph(graph_dir, path)
        if error:
            errors.append(error["code"])
            continue
        validation = validate_lane_output(
            payload,
            allowed_lane_ids=allowed_lane_ids,
            allowed_statuses=allowed_statuses,
            chunk_source_range=chunk_ranges.get(payload.get("chunk_id"))
            if isinstance(payload, dict)
            else None,
        )
        if not validation.ok:
            errors.extend(validation.errors)
            continue
        key = (payload["chunk_id"], payload["lane_id"])
        record = {"payload": payload, "relative_path": relative_path}
        existing = latest_by_lane.get(key)
        if existing is None or relative_path > existing["relative_path"]:
            latest_by_lane[key] = record
    outputs: dict[str, list[dict]] = {}
    for (chunk_id, _lane_id), record in sorted(latest_by_lane.items()):
        outputs.setdefault(chunk_id, []).append(record)
    return outputs, _dedupe(errors)


class _ReviewRecords:
    def __init__(self) -> None:
        self.statuses: dict[tuple[str, str], str] = {}
        self.findings_by_chunk: dict[str, list[dict]] = {}


def _read_review_records(graph_dir: Path, config: dict) -> tuple[_ReviewRecords, list[str]]:
    records = _ReviewRecords()
    review_path = _artifact_path(graph_dir, _artifact_paths(config)["review_findings"])
    if not review_path.exists():
        return records, ["review_findings_missing"] if _require_review_before_merge(config) else []
    payload, error = _read_json_artifact(
        review_path,
        missing_code="review_findings_missing",
        bad_code="review_findings_invalid",
    )
    if error:
        return records, [error["code"]]
    if isinstance(payload, dict):
        items = payload.get("reviews") or payload.get("findings") or []
    else:
        items = payload
    if not isinstance(items, list):
        return records, ["review_findings_invalid"]
    errors: list[str] = []
    allowed_reviewer_statuses = _reviewer_statuses(config)
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"review_record_not_object:{index}")
            continue
        chunk_id = item.get("chunk_id")
        lane_id = item.get("lane_id")
        if isinstance(chunk_id, str) and isinstance(lane_id, str):
            reviewer_status = item.get("reviewer_status")
            if isinstance(reviewer_status, str) and reviewer_status:
                if reviewer_status not in allowed_reviewer_statuses:
                    errors.append(f"reviewer_status_not_allowed:{reviewer_status}")
                    continue
                records.statuses[(chunk_id, lane_id)] = reviewer_status
            for finding in item.get("findings", []):
                if isinstance(finding, dict):
                    finding = dict(finding)
                    finding.setdefault("chunk_id", chunk_id)
                    finding.setdefault("lane_id", lane_id)
                    records.findings_by_chunk.setdefault(chunk_id, []).append(finding)
        elif "finding_id" in item:
            finding_chunk = item.get("chunk_id")
            if isinstance(finding_chunk, str):
                records.findings_by_chunk.setdefault(finding_chunk, []).append(item)
            else:
                errors.append(f"review_finding_missing_chunk:{index}")
        else:
            errors.append(f"review_record_missing_scope:{index}")
    return records, _dedupe(errors)


def _chunk_ranges(graph_dir: Path) -> dict[str, list[int]]:
    path = graph_dir / "coverage" / "chunk-ledger.json"
    try:
        chunks = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError):
        return {}
    if not isinstance(chunks, list):
        return {}
    ranges = {}
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        chunk_id = chunk.get("chunk_id")
        source_range = chunk.get("source_range")
        if isinstance(chunk_id, str) and isinstance(source_range, list):
            ranges[chunk_id] = source_range
    return ranges


def _review_gate_errors(
    chunk_id: str,
    lane_outputs: list[dict],
    review_statuses: dict[tuple[str, str], str],
    accepted_statuses: set[str],
    *,
    require_review: bool,
) -> list[str]:
    if not require_review:
        return []
    errors: list[str] = []
    for lane_output in lane_outputs:
        lane_id = lane_output.get("lane_id")
        if not isinstance(lane_id, str):
            continue
        status = review_statuses.get((chunk_id, lane_id))
        if status in accepted_statuses:
            continue
        if status is None:
            errors.append(f"review_missing:{chunk_id}:{lane_id}")
        else:
            errors.append(f"review_not_passed:{chunk_id}:{lane_id}:{status}")
    return errors


def _required_lane_errors(required_lane_ids: list[str], lane_outputs: list[dict]) -> list[str]:
    errors: list[str] = []
    by_lane: dict[str, list[dict]] = {}
    for output in lane_outputs:
        lane_id = output.get("lane_id")
        if isinstance(lane_id, str):
            by_lane.setdefault(lane_id, []).append(output)
    for lane_id in required_lane_ids:
        outputs = by_lane.get(lane_id, [])
        if any(output.get("output_status") == "completed" for output in outputs):
            continue
        if any(_has_qualified_structured_failure(output) for output in outputs):
            continue
        errors.append(f"required_lane_missing:{lane_id}")
    return errors


def _has_qualified_structured_failure(output: dict) -> bool:
    failures = output.get("structured_failures")
    return output.get("output_status") in {"blocked", "failed", "needs_repair"} and isinstance(
        failures, list
    ) and bool(failures)


def _reviewed_bundle(
    bundle: dict,
    lane_outputs: list[dict],
    lane_output_paths: list[str],
    *,
    reviewer_status: str | None,
    review_state: str,
    review_policy_mode: str,
) -> dict:
    reviewed = dict(bundle)
    reviewed["ready_for_merge"] = True
    if reviewer_status is not None:
        reviewed["reviewer_status"] = reviewer_status
    else:
        reviewed.pop("reviewer_status", None)
    reviewed["merge_gate_status"] = review_state
    reviewed["review_state"] = review_state
    reviewed["review_policy_mode"] = review_policy_mode
    reviewed["lane_output_paths"] = lane_output_paths
    reviewed["normalized_nodes"] = _flatten_lane_items(lane_outputs, "extracted_nodes")
    reviewed["normalized_edges"] = _flatten_lane_items(lane_outputs, "extracted_edges")
    reviewed["normalized_events"] = _flatten_lane_items(lane_outputs, "extracted_events")
    reviewed["normalized_evidence"] = _flatten_lane_items(lane_outputs, "extracted_evidence")
    return reviewed


def _flatten_lane_items(lane_outputs: list[dict], field: str) -> list[dict]:
    items: list[dict] = []
    for output in lane_outputs:
        values = output.get(field, [])
        if isinstance(values, list):
            items.extend(item for item in values if isinstance(item, dict))
    return items


def _validate_merge_queue(queue: Any) -> tuple[list[str], list[str]]:
    if not isinstance(queue, dict):
        return [], ["merge_queue_invalid"]

    status = queue.get("status")
    if status != "ready":
        return [], ["merge_queue_not_ready"]

    values = queue.get("bundle_paths")
    if not isinstance(values, list) or not values:
        return [], ["merge_queue_invalid"]

    paths: list[str] = []
    errors: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            errors.append("merge_queue_invalid")
            continue
        try:
            paths.append(normalize_relative_output_path(value))
        except OutputWriteError:
            errors.append("merge_queue_invalid")
    if errors:
        return [], _dedupe(errors)
    return paths, []


def _embedded_lane_output_errors(
    bundle: dict,
    *,
    allowed_lane_ids: set[str],
    allowed_statuses: list[str],
) -> list[str]:
    lane_outputs = bundle.get("lane_outputs")
    if not isinstance(lane_outputs, list):
        return ["lane_output_invalid"]

    errors: list[str] = []
    for lane_output in lane_outputs:
        validation = validate_lane_output(
            lane_output,
            allowed_lane_ids=allowed_lane_ids,
            allowed_statuses=allowed_statuses,
            chunk_source_range=bundle.get("source_range"),
        )
        if validation.ok:
            continue
        errors.append("lane_output_invalid")
        errors.extend(validation.errors)
    return _dedupe(errors)


def _required_lane_ids_with_queue_guard(queue: Any, config: dict) -> list[str]:
    configured_lanes = _configured_lanes(config)
    config_required_lane_ids = _required_lane_ids(configured_lanes)
    if not isinstance(queue, dict) or "required_lane_ids" not in queue:
        return config_required_lane_ids

    queue_required_lane_ids = _validated_queue_required_lane_ids(
        queue.get("required_lane_ids"),
        allowed_lane_ids=set(_lane_ids(configured_lanes)),
    )
    missing_config_required_lanes = [
        lane_id
        for lane_id in config_required_lane_ids
        if lane_id not in queue_required_lane_ids
    ]
    if missing_config_required_lanes:
        raise ValueError("merge_queue_invalid")
    return config_required_lane_ids


def _validated_queue_required_lane_ids(values: Any, *, allowed_lane_ids: set[str]) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("merge_queue_invalid")
    lane_ids: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value or value not in allowed_lane_ids:
            raise ValueError("merge_queue_invalid")
        if value not in lane_ids:
            lane_ids.append(value)
    return lane_ids


def _read_json_artifact(
    path: Path,
    *,
    missing_code: str,
    bad_code: str,
) -> tuple[Any | None, dict | None]:
    if not path.exists():
        return None, {"code": missing_code, "path": str(path)}
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except UnicodeError:
        return None, {"code": f"{bad_code}_utf8_decode_error", "path": str(path)}
    except json.JSONDecodeError:
        return None, {"code": f"{bad_code}_json", "path": str(path)}
    except RecursionError:
        return None, {"code": f"{bad_code}_too_deep", "path": str(path)}
    except OSError:
        return None, {"code": bad_code, "path": str(path)}


def _artifact_paths(config: dict) -> dict[str, str]:
    paths = dict(DEFAULT_STAGE1_ARTIFACTS)
    configured = config.get("stage1_artifacts")
    if isinstance(configured, dict):
        for key, value in configured.items():
            if isinstance(value, str) and value:
                paths[key] = value
    return paths


def _managed_outputs(config: dict) -> list[str]:
    configured = list(config.get("writer_policy", {}).get("managed_outputs", []))
    artifacts = _artifact_paths(config)
    derived = [
        artifacts["requirements"],
        artifacts["agent_dispatch_plan"],
        _join_artifact(artifacts["task_packet_dir"], "*", "*.json"),
        _join_artifact(artifacts["template_requirements_part_dir"], "*.json"),
        _join_artifact(artifacts["chunk_text_dir"], "*.txt"),
        _join_artifact(artifacts["lane_output_dir"], "*", "*", "*.json"),
        _join_artifact(artifacts["reviewed_bundle_dir"], "*.json"),
        artifacts["merge_queue"],
        artifacts["review_findings"],
        artifacts["canonical_graph"],
        artifacts["agent_run_ledger"],
    ]
    return _dedupe([*configured, *derived])


def _join_artifact(base: str | Path, *parts: str) -> str:
    normalized = normalize_relative_output_path(base, allow_wildcards=True)
    return PurePosixPath(normalized, *parts).as_posix()


def _artifact_path(graph_dir: Path, relative_path: str | Path) -> Path:
    normalized = normalize_relative_output_path(relative_path)
    return graph_dir / Path(*normalized.split("/"))


def _relative_to_graph(graph_dir: Path, path: Path) -> str:
    return path.relative_to(graph_dir).as_posix()


def _lane_output_statuses(config: dict) -> list[str]:
    statuses = config.get("status_enums", {}).get("lane_output_statuses")
    if isinstance(statuses, list) and all(isinstance(item, str) for item in statuses):
        return statuses
    return ["pending", "completed", "blocked", "failed", "needs_repair"]


def _finding_statuses(config: dict) -> list[str]:
    statuses = config.get("status_enums", {}).get("finding_statuses")
    if isinstance(statuses, list) and all(isinstance(item, str) for item in statuses):
        return statuses
    return ["open", "closed", "waived"]


def _finding_severities(config: dict) -> list[str]:
    severities = config.get("status_enums", {}).get("finding_severities")
    if isinstance(severities, list) and all(isinstance(item, str) for item in severities):
        return severities
    return ["must_fix", "should_fix", "note"]


def _reviewer_statuses(config: dict) -> set[str]:
    statuses = config.get("status_enums", {}).get("reviewer_statuses")
    if isinstance(statuses, list) and all(isinstance(item, str) for item in statuses):
        return {status for status in statuses if status}
    return {"pending", "passed", "failed", "blocked"}


def _accepted_review_statuses(config: dict) -> set[str]:
    accepted_statuses = {"passed"}
    review_policy = config.get("review_policy", {})
    if isinstance(review_policy, dict):
        configured_accepted = review_policy.get("accepted_reviewer_statuses")
        if isinstance(configured_accepted, list) and all(
            isinstance(item, str) for item in configured_accepted
        ):
            accepted_statuses = {status for status in configured_accepted if status}
    return _reviewer_statuses(config) & accepted_statuses


def _require_review_before_merge(config: dict) -> bool:
    review_policy = config.get("review_policy", {})
    if isinstance(review_policy, dict):
        mode = review_policy.get("mode")
        if mode == "pre_merge_required":
            return True
        if mode in {"post_merge_incremental", "disabled"}:
            return False
        return bool(review_policy.get("require_review_before_canonical_merge", True))
    return True


def _review_policy_mode(config: dict) -> str:
    review_policy = config.get("review_policy", {})
    if isinstance(review_policy, dict):
        mode = review_policy.get("mode")
        if mode in {"pre_merge_required", "post_merge_incremental", "disabled"}:
            return mode
        if review_policy.get("require_review_before_canonical_merge") is False:
            return "post_merge_incremental"
    return "pre_merge_required"


def _bundle_review_state(config: dict, *, reviewed: bool) -> str:
    if reviewed:
        return "reviewed_passed"
    review_policy = config.get("review_policy", {})
    if isinstance(review_policy, dict):
        status = review_policy.get("unreviewed_merge_status")
        if isinstance(status, str) and status:
            return status
    return "unreviewed_usable"


def _review_state_summary_from_paths(graph_root: Path, bundle_paths: list[str]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for relative_path in bundle_paths:
        payload, error = _read_json_artifact(
            _artifact_path(graph_root, relative_path),
            missing_code="reviewed_bundle_missing",
            bad_code="reviewed_bundle_invalid",
        )
        if error or not isinstance(payload, dict):
            continue
        state = payload.get("review_state") or payload.get("merge_gate_status")
        if not isinstance(state, str) or not state:
            state = "unknown"
        summary[state] = summary.get(state, 0) + 1
    return summary


def _status_enums_for_merge(config: dict) -> dict:
    status_enums = dict(config.get("status_enums", {}))
    if _require_review_before_merge(config):
        return status_enums
    status_enums.setdefault(
        "bundle_review_statuses",
        [
            "reviewed_passed",
            "unreviewed_usable",
            "needs_incremental_review",
            "review_failed",
        ],
    )
    status_enums.setdefault(
        "graph_review_statuses",
        ["reviewed", "unreviewed_usable", "needs_incremental_review"],
    )
    return status_enums


def _canonical_validation_errors(errors: list[str]) -> list[str]:
    mapped: list[str] = []
    for error in errors:
        if error.startswith(
            (
                "required_lane_missing:",
                "missing_required_lane:",
                "required_lane_not_completed:",
                "required_lane_blocked_by_open_finding:",
                "required_lane_structured_failure:",
            )
        ):
            mapped.append("required_lane_missing")
        mapped.append(error)
    return _dedupe(mapped)


def _stage_result(
    status: str,
    graph_dir: Path,
    warnings: list[dict],
    validation_errors: list[str],
    error: dict | None,
    *,
    next_action: str | None,
    extra: dict | None = None,
) -> dict:
    result = {
        "status": status,
        "graph_dir": str(graph_dir),
        "manifest_written": (graph_dir / "manifest.json").exists(),
        "warnings": warnings,
        "validation_errors": validation_errors,
    }
    if error:
        result["error"] = error
    if next_action:
        result["next_action"] = next_action
    if extra:
        result.update(extra)
    return result


def _failure_response(
    graph_dir: Path | None,
    error: dict,
    manifest_written: bool,
    *,
    validation_errors: list[str] | None = None,
) -> dict:
    return {
        "status": "failed",
        "graph_dir": str(graph_dir) if graph_dir else None,
        "manifest_written": manifest_written,
        "error": error,
        "validation_errors": validation_errors or [error["code"]],
    }


def _error(code: str, exc: Exception) -> dict:
    return {"code": code, "message": str(exc)}


def _exception_code(exc: Exception, fallback: str) -> str:
    text = str(exc)
    if text and text.replace("_", "").replace("-", "").isalnum():
        return text
    return fallback


def _manifest_exists(graph_dir: Path) -> bool:
    return (graph_dir / "manifest.json").exists()


def _read_manifest(graph_dir: Path) -> dict:
    try:
        payload = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _novel_name_from_manifest_or_graph_dir(manifest: dict, graph_dir: Path) -> str:
    novel_name = manifest.get("novel_name")
    if isinstance(novel_name, str) and novel_name:
        return novel_name
    stem = graph_dir.stem
    return stem.removesuffix(".storygraph") or stem


def _update_manifest_stage(manifest_path: Path, stage1_status: str) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stage_status = manifest.setdefault("stage_status", {})
    stage_status["stage1"] = stage1_status
    stage_status.setdefault("stage2", "not_requested")
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _remove_graphify_artifacts(graph_dir: Path) -> None:
    for relative in [
        "graphify-out/graph.json",
        "graphify-out/GRAPH_REPORT.md",
        "graphify-out/graph.html",
    ]:
        path = graph_dir / Path(*relative.split("/"))
        if path.exists() and path.is_file():
            path.unlink()
        elif path.exists() and path.is_dir():
            shutil.rmtree(path)


def _stable_json_hash(value: Any) -> str:
    return sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _template_inventory_hash(templates: list) -> str:
    inventory = [
        {
            "template_name": template.name,
            "template_file": str(template.path),
            "template_file_hash": template.file_hash,
        }
        for template in templates
    ]
    return _stable_json_hash(inventory)


def _task_packet_schema_hash(config: dict) -> str:
    relevant = {
        "element_lanes": config.get("element_lanes"),
        "stage1_artifacts": config.get("stage1_artifacts"),
        "lane_output_statuses": config.get("status_enums", {}).get("lane_output_statuses"),
    }
    return _stable_json_hash(relevant)


def _directory_content_hash(root: Path) -> str | None:
    if not root.exists() or not root.is_dir():
        return None
    excluded_dirs = {".git", "__pycache__", ".pytest_cache", "node_modules", "graphify-out"}
    h = sha256()
    file_count = 0
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative_parts = path.relative_to(root).parts
        if any(part in excluded_dirs or part.endswith(".storygraph") for part in relative_parts):
            continue
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(root).as_posix()
            data = path.read_bytes()
        except OSError:
            continue
        h.update(relative.encode("utf-8"))
        h.update(b"\0")
        h.update(sha256(data).digest())
        file_count += 1
    h.update(f"files:{file_count}".encode("utf-8"))
    return h.hexdigest()


def _executable_fingerprint(command: object) -> dict:
    if not isinstance(command, list) or not command or not isinstance(command[0], str):
        return {}
    executable = command[0]
    resolved = shutil.which(executable) or executable
    version = None
    try:
        completed = subprocess.run(
            [resolved, "--version"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        completed = None
    if completed is not None and completed.returncode == 0:
        version = (completed.stdout or completed.stderr).strip().splitlines()[:1]
    return {"executable": executable, "resolved": resolved, "version": version}


def _graphify_adapter(config: dict) -> GraphifyAdapter:
    adapter_config, adapter_config_error = _graphify_adapter_config(config)
    repo_value = config.get("paths", {}).get("graphify_repo")
    return GraphifyAdapter(
        Path(repo_value) if repo_value else None,
        adapter_config.get("command", []),
        adapter_config.get("timeout_seconds", 1800),
        adapter_config.get("mode", "local-repo-or-cli"),
        failure_policy=adapter_config.get("failure_policy", "blocking"),
        input_strategy=adapter_config.get(
            "input_strategy", "canonical-graph-or-graph-dir-only"
        ),
        config_error=adapter_config_error,
    )


def _graphify_adapter_enabled(config: dict) -> bool:
    return "graphify_adapter" in config


def _graphify_failure_policy(config: dict) -> str:
    adapter_config = config.get("graphify_adapter")
    if isinstance(adapter_config, dict):
        policy = adapter_config.get("failure_policy")
        if isinstance(policy, str) and policy:
            return policy
    return "blocking"


def _graphify_input_strategy(config: dict) -> str:
    adapter_config = config.get("graphify_adapter")
    if isinstance(adapter_config, dict):
        strategy = adapter_config.get("input_strategy")
        if isinstance(strategy, str) and strategy:
            return strategy
    return "canonical-graph-or-graph-dir-only"


def _graph_with_graphify_metadata(graph: dict, config: dict) -> dict:
    metadata = graph.setdefault("metadata", {})
    if isinstance(metadata, dict):
        metadata["graphify_input_strategy"] = _graphify_input_strategy(config)
        metadata.pop("source_semantic_base_graph", None)
    return graph


def _write_graphify_adapter_ledger(
    graph_dir: Path,
    config: dict,
    graphify_result,
    *,
    input_path: str,
) -> None:
    artifacts = _artifact_paths(config)
    ledger_path = _artifact_path(graph_dir, artifacts["agent_run_ledger"])
    records: list[dict] = []
    if ledger_path.exists():
        existing, existing_error = _read_json_artifact(
            ledger_path,
            missing_code="agent_run_ledger_missing",
            bad_code="agent_run_ledger_invalid",
        )
        if existing_error is None and isinstance(existing, list):
            records = [record for record in existing if isinstance(record, dict)]

    graphify_output_dir = PurePosixPath(input_path).parent
    output_paths = [
        graphify_output_dir.joinpath("GRAPH_REPORT.md").as_posix(),
        graphify_output_dir.joinpath("graph.html").as_posix(),
    ]
    now = datetime.now(timezone.utc).isoformat()
    error = graphify_result.error if not graphify_result.ok else None
    status = "completed" if graphify_result.ok else "failed"
    errors = [error] if error else []
    warnings = list(graphify_result.warnings)
    if _graphify_failure_policy(config) == "degrade-visualization-and-query":
        status = "completed"
        if not graphify_result.ok:
            warnings = _dedupe(
                [
                    *[warning for warning in warnings if isinstance(warning, str)],
                    _graphify_error_code(error),
                ]
            )
    records.append(
        {
            "run_id": "stage1-graphify-adapter",
            "stage": "stage1",
            "chunk_id": "graphify-adapter",
            "lane_id": "graphify_adapter",
            "agent_role": "graphify-adapter",
            "prompt_or_input_packet": input_path,
            "input_paths": [input_path],
            "output_paths": output_paths,
            "write_scope": output_paths,
            "status": status,
            "errors": errors,
            "warnings": warnings,
            "command": list(graphify_result.command),
            "reviewer_status": "passed",
            "started_at": now,
            "finished_at": now,
        }
    )
    OutputWriter(graph_dir, _managed_outputs(config)).write_json(
        artifacts["agent_run_ledger"], records
    )


def _graphify_error_code(error: dict | None) -> str:
    if isinstance(error, dict) and isinstance(error.get("code"), str):
        return error["code"]
    return "graphify_failed"


def _graphify_adapter_config(config: dict) -> tuple[dict, dict | None]:
    adapter_config = config.get("graphify_adapter", {})
    if isinstance(adapter_config, dict):
        return adapter_config, None
    return {}, {
        "code": "graphify_bad_command",
        "field": "graphify_adapter",
        "message": "graphify_adapter must be an object",
    }


def _read_graphify_artifacts(graph_path: Path, output_dir: Path) -> tuple[dict | None, dict | None]:
    try:
        base_graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        return None, _artifact_error("graphify_failed", "graph.json", exc)
    if not isinstance(base_graph, dict):
        return None, {
            "code": "graphify_failed",
            "artifact": "graph.json",
            "message": "graph.json must contain a JSON object",
        }
    if "metadata" in base_graph and not isinstance(base_graph["metadata"], dict):
        return None, {
            "code": "graphify_failed",
            "artifact": "graph.json",
            "message": "graph.json field metadata must be an object",
        }
    for key in ["nodes", "edges", "hyperedges", "events", "evidence_index"]:
        if key in base_graph and not isinstance(base_graph[key], list):
            return None, {
                "code": "graphify_failed",
                "artifact": "graph.json",
                "message": f"graph.json field {key} must be a list",
            }
        if key in base_graph and any(not isinstance(item, dict) for item in base_graph[key]):
            return None, {
                "code": "graphify_failed",
                "artifact": "graph.json",
                "message": f"graph.json field {key} must contain objects",
            }
    report, report_error = _read_utf8_artifact(output_dir, "GRAPH_REPORT.md")
    if report_error:
        return None, report_error
    html, html_error = _read_utf8_artifact(output_dir, "graph.html")
    if html_error:
        return None, html_error
    return {"graph": base_graph, "report": report, "html": html}, None


def _read_utf8_artifact(output_dir: Path, artifact: str) -> tuple[str | None, dict | None]:
    try:
        return (output_dir / artifact).read_text(encoding="utf-8"), None
    except (OSError, UnicodeDecodeError) as exc:
        return None, _artifact_error("graphify_failed", artifact, exc)


def _artifact_error(code: str, artifact: str, exc: Exception) -> dict:
    return {"code": code, "artifact": artifact, "message": str(exc)}


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
