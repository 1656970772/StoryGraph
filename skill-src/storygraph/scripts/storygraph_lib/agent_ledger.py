from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class LedgerValidation:
    ok: bool
    errors: list[str]


def make_agent_run_record(
    role: str,
    input: Iterable[str | Path] | str | Path,
    output: Iterable[str | Path] | str | Path,
    write_scope: Iterable[str | Path] | str | Path,
    status: str = "pending",
    merge_owner: str = "single-writer",
) -> dict:
    record = {
        "role": role,
        "input": _path_list(input),
        "output": _path_list(output),
        "write_scope": _path_list(write_scope),
        "status": status,
        "merge_owner": merge_owner,
    }
    record["run_id"] = _run_id(record)
    return record


def make_stage_agent_records(source_path: str | Path, graph_dir: str | Path) -> list[dict]:
    source = _path_text(source_path)
    graph = _path_text(graph_dir)
    return [
        make_agent_run_record(
            role="模板需求分析",
            input=[source],
            output=["requirements/template-requirements.json"],
            write_scope=["requirements/template-requirements.json"],
        ),
        make_agent_run_record(
            role="图抽取",
            input=[source, "requirements/template-requirements.json"],
            output=[
                "graphify-out/graph.json",
                "graphify-out/GRAPH_REPORT.md",
                "graphify-out/graph.html",
            ],
            write_scope=[
                "graphify-out/graph.json",
                "graphify-out/GRAPH_REPORT.md",
                "graphify-out/graph.html",
            ],
        ),
        make_agent_run_record(
            role="覆盖审查",
            input=[source, "requirements/template-requirements.json", "graphify-out/graph.json"],
            output=[
                "coverage/chunk-ledger.json",
                "coverage/evidence-index.json",
                "coverage/template-readiness.json",
                "coverage/gap-report.md",
            ],
            write_scope=[
                "coverage/chunk-ledger.json",
                "coverage/evidence-index.json",
                "coverage/template-readiness.json",
                "coverage/gap-report.md",
            ],
        ),
        make_agent_run_record(
            role="质量审查",
            input=[
                graph,
                "requirements/template-requirements.json",
                "coverage/template-readiness.json",
            ],
            output=["coverage/agent-run-ledger.json"],
            write_scope=["coverage/agent-run-ledger.json"],
        ),
    ]


def validate_single_writer(records: Iterable[dict]) -> LedgerValidation:
    output_owners: dict[str, str] = {}
    scope_owners: dict[str, str] = {}
    errors: list[str] = []
    for record in records:
        role = str(record.get("role", "unknown"))
        for output_path in _path_list(record.get("output", [])):
            if output_path in output_owners:
                errors.append(f"duplicate_output:{output_path}")
            output_owners[output_path] = role
        for scope in _path_list(record.get("write_scope", [])):
            if scope in scope_owners:
                errors.append(f"write_conflict:{scope}")
            scope_owners[scope] = role
    return LedgerValidation(ok=not errors, errors=errors)


def _path_list(values: Iterable[str | Path] | str | Path) -> list[str]:
    if isinstance(values, (str, Path)):
        return [_path_text(values)]
    return [_path_text(value) for value in values]


def _path_text(value: str | Path) -> str:
    return Path(value).as_posix() if isinstance(value, Path) else str(value).replace("\\", "/")


def _run_id(record: dict) -> str:
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"agent-run:{sha256(payload.encode('utf-8')).hexdigest()[:16]}"
