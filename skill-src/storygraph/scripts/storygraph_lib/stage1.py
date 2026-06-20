from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from .agent_ledger import make_stage_agent_records, validate_single_writer
from .coverage import make_chunk_ledger, write_coverage_outputs
from .graph_schema import merge_template_supplements, validate_canonical_graph
from .graphify_adapter import GraphifyAdapter
from .manifest import write_manifest
from .output_writer import OutputWriter
from .paths import resolve_novel_context
from .state import stage1_state
from .template_aware import extract_template_aware_supplements
from .templates import build_requirement_matrix, discover_templates
from .validation import validate_graph_dir


@dataclass(frozen=True)
class PreflightNovelContext:
    source_path: Path
    source_hash: str | None
    source_size: int
    novel_name: str
    novel_dir: Path
    graph_dir: Path


def _infer_novel_context_without_reading(
    source_path: Path,
    graph_dir_suffix: str,
    create: bool = False,
) -> PreflightNovelContext:
    source = Path(source_path).expanduser().resolve(strict=False)
    if not source.name or source.name in {".", ".."}:
        raise OSError("cannot infer graph directory from source path")
    graph_dir = source.parent / f"{source.stem}{graph_dir_suffix}"
    if create:
        graph_dir.mkdir(parents=True, exist_ok=True)
    return PreflightNovelContext(
        source_path=source,
        source_hash=None,
        source_size=0,
        novel_name=source.stem,
        novel_dir=source.parent,
        graph_dir=graph_dir,
    )


