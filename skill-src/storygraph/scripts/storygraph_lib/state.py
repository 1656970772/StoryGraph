from __future__ import annotations

import json
from pathlib import Path
from typing import Callable


REQUIRED_STAGE1_FILES = [
    "manifest.json",
    "graphify-out/graph.json",
    "graphify-out/GRAPH_REPORT.md",
    "graphify-out/graph.html",
    "requirements/template-requirements.json",
    "coverage/chunk-ledger.json",
    "coverage/evidence-index.json",
    "coverage/template-readiness.json",
    "coverage/agent-run-ledger.json",
    "coverage/gap-report.md",
]


def _has_blocking_failure(graph_dir: Path) -> bool:
    ledger_path = graph_dir / "coverage" / "agent-run-ledger.json"
    if not ledger_path.exists():
        return False
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(ledger, list):
        return False
    for record in ledger:
        if not isinstance(record, dict) or record.get("status") != "failed":
            continue
        record_errors = record.get("errors", [])
        if not isinstance(record_errors, list):
            continue
        for error in record_errors:
            if isinstance(error, dict) and str(error.get("code", "")).startswith("graphify_"):
                return True
    return False


def _stage1_status(manifest: dict):
    stage_status = manifest.get("stage_status", {})
    if not isinstance(stage_status, dict):
        return None
    return stage_status.get("stage1")


def stage1_state(ctx, config_hash: str, graph_validator: Callable[[Path], object]) -> dict:
    manifest_path = ctx.graph_dir / "manifest.json"
    missing = [item for item in REQUIRED_STAGE1_FILES if not (ctx.graph_dir / item).exists()]
    if not manifest_path.exists():
        return {"action": "build", "source_state": "new", "missing": missing}

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"action": "rebuild", "source_state": "changed", "missing": missing}
    if not isinstance(manifest, dict):
        return {"action": "rebuild", "source_state": "changed", "missing": missing}

    if missing:
        return {"action": "rebuild", "source_state": "changed", "missing": missing}

    stage_success = _stage1_status(manifest) == "success"
    same_source = manifest.get("source_hash") == ctx.source_hash
    same_config = manifest.get("config_hash") == config_hash
    graph_ok = bool(getattr(graph_validator(ctx.graph_dir), "ok", False))
    if same_source and same_config and stage_success and graph_ok and not _has_blocking_failure(
        ctx.graph_dir
    ):
        return {"action": "reuse", "source_state": "unchanged", "missing": []}
    return {"action": "rebuild", "source_state": "changed", "missing": missing}
