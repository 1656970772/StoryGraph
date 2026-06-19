from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class OutputWriteError(ValueError):
    def __init__(self, code: str, path: str):
        self.code = code
        self.path = path
        super().__init__(f"{code}:{path}")


class OutputWriter:
    def __init__(self, graph_dir: str | Path, managed_outputs: list[str | Path]):
        self.graph_dir = Path(graph_dir)
        self.managed_outputs = {_normalize_output_path(path) for path in managed_outputs}
        self._written: set[str] = set()

    def write_json(self, relative_path: str | Path, data: Any) -> Path:
        path = self._managed_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def write_text(self, relative_path: str | Path, text: str) -> Path:
        path = self._managed_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _managed_path(self, relative_path: str | Path) -> Path:
        normalized = _normalize_output_path(relative_path)
        if normalized not in self.managed_outputs:
            raise OutputWriteError("unmanaged_output", normalized)
        if normalized in self._written:
            raise OutputWriteError("duplicate_write", normalized)
        self._written.add(normalized)
        return self.graph_dir / Path(*normalized.split("/"))


def _normalize_output_path(path: str | Path) -> str:
    candidate = Path(path)
    parts = candidate.parts
    if candidate.is_absolute() or ".." in parts or not parts:
        raise OutputWriteError("unmanaged_output", str(path))
    return "/".join(parts)
