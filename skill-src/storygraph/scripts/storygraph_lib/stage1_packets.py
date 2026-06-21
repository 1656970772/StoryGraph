from __future__ import annotations

import copy
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .output_writer import OutputWriteError, normalize_relative_output_path


DEFAULT_TEMPLATE_REQUIREMENTS_STRATEGY = {
    "agent_role": "template-requirements-analysis-agent",
    "lane_id": "template_requirements",
    "schema": "template-requirements.schema.json",
    "templates_per_packet": 5,
}


def build_task_packets(
    source_path: str | Path,
    chunks: Iterable[dict],
    lanes: Iterable[dict],
    template_requirements_path: str | Path,
    *,
    task_packet_dir: str | Path | None = None,
    attempt: int = 1,
    required_evidence_policy: dict | None = None,
) -> list[dict]:
    packets = []
    required_lanes = []
    safe_source_path = _safe_source_path(source_path)
    safe_template_requirements_path = _safe_artifact_path(
        template_requirements_path, "invalid_template_requirements_path"
    )
    for lane_record in lanes:
        lane = _required_record(lane_record, "lane")
        if lane.get("required") is True:
            required_lanes.append(lane)

    for chunk_record in chunks:
        chunk = _required_record(chunk_record, "chunk")
        chunk_id = _safe_path_segment(
            _required_field(chunk, "chunk_id"), "invalid_chunk_id"
        )
        source_range = _source_range(chunk)
        chunk_text_path = _optional_artifact_path(
            chunk.get("chunk_text_path"), "invalid_chunk_text_path"
        )
        for lane in required_lanes:
            lane_id = _safe_path_segment(
                _required_field(lane, "lane_id"), "invalid_lane_id"
            )
            lane_contract = dict(lane)
            if "required_evidence_policy" in lane_contract:
                lane_contract["required_evidence_policy"] = copy.deepcopy(
                    lane_contract["required_evidence_policy"]
                )
            evidence_policy = lane.get(
                "required_evidence_policy", required_evidence_policy
            )
            packet = {
                "task_packet_id": _task_packet_id(chunk_id, lane_id, attempt),
                "stage": "stage1",
                "chunk_id": chunk_id,
                "lane_id": lane_id,
                "agent_role": _required_field(lane, "agent_role"),
                "source_path": safe_source_path,
                "source_range": source_range,
                "chapter_hint": chunk.get("chapter_hint"),
                "chunk_text_path": chunk_text_path,
                "relevant_template_requirements": {
                    "path": safe_template_requirements_path,
                },
                "lane_contract": lane_contract,
                "allowed_output_schema": _required_field(lane, "schema"),
                "required_evidence_policy": copy.deepcopy(evidence_policy),
                "attempt": attempt,
            }
            packet_path = lane.get("task_packet_path")
            if packet_path is None:
                packet_path = lane.get("packet_path")
            if packet_path is not None:
                packet["task_packet_path"] = _safe_task_packet_path(packet_path)
            elif task_packet_dir is not None:
                packet["task_packet_path"] = _safe_task_packet_path(
                    _packet_path(task_packet_dir, chunk_id, lane_id)
                )
            packets.append(packet)
    return packets


def build_template_requirements_task_packet(
    source_path: str | Path,
    chunks: Iterable[dict],
    templates: Iterable[Any],
    template_requirements_path: str | Path,
    *,
    task_packet_dir: str | Path,
    attempt: int = 1,
    strategy: dict | None = None,
) -> dict:
    return build_template_requirements_task_packets(
        source_path=source_path,
        chunks=chunks,
        templates=templates,
        template_requirements_path=template_requirements_path,
        task_packet_dir=task_packet_dir,
        template_requirements_part_dir="intermediate/template-requirements-parts",
        attempt=attempt,
        strategy=strategy,
    )[0]


def build_template_requirements_task_packets(
    source_path: str | Path,
    chunks: Iterable[dict],
    templates: Iterable[Any],
    template_requirements_path: str | Path,
    *,
    task_packet_dir: str | Path,
    template_requirements_part_dir: str | Path,
    attempt: int = 1,
    strategy: dict | None = None,
) -> list[dict]:
    safe_source_path = _safe_source_path(source_path)
    safe_template_requirements_path = _safe_artifact_path(
        template_requirements_path, "invalid_template_requirements_path"
    )
    chunk_summaries = [_chunk_summary(_required_record(chunk, "chunk")) for chunk in chunks]
    template_inventory = [_template_inventory_item(template) for template in templates]
    resolved_strategy = _template_requirements_strategy(strategy)
    lane_id = resolved_strategy["lane_id"]
    agent_role = resolved_strategy["agent_role"]
    schema = resolved_strategy["schema"]
    templates_per_packet = resolved_strategy["templates_per_packet"]
    if not template_inventory:
        raise ValueError("invalid_template_requirements_template_set_empty")
    batches = [
        template_inventory[index : index + templates_per_packet]
        for index in range(0, len(template_inventory), templates_per_packet)
    ]

    packets = []
    for batch_index, batch in enumerate(batches, start=1):
        batch_id = f"batch-{batch_index:04d}"
        chunk_id = f"stage1-template-requirements-{batch_id}"
        output_path = _template_requirements_part_path(
            template_requirements_part_dir, batch_id
        )
        packet = {
            "task_packet_id": _task_packet_id(chunk_id, lane_id, attempt),
            "stage": "stage1",
            "chunk_id": chunk_id,
            "batch_id": batch_id,
            "lane_id": lane_id,
            "agent_role": agent_role,
            "source_path": safe_source_path,
            "allowed_output_schema": schema,
            "relevant_template_requirements": {
                "path": safe_template_requirements_path,
            },
            "lane_contract": {
                "lane_id": lane_id,
                "required": True,
                "agent_role": agent_role,
                "schema": schema,
                "output_path": output_path,
            },
            "template_inventory": batch,
            "template_names": [item["template_name"] for item in batch],
            "chunk_ids": [chunk["chunk_id"] for chunk in chunk_summaries],
            "chunks": chunk_summaries,
            "output_path": output_path,
            "write_scope": [output_path],
            "attempt": attempt,
        }
        packet["task_packet_path"] = _safe_task_packet_path(
            _template_requirements_packet_path(task_packet_dir, batch_id)
        )
        packets.append(packet)
    return packets


