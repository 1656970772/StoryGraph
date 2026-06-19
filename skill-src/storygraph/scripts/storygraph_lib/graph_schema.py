from copy import deepcopy
from dataclasses import dataclass
from typing import Any


DEFAULT_STATUS_ENUMS = {
    "requirement_statuses": ["covered", "needs_review", "not_found_in_source"],
    "verification_statuses": ["verified", "needs_review", "rejected"],
    "confidence_levels": ["EXTRACTED", "INFERRED", "AMBIGUOUS"],
}

REQUIRED_TOP_LEVEL_FIELDS = [
    "schema_version",
    "graphify_schema_version",
    "storygraph_schema_version",
    "nodes",
    "edges",
    "hyperedges",
    "events",
    "evidence_index",
    "metadata",
]

STORYGRAPH_MARKERS = {
    "node_type",
    "edge_type",
    "event_type",
    "evidence_ids",
    "supports_templates",
    "confidence",
    "verification_status",
}


@dataclass(frozen=True)
class SchemaValidation:
    ok: bool
    errors: list[str]


def merge_template_supplements(base: dict[str, Any], supplement: dict[str, Any]) -> dict[str, Any]:
    graph = deepcopy(base)
    graph.setdefault("nodes", [])
    graph.setdefault("edges", [])
    graph.setdefault("hyperedges", [])
    graph.setdefault("events", [])
    graph.setdefault("evidence_index", [])
    graph.setdefault("metadata", {})
    graph.setdefault("schema_version", "1.0")
    graph.setdefault(
        "graphify_schema_version",
        graph.get("metadata", {}).get("graphify_schema_version", "unknown"),
    )
    graph.setdefault("storygraph_schema_version", "1.0")

    merged_nodes: dict[str, dict[str, Any]] = {}
    node_order: list[str] = []
    anonymous_nodes: list[dict[str, Any]] = []
    for node in graph["nodes"]:
        copied = deepcopy(node)
        node_id = copied.get("id")
        if not node_id:
            anonymous_nodes.append(copied)
            continue
        merged_nodes[node_id] = copied
        node_order.append(node_id)

    for node in supplement.get("nodes", []):
        copied = deepcopy(node)
        node_id = copied.get("id")
        if not node_id:
            anonymous_nodes.append(copied)
            continue
        if node_id not in merged_nodes:
            node_order.append(node_id)
        merged_nodes[node_id] = {**merged_nodes.get(node_id, {}), **copied}

    graph["nodes"] = anonymous_nodes + [merged_nodes[node_id] for node_id in node_order]
    graph["edges"].extend(deepcopy(supplement.get("edges", [])))
    graph["events"].extend(deepcopy(supplement.get("events", [])))
    graph["evidence_index"].extend(deepcopy(supplement.get("evidence_index", [])))
    if "hyperedges" in supplement:
        graph["hyperedges"].extend(deepcopy(supplement.get("hyperedges", [])))
    return graph


def validate_canonical_graph(
    graph: dict[str, Any], status_enums: dict[str, list[str]] | None = None
) -> SchemaValidation:
    enums = _status_enums(status_enums)
    errors = [f"missing:{key}" for key in REQUIRED_TOP_LEVEL_FIELDS if key not in graph]
    collections = {
        key: _graph_collection(graph, key, errors)
        for key in ["nodes", "edges", "hyperedges", "events", "evidence_index"]
    }
    evidence_ids = {
        evidence.get("evidence_id")
        for evidence in collections["evidence_index"]
        if isinstance(evidence, dict)
    }
    node_ids = {
        node.get("id") for node in collections["nodes"] if isinstance(node, dict)
    }

    for node in collections["nodes"]:
        if not isinstance(node, dict) or not _is_storygraph_item(node):
            continue
        _validate_node(node, evidence_ids, enums, errors)

    for edge in collections["edges"]:
        if not isinstance(edge, dict) or not _is_storygraph_item(edge):
            continue
        _validate_edge(edge, node_ids, evidence_ids, enums, errors)

    for event in collections["events"]:
        if not isinstance(event, dict) or not _is_storygraph_item(event):
            continue
        _validate_event(event, node_ids, evidence_ids, enums, errors)

    for evidence in collections["evidence_index"]:
        if not isinstance(evidence, dict):
            errors.append("bad_evidence_record")
            continue
        _validate_evidence(evidence, enums, errors)

    return SchemaValidation(ok=not errors, errors=errors)


def _graph_collection(graph: dict[str, Any], key: str, errors: list[str]) -> list:
    values = graph.get(key, [])
    if not isinstance(values, list):
        errors.append(f"bad_graph_collection:{key}")
        return []
    return values


def _status_enums(status_enums: dict[str, list[str]] | None) -> dict[str, set[str]]:
    merged = {key: list(value) for key, value in DEFAULT_STATUS_ENUMS.items()}
    if status_enums:
        for key, value in status_enums.items():
            merged[key] = list(value)
    return {key: set(value) for key, value in merged.items()}


def _is_storygraph_item(item: dict[str, Any]) -> bool:
    return any(marker in item for marker in STORYGRAPH_MARKERS)


