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

GRAPH_COLLECTION_FIELDS = ["nodes", "edges", "hyperedges", "events", "evidence_index"]
GRAPH_ITEM_OWNERS = {
    "nodes": "node",
    "edges": "edge",
    "hyperedges": "hyperedge",
    "events": "event",
    "evidence_index": "evidence",
}

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
    for key in GRAPH_COLLECTION_FIELDS:
        if not isinstance(graph.get(key), list):
            graph[key] = []
    if not isinstance(graph.get("metadata"), dict):
        graph["metadata"] = {}
    graph.setdefault("schema_version", "1.0")
    graph.setdefault(
        "graphify_schema_version",
        graph["metadata"].get("graphify_schema_version", "unknown"),
    )
    graph.setdefault("storygraph_schema_version", "1.0")

    merged_nodes: dict[str, dict[str, Any]] = {}
    node_order: list[str] = []
    anonymous_nodes: list[dict[str, Any]] = []
    for node in graph["nodes"]:
        copied = deepcopy(node)
        if not isinstance(copied, dict):
            continue
        node_id = copied.get("id")
        if not isinstance(node_id, str) or not node_id:
            anonymous_nodes.append(copied)
            continue
        merged_nodes[node_id] = copied
        node_order.append(node_id)

    for node in _safe_collection(supplement.get("nodes")):
        copied = deepcopy(node)
        if not isinstance(copied, dict):
            continue
        node_id = copied.get("id")
        if not isinstance(node_id, str) or not node_id:
            anonymous_nodes.append(copied)
            continue
        if node_id not in merged_nodes:
            node_order.append(node_id)
        merged_nodes[node_id] = {**merged_nodes.get(node_id, {}), **copied}

    graph["nodes"] = anonymous_nodes + [merged_nodes[node_id] for node_id in node_order]
    graph["edges"].extend(deepcopy(_safe_collection(supplement.get("edges"))))
    graph["events"].extend(deepcopy(_safe_collection(supplement.get("events"))))
    graph["evidence_index"].extend(deepcopy(_safe_collection(supplement.get("evidence_index"))))
    if "hyperedges" in supplement:
        graph["hyperedges"].extend(deepcopy(_safe_collection(supplement.get("hyperedges"))))
    return graph


def validate_canonical_graph(
    graph: dict[str, Any], status_enums: dict[str, list[str]] | None = None
) -> SchemaValidation:
    errors = [f"missing:{key}" for key in REQUIRED_TOP_LEVEL_FIELDS if key not in graph]
    _validate_top_level_shapes(graph, errors)
    _validate_agent_produced_metadata(graph.get("metadata"), errors)
    enums = _status_enums(status_enums, errors)
    collections = {
        key: _graph_collection(graph, key, errors)
        for key in GRAPH_COLLECTION_FIELDS
    }
    collections = {
        key: _valid_graph_items(key, values, errors)
        for key, values in collections.items()
    }
    evidence_ids = _string_field_set(collections["evidence_index"], "evidence_id")
    node_ids = _string_field_set(collections["nodes"], "id")

    for node in collections["nodes"]:
        if not _is_storygraph_item(node):
            continue
        _validate_node(node, evidence_ids, enums, errors)

    for edge in collections["edges"]:
        if not _is_storygraph_item(edge):
            continue
        _validate_edge(edge, node_ids, evidence_ids, enums, errors)

    for hyperedge in collections["hyperedges"]:
        if not _is_storygraph_item(hyperedge):
            continue
        _validate_hyperedge(hyperedge, evidence_ids, enums, errors)

    for event in collections["events"]:
        if not _is_storygraph_item(event):
            continue
        _validate_event(event, node_ids, evidence_ids, enums, errors)

    for evidence in collections["evidence_index"]:
        _validate_evidence(evidence, enums, errors)

    return SchemaValidation(ok=not errors, errors=errors)


def _validate_top_level_shapes(graph: dict[str, Any], errors: list[str]) -> None:
    for key in ["schema_version", "graphify_schema_version", "storygraph_schema_version"]:
        if key in graph and not isinstance(graph.get(key), str):
            errors.append(f"bad_graph_top_level:{key}")
    if "metadata" in graph and not isinstance(graph.get("metadata"), dict):
        errors.append("bad_graph_top_level:metadata")


