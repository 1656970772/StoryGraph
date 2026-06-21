from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re
from typing import Iterable

from .output_writer import OutputWriter


DEFAULT_COVERAGE_OUTPUTS = [
    "coverage/chunk-ledger.json",
    "coverage/evidence-index.json",
    "coverage/template-readiness.json",
    "coverage/agent-run-ledger.json",
    "coverage/gap-report.md",
]


def make_chunk_ledger(
    source_path: str | Path,
    strategy: dict,
    processor: str,
    target_lane_ids: Iterable[str] | None = None,
    required_lane_ids: Iterable[str] | None = None,
) -> list[dict]:
    source = Path(source_path)
    text = source.read_text(encoding="utf-8")
    active_strategy = strategy or {}
    mode = active_strategy.get("mode", "chapter-aware")
    max_chars = int(active_strategy.get("max_chars", 20000))
    overlap_chars = int(active_strategy.get("overlap_chars", 0))
    patterns = active_strategy.get("chapter_heading_patterns") or [r"^第.+章", r"^Chapter\s+\d+"]

    sections = _chapter_sections(text, patterns) if mode == "chapter-aware" else []
    if not sections:
        sections = [(0, len(text), None)]

    target_lanes = list(target_lane_ids or [])
    required_lanes = list(required_lane_ids or [])
    lane_tracking_enabled = bool(target_lane_ids is not None or required_lane_ids is not None)

    chunks = []
    for section_start, section_end, chapter_hint in sections:
        for start, end in _bounded_ranges(section_start, section_end, max_chars, overlap_chars):
            chunk_text = text[start:end]
            chunk = {
                "chunk_id": f"chunk-{len(chunks) + 1:04d}",
                "source_path": str(source),
                "source_range": [start, end],
                "chapter_hint": chapter_hint,
                "hash": sha256(chunk_text.encode("utf-8")).hexdigest(),
                "scanned_at": None,
                "processor": processor,
                "extraction_status": "pending_agent_outputs"
                if lane_tracking_enabled
                else "pending",
                "failure": None,
                "retry_count": 0,
                "text": chunk_text,
            }
            if lane_tracking_enabled:
                chunk["target_lane_ids"] = list(target_lanes)
                chunk["required_lane_ids"] = list(required_lanes)
                chunk["lane_statuses"] = {
                    lane_id: "pending_agent_outputs" for lane_id in required_lanes
                }
            chunks.append(chunk)
    return chunks


def write_coverage_outputs(
    writer: OutputWriter,
    chunks: list[dict],
    evidences: list[dict],
    readiness: list[dict],
    agent_runs: list[dict],
    gap_lines: Iterable[str],
) -> dict[str, Path]:
    gap_text = "\n".join(gap_lines)
    if gap_text:
        gap_text += "\n"
    return {
        "chunks": writer.write_json("coverage/chunk-ledger.json", chunks),
        "evidences": writer.write_json("coverage/evidence-index.json", evidences),
        "readiness": writer.write_json("coverage/template-readiness.json", readiness),
        "agent_runs": writer.write_json("coverage/agent-run-ledger.json", agent_runs),
        "gap_report": writer.write_text("coverage/gap-report.md", gap_text),
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
    for index, (start, chapter_hint) in enumerate(headings):
        end = headings[index + 1][0] if index + 1 < len(headings) else len(text)
        sections.append((start, end, chapter_hint))
    return [(start, end, chapter_hint) for start, end, chapter_hint in sections if start < end]


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
