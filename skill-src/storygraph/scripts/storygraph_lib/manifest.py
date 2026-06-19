import json
from datetime import datetime, timezone
from pathlib import Path

from .paths import NovelContext


def write_manifest(ctx: NovelContext, config_hash: str, graphify_source: str) -> Path:
    path = ctx.graph_dir / "manifest.json"
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "source_path": str(ctx.source_path),
        "source_hash": ctx.source_hash,
        "source_size": ctx.source_size,
        "novel_name": ctx.novel_name,
        "graph_dir": str(ctx.graph_dir),
        "config_hash": config_hash,
        "graphify_repo": graphify_source,
        "graphify_version_or_commit": None,
        "created_at": now,
        "updated_at": now,
        "stage_status": {"stage1": "initialized", "stage2": "not_requested"},
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