def _graph_collection(graph: dict[str, Any], key: str, errors: list[str]) -> list:
    values = graph.get(key, [])
    if not isinstance(values, list):
        errors.append(f"bad_graph_collection:{key}")
        return []
    return values


def _valid_graph_items(key: str, values: list, errors: list[str]) -> list[dict[str, Any]]:
    valid_items = []
    owner = GRAPH_ITEM_OWNERS[key]
    for item in values:
        if not isinstance(item, dict):
            errors.append(
                "bad_evidence_record" if key == "evidence_index" else f"bad_graph_item:{key}"
            )
            continue
        _validate_graph_item_id(key, item, errors)
        _validate_locator_ranges(owner, _graph_item_owner_id(key, item), item, errors)
        _validate_provenance(
            owner,
            _graph_item_owner_id(key, item),
            item.get("provenance"),
            _is_storygraph_item(item),
            errors,
        )
        valid_items.append(item)
    return valid_items


def _validate_graph_item_id(key: str, item: dict[str, Any], errors: list[str]) -> None:
    if key == "evidence_index":
        return
    owner = GRAPH_ITEM_OWNERS[key]
    item_id = item.get("id")
    if not isinstance(item_id, str) or not item_id:
        errors.append(f"{owner}_bad_id:{item_id}")


def _graph_item_owner_id(key: str, item: dict[str, Any]) -> object:
    if key == "evidence_index":
        return item.get("evidence_id")
    return item.get("id")


def _safe_collection(values: object) -> list:
    return values if isinstance(values, list) else []


def _validate_agent_produced_metadata(metadata: object, errors: list[str]) -> None:
    if not isinstance(metadata, dict):
        return
    semantic_generation = metadata.get("semantic_generation")
    if semantic_generation is not None and not isinstance(semantic_generation, str):
        errors.append("bad_agent_metadata:semantic_generation")
    if semantic_generation != "agent-produced":
        return

    version = metadata.get("canonical_writer_version")
    if not isinstance(version, str) or not version:
        errors.append("bad_agent_metadata:canonical_writer_version")

    source_bundle_paths = metadata.get("source_bundle_paths")
    if not isinstance(source_bundle_paths, list) or any(
        not isinstance(path, str) or not path for path in source_bundle_paths
    ):
        errors.append("bad_agent_metadata:source_bundle_paths")


def _validate_provenance(
    owner: str,
    owner_id: object,
    provenance: object,
    require_agent_produced: bool,
    errors: list[str],
) -> None:
    if provenance is None:
        if require_agent_produced:
            errors.append(f"{owner}_missing_provenance:{owner_id}")
        return
    if not isinstance(provenance, dict):
        errors.append(f"bad_provenance:{owner_id}")
        return

    semantic_generation = provenance.get("semantic_generation")
    if not isinstance(semantic_generation, str):
        if semantic_generation is not None or require_agent_produced:
            errors.append(f"bad_provenance_semantic_generation:{owner_id}")
    elif require_agent_produced and semantic_generation != "agent-produced":
        errors.append(f"bad_provenance_semantic_generation:{owner_id}")

    _validate_provenance_string_list("chunk_id", owner_id, provenance.get("chunk_ids"), errors)
    _validate_provenance_string_list(
        "lane_output_path", owner_id, provenance.get("lane_output_paths"), errors
    )


def _validate_provenance_string_list(
    label: str, owner_id: object, values: object, errors: list[str]
) -> None:
    if values is None:
        return
    if not isinstance(values, list):
        errors.append(f"bad_provenance_{label}s:{owner_id}")
        return
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value:
            errors.append(f"bad_provenance_{label}:{owner_id}:{index}")


def _status_enums(status_enums: dict[str, list[str]] | None, errors: list[str]) -> dict[str, set[str]]:
    merged = {key: list(value) for key, value in DEFAULT_STATUS_ENUMS.items()}
    if status_enums is None:
        return {key: set(value) for key, value in merged.items()}
    if not isinstance(status_enums, dict):
        errors.append("bad_status_enums")
        return {key: set(value) for key, value in merged.items()}
    for key, value in status_enums.items():
        if not isinstance(value, list):
            errors.append(f"bad_status_enum:{key}")
            continue
        merged[key] = _string_enum_values(key, value, errors)
    return {key: set(value) for key, value in merged.items()}


def _string_field_set(records: list, key: str) -> set[str]:
    values = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        value = record.get(key)
        if isinstance(value, str):
            values.add(value)
    return values


