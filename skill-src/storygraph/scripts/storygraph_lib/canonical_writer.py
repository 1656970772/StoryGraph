from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
from typing import Any

from .graph_schema import GRAPH_COLLECTION_FIELDS, validate_canonical_graph
from .ids import stable_edge_id, stable_event_id, stable_evidence_id, stable_node_id


CANONICAL_WRITER_VERSION = "1.0"
SEMANTIC_GENERATION = "agent-produced"
DEFAULT_REVIEWER_STATUSES = ("passed",)
# Keep below Python's recursive deepcopy limit for nested JSON-like lists/dicts.
JSON_SAFE_MAX_DEPTH = 256

NORMALIZED_COLLECTIONS = (
    ("normalized_nodes", "nodes", "node"),
    ("normalized_edges", "edges", "edge"),
    ("normalized_events", "events", "event"),
    ("normalized_evidence", "evidence_index", "evidence"),
)


@dataclass(frozen=True)
class CanonicalGraphResult:
    ok: bool
    errors: list[str]
    graph: dict[str, Any]


def build_canonical_graph_from_bundles(
    bundles: Any,
    *,
    novel_name: str,
    status_enums: dict[str, list[str]] | None,
    source_bundle_paths: Any | None = None,
) -> CanonicalGraphResult:
    errors: list[str] = []
    graph = _empty_graph(source_bundle_paths, errors)

    if not isinstance(novel_name, str) or not novel_name:
        errors.append("novel_name_not_string")

    allowed_reviewer_statuses = _allowed_reviewer_statuses(status_enums)
    allowed_merge_gate_statuses = _allowed_merge_gate_statuses(status_enums)
    review_state_counts: dict[str, int] = {}

    if not isinstance(bundles, list):
        errors.append("bundles_not_list")
        validation = validate_canonical_graph(graph, status_enums)
        errors.extend(validation.errors)
        return CanonicalGraphResult(ok=False, errors=_dedupe(errors), graph=graph)

    indexes = {key: _CollectionIndex(key) for key in GRAPH_COLLECTION_FIELDS}
    conflicts: list[dict[str, str]] = []

    for bundle_index, bundle in enumerate(bundles):
        if not isinstance(bundle, dict):
            errors.append(f"bundle_not_object:{bundle_index}")
            continue

        chunk_id = _chunk_id(bundle, bundle_index, errors)
        lane_output_paths = _lane_output_paths(bundle, chunk_id, errors)

        merge_gate_status = _merge_gate_status(
            bundle,
            allowed_reviewer_statuses=allowed_reviewer_statuses,
            allowed_merge_gate_statuses=allowed_merge_gate_statuses,
        )
        if merge_gate_status is None:
            code = "bundle_not_merge_gated" if allowed_merge_gate_statuses is not None else "bundle_not_reviewed"
            errors.append(f"{code}:{chunk_id}")
            continue
        review_state_counts[merge_gate_status] = review_state_counts.get(merge_gate_status, 0) + 1

        for source_field, graph_field, owner in NORMALIZED_COLLECTIONS:
            normalized_items = _normalized_items(bundle, source_field, owner, chunk_id, errors)
            for item_index, item in enumerate(normalized_items):
                if not _json_safe(item, graph_field, chunk_id, item_index, errors):
                    continue
                canonical_item = _canonical_item(
                    item,
                    owner=owner,
                    novel_name=novel_name,
                    chunk_id=chunk_id,
                    lane_output_paths=lane_output_paths,
                    errors=errors,
                )
                if canonical_item is None:
                    continue
                indexes[graph_field].add(canonical_item, chunk_id, conflicts, errors)

    for key in GRAPH_COLLECTION_FIELDS:
        graph[key] = indexes[key].items()
    graph["metadata"]["conflicts"] = conflicts
    if review_state_counts:
        graph["metadata"]["review_status"] = _graph_review_status(review_state_counts)
        graph["metadata"]["unreviewed_bundle_count"] = review_state_counts.get(
            "unreviewed_usable", 0
        )

    validation = validate_canonical_graph(graph, status_enums)
    errors.extend(validation.errors)
    return CanonicalGraphResult(ok=not errors, errors=_dedupe(errors), graph=graph)


