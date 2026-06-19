from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any

from .ids import stable_edge_id, stable_event_id, stable_evidence_id, stable_node_id
from .template_rules import DEFAULT_REQUIREMENT_STATUSES


def extract_template_aware_supplements(
    source_path: str | Path,
    requirement_matrix: dict,
    chunk_ledger: dict,
    novel_name: str | None = None,
    matching_strategy: dict | None = None,
) -> dict[str, Any]:
    source = Path(source_path)
    active_novel_name = novel_name or source.stem
    strategy = matching_strategy or {}
    case_sensitive = bool(strategy.get("case_sensitive", False))
    confidence = strategy.get("minimum_confidence", "EXTRACTED")

    nodes: OrderedDict[str, dict] = OrderedDict()
    edges: OrderedDict[str, dict] = OrderedDict()
    events: OrderedDict[str, dict] = OrderedDict()
    evidence_index: OrderedDict[str, dict] = OrderedDict()
    template_readiness = []

    for template in requirement_matrix.get("templates", []):
        template_name = template.get("template_name") or template.get("name")
        if not template_name:
            continue
        requirements = _template_requirements(template, template_name)
        covered = 0
        for requirement in requirements:
            match = _find_evidence(requirement["value"], chunk_ledger, case_sensitive)
            if not match:
                continue
            covered += 1
            support = _support(template_name, requirement, "covered")
            evidence_id = stable_evidence_id(
                active_novel_name,
                f"{match['chunk_id']}:{requirement['requirement_id']}",
                match["source_range"],
            )
            source_location = {
                "source_path": str(source),
                "chunk_id": match["chunk_id"],
                "chapter": match.get("chapter"),
                "source_range": match["source_range"],
            }
            evidence_index[evidence_id] = {
                "evidence_id": evidence_id,
                "source_path": str(source),
                "source_range": match["source_range"],
                "source_location": source_location,
                "chunk_id": match["chunk_id"],
                "support": match["support"],
                "fact_summary": f"{template_name}:{requirement['kind']}:{requirement['value']}",
                "confidence": confidence,
                "verification_status": "verified",
                "supports_templates": [support],
            }

            node_type = _first_mapping(template, "graph_node_mapping", f"{template_name}.node")
            event_type = _first_mapping(template, "graph_event_mapping", f"{template_name}.event")
            relation_type = _first_mapping(
                template, "graph_relation_mapping", f"{template_name}.relation"
            )
            requirement_node_id = stable_node_id(
                active_novel_name,
                f"{template_name}:{requirement['kind']}:{requirement['value']}",
                node_type,
            )
            event_node_id = stable_node_id(
                active_novel_name,
                f"{template_name}:{requirement['requirement_id']}:event-node",
                "event_node",
            )
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
            event_id = stable_event_id(
                active_novel_name,
                event_type,
                requirement["requirement_id"],
                match["source_range"],
            )
            events[event_id] = {
                "id": event_id,
                "event_type": event_type,
                "participants": [event_node_id, requirement_node_id],
                "source_range": match["source_range"],
                "source_location": source_location,
                "evidence_ids": [evidence_id],
                "supports_templates": [support],
                "confidence": confidence,
                "verification_status": "verified",
            }
            edge_id = stable_edge_id(
                active_novel_name,
                event_node_id,
                requirement_node_id,
                relation_type,
            )
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
        template_readiness.append(
            {
                "template_name": template_name,
                "status": _readiness_status(covered, len(requirements)),
                "covered_requirements": covered,
                "total_requirements": len(requirements),
            }
        )

    return {
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
        "events": list(events.values()),
        "evidence_index": list(evidence_index.values()),
        "template_readiness": template_readiness,
        "metadata": {
            "readiness_statuses": list(DEFAULT_REQUIREMENT_STATUSES),
            "evidence_matching_strategy": "substring",
        },
    }


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
            requirement_id = f"{template_name}.{key}.{value}"
            requirement = {"kind": kind, "key": key, "value": value, "requirement_id": requirement_id}
            requirements.append(requirement)
    return requirements


def _find_evidence(value: str, chunk_ledger: dict, case_sensitive: bool) -> dict | None:
    needle = value if case_sensitive else value.casefold()
    for chunk in chunk_ledger.get("chunks", []):
        text = chunk.get("text", "")
        haystack = text if case_sensitive else text.casefold()
        offset = haystack.find(needle)
        if offset < 0:
            continue
        start = chunk["source_range"][0] + offset
        end = start + len(value)
        return {
            "chunk_id": chunk["chunk_id"],
            "chapter": chunk.get("chapter"),
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


def _readiness_status(covered: int, total: int) -> str:
    if total == 0:
        return "needs_review"
    if covered == total:
        return "covered"
    if covered:
        return "needs_review"
    return "not_found_in_source"
