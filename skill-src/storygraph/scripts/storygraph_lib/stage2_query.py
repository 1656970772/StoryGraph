from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .output_writer import OutputWriter


QUERY_RESULT_SCHEMA = "stage2-template-query-result.v1"
DEFAULT_QUERY_RESULT_PATH = "intermediate/stage2/query-results/query-result.json"
DEFAULT_EVIDENCE_TEXT_FIELDS = ["fact_summary", "support", "quote", "source_excerpt"]
DEFAULT_GRAPH_TEXT_FIELDS = ["label", "name", "description", "summary"]


class Stage2QueryError(ValueError):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}")


def query_template_candidates(graph_dir: str | Path, query_parameters: dict) -> dict:
    return query_stage2_cases(graph_dir, query_parameters)


def query_stage2_cases(graph_dir: str | Path, query_parameters: dict) -> dict:
    graph_dir = Path(graph_dir)
    normalized_parameters = _normalize_query_parameters(query_parameters)
    graph = _read_json(graph_dir / "graphify-out" / "graph.json")
    evidence_index = _read_json(graph_dir / "coverage" / "evidence-index.json")
    graph_records = _graph_records_by_id(graph)
    template_name = normalized_parameters.get("template_name")
    candidate_cases = []
    rejected_candidates = []
    limit = normalized_parameters.get("limit")
    source_text_cache: dict[str, str | None] = {}

    for evidence in evidence_index if isinstance(evidence_index, list) else []:
        if not isinstance(evidence, dict):
            continue
        linked_records = _linked_graph_records(evidence, graph_records)
        target_records = _target_records(linked_records, normalized_parameters)
        if _target_type_mismatch(linked_records, target_records, normalized_parameters):
            rejected_candidates.append(
                _rejected_candidate(
                    evidence,
                    _target_mismatch_reason(normalized_parameters),
                )
            )
            continue
        excluded_terms = _matched_terms(
            evidence,
            target_records,
            normalized_parameters,
            graph_dir=graph_dir,
            source_text_cache=source_text_cache,
            term_key="exclude_terms",
        )
        if excluded_terms:
            rejected_candidates.append(
                _rejected_candidate(
                    evidence,
                    "exclude_terms_matched:" + ",".join(excluded_terms),
                )
            )
            continue
        matched_terms = _matched_terms(
            evidence,
            target_records,
            normalized_parameters,
            graph_dir=graph_dir,
            source_text_cache=source_text_cache,
        )
        if len(matched_terms) < _min_term_matches(normalized_parameters):
            rejected_candidates.append(_rejected_candidate(evidence, "no_query_terms_matched"))
            continue
        required_terms = _matched_terms(
            evidence,
            target_records,
            normalized_parameters,
            graph_dir=graph_dir,
            source_text_cache=source_text_cache,
            term_key="require_any_term",
        )
        if normalized_parameters.get("require_any_term") and not required_terms:
            rejected_candidates.append(_rejected_candidate(evidence, "required_terms_missing"))
            continue
        candidate_cases.append(
            _candidate_case(
                evidence,
                target_records,
                matched_terms,
                normalized_parameters,
                graph_dir=graph_dir,
                source_text_cache=source_text_cache,
            )
        )
        if isinstance(limit, int) and limit > 0 and len(candidate_cases) >= limit:
            break

    return {
        "schema": QUERY_RESULT_SCHEMA,
        "template_name": template_name,
        "template_file": normalized_parameters.get("template_file"),
        "template_path": normalized_parameters.get("template_path"),
        "graph_dir": str(graph_dir),
        "source_graph": "graphify-out/graph.json",
        "source_evidence_index": "coverage/evidence-index.json",
        "query_parameters": normalized_parameters,
        "candidate_cases": candidate_cases,
        "rejected_candidates": rejected_candidates,
        "summary": {
            "candidate_count": len(candidate_cases),
            "rejected_count": len(rejected_candidates),
            "include_terms": list(normalized_parameters.get("include_terms") or []),
            "exclude_terms": list(normalized_parameters.get("exclude_terms") or []),
            "target_kinds": list(normalized_parameters.get("target_kinds") or []),
        },
    }


def write_query_result(
    graph_dir: str | Path,
    query_result: dict,
    output_path: str | Path = DEFAULT_QUERY_RESULT_PATH,
) -> Path:
    writer = OutputWriter(
        graph_dir,
        ["intermediate/stage2/query-results/*.json"],
    )
    return writer.write_json(output_path, query_result)


def write_stage2_query_result(
    graph_dir: str | Path,
    query_result: dict,
    output_path: str | Path = DEFAULT_QUERY_RESULT_PATH,
) -> Path:
    return write_query_result(graph_dir, query_result, output_path)


