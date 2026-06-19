from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


@dataclass(frozen=True)
class NovelContext:
    source_path: Path
    source_hash: str
    source_size: int
    novel_name: str
    novel_dir: Path
    graph_dir: Path


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
