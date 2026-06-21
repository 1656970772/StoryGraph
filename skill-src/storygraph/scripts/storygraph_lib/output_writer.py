from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


class OutputWriteError(ValueError):
    def __init__(self, code: str, path: str):
        self.code = code
        self.path = path
        super().__init__(f"{code}:{path}")


@dataclass(frozen=True)
class ManagedOutputPathValidation:
    ok: bool
    normalized_path: str | None
    target_path: Path | None
    errors: list[str]


class OutputWriter:
    def __init__(self, graph_dir: str | Path, managed_outputs: list[str | Path]):
        self.graph_dir = Path(graph_dir)
        self.managed_outputs = [
            normalize_relative_output_path(path, allow_wildcards=True)
            for path in managed_outputs
        ]
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
        validation = validate_managed_output_path(
            self.graph_dir, relative_path, self.managed_outputs
        )
        if not validation.ok:
            path = validation.normalized_path or str(relative_path)
            raise OutputWriteError("unmanaged_output", path)
        normalized = validation.normalized_path or normalize_relative_output_path(relative_path)
        if normalized in self._written:
            raise OutputWriteError("duplicate_write", normalized)
        self._written.add(normalized)
        return validation.target_path or (self.graph_dir / Path(*normalized.split("/"))).resolve()


def validate_managed_output_path(
    graph_dir: str | Path,
    relative_path: str | Path,
    managed_outputs: list[str | Path],
) -> ManagedOutputPathValidation:
    try:
        normalized = normalize_relative_output_path(relative_path)
        normalized_managed_outputs = [
            normalize_relative_output_path(path, allow_wildcards=True)
            for path in managed_outputs
        ]
    except OutputWriteError as exc:
        return ManagedOutputPathValidation(
            ok=False,
            normalized_path=None,
            target_path=None,
            errors=[f"{exc.code}:{exc.path}"],
        )

    if not _matches_managed_output(normalized, normalized_managed_outputs):
        return ManagedOutputPathValidation(
            ok=False,
            normalized_path=normalized,
            target_path=None,
            errors=[f"unmanaged_output:{normalized}"],
        )

    root = Path(graph_dir).resolve()
    target = (Path(graph_dir) / Path(*normalized.split("/"))).resolve()
    if not _is_within(target, root):
        return ManagedOutputPathValidation(
            ok=False,
            normalized_path=normalized,
            target_path=None,
            errors=[f"unmanaged_output:{normalized}"],
        )

    return ManagedOutputPathValidation(
        ok=True,
        normalized_path=normalized,
        target_path=target,
        errors=[],
    )


def normalize_relative_output_path(
    path: str | Path, *, allow_wildcards: bool = False
) -> str:
    if not isinstance(path, (str, Path)):
        raise OutputWriteError("unmanaged_output", str(path))
    raw = str(path)
    if not raw:
        raise OutputWriteError("unmanaged_output", raw)
    if "\0" in raw:
        raise OutputWriteError("unmanaged_output", raw)
    if not allow_wildcards and any(marker in raw for marker in ("*", "?")):
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
        if ":" in part:
            raise OutputWriteError("unmanaged_output", raw)
        normalized_parts.append(part)
    if not normalized_parts:
        raise OutputWriteError("unmanaged_output", str(path))
    return "/".join(normalized_parts)


def _is_within(target: Path, root: Path) -> bool:
    return target == root or target.is_relative_to(root)


def _matches_managed_output(path: str, managed_outputs: list[str]) -> bool:
    return any(_matches_managed_pattern(path, managed) for managed in managed_outputs)


def _matches_managed_pattern(path: str, managed: str) -> bool:
    path_parts = path.split("/")
    managed_parts = managed.split("/")
    if len(path_parts) != len(managed_parts):
        return False
    return all(
        fnmatchcase(path_part, managed_part)
        for path_part, managed_part in zip(path_parts, managed_parts)
    )