def _normalize_query_parameters(query_parameters: dict) -> dict:
    normalized = dict(query_parameters)
    normalized["_uses_target_kinds"] = "target_kinds" in normalized
    if "include_terms" not in normalized:
        normalized["include_terms"] = list(normalized.get("query_terms") or [])
    if "query_terms" not in normalized:
        normalized["query_terms"] = list(normalized.get("include_terms") or [])
    if "target_kinds" not in normalized:
        normalized["target_kinds"] = list(normalized.get("target_types") or [])
    if "target_types" not in normalized:
        normalized["target_types"] = list(normalized.get("target_kinds") or [])
    normalized.setdefault("exclude_terms", [])
    normalized.setdefault("require_any_term", [])
    normalized.setdefault("field_alias", {})
    normalized.setdefault("rough_filter_rules", normalized.get("rough_filter") or {})
    normalized.setdefault("rough_filter", normalized.get("rough_filter_rules") or {})
    return normalized


def _read_json(path: Path) -> Any:
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        raise Stage2QueryError("json_utf8_bom", str(path))
    try:
        return json.loads(data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise Stage2QueryError("json_utf8_decode_failed", f"{path}:{exc}") from exc
    except json.JSONDecodeError as exc:
        raise Stage2QueryError("json_parse_failed", f"{path}:{exc.msg}") from exc


def _graph_records_by_id(graph: dict) -> dict[str, dict]:
    records = {}
    for collection, default_kind in (
        ("nodes", "node"),
        ("edges", "edge"),
        ("events", "event"),
    ):
        for item in graph.get(collection, []) if isinstance(graph, dict) else []:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            record = dict(item)
            record["_graph_kind"] = default_kind
            records[record["id"]] = record
    return records


def _linked_graph_records(evidence: dict, graph_records: dict[str, dict]) -> list[dict]:
    linked_ids = []
    for key in ("linked_node_ids", "linked_edge_ids", "linked_event_ids"):
        values = evidence.get(key)
        if isinstance(values, list):
            linked_ids.extend(value for value in values if isinstance(value, str))
    records = [graph_records[item_id] for item_id in linked_ids if item_id in graph_records]
    evidence_id = evidence.get("evidence_id")
    if evidence_id:
        for record in graph_records.values():
            record_evidence_ids = record.get("evidence_ids")
            if isinstance(record_evidence_ids, list) and evidence_id in record_evidence_ids:
                if record not in records:
                    records.append(record)
    return records


def _target_records(linked_records: list[dict], query_parameters: dict) -> list[dict]:
    target_types = set(query_parameters.get("target_kinds") or query_parameters.get("target_types") or [])
    if not target_types:
        return linked_records
    return [
        record
        for record in linked_records
        if _record_type(record) in target_types
    ]


def _target_type_mismatch(
    linked_records: list[dict],
    target_records: list[dict],
    query_parameters: dict,
) -> bool:
    return bool(query_parameters.get("target_kinds") or query_parameters.get("target_types")) and bool(linked_records) and not target_records


def _target_mismatch_reason(query_parameters: dict) -> str:
    if query_parameters.get("_uses_target_kinds"):
        return "target_kind_mismatch"
    return "target_type_mismatch"


def _record_type(record: dict) -> str | None:
    for key in ("node_type", "edge_type", "event_type", "type", "category"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return record.get("_graph_kind")


def _matched_terms(
    evidence: dict,
    target_records: list[dict],
    query_parameters: dict,
    *,
    graph_dir: Path | None = None,
    source_text_cache: dict[str, str | None] | None = None,
    term_key: str = "include_terms",
) -> list[str]:
    terms = [term for term in query_parameters.get(term_key, []) if isinstance(term, str)]
    include_source_chunks = term_key != "exclude_terms"
    haystack = "\n".join(
        _candidate_texts(
            evidence,
            target_records,
            query_parameters,
            graph_dir=graph_dir,
            source_text_cache=source_text_cache,
            include_source_chunks=include_source_chunks,
        )
    )
    return [term for term in terms if term and term in haystack]


def _candidate_texts(
    evidence: dict,
    target_records: list[dict],
    query_parameters: dict,
    *,
    graph_dir: Path | None = None,
    source_text_cache: dict[str, str | None] | None = None,
    include_source_chunks: bool = True,
) -> list[str]:
    rough_filter = query_parameters.get("rough_filter_rules") or query_parameters.get("rough_filter") or {}
    field_alias = query_parameters.get("field_alias") or {}
    evidence_fields = (
        field_alias.get("evidence_text")
        or rough_filter.get("text_fields")
        or DEFAULT_EVIDENCE_TEXT_FIELDS
    )
    graph_fields = (
        field_alias.get("graph_text")
        or rough_filter.get("graph_text_fields")
        or rough_filter.get("text_fields")
        or DEFAULT_GRAPH_TEXT_FIELDS
    )
    texts = _values_for_fields(evidence, evidence_fields)
    if rough_filter.get("include_graph_links", True):
        for record in target_records:
            texts.extend(_values_for_fields(record, graph_fields))
    if include_source_chunks and rough_filter.get("include_source_chunks", True):
        source_text = _source_chunk_text(evidence, graph_dir, source_text_cache)
        if source_text:
            texts.append(source_text)
    return texts


def _values_for_fields(record: dict, field_names: list[str]) -> list[str]:
    values = []
    for field_name in field_names:
        value = record.get(field_name)
        if isinstance(value, str) and value:
            values.append(value)
        elif isinstance(value, (list, dict)):
            values.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return values


def _min_term_matches(query_parameters: dict) -> int:
    rough_filter = query_parameters.get("rough_filter_rules") or query_parameters.get("rough_filter") or {}
    value = rough_filter.get("min_term_matches", 1)
    return value if isinstance(value, int) and value > 0 else 1


def _candidate_case(
    evidence: dict,
    target_records: list[dict],
    matched_terms: list[str],
    query_parameters: dict,
    *,
    graph_dir: Path | None = None,
    source_text_cache: dict[str, str | None] | None = None,
) -> dict:
    primary = target_records[0] if target_records else {}
    evidence_id = evidence.get("evidence_id")
    source_text = _source_chunk_text(evidence, graph_dir, source_text_cache)
    return {
        "candidate_name": _candidate_name(primary, evidence, matched_terms),
        "item_kind": _record_type(primary) if primary else None,
        "source_kind": "evidence",
        "candidate_type": _record_type(primary) if primary else None,
        "matched_terms": matched_terms,
        "required_fields": list(query_parameters.get("required_fields") or []),
        "evidence_ids": [evidence_id] if evidence_id else [],
        "source_excerpt": _source_excerpt(evidence, source_text, matched_terms),
        "fact_summary": evidence.get("fact_summary"),
        "source_range": evidence.get("source_range"),
        "source_locations": _source_locations(evidence, primary),
        "confidence": evidence.get("confidence") or primary.get("confidence"),
        "review_status": (
            evidence.get("verification_status")
            or evidence.get("review_status")
            or primary.get("verification_status")
            or primary.get("review_status")
        ),
        "rough_filter_reason": _rough_filter_reason(matched_terms, query_parameters),
    }


def _source_excerpt(evidence: dict, source_text: str | None, matched_terms: list[str]) -> str | None:
    if source_text:
        excerpt = _excerpt_around_terms(source_text, matched_terms)
        if excerpt:
            return excerpt
    return (
        evidence.get("source_excerpt")
        or evidence.get("quote")
        or evidence.get("support")
        or evidence.get("fact_summary")
    )


def _excerpt_around_terms(text: str, terms: list[str], *, radius: int = 80) -> str:
    if not text:
        return ""
    positions = [text.find(term) for term in terms if term and text.find(term) >= 0]
    if not positions:
        return text[: radius * 2].strip()
    start = max(0, min(positions) - radius)
    end = min(len(text), min(positions) + radius)
    return text[start:end].strip()


def _source_chunk_text(
    evidence: dict,
    graph_dir: Path | None,
    source_text_cache: dict[str, str | None] | None,
) -> str | None:
    if graph_dir is None:
        return None
    chunk_id = _chunk_id(evidence)
    if not chunk_id:
        return None
    if source_text_cache is not None and chunk_id in source_text_cache:
        return source_text_cache[chunk_id]
    path = graph_dir / "intermediate" / "chunks" / f"{chunk_id}.txt"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = None
    if source_text_cache is not None:
        source_text_cache[chunk_id] = text
    return text


def _chunk_id(evidence: dict) -> str | None:
    chunk_id = evidence.get("chunk_id")
    if isinstance(chunk_id, str) and chunk_id:
        return chunk_id
    location = evidence.get("source_location")
    if isinstance(location, dict):
        chunk_id = location.get("chunk_id")
        if isinstance(chunk_id, str) and chunk_id:
            return chunk_id
    return None


def _candidate_name(primary: dict, evidence: dict, matched_terms: list[str]) -> str:
    for key in ("label", "name", "title", "id"):
        value = primary.get(key)
        if isinstance(value, str) and value:
            return value
    return matched_terms[0] if matched_terms else evidence.get("evidence_id", "未命名候选")


def _source_locations(evidence: dict, primary: dict) -> list[dict]:
    locations = []
    for source in (evidence, primary):
        location = source.get("source_location")
        if isinstance(location, dict) and location not in locations:
            locations.append(location)
    return locations


def _rough_filter_reason(matched_terms: list[str], query_parameters: dict) -> str:
    if query_parameters.get("include_terms"):
        return "matched_include_terms:" + ",".join(matched_terms)
    return "matched_query_terms:" + ",".join(matched_terms)


def _rejected_candidate(evidence: dict, reason: str) -> dict:
    return {
        "evidence_id": evidence.get("evidence_id"),
        "reason": reason,
        "fact_summary": evidence.get("fact_summary"),
        "source_range": evidence.get("source_range"),
    }
