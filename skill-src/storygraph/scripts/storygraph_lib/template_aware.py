from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any

from .ids import stable_edge_id, stable_event_id, stable_evidence_id, stable_node_id
from .template_rules import DEFAULT_REQUIREMENT_STATUSES


def extract_template_aware_supplements(
    novel_name: str,
    source_path: str | Path,
    chunks: list[dict],
    matrix: dict,
    evidence_strategy: dict | None,
) -> tuple[dict[str, Any], list[dict]]:
    source = Path(source_path)
    source_text = source.read_text(encoding="utf-8")
    strategy = evidence_strategy or {}
    case_sensitive = bool(strategy.get("case_sensitive", False))
    confidence = strategy.get("minimum_confidence", "EXTRACTED")

    nodes: OrderedDict[str, dict] = OrderedDict()
    edges: OrderedDict[str, dict] = OrderedDict()
    events: OrderedDict[str, dict] = OrderedDict()
    evidence_index: OrderedDict[str, dict] = OrderedDict()
    readiness: list[dict] = []

    for template in matrix.get("templates", []):
        template_name = template.get("template_name") or template.get("name")
        if not template_name:
            continue
        template_node_ids: set[str] = set()
        template_edge_ids: set[str] = set()
        template_event_ids: set[str] = set()
        template_evidence_ids: set[str] = set()
        requirement_statuses = []
        requirements = _template_requirements(template, template_name)

        for requirement in requirements:
            match = _find_evidence(requirement["value"], chunks, source_text, case_sensitive)
            if match:
                support = _support(template_name, requirement, "covered")
                evidence_id = stable_evidence_id(
                    novel_name,
                    f"{match['chunk_id']}:{requirement['requirement_id']}",
                    match["source_range"],
                )
                source_location = {
                    "source_path": str(source),
                    "chunk_id": match["chunk_id"],
                    "chapter_hint": match.get("chapter_hint"),
                    "source_range": match["source_range"],
                }
                node_type = _first_mapping(template, "graph_node_mapping", f"{template_name}.node")
                event_type = _first_mapping(template, "graph_event_mapping", f"{template_name}.event")
                relation_type = _first_mapping(
                    template, "graph_relation_mapping", f"{template_name}.relation"
                )
                requirement_node_id = stable_node_id(
                    novel_name,
                    f"{template_name}:{requirement['kind']}:{requirement['value']}",
                    node_type,
                )
                event_node_id = stable_node_id(
                    novel_name,
                    f"{template_name}:{requirement['requirement_id']}:event-node",
                    "event_node",
                )
                event_id = stable_event_id(
                    novel_name,
                    event_type,
                    requirement["requirement_id"],
                    match["source_range"],
                )
                edge_id = stable_edge_id(
                    novel_name,
                    event_node_id,
                    requirement_node_id,
                    relation_type,
                )
                linked_node_ids = [event_node_id, requirement_node_id]
                linked_edge_ids = [edge_id]
                linked_event_ids = [event_id]
                template_node_ids.update(linked_node_ids)
                template_edge_ids.add(edge_id)
                template_event_ids.add(event_id)
                template_evidence_ids.add(evidence_id)

                evidence_index[evidence_id] = {
                    "evidence_id": evidence_id,
                    "source_path": str(source),
                    "source_range": match["source_range"],
                    "source_location": source_location,
                    "chunk_id": match["chunk_id"],
                    "chapter_hint": match.get("chapter_hint"),
                    "support": match["support"],
                    "fact_summary": f"{template_name}:{requirement['kind']}:{requirement['value']}",
                    "confidence": confidence,
                    "verification_status": "verified",
                    "supports_templates": [support],
                    "linked_node_ids": linked_node_ids,
                    "linked_edge_ids": linked_edge_ids,
                    "linked_event_ids": linked_event_ids,
                }
                nodes[requirement_node_id] = {
                    "id": requirement_node_id,
                    "label": requirement["value"],
                    "node_type": node_type,
                    "requirement_kind": requirement["kind"],
                    "source_range": match["source_range"],
                    "source_location": source_location,
                    "evidence_ids": [evidence_id],
                    "supports_templates": [support],
                    "confidence": confidence,
                    "verification_status": "verified",
                }
                nodes[event_node_id] = {
                    "id": event_node_id,
                    "label": f"{template_name} evidence event",
                    "node_type": "event_node",
                    "source_range": match["source_range"],
                    "source_location": source_location,
                    "evidence_ids": [evidence_id],
                    "supports_templates": [support],
                    "confidence": confidence,
                    "verification_status": "verified",
                }
                events[event_id] = {
                    "id": event_id,
                    "event_type": event_type,
                    "participants": linked_node_ids,
                    "source_range": match["source_range"],
                    "source_location": source_location,
                    "evidence_ids": [evidence_id],
                    "supports_templates": [support],
                    "confidence": confidence,
                    "verification_status": "verified",
                }
                edges[edge_id] = {
                    "id": edge_id,
                    "source": event_node_id,
                    "target": requirement_node_id,
                    "edge_type": relation_type,
                    "source_range": match["source_range"],
                    "source_location": source_location,
                    "evidence_ids": [evidence_id],
                    "supports_templates": [support],
                    "confidence": confidence,
                    "verification_status": "verified",
                }
                requirement_statuses.append(
                    _requirement_status(requirement, "covered", linked_node_ids, linked_edge_ids, linked_event_ids, [evidence_id], [])
                )
            else:
                requirement_statuses.append(
                    _requirement_status(
                        requirement,
                        "not_found_in_source",
                        [],
                        [],
                        [],
                        [],
                        ["No substring evidence found in source chunks."],
                    )
                )

        readiness.append(
            _readiness_record(
                template_name,
                requirement_statuses,
                template_node_ids,
                template_edge_ids,
                template_event_ids,
                template_evidence_ids,
            )
        )

    supplement = {
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
        "events": list(events.values()),
        "evidence_index": list(evidence_index.values()),
        "metadata": {
            "readiness_statuses": list(DEFAULT_REQUIREMENT_STATUSES),
            "evidence_matching_strategy": "substring",
        },
    }
    return supplement, readiness