def _template_requirements_strategy(strategy: dict | None) -> dict[str, Any]:
    if strategy is not None and not isinstance(strategy, dict):
        raise ValueError("invalid_template_requirements_strategy")
    configured = dict(DEFAULT_TEMPLATE_REQUIREMENTS_STRATEGY)
    if strategy:
        configured.update(strategy)
    templates_per_packet = configured.get("templates_per_packet")
    if (
        type(templates_per_packet) is not int
        or templates_per_packet < 1
        or templates_per_packet > 5
    ):
        raise ValueError("invalid_template_requirements_templates_per_packet")
    return {
        "agent_role": _required_string_field(
            configured,
            "agent_role",
            "invalid_template_requirements_agent_role",
        ),
        "lane_id": _safe_path_segment(
            _required_string_field(
                configured,
                "lane_id",
                "invalid_template_requirements_lane_id",
            ),
            "invalid_template_requirements_lane_id",
        ),
        "schema": _required_string_field(
            configured,
            "schema",
            "invalid_template_requirements_schema",
        ),
        "templates_per_packet": templates_per_packet,
    }


def _required_record(record: Any, record_type: str) -> dict:
    if not isinstance(record, dict):
        raise ValueError(f"invalid_{record_type}_record")
    return record


def _required_field(record: dict, field: str) -> Any:
    value = record.get(field)
    if value in (None, ""):
        raise ValueError(f"missing_{field}")
    return value


def _required_string_field(record: dict, field: str, error_code: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(error_code)
    return value


def _safe_path_segment(value: Any, error_code: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(error_code)
    if value in (".", "..") or ".." in value:
        raise ValueError(error_code)
    if any(marker in value for marker in ("/", "\\", "\0", ":", "*", "?")):
        raise ValueError(error_code)
    return value


def _source_range(record: dict) -> list[int]:
    if "source_range" not in record:
        return []
    value = record["source_range"]
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or any(type(item) is not int for item in value)
    ):
        raise ValueError("invalid_source_range")
    start, end = value
    if start < 0 or end < start:
        raise ValueError("invalid_source_range")
    return list(value)


def _safe_source_path(path: Any) -> str:
    if not isinstance(path, (str, Path)):
        raise ValueError("invalid_source_path")
    raw = str(path)
    if not raw or "\0" in raw:
        raise ValueError("invalid_source_path")
    return raw


def _optional_artifact_path(path: Any, error_code: str) -> str | None:
    if path is None:
        return None
    return _safe_artifact_path(path, error_code)


def _safe_artifact_path(path: str | Path, error_code: str) -> str:
    try:
        return normalize_relative_output_path(path)
    except OutputWriteError as exc:
        raise ValueError(error_code) from exc


def _safe_task_packet_path(path: str | Path) -> str:
    try:
        return normalize_relative_output_path(path)
    except OutputWriteError as exc:
        raise ValueError("invalid_task_packet_path") from exc


def _task_packet_id(chunk_id: str, lane_id: str, attempt: int) -> str:
    return f"{chunk_id}:{lane_id}:attempt-{attempt:03d}"


def _packet_path(task_packet_dir: str | Path, chunk_id: str, lane_id: str) -> str:
    try:
        safe_task_packet_dir = normalize_relative_output_path(task_packet_dir)
    except OutputWriteError as exc:
        raise ValueError("invalid_task_packet_path") from exc
    return PurePosixPath(safe_task_packet_dir, chunk_id, f"{lane_id}.json").as_posix()


def _template_requirements_packet_path(task_packet_dir: str | Path, batch_id: str) -> str:
    try:
        safe_task_packet_dir = normalize_relative_output_path(task_packet_dir)
    except OutputWriteError as exc:
        raise ValueError("invalid_task_packet_path") from exc
    return PurePosixPath(
        safe_task_packet_dir,
        "template-requirements",
        f"{batch_id}.json",
    ).as_posix()


def _template_requirements_part_path(
    template_requirements_part_dir: str | Path, batch_id: str
) -> str:
    try:
        safe_part_dir = normalize_relative_output_path(template_requirements_part_dir)
    except OutputWriteError as exc:
        raise ValueError("invalid_template_requirements_part_dir") from exc
    return PurePosixPath(safe_part_dir, f"{batch_id}.json").as_posix()


def _chunk_summary(chunk: dict) -> dict:
    chunk_id = _safe_path_segment(_required_field(chunk, "chunk_id"), "invalid_chunk_id")
    summary = {
        "chunk_id": chunk_id,
        "source_range": _source_range(chunk),
        "chapter_hint": chunk.get("chapter_hint"),
    }
    chunk_text_path = _optional_artifact_path(
        chunk.get("chunk_text_path"), "invalid_chunk_text_path"
    )
    if chunk_text_path is not None:
        summary["chunk_text_path"] = chunk_text_path
    return summary


def _template_inventory_item(template: Any) -> dict:
    path = getattr(template, "path", None)
    return {
        "template_name": str(getattr(template, "name", "")),
        "template_file": str(path) if path is not None else "",
        "template_file_hash": str(getattr(template, "file_hash", "")),
    }