class _CollectionIndex:
    def __init__(self, collection: str):
        self.collection = collection
        self._items: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []

    def add(
        self,
        item: dict[str, Any],
        chunk_id: str,
        conflicts: list[dict[str, str]],
        errors: list[str],
    ) -> None:
        item_id = _item_id(self.collection, item)
        if not isinstance(item_id, str) or not item_id:
            return
        if item_id not in self._items:
            self._items[item_id] = item
            self._order.append(item_id)
            return

        existing = self._items[item_id]
        if _without_provenance(existing) == _without_provenance(item):
            _merge_provenance(existing, item)
            return

        existing_provenance = existing.setdefault("provenance", {})
        existing_conflicts = existing_provenance.get("conflicts")
        if existing_conflicts is None:
            existing_conflicts = []
            existing_provenance["conflicts"] = existing_conflicts
        elif not isinstance(existing_conflicts, list):
            errors.append(f"bad_provenance_conflicts:{item_id}")
            return

        conflict = {
            "collection": self.collection,
            "id": item_id,
            "kept_chunk_id": _first_chunk_id(existing_provenance),
            "conflicting_chunk_id": chunk_id,
            "reason": "duplicate_id_conflict",
        }
        conflicts.append(conflict)
        existing_conflicts.append(
            {
                "chunk_id": chunk_id,
                "lane_output_paths": item.get("provenance", {}).get("lane_output_paths", []),
                "item": deepcopy(item),
            }
        )

    def items(self) -> list[dict[str, Any]]:
        return [self._items[item_id] for item_id in self._order]


def _empty_graph(source_bundle_paths: Any | None, errors: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "graphify_schema_version": SEMANTIC_GENERATION,
        "storygraph_schema_version": "1.0",
        "nodes": [],
        "edges": [],
        "hyperedges": [],
        "events": [],
        "evidence_index": [],
        "metadata": {
            "semantic_generation": SEMANTIC_GENERATION,
            "canonical_writer_version": CANONICAL_WRITER_VERSION,
            "source_bundle_paths": _string_list(
                source_bundle_paths,
                "source_bundle_paths_not_list",
                "source_bundle_path_not_string",
                errors,
                default=[],
            ),
        },
    }


def _allowed_reviewer_statuses(status_enums: Any) -> set[str]:
    if not isinstance(status_enums, dict):
        return set(DEFAULT_REVIEWER_STATUSES)
    values = status_enums.get("allowed_reviewer_statuses")
    if values is None:
        return set(DEFAULT_REVIEWER_STATUSES)
    if not isinstance(values, list):
        return set(DEFAULT_REVIEWER_STATUSES)
    allowed = {value for value in values if isinstance(value, str) and value}
    return allowed or set(DEFAULT_REVIEWER_STATUSES)


def _allowed_merge_gate_statuses(status_enums: Any) -> set[str] | None:
    if not isinstance(status_enums, dict):
        return None
    values = status_enums.get("bundle_review_statuses")
    if values is None:
        return None
    if not isinstance(values, list):
        return None
    allowed = {value for value in values if isinstance(value, str) and value}
    return allowed or None


def _chunk_id(bundle: dict[str, Any], bundle_index: int, errors: list[str]) -> str:
    value = bundle.get("chunk_id")
    if isinstance(value, str) and value:
        return value
    errors.append(f"bad_chunk_id:{bundle_index}")
    return f"unknown-{bundle_index}"


def _lane_output_paths(bundle: dict[str, Any], chunk_id: str, errors: list[str]) -> list[str]:
    return _string_list(
        bundle.get("lane_output_paths", []),
        f"lane_output_paths_not_list:{chunk_id}",
        f"lane_output_path_not_string:{chunk_id}",
        errors,
        default=[],
    )


