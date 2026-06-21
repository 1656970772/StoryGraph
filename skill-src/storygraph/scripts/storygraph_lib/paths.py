from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath, PureWindowsPath


@dataclass(frozen=True)
class NovelContext:
    source_path: Path
    source_hash: str
    source_size: int
    novel_name: str
    novel_dir: Path
    graph_dir: Path


@dataclass(frozen=True)
class RelativeArtifactPathValidation:
    ok: bool
    normalized_path: str | None
    target_path: Path | None
    errors: list[str]


def file_sha256(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def resolve_novel_context(
    source_path: Path,
    graph_dir_suffix: str,
    create: bool = False,
) -> NovelContext:
    source = source_path.expanduser().resolve()
    graph_dir = source.parent / f"{source.stem}{graph_dir_suffix}"
    if create:
        graph_dir.mkdir(parents=True, exist_ok=True)
    return NovelContext(
        source,
        file_sha256(source),
        source.stat().st_size,
        source.stem,
        source.parent,
        graph_dir,
    )


def validate_relative_artifact_path(
    raw_path: str | Path,
    *,
    base_dir: str | Path,
) -> RelativeArtifactPathValidation:
    if not isinstance(raw_path, (str, Path)):
        return RelativeArtifactPathValidation(
            False,
            None,
            None,
            ["path_field_type_error"],
        )

    raw = str(raw_path)
    if not raw:
        return RelativeArtifactPathValidation(False, None, None, ["path_empty"])
    if "\0" in raw:
        return RelativeArtifactPathValidation(False, None, None, ["path_embedded_nul"])

    windows_path = PureWindowsPath(raw)
    posix_path = PurePosixPath(raw.replace("\\", "/"))
    if (
        windows_path.drive
        or windows_path.root
        or windows_path.anchor
        or posix_path.root
        or posix_path.anchor
    ):
        return RelativeArtifactPathValidation(False, None, None, ["path_absolute_rejected"])

    normalized_parts: list[str] = []
    for part in raw.replace("\\", "/").split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            return RelativeArtifactPathValidation(
                False,
                None,
                None,
                ["path_parent_traversal_rejected"],
            )
        if ":" in part:
            return RelativeArtifactPathValidation(
                False,
                None,
                None,
                ["path_absolute_rejected"],
            )
        normalized_parts.append(part)

    if not normalized_parts:
        return RelativeArtifactPathValidation(False, None, None, ["path_empty"])

    normalized = "/".join(normalized_parts)
    root = Path(base_dir).resolve(strict=False)
    target = (root / Path(*normalized_parts)).resolve(strict=False)
    if target != root and root not in target.parents:
        return RelativeArtifactPathValidation(
            False,
            normalized,
            None,
            ["path_parent_traversal_rejected"],
        )
    return RelativeArtifactPathValidation(True, normalized, target, [])
