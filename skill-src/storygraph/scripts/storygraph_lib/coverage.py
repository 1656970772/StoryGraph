from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re
from typing import Any

from .output_writer import OutputWriter


DEFAULT_COVERAGE_OUTPUTS = [
    "coverage/chunk-ledger.json",
    "coverage/evidence-index.json",
    "coverage/template-readiness.json",
    "coverage/gap-report.md",
]


def make_chunk_ledger(source_path: str | Path, chunk_strategy: dict | None = None) -> dict:
    source = Path(source_path)
    text = source.read_text(encoding="utf-8")
    strategy = chunk_strategy or {}
    mode = strategy.get("mode", "chapter-aware")
    max_chars = int(strategy.get("max_chars", 20000))
    overlap_chars = int(strategy.get("overlap_chars", 0))
    patterns = strategy.get("chapter_heading_patterns") or [r"^第.+章", r"^Chapter\s+\d+"]

    sections = _chapter_sections(text, patterns) if mode == "chapter-aware" else []
    if not sections:
        sections = [(0, len(text), None)]

    chunks = []
    for section_start, section_end, chapter in sections:
        for start, end in _bounded_ranges(section_start, section_end, max_chars, overlap_chars):
            chunk_text = text[start:end]
            chunks.append(
                {
                    "chunk_id": f"chunk-{len(chunks) + 1:04d}",
                    "source_path": str(source),
                    "source_range": [start, end],
                    "chapter": chapter,
                    "text": chunk_text,
                    "text_hash": sha256(chunk_text.encode("utf-8")).hexdigest(),
                    "scanned": True,
                }
            )

    return {
        "source_path": str(source),
        "source_size": len(text),
        "strategy": {
            "mode": mode,
            "max_chars": max_chars,
            "overlap_chars": overlap_chars,
            "chapter_heading_patterns": list(patterns),
        },
        "all_chunks_scanned": all(chunk["scanned"] for chunk in chunks),
        "chunks": chunks,
    }


def write_coverage_outputs(
    graph_dir: str | Path,
    *,
    chunk_ledger: dict,
    evidence_index: list[dict],
    template_readiness: list[dict],
    gap_report: str,
    managed_outputs: list[str | Path] | None = None,
    writer: OutputWriter | None = None,
) -> dict[str, Path]:
    active_writer = writer or OutputWriter(
        graph_dir=graph_dir,
        managed_outputs=managed_outputs or DEFAULT_COVERAGE_OUTPUTS,
    )
    return {
        "chunk_ledger": active_writer.write_json("coverage/chunk-ledger.json", chunk_ledger),
        "evidence_index": active_writer.write_json("coverage/evidence-index.json", evidence_index),
        "template_readiness": active_writer.write_json(
            "coverage/template-readiness.json", template_readiness
        ),
        "gap_report": active_writer.write_text("coverage/gap-report.md", gap_report),
    }


def _chapter_sections(text: str, patterns: list[str]) -> list[tuple[int, int, str | None]]:
    headings: list[tuple[int, str]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        heading = line.rstrip("\r\n")
        if any(re.match(pattern, heading) for pattern in patterns):
            headings.append((offset, heading))
        offset += len(line)
    if not headings:
        return []

    sections: list[tuple[int, int, str | None]] = []
    if headings[0][0] > 0:
        sections.append((0, headings[0][0], None))
    for index, (start, chapter) in enumerate(headings):
        end = headings[index + 1][0] if index + 1 < len(headings) else len(text)
        sections.append((start, end, chapter))
    return [(start, end, chapter) for start, end, chapter in sections if start < end]


def _bounded_ranges(
    start: int, end: int, max_chars: int, overlap_chars: int
) -> list[tuple[int, int]]:
    if max_chars <= 0 or end - start <= max_chars:
        return [(start, end)]
    overlap = min(max(overlap_chars, 0), max_chars - 1)
    ranges = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + max_chars, end)
        ranges.append((cursor, chunk_end))
        if chunk_end == end:
            break
        cursor = chunk_end - overlap
    return ranges