def build_stage1_graph(source_path: str | Path, config: dict) -> dict:
    graph_dir_suffix = config.get("graph_dir_suffix", ".storygraph")
    try:
        preflight_ctx = _infer_novel_context_without_reading(
            Path(source_path), graph_dir_suffix, create=True
        )
    except (OSError, ValueError) as exc:
        error = {"code": "source_unreadable", "message": str(exc), "source_path": str(source_path)}
        return _failure_response(None, error, manifest_written=False)

    try:
        ctx = resolve_novel_context(Path(source_path), graph_dir_suffix, create=True)
    except UnicodeDecodeError as exc:
        error = _error("source_encoding_error", exc, preflight_ctx.source_path)
        _write_preflight_failure(preflight_ctx, config, error)
        return _failure_response(preflight_ctx.graph_dir, error, manifest_written=True)
    except (FileNotFoundError, PermissionError, OSError) as exc:
        error = _error("source_unreadable", exc, preflight_ctx.source_path)
        _write_preflight_failure(preflight_ctx, config, error)
        return _failure_response(preflight_ctx.graph_dir, error, manifest_written=True)

    try:
        discovery = _discover_templates(config)
        matrix = _build_matrix(discovery.templates, config)
    except Exception as exc:
        error = {"code": getattr(exc, "code", "template_discovery_failed"), "message": str(exc)}
        _write_preflight_failure(preflight_ctx, config, error, role="模板需求分析")
        return _failure_response(preflight_ctx.graph_dir, error, manifest_written=True)

    config_hash = stable_stage_input_hash(ctx, config, discovery.templates)
    current_state = stage1_state(ctx, config_hash, validate_graph_dir)
    if current_state["action"] == "reuse":
        return {
            "status": "reused",
            "source_state": "unchanged",
            "graph_dir": str(ctx.graph_dir),
            "manifest_written": False,
            "validation_errors": [],
            "warnings": discovery.warnings,
        }

    _remove_graphify_artifacts(ctx.graph_dir)
    manifest_path = write_manifest(
        ctx,
        config_hash=config_hash,
        graphify_source=str(config.get("paths", {}).get("graphify_repo")),
    )
    writer = OutputWriter(ctx.graph_dir, _managed_outputs(config))
    writer.write_json("requirements/template-requirements.json", matrix)

    try:
        chunks = make_chunk_ledger(
            ctx.source_path,
            config.get("chunk_strategy", {}),
            processor="storygraph-stage1",
        )
    except UnicodeDecodeError as exc:
        error = _error("source_encoding_error", exc, ctx.source_path)
        _write_chunk_failure(ctx, config, manifest_path, matrix, error, current_state["source_state"])
        return _failure_response(ctx.graph_dir, error, manifest_written=True)
    except Exception as exc:
        error = _error("chunk_extraction_failure", exc, ctx.source_path)
        _write_chunk_failure(ctx, config, manifest_path, matrix, error, current_state["source_state"])
        return _failure_response(ctx.graph_dir, error, manifest_written=True)

    agent_runs = make_stage_agent_records(
        [chunk["chunk_id"] for chunk in chunks],
        [record["template_name"] for record in matrix["templates"]],
    )
    single_writer = validate_single_writer(agent_runs)
    if not single_writer.ok:
        errors = [{"code": "single_writer_conflict", "detail": detail} for detail in single_writer.errors]
        for error in errors:
            _append_error(agent_runs, "质量审查", error)
        write_coverage_outputs(
            writer,
            _complete_pending_chunks(chunks),
            [],
            [],
            agent_runs,
            [f"- single_writer_conflict: {error['detail']}" for error in errors],
        )
        _update_manifest_stage(manifest_path, "failed")
        _remove_graphify_artifacts(ctx.graph_dir)
        return _stage_result(
            "failed",
            current_state["source_state"],
            ctx.graph_dir,
            discovery.warnings,
            ["single_writer_conflict"],
            errors[0],
        )

    try:
        supplement, readiness = extract_template_aware_supplements(
            ctx.novel_name,
            ctx.source_path,
            chunks,
            matrix,
            config.get("evidence_matching_strategy", {}),
        )
    except UnicodeDecodeError as exc:
        error = _error("source_encoding_error", exc, ctx.source_path)
        _append_error(agent_runs, "图抽取", error)
        write_coverage_outputs(
            writer,
            _failed_chunks_from_error(ctx, error),
            [],
            _empty_readiness(matrix, "source_encoding_error"),
            agent_runs,
            [f"- source_encoding_error: {error['message']}"],
        )
        _update_manifest_stage(manifest_path, "failed")
        _remove_graphify_artifacts(ctx.graph_dir)
        return _failure_response(ctx.graph_dir, error, manifest_written=True)

    chunks = _complete_pending_chunks(chunks)
    gap_lines = [f"- warning: {warning}" for warning in discovery.warnings]
    contract_errors, contract_warnings = _evaluate_coverage_failures(
        readiness, chunks, config, agent_runs, gap_lines
    )
    subagent_errors, subagent_warnings = _parse_subagent_payloads(config, agent_runs, gap_lines)
    contract_errors.extend(subagent_errors)
    contract_warnings.extend(subagent_warnings)

    graph_validation_errors: list[str] = []
    adapter_error: dict | None = None
    adapter = _graphify_adapter(config)
    adapter_result = adapter.build_graph(ctx.source_path, ctx.graph_dir / "graphify-out")
    if not adapter_result.ok:
        adapter_error = adapter_result.error or {"code": "graphify_failed"}
        _append_error(agent_runs, "图抽取", adapter_error)
        gap_lines.append(f"- {adapter_error['code']}: graphify")
        _remove_graphify_artifacts(ctx.graph_dir)
    else:
        artifacts, artifact_error = _read_graphify_artifacts(
            adapter_result.graph_path,
            ctx.graph_dir / "graphify-out",
        )
        if artifact_error:
            adapter_error = artifact_error
            _append_error(agent_runs, "图抽取", adapter_error)
            gap_lines.append(f"- {adapter_error['code']}: {adapter_error.get('message', '')}")
            _remove_graphify_artifacts(ctx.graph_dir)
        else:
            graph = merge_template_supplements(artifacts["graph"], supplement)
            validation = validate_canonical_graph(graph, config.get("status_enums"))
            graph_validation_errors = validation.errors
            if graph_validation_errors:
                adapter_error = {
                    "code": "graphify_failed",
                    "message": "merged graph failed canonical validation",
                    "validation_errors": graph_validation_errors,
                }
                _append_error(agent_runs, "图抽取", adapter_error)
                gap_lines.append("- graphify_failed: merged graph failed canonical validation")
                _remove_graphify_artifacts(ctx.graph_dir)
            else:
                writer.write_json("graphify-out/graph.json", graph)
                writer.write_text("graphify-out/GRAPH_REPORT.md", artifacts["report"])
                writer.write_text("graphify-out/graph.html", artifacts["html"])

    validation_errors = [
        *(error["code"] for error in contract_errors),
        *(error["code"] for error in contract_warnings),
        *graph_validation_errors,
    ]
    if adapter_error:
        validation_errors.insert(0, adapter_error["code"])

    status = _stage_status(adapter_error, contract_errors, contract_warnings, graph_validation_errors)
    if status in {"success", "warning"}:
        _mark_completed(agent_runs)

    if graph_validation_errors:
        gap_lines = [f"- validation error: {error}" for error in graph_validation_errors] + gap_lines
    write_coverage_outputs(
        writer,
        chunks,
        supplement.get("evidence_index", []),
        readiness,
        agent_runs,
        gap_lines,
    )
    _update_manifest_stage(manifest_path, status)
    error = None
    if status == "failed":
        if adapter_error:
            error = adapter_error
        elif contract_errors:
            error = contract_errors[0]
        elif graph_validation_errors:
            error = {"code": graph_validation_errors[0]}
    return _stage_result(
        status,
        current_state["source_state"],
        ctx.graph_dir,
        discovery.warnings,
        validation_errors,
        error,
    )


