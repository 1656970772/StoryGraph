from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .output_writer import OutputWriteError, normalize_relative_output_path


@dataclass(frozen=True)
class LedgerValidation:
    ok: bool
    errors: list[str]


def make_agent_run_record(
    run_id: str,
    agent_role: str,
    stage: str,
    chunk_ids: Iterable[str],
    template_names: Iterable[str],
    input_paths: Iterable[str | Path] | str | Path,
    output_paths: Iterable[str | Path] | str | Path,
    write_scope: Iterable[str | Path] | str | Path,
) -> dict:
    return {
        "run_id": run_id,
        "agent_role": agent_role,
        "stage": stage,
        "assigned_chunk_ids": list(chunk_ids),
        "assigned_template_names": list(template_names),
        "input_paths": _path_list(input_paths),
        "output_paths": _path_list(output_paths),
        "write_scope": _path_list(write_scope),
        "status": "pending",
        "errors": [],
        "merge_owner": "single-writer",
        "reviewer_status": "pending",
        "started_at": None,
        "finished_at": None,
    }


def make_stage_agent_records(chunk_ids: Iterable[str], template_names: Iterable[str]) -> list[dict]:
    chunks = list(chunk_ids)
    templates = list(template_names)
    return [
        make_agent_run_record(
            "stage1-template-requirements",
            "模板需求分析",
            "stage1",
            chunks,
            templates,
            ["templates"],
            ["requirements/template-requirements.json"],
            ["requirements/template-requirements.json"],
        ),
        make_agent_run_record(
            "stage1-graph-extraction",
            "图抽取",
            "stage1",
            chunks,
            templates,
            ["source", "requirements/template-requirements.json"],
            [
                "graphify-out/graph.json",
                "graphify-out/GRAPH_REPORT.md",
                "graphify-out/graph.html",
            ],
            [
                "graphify-out/graph.json",
                "graphify-out/GRAPH_REPORT.md",
                "graphify-out/graph.html",
            ],
        ),
        make_agent_run_record(
            "stage1-coverage-review",
            "覆盖审查",
            "stage1",
            chunks,
            templates,
            ["source", "requirements/template-requirements.json", "graphify-out/graph.json"],
            [
                "coverage/chunk-ledger.json",
                "coverage/evidence-index.json",
                "coverage/template-readiness.json",
                "coverage/gap-report.md",
            ],
            [
                "coverage/chunk-ledger.json",
                "coverage/evidence-index.json",
                "coverage/template-readiness.json",
                "coverage/gap-report.md",
            ],
        ),
        make_agent_run_record(
            "stage1-quality-review",
            "质量审查",
            "stage1",
            chunks,
            templates,
            [
                "graphify-out/graph.json",
                "coverage/evidence-index.json",
                "coverage/template-readiness.json",
                "coverage/gap-report.md",
            ],
            ["coverage/agent-run-ledger.json"],
            ["coverage/agent-run-ledger.json"],
        ),
    ]


def validate_single_writer(records: Iterable[dict]) -> LedgerValidation:
    output_owners: dict[str, str] = {}
    scope_owners: dict[str, str] = {}
    errors: list[str] = []
    normalized_records = []
    for record in records:
        if not isinstance(record, dict):
            errors.append("bad_agent_ledger_record")
            continue
        owner = str(record.get("run_id") or record.get("agent_role") or "unknown")
        outputs, output_errors = _safe_path_list(
            record.get("output_paths", []), f"{owner}:output_paths"
        )
        scopes, scope_errors = _safe_path_list(
            record.get("write_scope", []), f"{owner}:write_scope"
        )
        errors.extend(output_errors)
        errors.extend(scope_errors)
        normalized_records.append((owner, outputs, scopes))
        for output_path in outputs:
            if output_path in output_owners:
                errors.append(f"duplicate_output:{output_path}")
            output_owners[output_path] = owner
        for scope in scopes:
            if scope in scope_owners:
                errors.append(f"write_conflict:{scope}")
            scope_owners[scope] = owner

    for output_owner, outputs, _ in normalized_records:
        for output_path in outputs:
            for scope_owner, _, scopes in normalized_records:
                if output_owner != scope_owner and output_path in scopes:
                    conflict = f"write_conflict:{output_path}"
                    if conflict not in errors:
                        errors.append(conflict)

    return LedgerValidation(ok=not errors, errors=errors)


def _path_list(values: Iterable[str | Path] | str | Path) -> list[str]:
    if values is None:
        return []
    if isinstance(values, (str, Path)):
        return [_path_text(values)]
    return [_path_text(value) for value in values]


def _path_text(value: str | Path) -> str:
    return Path(value).as_posix() if isinstance(value, Path) else str(value).replace("\\", "/")


def _safe_path_list(
    values: Iterable[str | Path] | str | Path, label: str = "paths"
) -> tuple[list[str], list[str]]:
    normalized = []
    errors = []
    if values is None:
        return [], []
    if isinstance(values, (str, Path)):
        path_items = [values]
    elif isinstance(values, dict):
        return [], [f"invalid_path_list:{label}"]
    else:
        try:
            path_items = list(values)
        except TypeError:
            return [], [f"invalid_path_list:{label}"]
    for value in path_items:
        if not isinstance(value, (str, Path)):
            errors.append(f"invalid_path_item:{label}")
            continue
        try:
            normalized.append(normalize_relative_output_path(_path_text(value)))
        except OutputWriteError:
            errors.append(f"invalid_path:{value}")
    return normalized, errors
