from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any


HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")

DEFAULT_RENDER_POLICY = {
    "draft_entry_policy": {
        "source_sections": ["facts"],
        "field_aliases": {},
        "fallback_name": "未命名条目",
        "kept_fields": [
            "name",
            "classification",
            "usage",
            "formula",
            "source_range",
            "source_excerpt",
            "evidence_ids",
            "confidence",
            "review_status",
        ],
    },
    "final_entry_policy": {
        "allowed_confidence": [],
        "min_evidence_count": 0,
        "require_explicit_name": False,
        "require_source_excerpt": False,
        "required_any_fields": [],
        "unstable_name_prefixes": [],
        "unstable_name_contains": [],
        "composite_name_markers": [],
        "review_only_statuses": [],
        "allow_missing_review_status": True,
    },
    "dedupe_policy": {
        "key_fields": ["name", "classification"],
        "merge_text_fields": ["usage", "formula", "source_excerpt"],
        "confidence_strategy": "most_conservative",
        "review_status_strategy": "review_only_wins",
    },
    "final_template_policy": {
        "case_section_names": ["案例", "典型案例", "案例清单", "示例"],
        "excluded_section_names": ["待复核", "缺口", "资料来源", "说明"],
        "fallback_to_first_non_root_heading": True,
    },
    "citation_format": "[{evidence_id}]",
}


def render_template_draft(
    record: dict,
    evidence_index: dict[str, dict],
    render_policy: dict | None = None,
    *,
    review_status: str | None = None,
) -> str:
    del review_status
    policy = _render_policy(render_policy)
    entries = build_draft_entries(record, evidence_index, policy)
    lines = [f"# {record['template_name']}", "", "## 审查草稿条目", ""]
    for entry in entries:
        lines.extend(_format_draft_entry(entry, policy))
    return "\n".join(lines).rstrip() + "\n"


def render_template_final(
    record: dict,
    evidence_index: dict[str, dict],
    template_markdown: str,
    render_policy: dict | None = None,
) -> str:
    policy = _render_policy(render_policy)
    entries = [
        entry
        for entry in build_draft_entries(record, evidence_index, policy)
        if classify_entry_for_final(entry, policy)["decision"] == "final"
    ]
    section = _select_final_section(template_markdown, policy)
    lines = [f"# {record['template_name']}", "", f"## {section}", ""]
    for entry in entries:
        lines.extend(_format_final_entry(entry, policy))
    return "\n".join(lines).rstrip() + "\n"


def build_draft_entries(
    record: dict,
    evidence_index: dict[str, dict],
    render_policy: dict | None = None,
) -> list[dict]:
    policy = _render_policy(render_policy)
    entries = []
    for section_name in policy["draft_entry_policy"].get("source_sections", ["facts"]):
        items = record.get(section_name) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                entries.append(_entry_from_item(item, evidence_index, policy))
    return dedupe_entries(entries, policy)


def classify_entry_for_final(entry: dict, render_policy: dict | None = None) -> dict:
    policy = _render_policy(render_policy)
    final_policy = policy["final_entry_policy"]
    reasons = []
    name = str(entry.get("name") or "").strip()
    if final_policy.get("require_explicit_name", True) and (
        not name or name == policy["draft_entry_policy"].get("fallback_name")
    ):
        reasons.append("name_missing")
    if _has_unstable_name(name, final_policy):
        reasons.append("name_unstable")
    confidence = entry.get("confidence")
    allowed_confidence = set(final_policy.get("allowed_confidence", []))
    if allowed_confidence and confidence not in allowed_confidence:
        reasons.append("confidence_not_allowed")
    evidence_ids = entry.get("evidence_ids") or []
    if len(evidence_ids) < int(final_policy.get("min_evidence_count", 1)):
        reasons.append("evidence_insufficient")
    if final_policy.get("require_source_excerpt", True) and not entry.get("source_excerpt"):
        reasons.append("source_excerpt_missing")
    required_any = final_policy.get("required_any_fields") or []
    if required_any and not any(entry.get(field) for field in required_any):
        reasons.append("required_fields_incomplete")
    review_status = entry.get("review_status")
    if review_status:
        if review_status in set(final_policy.get("review_only_statuses", [])):
            reasons.append("review_status_not_final")
    elif not final_policy.get("allow_missing_review_status", True):
        reasons.append("review_status_missing")
    return {
        "decision": "review_only" if reasons else "final",
        "reasons": reasons,
    }