def graphify_source_fingerprint(config: dict) -> dict:
    repo_value = config.get("paths", {}).get("graphify_repo")
    repo = Path(repo_value) if repo_value else None
    commit = None
    tree_hash = None
    dirty_status = None
    dirty_diff_hash = None
    repo_content_hash = None
    if repo and (repo / ".git").exists():
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            commit = completed.stdout.strip()
        tree = subprocess.run(
            ["git", "rev-parse", "HEAD^{tree}"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if tree.returncode == 0:
            tree_hash = tree.stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z"],
            cwd=repo,
            capture_output=True,
        )
        if status.returncode == 0:
            dirty_status = sha256(status.stdout).hexdigest()
        diff = subprocess.run(
            ["git", "diff", "--binary", "HEAD"],
            cwd=repo,
            capture_output=True,
        )
        if diff.returncode == 0:
            dirty_diff_hash = sha256(diff.stdout).hexdigest()
        repo_content_hash = _directory_content_hash(repo)
    elif repo and repo.exists():
        repo_content_hash = _directory_content_hash(repo)
    adapter_config = config.get("graphify_adapter", {})
    command = adapter_config.get("command", [])
    return {
        "graphify_repo": str(repo) if repo else None,
        "graphify_commit": commit,
        "graphify_tree_hash": tree_hash,
        "graphify_dirty_status": dirty_status,
        "graphify_dirty_diff_hash": dirty_diff_hash,
        "graphify_content_hash": repo_content_hash,
        "adapter_mode": adapter_config.get("mode"),
        "adapter_command": command,
        "adapter_timeout_seconds": adapter_config.get("timeout_seconds"),
        "adapter_executable": _executable_fingerprint(command),
    }


def stable_stage_input_hash(ctx, config: dict, templates: list) -> str:
    relevant = {
        "source_hash": ctx.source_hash,
        "config": config,
        "graphify_source": graphify_source_fingerprint(config),
        "templates": [
            {
                "template_name": template.name,
                "template_file": str(template.path),
                "template_file_hash": template.file_hash,
            }
            for template in templates
        ],
    }
    return sha256(
        json.dumps(relevant, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _discover_templates(config: dict):
    template_config = config.get("template_discovery", {})
    return discover_templates(
        Path(config.get("paths", {}).get("template_dir")),
        glob=template_config.get("glob", "*模板.md"),
        readme_index_file=template_config.get("readme_index_file", "README.md"),
        exclude_files=template_config.get("exclude_files", []),
        readme_missing_policy=template_config.get("readme_missing_policy", "warn"),
    )


def _build_matrix(templates: list, config: dict) -> dict:
    matrix = build_requirement_matrix(
        templates,
        rules=config.get("template_parser_rules"),
        mappings=config.get("template_graph_mappings", {}),
        status_enums=config.get("status_enums"),
        output_language=config.get("output_language", "zh-CN"),
    )
    matrix["template_count_policy"] = config.get("template_count_policy", {})
    matrix["status_enums"] = config.get("status_enums", {})
    count_policy = matrix["template_count_policy"]
    expected = count_policy.get("expected_existing_templates")
    if count_policy.get("enforce_integration_count") and expected is not None:
        matrix["count_matches_expected"] = matrix["template_count"] == expected
        if matrix["template_count"] != expected:
            raise ValueError(f"template_count_mismatch:{matrix['template_count']}:{expected}")
    return matrix


def _graphify_adapter(config: dict) -> GraphifyAdapter:
    adapter_config = config.get("graphify_adapter", {})
    repo_value = config.get("paths", {}).get("graphify_repo")
    return GraphifyAdapter(
        Path(repo_value) if repo_value else None,
        adapter_config.get("command", []),
        adapter_config.get("timeout_seconds", 1800),
        adapter_config.get("mode", "local-repo-or-cli"),
    )


def _read_graphify_artifacts(graph_path: Path, output_dir: Path) -> tuple[dict | None, dict | None]:
    try:
        base_graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
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
    try:
        report = (output_dir / "GRAPH_REPORT.md").read_text(encoding="utf-8")
        html = (output_dir / "graph.html").read_text(encoding="utf-8")
    except OSError as exc:
        artifact = "GRAPH_REPORT.md" if "GRAPH_REPORT.md" in str(exc) else "graph.html"
        return None, _artifact_error("graphify_failed", artifact, exc)
    return {"graph": base_graph, "report": report, "html": html}, None


def _artifact_error(code: str, artifact: str, exc: Exception) -> dict:
    return {"code": code, "artifact": artifact, "message": str(exc)}


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


def _managed_outputs(config: dict) -> list[str]:
    return list(config.get("writer_policy", {}).get("managed_outputs", []))


def _error(code: str, exc: Exception, source_path: Path) -> dict:
    return {"code": code, "message": str(exc), "source_path": str(source_path)}


def _failure_response(graph_dir: Path | None, error: dict, manifest_written: bool) -> dict:
    return {
        "status": "failed",
        "source_state": "unknown",
        "graph_dir": str(graph_dir) if graph_dir else None,
        "manifest_written": manifest_written,
        "error": error,
        "validation_errors": [error["code"]],
    }


def _stage_result(
    status: str,
    source_state: str,
    graph_dir: Path,
    warnings: list[dict],
    validation_errors: list[str],
    error: dict | None,
) -> dict:
    result = {
        "status": status,
        "source_state": source_state,
        "graph_dir": str(graph_dir),
        "manifest_written": True,
        "warnings": warnings,
        "validation_errors": validation_errors,
    }
    if error:
        result["error"] = error
    return result


def _write_preflight_failure(
    ctx: PreflightNovelContext,
    config: dict,
    error: dict,
    role: str = "图抽取",
) -> None:
    _remove_graphify_artifacts(ctx.graph_dir)
    writer = OutputWriter(ctx.graph_dir, _managed_outputs(config))
    manifest = {
        "source_path": str(ctx.source_path),
        "source_hash": ctx.source_hash,
        "source_size": ctx.source_size,
        "novel_name": ctx.novel_name,
        "graph_dir": str(ctx.graph_dir),
        "config_hash": None,
        "graphify_repo": str(config.get("paths", {}).get("graphify_repo")),
        "graphify_version_or_commit": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "stage_status": {"stage1": "failed", "stage2": "not_requested"},
    }
    chunks = _failed_chunks_from_error(ctx, error)
    agent_runs = make_stage_agent_records([chunks[0]["chunk_id"]], [])
    _append_error(agent_runs, role, error)
    writer.write_json("manifest.json", manifest)
    write_coverage_outputs(
        writer,
        chunks,
        [],
        [],
        agent_runs,
        [f"- {error['code']}: {error.get('message', '')}"],
    )


def _write_chunk_failure(
    ctx,
    config: dict,
    manifest_path: Path,
    matrix: dict,
    error: dict,
    source_state: str,
) -> None:
    writer = OutputWriter(ctx.graph_dir, _managed_outputs(config))
    chunks = _failed_chunks_from_error(ctx, error)
    readiness = _empty_readiness(matrix, error["code"])
    agent_runs = make_stage_agent_records(
        [chunks[0]["chunk_id"]],
        [record["template_name"] for record in matrix.get("templates", [])],
    )
    _append_error(agent_runs, "图抽取", error)
    write_coverage_outputs(
        writer,
        chunks,
        [],
        readiness,
        agent_runs,
        [f"- {error['code']}: {error.get('message', '')}", f"- source_state: {source_state}"],
    )
    _update_manifest_stage(manifest_path, "failed")
    _remove_graphify_artifacts(ctx.graph_dir)


def _failed_chunks_from_error(ctx, error: dict) -> list[dict]:
    return [
        {
            "chunk_id": "chunk-0001",
            "source_path": str(ctx.source_path),
            "source_range": [0, int(getattr(ctx, "source_size", 0) or 0)],
            "chapter_hint": None,
            "hash": None,
            "scanned_at": None,
            "processor": "storygraph-stage1",
            "extraction_status": "failed",
            "failure": error,
            "retry_count": 0,
        }
    ]


def _empty_readiness(matrix: dict, code: str) -> list[dict]:
    return [
        {
            "template_name": record["template_name"],
            "readiness_score": 0,
            "supporting_node_count": 0,
            "supporting_edge_count": 0,
            "supporting_event_count": 0,
            "evidence_count": 0,
            "missing_requirement_types": [code],
            "requirement_statuses": [],
            "notes": [code],
        }
        for record in matrix.get("templates", [])
    ]


def _append_error(agent_runs: list[dict], role: str, error: dict) -> None:
    target = next((record for record in agent_runs if record.get("agent_role") == role), None)
    if target is None and agent_runs:
        target = agent_runs[-1]
    if target is None:
        return
    target["status"] = "failed"
    target.setdefault("errors", []).append(error)


def _mark_completed(agent_runs: list[dict]) -> None:
    for record in agent_runs:
        if record.get("status") == "pending":
            record["status"] = "completed"
            record["reviewer_status"] = "passed"


def _complete_pending_chunks(chunks: list[dict]) -> list[dict]:
    for chunk in chunks:
        if chunk.get("extraction_status") == "pending":
            chunk["extraction_status"] = "completed"
    return chunks


def _parse_subagent_payloads(
    config: dict, agent_runs: list[dict], gap_lines: list[str]
) -> tuple[list[dict], list[dict]]:
    errors = []
    warnings = []
    blocking = config.get("coverage_thresholds", {}).get("block_on_unparsable_subagent_json", True)
    for index, payload in enumerate(config.get("agent_policy", {}).get("sub_agent_json_payloads", []), 1):
        try:
            json.loads(payload)
        except json.JSONDecodeError as exc:
            error = {
                "code": "unparsable_subagent_json",
                "payload_index": index,
                "message": str(exc),
            }
            gap_lines.append(f"- unparsable_subagent_json: payload {index}")
            if blocking:
                errors.append(error)
                _append_error(agent_runs, "质量审查", error)
            else:
                warnings.append(error)
    return errors, warnings


def _evaluate_coverage_failures(
    readiness: list[dict],
    chunks: list[dict],
    config: dict,
    agent_runs: list[dict],
    gap_lines: list[str],
) -> tuple[list[dict], list[dict]]:
    errors = []
    warnings = []
    thresholds = config.get("coverage_thresholds", {})
    readiness_threshold = thresholds.get("readiness_warning_threshold", 0)
    for record in readiness:
        score = record.get("readiness_score", 0)
        if score < readiness_threshold:
            error = {
                "code": "readiness_below_threshold",
                "template_name": record.get("template_name"),
                "readiness_score": score,
                "threshold": readiness_threshold,
            }
            gap_lines.append(
                f"- readiness_below_threshold: {record.get('template_name')} {score} < {readiness_threshold}"
            )
            if thresholds.get("block_on_low_readiness", True):
                errors.append(error)
                _append_error(agent_runs, "覆盖审查", error)
            else:
                warnings.append(error)
        if record.get("evidence_count", 0) == 0:
            error = {
                "code": "template_without_reliable_evidence",
                "template_name": record.get("template_name"),
            }
            gap_lines.append(f"- template_without_reliable_evidence: {record.get('template_name')}")
            if thresholds.get("block_on_template_without_reliable_evidence", True):
                errors.append(error)
                _append_error(agent_runs, "覆盖审查", error)
            else:
                warnings.append(error)

    if thresholds.get("require_all_chunks_scanned", True):
        for chunk in chunks:
            if chunk.get("extraction_status") != "completed":
                error = {
                    "code": "chunk_extraction_failure",
                    "chunk_id": chunk.get("chunk_id"),
                    "failure": chunk.get("failure"),
                }
                errors.append(error)
                gap_lines.append(f"- chunk_extraction_failure: {chunk.get('chunk_id')}")
                _append_error(agent_runs, "图抽取", error)
    return errors, warnings


def _stage_status(
    adapter_error: dict | None,
    contract_errors: list[dict],
    contract_warnings: list[dict],
    graph_validation_errors: list[str],
) -> str:
    if adapter_error or contract_errors or graph_validation_errors:
        return "failed"
    if contract_warnings:
        return "warning"
    return "success"


def _update_manifest_stage(manifest_path: Path, stage1_status: str) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stage_status = manifest.setdefault("stage_status", {})
    stage_status["stage1"] = stage1_status
    stage_status.setdefault("stage2", "not_requested")
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _remove_graphify_artifacts(graph_dir: Path) -> None:
    for relative in ["graphify-out/graph.json", "graphify-out/GRAPH_REPORT.md", "graphify-out/graph.html"]:
        path = graph_dir / Path(*relative.split("/"))
        if path.exists() and path.is_file():
            path.unlink()
        elif path.exists() and path.is_dir():
            shutil.rmtree(path)
