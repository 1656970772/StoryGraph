from __future__ import annotations

import json
from hashlib import md5, sha256
from pathlib import Path
from typing import Any


CACHE_SCHEMA_VERSION = "storygraph.stage1-input-cache.v1"


def build_stage1_input_cache(
    *,
    ctx: Any,
    template_dir: str | Path,
    templates: list[Any],
    config: dict,
) -> dict:
    return {
        "schema_version": CACHE_SCHEMA_VERSION,
        "source": {
            "path": str(ctx.source_path),
            "hash": ctx.source_hash,
            "size": ctx.source_size,
        },
        "templates": template_inventory(template_dir, templates),
        "chunk_strategy_hash": stable_json_hash(config.get("chunk_strategy", {})),
        "template_requirements_config_hash": stable_json_hash(
            {
                "template_requirements_strategy": config.get(
                    "template_requirements_strategy"
                ),
                "stage1_artifacts": _selected_artifacts(
                    config,
                    [
                        "requirements",
                        "task_packet_dir",
                        "template_requirements_part_dir",
                    ],
                ),
            }
        ),
        "lane_task_packet_config_hash": stable_json_hash(
            {
                "element_lanes": config.get("element_lanes"),
                "agent_orchestration": config.get("agent_orchestration"),
                "agent_policy": config.get("agent_policy"),
                "required_evidence_policy": config.get("required_evidence_policy"),
                "stage1_artifacts": _selected_artifacts(
                    config,
                    [
                        "requirements",
                        "task_packet_dir",
                        "chunk_text_dir",
                        "lane_output_dir",
                    ],
                ),
            }
        ),
    }


def template_inventory(template_dir: str | Path, templates: list[Any]) -> list[dict]:
    root = Path(template_dir).resolve()
    inventory: list[dict] = []
    for template in templates:
        path = Path(getattr(template, "path"))
        text = str(getattr(template, "text", ""))
        inventory.append(
            {
                "template_name": str(getattr(template, "name", "")),
                "template_file": template_relative_path(root, path),
                "md5": md5(text.encode("utf-8")).hexdigest(),
                "sha256": str(getattr(template, "file_hash", "")),
            }
        )
    return inventory


def template_relative_path(template_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(template_dir).as_posix()
    except ValueError:
        return path.name


def template_key(item: dict) -> str:
    value = item.get("template_file")
    if isinstance(value, str) and value:
        return _portable_template_path(value)
    name = item.get("template_name")
    return name if isinstance(name, str) else ""


def template_name_to_key(items: list[dict]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in items:
        name = item.get("template_name")
        key = template_key(item)
        if isinstance(name, str) and name and key:
            mapping[name] = key
    return mapping


def templates_by_key(items: list[dict]) -> dict[str, dict]:
    return {template_key(item): item for item in items if template_key(item)}


def requirement_key(item: dict, *, name_to_current_key: dict[str, str] | None = None) -> str:
    file_value = item.get("template_file")
    if isinstance(file_value, str) and file_value:
        file_key = _portable_template_path(file_value)
        name = item.get("template_name")
        if name_to_current_key and isinstance(name, str):
            return name_to_current_key.get(name, file_key)
        return file_key
    name = item.get("template_name")
    if isinstance(name, str) and name:
        return (name_to_current_key or {}).get(name, name)
    return ""


def stable_json_hash(value: Any) -> str:
    return sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _selected_artifacts(config: dict, keys: list[str]) -> dict:
    artifacts = config.get("stage1_artifacts", {})
    if not isinstance(artifacts, dict):
        return {}
    return {key: artifacts.get(key) for key in keys}


def _portable_template_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    drive_marker = len(normalized) >= 2 and normalized[1] == ":"
    if normalized.startswith("/") or drive_marker:
        return Path(value).name
    return normalized