def _merge_gate_status(
    bundle: dict[str, Any],
    *,
    allowed_reviewer_statuses: set[str],
    allowed_merge_gate_statuses: set[str] | None,
) -> str | None:
    if bundle.get("ready_for_merge") is not True:
        return None
    if allowed_merge_gate_statuses is not None:
        status = bundle.get("merge_gate_status")
        if isinstance(status, str) and status in allowed_merge_gate_statuses:
            return status
        return None
    reviewer_status = bundle.get("reviewer_status")
    if isinstance(reviewer_status, str) and reviewer_status in allowed_reviewer_statuses:
        return "reviewed_passed"
    return None


def _graph_review_status(review_state_counts: dict[str, int]) -> str:
    if review_state_counts.get("needs_incremental_review"):
        return "needs_incremental_review"
    if review_state_counts.get("review_failed"):
        return "needs_incremental_review"
    if review_state_counts.get("unreviewed_usable"):
        return "unreviewed_usable"
    return "reviewed"


def _normalized_items(
    bundle: dict[str, Any],
    source_field: str,
    owner: str,
    chunk_id: str,
    errors: list[str],
) -> list[dict[str, Any]]:
    if source_field not in bundle:
        errors.append(f"missing:{source_field}:{chunk_id}")
        return []
    values = bundle.get(source_field)
    if not isinstance(values, list):
        errors.append(f"{source_field}_not_list:{chunk_id}")
        return []

    items: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            errors.append(f"normalized_{owner}_not_object:{chunk_id}:{index}")
            continue
        items.append(value)
    return items


def _canonical_item(
    item: dict[str, Any],
    *,
    owner: str,
    novel_name: str,
    chunk_id: str,
    lane_output_paths: list[str],
    errors: list[str],
) -> dict[str, Any] | None:
    copied = deepcopy(item)
    item_id = _canonical_id(copied, owner, novel_name, chunk_id, errors)
    if item_id is None:
        return None
    if owner == "evidence":
        copied["evidence_id"] = item_id
    else:
        copied["id"] = item_id

    if "source_locator" in copied and "source_location" not in copied and "source_range" not in copied:
        copied["source_location"] = {"locator": copied["source_locator"]}

    provenance = copied.get("provenance")
    if provenance is None:
        provenance = {}
    elif not isinstance(provenance, dict):
        errors.append(f"bad_provenance:{item_id}")
        provenance = {}
    provenance = deepcopy(provenance)
    existing_chunk_ids = _provenance_strings(
        provenance,
        "chunk_ids",
        "chunk_id",
        item_id,
        errors,
    )
    existing_lane_output_paths = _provenance_strings(
        provenance,
        "lane_output_paths",
        "lane_output_path",
        item_id,
        errors,
    )
    provenance["semantic_generation"] = SEMANTIC_GENERATION
    provenance["chunk_ids"] = _dedupe(existing_chunk_ids + [chunk_id])
    provenance["lane_output_paths"] = _dedupe(existing_lane_output_paths + lane_output_paths)
    copied["provenance"] = provenance
    return copied


def _canonical_id(
    item: dict[str, Any],
    owner: str,
    novel_name: str,
    chunk_id: str,
    errors: list[str],
) -> str | None:
    id_field = "evidence_id" if owner == "evidence" else "id"
    item_id = item.get(id_field)
    if isinstance(item_id, str) and item_id:
        return item_id

    if owner == "node":
        label = _first_string(item.get("canonical_name"), item.get("label"), item.get("name"))
        node_type = item.get("node_type")
        if label is not None and isinstance(node_type, str) and node_type:
            return stable_node_id(novel_name, label, node_type)
    elif owner == "edge":
        source = item.get("source")
        target = item.get("target")
        relation = _first_string(item.get("edge_type"), item.get("relation"))
        if isinstance(source, str) and source and isinstance(target, str) and target and relation:
            return stable_edge_id(novel_name, source, target, relation)
    elif owner == "event":
        event_type = item.get("event_type")
        actor = _event_actor(item)
        source_range = _source_range(item)
        if isinstance(event_type, str) and event_type and actor is not None and source_range is not None:
            return stable_event_id(novel_name, event_type, actor, source_range)
    elif owner == "evidence":
        source_range = _source_range(item)
        if source_range is not None:
            return stable_evidence_id(novel_name, chunk_id, source_range)

    errors.append(f"{owner}_missing_stable_id_fields:{chunk_id}")
    return None


