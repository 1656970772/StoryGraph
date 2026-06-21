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


def make_lane_agent_record(
    *,
    run_id: str,
    chunk_id: str,
    lane_id: str,
    agent_role: str,
    task_packet_path: str | Path,
    output_path: str | Path,
    attempt: int = 1,
    input_paths: Iterable[str | Path] | str | Path | None = None,
    write_scope: Iterable[str | Path] | str | Path | None = None,
    status: str = "pending",
    errors: Iterable[str] | None = None,
    reviewer_status: str = "pending",
    repair_of: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
) -> dict:
    return _make_stage1_rewrite_record(
        run_id=run_id,
        chunk_id=chunk_id,
        lane_id=lane_id,
        agent_role=agent_role,
        prompt_or_input_packet=task_packet_path,
        input_paths=input_paths,
        output_paths=output_path,
        write_scope=write_scope,
        status=status,
        errors=errors,
        reviewer_status=reviewer_status,
        repair_of=repair_of,
        attempt=attempt,
        started_at=started_at,
        ended_at=ended_at,
    )


def make_template_agent_record(
    *,
    run_id: str,
    chunk_id: str,
    lane_id: str,
    agent_role: str,
    template_name: str,
    task_packet_path: str | Path,
    output_path: str | Path,
    attempt: int,
    input_paths: Iterable[str | Path] | str | Path | None = None,
    write_scope: Iterable[str | Path] | str | Path | None = None,
    status: str = "pending",
    errors: Iterable[str] | None = None,
    reviewer_status: str = "pending",
    repair_of: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
) -> dict:
    record = _make_stage1_rewrite_record(
        run_id=run_id,
        chunk_id=chunk_id,
        lane_id=lane_id,
        agent_role=agent_role,
        prompt_or_input_packet=task_packet_path,
        input_paths=input_paths,
        output_paths=output_path,
        write_scope=write_scope,
        status=status,
        errors=errors,
        reviewer_status=reviewer_status,
        repair_of=repair_of,
        attempt=attempt,
        started_at=started_at,
        ended_at=ended_at,
    )
    record["template_name"] = template_name
    return record


def make_review_agent_record(
    *,
    run_id: str,
    chunk_id: str,
    lane_id: str,
    agent_role: str,
    review_input_path: str | Path,
    output_path: str | Path,
    attempt: int,
    input_paths: Iterable[str | Path] | str | Path | None = None,
    write_scope: Iterable[str | Path] | str | Path | None = None,
    status: str = "pending",
    errors: Iterable[str] | None = None,
    reviewer_status: str = "pending",
    repair_of: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
) -> dict:
    return _make_stage1_rewrite_record(
        run_id=run_id,
        chunk_id=chunk_id,
        lane_id=lane_id,
        agent_role=agent_role,
        prompt_or_input_packet=review_input_path,
        input_paths=input_paths,
        output_paths=output_path,
        write_scope=write_scope,
        status=status,
        errors=errors,
        reviewer_status=reviewer_status,
        repair_of=repair_of,
        attempt=attempt,
        started_at=started_at,
        ended_at=ended_at,
    )


def make_repair_agent_record(
    *,
    run_id: str,
    chunk_id: str,
    lane_id: str,
    agent_role: str,
    task_packet_path: str | Path,
    output_path: str | Path,
    repair_of: str,
    attempt: int,
    input_paths: Iterable[str | Path] | str | Path | None = None,
    write_scope: Iterable[str | Path] | str | Path | None = None,
    status: str = "pending",
    errors: Iterable[str] | None = None,
    reviewer_status: str = "pending",
    started_at: str | None = None,
    ended_at: str | None = None,
) -> dict:
    return _make_stage1_rewrite_record(
        run_id=run_id,
        chunk_id=chunk_id,
        lane_id=lane_id,
        agent_role=agent_role,
        prompt_or_input_packet=task_packet_path,
        input_paths=input_paths,
        output_paths=output_path,
        write_scope=write_scope,
        status=status,
        errors=errors,
        reviewer_status=reviewer_status,
        repair_of=repair_of,
        attempt=attempt,
        started_at=started_at,
        ended_at=ended_at,
    )


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


