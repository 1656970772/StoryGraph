import json
from datetime import datetime, timezone
from pathlib import Path

from .canonical_writer import CANONICAL_WRITER_VERSION
from .paths import NovelContext


DEFAULT_STAGE_STATUS = {"stage1": "initialized", "stage2": "not_requested"}
MANIFEST_SCHEMA_VERSION = "storygraph.manifest.v1"
STAGE1_MODE = "agent-driven"
STAGE1_AGENT_SCHEMA_VERSION = "stage1-agent-driven.v1"


def _load_existing_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return {}
    if not isinstance(existing, dict):
        return {}
    return existing


def write_manifest(ctx: NovelContext, config_hash: str, graphify_source: str) -> Path:
    ctx.graph_dir.mkdir(parents=True, exist_ok=True)
    path = ctx.graph_dir / "manifest.json"
    existing = _load_existing_manifest(path)
    now = datetime.now(timezone.utc).isoformat()
    stage_status = existing.get("stage_status", DEFAULT_STAGE_STATUS)
    if not isinstance(stage_status, dict):
        stage_status = DEFAULT_STAGE_STATUS
    data = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "stage1_mode": STAGE1_MODE,
        "stage1_agent_schema_version": STAGE1_AGENT_SCHEMA_VERSION,
        "canonical_writer_version": CANONICAL_WRITER_VERSION,
        "source_path": str(ctx.source_path),
        "source_hash": ctx.source_hash,
        "source_size": ctx.source_size,
        "novel_name": ctx.novel_name,
        "graph_dir": str(ctx.graph_dir),
        "config_hash": config_hash,
        "graphify_repo": graphify_source,
        "graphify_version_or_commit": None,
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
        "stage_status": stage_status,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
