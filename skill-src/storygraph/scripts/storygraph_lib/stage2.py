from __future__ import annotations

import json
from pathlib import Path

from .output_writer import OutputWriteError, OutputWriter, normalize_relative_output_path
from .stage2_evidence import evidence_by_id, evidence_id_set, evidence_ids_for_category
from .stage2_render import render_template_draft
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
) -> dict:
    graph_dir = Path(graph_dir)
    template_dir = Path(template_dir)
    artifacts = _stage2_artifacts(config)
    writer = _writer(graph_dir, config)
    requirements = _read_json(graph_dir / "requirements" / "template-requirements.json")
    stage1_cache = _read_json(graph_dir / "intermediate" / "stage1-input-cache.json")
    evidence_index = _read_json(graph_dir / "coverage" / "evidence-index.json")
    templates = discover_stage2_templates(template_dir, config)
    template_errors = assert_templates_match_stage1_cache(templates, stage1_cache)
    if template_errors:
        return {"status": "failed", "error": "template_cache_mismatch", "errors": template_errors}

    templates_by_name = {template["template_name"]: template for template in templates}
    batches = []
    categories = requirements.get("categories", []) if isinstance(requirements, dict) else []
    record_root = artifacts["extraction_record_dir"]
    for category in categories:
        category_id = category.get("category_id")
        if not category_id:
            continue
        category_templates = []
        for template_name in category.get("template_coverage", []):
            template = templates_by_name.get(template_name)
            if template:
                category_templates.append(template)
        if not category_templates:
            continue
        expected_rel_paths = [
            f"{record_root}/{template['template_name']}/run-001.json"
            for template in category_templates
        ]
        batches.append(
            {
                "batch_id": category_id,
                "category_id": category_id,
                "category_name": category.get("category_name"),
                "agent_role": config.get("stage2_agent_orchestration", {}).get(
                    "agent_role", "stage2-template-document-agent"
                ),
                "status": "pending",
                "templates": category_templates,
                "requirements": {
                    "required_extraction_targets": category.get(
                        "required_extraction_targets", []
                    ),
                    "evidence_requirements": category.get("evidence_requirements", []),
                },
                "evidence_ids": evidence_ids_for_category(
                    evidence_index,
                    category_id,
                    [template["template_name"] for template in category_templates],
                ),
                "expected_output_rel_paths": expected_rel_paths,
                "expected_output_paths": [
                    str((graph_dir / Path(*rel.split("/"))).resolve())
                    for rel in expected_rel_paths
                ],
            }
        )

    for batch in batches:
        packet = dict(batch)
        packet["schema"] = "stage2-task-packet.v1"
        writer.write_json(f"{artifacts['task_packet_dir']}/{batch['batch_id']}.json", packet)

    state = _dispatch_state(batches)
    writer.write_json(artifacts["dispatch_state"], state)
    writer.write_json(TEMPLATE_RUN_LEDGER, _template_run_ledger(templates, batches))
    writer.write_json(TEMPLATE_EVIDENCE_USAGE, _template_evidence_usage(batches))
    writer.write_text(TEMPLATE_GAP_REPORT, "# Stage 2 Template Gap Report\n\n")
    _update_manifest_stage2(graph_dir, "prepared")
    return {
        "status": "prepared",
        "batch_count": len(batches),
        "template_count": len(templates),
        "overwrite_policy": overwrite_policy or config.get("overwrite_policy", "draft"),
    }


def inspect_stage2_dispatch(graph_dir: str | Path, config: dict | None = None) -> dict:
    graph_dir = Path(graph_dir)
    artifacts = _stage2_artifacts(config or {})
    return _read_json(graph_dir / Path(*artifacts["dispatch_state"].split("/")))


def claim_stage2_batches(graph_dir: str | Path, limit: int, config: dict | None = None) -> dict:
    graph_dir = Path(graph_dir)
    artifacts = _stage2_artifacts(config or {})
    state_path = graph_dir / Path(*artifacts["dispatch_state"].split("/"))
    state = _read_json(state_path)
    writer = _writer(graph_dir, config or {})
    evidence_index = _read_json(graph_dir / "coverage" / "evidence-index.json")
    known_evidence = evidence_id_set(evidence_index)
    for batch in state.get("batches", []):
        if batch.get("status") == "running":
            outputs_valid, output_errors = _batch_outputs_valid(
                graph_dir,
                batch,
                known_evidence,
            )
            if outputs_valid:
                batch["status"] = "completed"
                batch["errors"] = []
            elif output_errors:
                batch["errors"] = output_errors
    available = max(0, limit - _count_status(state, "running"))
    claimed = []
    for batch in state.get("batches", []):
        if available <= 0:
            break
        if batch.get("status") == "pending":
            batch["status"] = "running"
            claimed.append(batch)
            available -= 1
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


def ingest_stage2(graph_dir: str | Path, config: dict) -> dict:
    graph_dir = Path(graph_dir)
    writer = _writer(graph_dir, config)
    state = inspect_stage2_dispatch(graph_dir, config)
    evidence_index = _read_json(graph_dir / "coverage" / "evidence-index.json")
    known_evidence = evidence_id_set(evidence_index)
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
                evidence_ids=known_evidence,
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
    graph_dir = Path(graph_dir)
    writer = _writer(graph_dir, config)
    ledger = _read_json(graph_dir / TEMPLATE_RUN_LEDGER)
    evidence_index = _read_json(graph_dir / "coverage" / "evidence-index.json")
    evidence_lookup = evidence_by_id(evidence_index)
    review_status = _stage1_review_status(graph_dir)
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
        validation = validate_extraction_record(
            record,
            evidence_ids=set(evidence_lookup),
            require_document_sections=True,
        )
        if not validation.ok:
            record_errors.extend(
                f"{normalized_rel_path}:{error}" for error in validation.errors
            )
            continue
        decision = resolve_render_target(
            graph_dir,
            _novel_dir(graph_dir),
            record["template_name"],
            config["stage2_output_policy"],
            record.get("overwrite_policy", config.get("overwrite_policy", "draft")),
        )
        try:
            relative_target = _relative_to_graph(graph_dir, Path(decision["target_path"]))
        except ValueError:
            return {
                "status": "failed",
                "error": "formal_render_requires_merge_contract",
                "template_name": record["template_name"],
                "target_path": decision["target_path"],
            }
        text = render_template_draft(
            record,
            evidence_lookup,
            config.get("stage2_render_policy", {}),
            review_status=review_status,
        )
        writer.write_text(relative_target, text)
        rendered.append(relative_target)
    if record_errors:
        return {
            "status": "failed",
            "error": "stage2_record_validation_failed",
            "errors": record_errors,
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
    try:
        evidence_index = _read_json(graph_dir / "coverage" / "evidence-index.json")
    except FileNotFoundError:
        return {"ok": False, "errors": ["evidence_index_missing"]}
    except Stage2ArtifactError as exc:
        return {"ok": False, "errors": [f"evidence_index_invalid:{exc.code}:{exc.detail}"]}
    known_evidence = evidence_id_set(evidence_index)
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
            evidence_ids=known_evidence,
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
    evidence_ids: set[str],
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
            evidence_ids=evidence_ids,
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
