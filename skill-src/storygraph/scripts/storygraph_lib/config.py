import json
from pathlib import Path


class ConfigLoadError(ValueError):
    def __init__(
        self,
        code: str,
        path: Path,
        *,
        line: int | None = None,
        column: int | None = None,
        source: str = "config",
    ):
        self.code = code
        self.path = Path(path)
        self.line = line
        self.column = column
        self.source = source
        super().__init__(code)

    def to_dict(self) -> dict:
        payload = {
            "ok": False,
            "error": self.code,
            "path": str(self.path),
            "source": self.source,
        }
        if self.line is not None:
            payload["line"] = self.line
        if self.column is not None:
            payload["column"] = self.column
        return payload


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
    config = _read_config_json(default_path, source="default_config")
    if local_override and local_override.exists():
        config = _deep_merge(config, _read_config_json(local_override, source="local_override"))
    if cli_overrides:
        config = _deep_merge(config, cli_overrides)
    return config


def _read_config_json(path: Path, source: str) -> dict:
    path = Path(path)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise ConfigLoadError("config_encoding_error", path, source=source) from exc
    except json.JSONDecodeError as exc:
        raise ConfigLoadError(
            "config_json_error",
            path,
            line=exc.lineno,
            column=exc.colno,
            source=source,
        ) from exc