def _string_enum_values(key: str, values: list, errors: list[str]) -> list[str]:
    strings = []
    for value in values:
        if not isinstance(value, str):
            errors.append(f"bad_status_enum_item:{key}")
            continue
        strings.append(value)
    return strings


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
    if not _known_string_ref(edge.get("source"), node_ids) or not _known_string_ref(
        edge.get("target"), node_ids
    ):
        errors.append(f"edge_unknown_node:{edge_id}")
    _validate_source_locator("edge", edge_id, edge, errors)
    _validate_evidence_refs("edge", edge_id, edge.get("evidence_ids"), evidence_ids, errors)
    _validate_status_fields(edge, enums, errors)
    _validate_supports("edge", edge_id, edge.get("supports_templates"), enums, errors)


def _validate_hyperedge(
    hyperedge: dict[str, Any],
    evidence_ids: set[str | None],
    enums: dict[str, set[str]],
    errors: list[str],
) -> None:
    hyperedge_id = hyperedge.get("id")
    if not isinstance(hyperedge_id, str) or not hyperedge_id.startswith("hyperedge:"):
        errors.append(f"bad_hyperedge_id:{hyperedge_id}")
    for key in ["id", "evidence_ids", "supports_templates", "confidence", "verification_status"]:
        if key not in hyperedge:
            errors.append(f"hyperedge_missing:{hyperedge_id}:{key}")
    _validate_source_locator("hyperedge", hyperedge_id, hyperedge, errors)
    _validate_evidence_refs(
        "hyperedge", hyperedge_id, hyperedge.get("evidence_ids"), evidence_ids, errors
    )
    _validate_status_fields(hyperedge, enums, errors)
    _validate_supports("hyperedge", hyperedge_id, hyperedge.get("supports_templates"), enums, errors)


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
    if not isinstance(participants, list) or any(
        not _known_string_ref(pid, node_ids) for pid in participants
    ):
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
    if "fact_summary" in evidence and not isinstance(evidence.get("fact_summary"), str):
        errors.append(f"bad_evidence_fact_summary:{evidence_id}")
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
    if any(not _known_string_ref(ref, known_evidence_ids) for ref in refs):
        errors.append(f"{owner}_unknown_evidence:{owner_id}")


def _known_string_ref(value: object, known_ids: set[str]) -> bool:
    return isinstance(value, str) and value in known_ids


def _validate_source_locator(
    owner: str, owner_id: object, item: dict[str, Any], errors: list[str]
) -> None:
    if not (_has_locator_value(item.get("source_location")) or _has_locator_value(item.get("source_range"))):
        errors.append(f"{owner}_without_source_location:{owner_id}")


def _validate_locator_ranges(
    owner: str, owner_id: object, item: dict[str, Any], errors: list[str]
) -> None:
    if "source_range" in item and _valid_source_range(item.get("source_range")) is None:
        errors.append(f"{owner}_bad_source_range:{owner_id}")
    source_location = item.get("source_location")
    if "source_location" not in item:
        return
    if isinstance(source_location, dict):
        if "source_range" in source_location and _valid_source_range(
            source_location.get("source_range")
        ) is None:
            errors.append(f"{owner}_bad_source_location_range:{owner_id}")
        return
    if isinstance(source_location, list) and _valid_source_range(source_location) is not None:
        return
    errors.append(f"{owner}_bad_source_location:{owner_id}")


def _valid_source_range(value: object) -> list[int] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    if not all(isinstance(item, int) and not isinstance(item, bool) for item in value):
        return None
    start = value[0]
    end = value[1]
    if start < 0 or end < start:
        return None
    return [start, end]


def _has_locator_value(value: object) -> bool:
    return value not in (None, "", [], {})


def _validate_status_fields(
    item: dict[str, Any], enums: dict[str, set[str]], errors: list[str]
) -> None:
    confidence = item.get("confidence")
    if not isinstance(confidence, str) or confidence not in enums["confidence_levels"]:
        errors.append(f"bad_confidence:{confidence}")
    verification_status = item.get("verification_status")
    if (
        not isinstance(verification_status, str)
        or verification_status not in enums["verification_statuses"]
    ):
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
        if not isinstance(status, str) or status not in enums["requirement_statuses"]:
            errors.append(f"bad_requirement_status:{status}")
