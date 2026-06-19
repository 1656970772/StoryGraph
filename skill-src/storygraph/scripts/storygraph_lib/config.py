import json
from pathlib import Path


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(
    default_path: Path,
    local_override: Path | None = None,
    cli_overrides: dict | None = None,
) -> dict:
    config = json.loads(default_path.read_text(encoding="utf-8"))
    if local_override and local_override.exists():
        config = _deep_merge(config, json.loads(local_override.read_text(encoding="utf-8")))
    if cli_overrides:
        config = _deep_merge(config, cli_overrides)
    return config