def validate_repair_attempts(findings: Iterable[dict], records: Iterable[dict]) -> LedgerValidation:
    errors: list[str] = []
    original_run_ids: set[str] = set()
    repairs_by_finding: dict[str, list[dict]] = {}

    record_items = _ledger_items(records, "bad_agent_ledger_records", errors)
    finding_items = _ledger_items(findings, "bad_review_findings", errors)

    for record in record_items:
        if not isinstance(record, dict):
            errors.append("bad_agent_ledger_record")
            continue
        run_id = record.get("run_id")
        repair_of = record.get("repair_of")
        if repair_of is not None:
            if not isinstance(repair_of, str) or not repair_of:
                errors.append("bad_repair_of")
                continue
            if not isinstance(run_id, str) or not run_id:
                errors.append(f"bad_repair_run_id:{repair_of}")
            repairs_by_finding.setdefault(repair_of, []).append(record)
            continue
        if not isinstance(run_id, str) or not run_id:
            errors.append("bad_agent_run_id")
            continue
        original_run_ids.add(run_id)

    for finding in finding_items:
        if not isinstance(finding, dict):
            errors.append("bad_review_finding")
            continue
        finding_id = finding.get("finding_id")
        if not isinstance(finding_id, str) or not finding_id:
            errors.append("bad_review_finding_id")
            continue
        status = finding.get("status")
        if not isinstance(status, str) or not status:
            errors.append(f"bad_review_finding_status:{finding_id}")
            continue
        repair_required = finding.get("repair_required")
        if not isinstance(repair_required, bool):
            errors.append(f"bad_review_finding_repair_required:{finding_id}")
            continue
        if status != "open" or repair_required is not True:
            continue
        finding_key = finding_id
        repair_records = repairs_by_finding.get(finding_key, [])
        if not repair_records:
            errors.append(f"missing_repair_attempt:{finding_key}")
            continue

        seen_repair_run_ids: set[str] = set()
        freshness_failed = False
        for repair_record in repair_records:
            repair_run_id = repair_record.get("run_id")
            if not isinstance(repair_run_id, str) or not repair_run_id:
                continue
            repair_run_key = repair_run_id
            if repair_run_key in original_run_ids or repair_run_key in seen_repair_run_ids:
                freshness_failed = True
            seen_repair_run_ids.add(repair_run_key)
        if freshness_failed:
            errors.append(f"repair_agent_not_fresh:{finding_key}")

    return LedgerValidation(ok=not errors, errors=errors)


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


def _make_stage1_rewrite_record(
    *,
    run_id: str,
    chunk_id: str,
    lane_id: str,
    agent_role: str,
    prompt_or_input_packet: str | Path,
    input_paths: Iterable[str | Path] | str | Path | None,
    output_paths: Iterable[str | Path] | str | Path,
    write_scope: Iterable[str | Path] | str | Path | None,
    status: str,
    errors: Iterable[str] | None,
    reviewer_status: str,
    repair_of: str | None,
    attempt: int,
    started_at: str | None,
    ended_at: str | None,
) -> dict:
    prompt_path = _normalized_ledger_path(
        prompt_or_input_packet, "prompt_or_input_packet"
    )
    normalized_inputs = _dedupe_paths(
        [prompt_path] + _normalized_ledger_path_list(input_paths, "input_paths")
    )
    normalized_outputs = _normalized_ledger_path_list(output_paths, "output_paths")
    if not normalized_outputs:
        raise OutputWriteError("unmanaged_output", "output_paths")
    normalized_scope = (
        _normalized_ledger_path_list(write_scope, "write_scope")
        if write_scope is not None
        else list(normalized_outputs)
    )
    return {
        "run_id": run_id,
        "stage": "stage1",
        "chunk_id": chunk_id,
        "lane_id": lane_id,
        "agent_role": agent_role,
        "prompt_or_input_packet": prompt_path,
        "input_paths": normalized_inputs,
        "output_paths": normalized_outputs,
        "write_scope": normalized_scope,
        "status": status,
        "errors": list(errors or []),
        "reviewer_status": reviewer_status,
        "repair_of": repair_of,
        "attempt": attempt,
        "started_at": started_at,
        "ended_at": ended_at,
    }


def _ledger_items(values: Iterable[dict], error_code: str, errors: list[str]) -> list[dict]:
    if isinstance(values, (dict, str, bytes)):
        errors.append(error_code)
        return []
    try:
        return list(values)
    except TypeError:
        errors.append(error_code)
        return []


def _normalized_ledger_path(value: str | Path, label: str = "paths") -> str:
    if not isinstance(value, (str, Path)):
        raise OutputWriteError("invalid_path_item", label)
    return normalize_relative_output_path(value)


def _normalized_ledger_path_list(
    values: Iterable[str | Path] | str | Path | None,
    label: str = "paths",
) -> list[str]:
    if values is None:
        return []
    if isinstance(values, (str, Path)):
        path_items = [values]
    elif isinstance(values, dict):
        raise OutputWriteError("invalid_path_list", label)
    else:
        try:
            path_items = list(values)
        except TypeError as exc:
            raise OutputWriteError("invalid_path_list", label) from exc

    normalized = []
    for value in path_items:
        if not isinstance(value, (str, Path)):
            raise OutputWriteError("invalid_path_item", label)
        normalized.append(_normalized_ledger_path(value))
    return normalized


def _dedupe_paths(paths: Iterable[str]) -> list[str]:
    seen = set()
    deduped = []
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        deduped.append(path)
    return deduped


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
