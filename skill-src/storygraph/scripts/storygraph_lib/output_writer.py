from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


class OutputWriteError(ValueError):
    def __init__(self, code: str, path: str):
        self.code = code
        self.path = path
        super().__init__(f"{code}:{path}")


class OutputWriter:
    def __init__(self, graph_dir: str | Path, managed_outputs: list[str | Path]):
        self.graph_dir = Path(graph_dir)
        self._resolved_graph_dir = self.graph_dir.resolve()
        self.managed_outputs = {normalize_relative_output_path(path) for path in managed_outputs}
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
        normalized = normalize_relative_output_path(relative_path)
        if normalized not in self.managed_outputs:
            raise OutputWriteError("unmanaged_output", normalized)
        if normalized in self._written:
            raise OutputWriteError("duplicate_write", normalized)
        target = (self.graph_dir / Path(*normalized.split("/"))).resolve()
        if not _is_within(target, self._resolved_graph_dir):
            raise OutputWriteError("unmanaged_output", str(relative_path))
        self._written.add(normalized)
        return target


def normalize_relative_output_path(path: str | Path) -> str:
    raw = str(path)
    if not raw:
        raise OutputWriteError("unmanaged_output", raw)
    if "\0" in raw:
        raise OutputWriteError("unmanaged_output", raw)
    windows_path = PureWindowsPath(raw)
    posix_path = PurePosixPath(raw.replace("\\", "/"))
    if (
        windows_path.drive
        or windows_path.root
        or windows_path.anchor
        or posix_path.root
        or posix_path.anchor
    ):
        raise OutputWriteError("unmanaged_output", raw)

    normalized_parts = []
    for part in raw.replace("\\", "/").split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise OutputWriteError("unmanaged_output", raw)
        normalized_parts.append(part)
    if not normalized_parts:
        raise OutputWriteError("unmanaged_output", str(path))
    return "/".join(normalized_parts)


def _is_within(target: Path, root: Path) -> bool:
    return target == root or target.is_relative_to(root)