def dedupe_entries(entries: list[dict], render_policy: dict | None = None) -> list[dict]:
    policy = _render_policy(render_policy)
    key_fields = policy["dedupe_policy"].get("key_fields", ["name", "classification"])
    merged: dict[str, dict] = {}
    order = []
    for entry in entries:
        key = _dedupe_key(entry, key_fields)
        if key not in merged:
            merged[key] = deepcopy(entry)
            order.append(key)
            continue
        _merge_entry(merged[key], entry, policy)
    return [merged[key] for key in order]


def _render_policy(render_policy: dict | None) -> dict:
    policy = deepcopy(DEFAULT_RENDER_POLICY)
    _deep_update(policy, render_policy or {})
    return policy


def _deep_update(base: dict, override: dict) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value


def _entry_from_item(
    item: dict,
    evidence_index: dict[str, dict],
    policy: dict,
) -> dict:
    aliases = policy["draft_entry_policy"].get("field_aliases", {})
    evidence_ids = _as_string_list(item.get("evidence_ids"))
    source_locations = item.get("source_locations") if isinstance(item.get("source_locations"), list) else []
    source_ranges = _source_ranges(source_locations, evidence_ids, evidence_index)
    source_excerpt = _first_value(item, aliases.get("source_excerpt", []))
    if not source_excerpt:
        source_excerpt = _evidence_excerpt(evidence_ids, evidence_index)
    return {
        "name": _first_value(item, aliases.get("name", []))
        or policy["draft_entry_policy"].get("fallback_name", "未命名条目"),
        "classification": _first_value(item, aliases.get("classification", [])),
        "usage": _first_value(item, aliases.get("usage", [])),
        "formula": _first_value(item, aliases.get("formula", [])),
        "content": str(item.get("content") or "").strip(),
        "source_range": _join_unique(source_ranges),
        "source_excerpt": source_excerpt or str(item.get("content") or "").strip(),
        "evidence_ids": evidence_ids,
        "confidence": item.get("confidence"),
        "review_status": _first_value(item, aliases.get("review_status", [])),
        "source_locations": source_locations,
    }


def _format_draft_entry(entry: dict, policy: dict) -> list[str]:
    kept_fields = policy["draft_entry_policy"].get("kept_fields", [])
    labels = {
        "name": "名称",
        "classification": "分类",
        "usage": "用途",
        "formula": "方方/材料",
        "source_range": "source_range",
        "source_excerpt": "原文摘录",
        "evidence_ids": "evidence",
        "confidence": "confidence",
        "review_status": "review_status",
    }
    lines = []
    first_label = labels["name"]
    lines.append(f"- {first_label}：{entry.get('name')}")
    for field in kept_fields:
        if field == "name":
            continue
        value = _display_value(entry.get(field), policy)
        if value:
            lines.append(f"  - {labels.get(field, field)}：{value}")
    lines.append("")
    return lines


def _format_final_entry(entry: dict, policy: dict) -> list[str]:
    lines = [f"- 名称：{entry.get('name')}"]
    for field, label in (
        ("classification", "分类"),
        ("usage", "用途"),
        ("formula", "方方/材料"),
        ("source_excerpt", "原文摘录"),
        ("evidence_ids", "证据"),
    ):
        value = _display_value(entry.get(field), policy)
        if value:
            lines.append(f"  - {label}：{value}")
    lines.append("")
    return lines


def _display_value(value: Any, policy: dict) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        if not value:
            return ""
        if all(isinstance(item, str) for item in value):
            citation_format = policy.get("citation_format", "[{evidence_id}]")
            if value and str(value[0]).startswith("evidence:"):
                return " ".join(
                    citation_format.format(evidence_id=item, chunk_id="", source_range="")
                    for item in value
                )
            return "；".join(_unique_strings(value))
        return "；".join(
            json.dumps(item, ensure_ascii=False, sort_keys=True)
            for item in value
        )
    return str(value).strip()


def _select_final_section(template_markdown: str, policy: dict) -> str:
    template_policy = policy["final_template_policy"]
    headings = _extract_template_headings(template_markdown)
    non_root = [heading for heading in headings if heading["level"] > 1]
    excluded = set(template_policy.get("excluded_section_names", []))
    case_names = set(template_policy.get("case_section_names", []))
    for heading in non_root:
        if heading["title"] in case_names and heading["title"] not in excluded:
            return heading["title"]
    if template_policy.get("fallback_to_first_non_root_heading", True):
        for heading in non_root:
            if heading["title"] not in excluded:
                return heading["title"]
    return "案例"


def _extract_template_headings(text: str) -> list[dict]:
    headings = []
    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            headings.append({"level": len(match.group(1)), "title": match.group(2).strip()})
    return headings