def _event_actor(item: dict[str, Any]) -> str | None:
    actor = _first_string(item.get("actor"), item.get("label"))
    if actor is not None:
        return actor
    participants = item.get("participants")
    if isinstance(participants, list):
        for participant in participants:
            if isinstance(participant, str) and participant:
                return participant
    return None


def _source_range(item: dict[str, Any]) -> list[int] | None:
    source_range = item.get("source_range")
    if not isinstance(source_range, list) or len(source_range) != 2:
        return None
    if all(isinstance(value, int) and not isinstance(value, bool) for value in source_range):
        return [source_range[0], source_range[1]]
    return None


def _first_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def _item_id(collection: str, item: dict[str, Any]) -> object:
    if collection == "evidence_index":
        return item.get("evidence_id")
    return item.get("id")


def _without_provenance(item: dict[str, Any]) -> dict[str, Any]:
    copied = deepcopy(item)
    copied.pop("provenance", None)
    return copied


def _merge_provenance(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    existing_provenance = existing.setdefault("provenance", {})
    incoming_provenance = incoming.get("provenance", {})
    for key in ["chunk_ids", "lane_output_paths"]:
        existing_provenance[key] = _dedupe(
            existing_provenance.get(key, []) + incoming_provenance.get(key, [])
        )


def _first_chunk_id(provenance: dict[str, Any]) -> str:
    chunk_ids = provenance.get("chunk_ids")
    if isinstance(chunk_ids, list):
        for chunk_id in chunk_ids:
            if isinstance(chunk_id, str) and chunk_id:
                return chunk_id
    return "unknown"


def _string_list(
    values: Any,
    shape_error: str,
    item_error: str,
    errors: list[str],
    *,
    default: list[str],
) -> list[str]:
    if values is None:
        return list(default)
    if not isinstance(values, list):
        errors.append(shape_error)
        return list(default)

    strings: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value:
            errors.append(f"{item_error}:{index}")
            continue
        strings.append(value)
    return _dedupe(strings)


def _provenance_strings(
    provenance: dict[str, Any],
    key: str,
    singular_label: str,
    item_id: str,
    errors: list[str],
) -> list[str]:
    values = provenance.get(key, [])
    if values is None:
        return []
    if not isinstance(values, list):
        errors.append(f"bad_provenance_{key}:{item_id}")
        return []

    strings: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value:
            errors.append(f"bad_provenance_{singular_label}:{item_id}:{index}")
            continue
        strings.append(value)
    return strings


def _json_safe(
    value: Any,
    collection: str,
    chunk_id: str,
    index: int,
    errors: list[str],
) -> bool:
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        current, depth = stack.pop()
        if depth > JSON_SAFE_MAX_DEPTH:
            errors.append(f"json_depth_exceeded:{collection}:{chunk_id}:{index}")
            return False
        if isinstance(current, float) and not math.isfinite(current):
            errors.append(f"non_finite_number:{collection}:{chunk_id}:{index}")
            return False
        if current is None or isinstance(current, (str, bool, int, float)):
            continue
        if isinstance(current, list):
            stack.extend((item, depth + 1) for item in reversed(current))
            continue
        if isinstance(current, dict):
            items = list(current.items())
            if any(not isinstance(key, str) for key, _item in items):
                errors.append(f"non_string_key:{collection}:{chunk_id}:{index}")
                return False
            stack.extend((item, depth + 1) for _key, item in reversed(items))
            continue
        errors.append(f"unsupported_value:{collection}:{chunk_id}:{index}")
        return False
    return True


def _dedupe(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if not isinstance(value, str) or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
