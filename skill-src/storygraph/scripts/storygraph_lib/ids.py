from hashlib import sha256
import json


def _canonical_part(part: object) -> str:
    if isinstance(part, (dict, list, tuple)):
        return json.dumps(part, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(part)


def _slug(*parts: object) -> str:
    payload = "|".join(_canonical_part(part) for part in parts)
    return sha256(payload.encode("utf-8")).hexdigest()[:16]


def stable_node_id(novel_name: str, canonical_name: str, node_type: str) -> str:
    return f"node:{node_type}:{_slug(novel_name, canonical_name, node_type)}"


def stable_edge_id(novel_name: str, source: str, target: str, relation: str) -> str:
    return f"edge:{relation}:{_slug(novel_name, source, target, relation)}"


def stable_event_id(
    novel_name: str, event_type: str, actor: str, source_range: list[int]
) -> str:
    return f"event:{event_type}:{_slug(novel_name, event_type, actor, source_range)}"


def stable_evidence_id(novel_name: str, chunk_id: str, source_range: list[int]) -> str:
    return f"evidence:{_slug(novel_name, chunk_id, source_range)}"