def _first_value(item: dict, aliases: list[str]) -> str:
    for alias in aliases:
        value = item.get(alias)
        if isinstance(value, list):
            text = "；".join(str(part).strip() for part in value if str(part).strip())
        else:
            text = str(value).strip() if value is not None else ""
        if text:
            return text
    return ""


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return _unique_strings(str(item).strip() for item in value if str(item).strip())


def _source_ranges(
    source_locations: list,
    evidence_ids: list[str],
    evidence_index: dict[str, dict],
) -> list[str]:
    ranges = []
    for location in source_locations:
        if not isinstance(location, dict):
            continue
        source_range = location.get("source_range")
        if source_range is not None:
            ranges.append(_range_text(source_range))
    for evidence_id in evidence_ids:
        evidence = evidence_index.get(evidence_id, {})
        source_range = evidence.get("source_range")
        if source_range is not None:
            ranges.append(_range_text(source_range))
    return _unique_strings(ranges)


def _range_text(source_range: Any) -> str:
    if isinstance(source_range, list):
        return "[" + ", ".join(str(item) for item in source_range) + "]"
    return str(source_range)


def _evidence_excerpt(evidence_ids: list[str], evidence_index: dict[str, dict]) -> str:
    for evidence_id in evidence_ids:
        evidence = evidence_index.get(evidence_id, {})
        for key in ("source_excerpt", "quote", "original_excerpt", "fact_summary"):
            value = evidence.get(key)
            if value:
                return str(value).strip()
    return ""


def _dedupe_key(entry: dict, key_fields: list[str]) -> str:
    parts = []
    for field in key_fields:
        value = entry.get(field)
        if value:
            parts.append(_normalize_key(str(value)))
    if parts:
        return "|".join(parts)
    return _normalize_key(str(entry.get("content") or entry))


def _normalize_key(value: str) -> str:
    return re.sub(r"[\s\W_]+", "", value, flags=re.UNICODE).lower()


def _merge_entry(target: dict, incoming: dict, policy: dict) -> None:
    merge_fields = policy["dedupe_policy"].get("merge_text_fields", [])
    for field in merge_fields:
        target[field] = _join_unique([target.get(field), incoming.get(field)])
    for field in ("evidence_ids", "source_locations"):
        target[field] = _unique_json_values(target.get(field, []), incoming.get(field, []))
    target["source_range"] = _join_unique([target.get("source_range"), incoming.get("source_range")])
    target["confidence"] = _merge_confidence(
        target.get("confidence"),
        incoming.get("confidence"),
        policy,
    )
    target["review_status"] = _merge_review_status(
        target.get("review_status"),
        incoming.get("review_status"),
        policy,
    )


def _join_unique(values: list[Any]) -> str:
    strings = []
    for value in values:
        if isinstance(value, list):
            strings.extend(str(item).strip() for item in value)
        elif value is not None:
            strings.append(str(value).strip())
    return "；".join(_unique_strings(value for value in strings if value))


def _unique_strings(values) -> list[str]:
    seen = set()
    unique = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _unique_json_values(existing: list, incoming: list) -> list:
    seen = set()
    unique = []
    for value in [*(existing or []), *(incoming or [])]:
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(value)
    return unique


def _merge_confidence(left: str | None, right: str | None, policy: dict) -> str | None:
    strategy = policy["dedupe_policy"].get("confidence_strategy", "most_conservative")
    rank = {"EXTRACTED": 3, "INFERRED": 2, "AMBIGUOUS": 1}
    if strategy == "highest":
        if rank.get(right, 0) > rank.get(left, 0):
            return right
        return left or right
    if left is None:
        return right
    if right is None:
        return left
    if rank.get(right, 0) < rank.get(left, 0):
        return right
    return left


def _merge_review_status(left: str | None, right: str | None, policy: dict) -> str | None:
    strategy = policy["dedupe_policy"].get("review_status_strategy", "review_only_wins")
    if strategy != "review_only_wins":
        return left or right
    review_only = set(policy["final_entry_policy"].get("review_only_statuses", []))
    if right in review_only:
        return right
    if left in review_only:
        return left
    return left or right


def _has_unstable_name(name: str, policy: dict) -> bool:
    if not name:
        return False
    if any(name.startswith(prefix) for prefix in policy.get("unstable_name_prefixes", [])):
        return True
    if any(marker in name for marker in policy.get("unstable_name_contains", [])):
        return True
    return any(marker in name for marker in policy.get("composite_name_markers", []))


def _format_citations(evidence_ids, evidence_index, citation_format):
    citations = []
    for evidence_id in evidence_ids:
        evidence = evidence_index.get(evidence_id, {})
        citations.append(
            citation_format.format(
                evidence_id=evidence_id,
                chunk_id=evidence.get("chunk_id", ""),
                source_range=evidence.get("source_range", ""),
            )
        )
    return citations