def _validate_node(
    node: dict[str, Any],
    evidence_ids: set[str | None],
    enums: dict[str, set[str]],
    errors: list[str],
) -> None:
    node_id = node.get("id")
    if not isinstance(node_id, str) or not node_id.startswith("node:"):
        errors.append(f"bad_node_id:{node_id}")
    for key in ["node_type", "evidence_ids", "supports_templates", "confidence", "verification_status"]:
        if key not in node:
            errors.append(f"node_missing:{node_id}:{key}")
    _validate_source_locator("node", node_id, node, errors)
    _validate_evidence_refs("node", node_id, node.get("evidence_ids"), evidence_ids, errors)
    _validate_status_fields(node, enums, errors)
    _validate_supports("node", node_id, node.get("supports_templates"), enums, errors)


def _validate_edge(
    edge: dict[str, Any],
    node_ids: set[str | None],
    evidence_ids: set[str | None],
    enums: dict[str, set[str]],
    errors: list[str],
) -> None:
    edge_id = edge.get("id")
    if not isinstance(edge_id, str) or not edge_id.startswith("edge:"):
        errors.append(f"bad_edge_id:{edge_id}")
    for key in [
        "id",
        "source",
        "target",
        "edge_type",
        "evidence_ids",
        "supports_templates",
        "confidence",
        "verification_status",
    ]:
        if key not in edge:
            errors.append(f"edge_missing:{edge_id}:{key}")
    if edge.get("source") not in node_ids or edge.get("target") not in node_ids:
        errors.append(f"edge_unknown_node:{edge_id}")
    _validate_source_locator("edge", edge_id, edge, errors)
    _validate_evidence_refs("edge", edge_id, edge.get("evidence_ids"), evidence_ids, errors)
    _validate_status_fields(edge, enums, errors)
    _validate_supports("edge", edge_id, edge.get("supports_templates"), enums, errors)


def _validate_event(
    event: dict[str, Any],
    node_ids: set[str | None],
    evidence_ids: set[str | None],
    enums: dict[str, set[str]],
    errors: list[str],
) -> None:
    event_id = event.get("id")
    if not isinstance(event_id, str) or not event_id.startswith("event:"):
        errors.append(f"bad_event_id:{event_id}")
    for key in [
        "id",
        "event_type",
        "participants",
        "evidence_ids",
        "supports_templates",
        "confidence",
        "verification_status",
    ]:
        if key not in event:
            errors.append(f"event_missing:{event_id}:{key}")
    participants = event.get("participants", [])
    if not isinstance(participants, list) or any(pid not in node_ids for pid in participants):
        errors.append(f"event_unknown_node:{event_id}")
    _validate_source_locator("event", event_id, event, errors)
    _validate_evidence_refs("event", event_id, event.get("evidence_ids"), evidence_ids, errors)
    _validate_status_fields(event, enums, errors)
    _validate_supports("event", event_id, event.get("supports_templates"), enums, errors)


def _validate_evidence(
    evidence: dict[str, Any], enums: dict[str, set[str]], errors: list[str]
) -> None:
    evidence_id = evidence.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.startswith("evidence:"):
        errors.append(f"bad_evidence_id:{evidence_id}")
    for key in [
        "source_range",
        "fact_summary",
        "confidence",
        "verification_status",
        "supports_templates",
    ]:
        if key not in evidence:
            errors.append(f"evidence_missing:{evidence_id}:{key}")
    _validate_status_fields(evidence, enums, errors)
    _validate_supports("evidence", evidence_id, evidence.get("supports_templates"), enums, errors)


def _validate_evidence_refs(
    owner: str,
    owner_id: object,
    refs: object,
    known_evidence_ids: set[str | None],
    errors: list[str],
) -> None:
    if not isinstance(refs, list) or not refs:
        errors.append(f"{owner}_without_evidence:{owner_id}")
        return
    if any(ref not in known_evidence_ids for ref in refs):
        errors.append(f"{owner}_unknown_evidence:{owner_id}")


def _validate_source_locator(
    owner: str, owner_id: object, item: dict[str, Any], errors: list[str]
) -> None:
    if not (_has_locator_value(item.get("source_location")) or _has_locator_value(item.get("source_range"))):
        errors.append(f"{owner}_without_source_location:{owner_id}")


def _has_locator_value(value: object) -> bool:
    return value not in (None, "", [], {})


def _validate_status_fields(
    item: dict[str, Any], enums: dict[str, set[str]], errors: list[str]
) -> None:
    confidence = item.get("confidence")
    if confidence not in enums["confidence_levels"]:
        errors.append(f"bad_confidence:{confidence}")
    verification_status = item.get("verification_status")
    if verification_status not in enums["verification_statuses"]:
        errors.append(f"bad_verification_status:{verification_status}")


def _validate_supports(
    owner: str,
    owner_id: object,
    supports: object,
    enums: dict[str, set[str]],
    errors: list[str],
) -> None:
    if not isinstance(supports, list) or not supports:
        errors.append(f"{owner}_without_supports:{owner_id}")
        return
    for support in supports:
        if not isinstance(support, dict):
            errors.append(f"{owner}_bad_support:{owner_id}")
            continue
        for key in ["template_name", "requirement_id", "status"]:
            if key not in support:
                errors.append(f"{owner}_support_missing:{owner_id}:{key}")
        status = support.get("status")
        if status not in enums["requirement_statuses"]:
            errors.append(f"bad_requirement_status:{status}")