def _template_requirements(template: dict, template_name: str) -> list[dict]:
    requirements = []
    seen: set[tuple[str, str]] = set()
    for kind, key in [
        ("fields", "required_fields"),
        ("tables", "required_tables"),
        ("cards", "required_cards"),
        ("cards", "required_card_headings"),
        ("cards", "required_card_fields"),
        ("cases", "required_case_patterns"),
    ]:
        for value in template.get(key, []):
            if not value:
                continue
            marker = (kind, value)
            if marker in seen:
                continue
            seen.add(marker)
            requirements.append(
                {
                    "kind": kind,
                    "key": key,
                    "value": value,
                    "requirement_id": f"{template_name}.{key}.{value}",
                }
            )
    return requirements


def _find_evidence(
    value: str,
    chunks: list[dict],
    source_text: str,
    case_sensitive: bool,
) -> dict | None:
    needle = value if case_sensitive else value.casefold()
    for chunk in chunks:
        chunk_range = chunk.get("source_range", [0, 0])
        text = chunk.get("text")
        if text is None:
            text = source_text[chunk_range[0] : chunk_range[1]]
        haystack = text if case_sensitive else text.casefold()
        offset = haystack.find(needle)
        if offset < 0:
            continue
        start = chunk_range[0] + offset
        end = start + len(value)
        return {
            "chunk_id": chunk["chunk_id"],
            "chapter_hint": chunk.get("chapter_hint"),
            "source_range": [start, end],
            "support": text[offset : offset + len(value)],
        }
    return None


def _support(template_name: str, requirement: dict, status: str) -> dict:
    return {
        "template_name": template_name,
        "requirement_id": requirement["requirement_id"],
        "status": status,
    }


def _first_mapping(template: dict, key: str, default: str) -> str:
    values = template.get(key) or []
    return values[0] if values else default


def _requirement_status(
    requirement: dict,
    status: str,
    linked_node_ids: list[str],
    linked_edge_ids: list[str],
    linked_event_ids: list[str],
    evidence_ids: list[str],
    notes: list[str],
) -> dict:
    return {
        "requirement_id": requirement["requirement_id"],
        "requirement_kind": requirement["kind"],
        "status": status,
        "linked_node_ids": linked_node_ids,
        "linked_edge_ids": linked_edge_ids,
        "linked_event_ids": linked_event_ids,
        "evidence_ids": evidence_ids,
        "notes": notes,
    }


def _readiness_record(
    template_name: str,
    requirement_statuses: list[dict],
    node_ids: set[str],
    edge_ids: set[str],
    event_ids: set[str],
    evidence_ids: set[str],
) -> dict:
    total = len(requirement_statuses)
    covered = sum(1 for item in requirement_statuses if item["status"] == "covered")
    missing_types = []
    for item in requirement_statuses:
        if item["status"] == "not_found_in_source" and item["requirement_kind"] not in missing_types:
            missing_types.append(item["requirement_kind"])
    notes = []
    if missing_types:
        notes.append(f"{total - covered} requirement(s) not found in source chunks.")
    return {
        "template_name": template_name,
        "readiness_score": round(covered / total, 4) if total else 0.0,
        "supporting_node_count": len(node_ids),
        "supporting_edge_count": len(edge_ids),
        "supporting_event_count": len(event_ids),
        "evidence_count": len(evidence_ids),
        "missing_requirement_types": missing_types,
        "requirement_statuses": requirement_statuses,
        "notes": notes,
    }
