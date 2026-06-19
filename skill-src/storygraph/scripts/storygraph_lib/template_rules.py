from __future__ import annotations

import re
from collections.abc import Iterable


DEFAULT_RULES = {
    "field_headings": ["字段", "字段说明", "核心字段", "输出字段"],
    "table_markers": ["|", "表格", "清单"],
    "card_markers": ["卡片", "档案", "条目卡"],
    "case_markers": ["案例", "示例", "样例", "场景"],
    "evidence_markers": ["证据", "原文", "引用", "依据"],
    "gap_markers": ["缺口", "待核验", "未见可靠证据"],
    "default_evidence_fields": ["原文位置"],
}

DEFAULT_REQUIREMENT_STATUSES = ["covered", "needs_review", "not_found_in_source"]

_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?P<item>.+?)\s*$")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*(?P<title>.*?)\s*$")


def _heading(line: str) -> str | None:
    match = _HEADING_RE.match(line)
    if not match:
        return None
    title = re.sub(r"\s+#+$", "", match.group("title")).strip()
    return title


def parse_template_requirements(template_name: str, text: str, rules: dict | None):
    active_rules = _active_rules(rules)
    required_fields: list[str] = []
    required_tables: list[str] = []
    required_cards: list[str] = []
    required_card_fields: list[str] = []
    required_case_patterns: list[str] = []
    required_evidence_fields: list[str] = []
    gap_markers: list[str] = []

    for section in _sections(text):
        heading = section["heading"]
        lines = section["lines"]
        items = _list_items(lines)
        table_headers = _table_headers(lines)

        if _contains_marker(heading, active_rules["field_headings"]):
            _extend_unique(required_fields, items)
        if table_headers or _contains_marker(heading, active_rules["table_markers"]):
            _extend_unique(required_tables, table_headers or items)
        if _contains_marker(heading, active_rules["card_markers"]):
            _append_unique(required_cards, heading)
            _extend_unique(required_card_fields, items)
        if _contains_marker(heading, active_rules["case_markers"]):
            _extend_unique(required_case_patterns, items)
        if _contains_marker(heading, active_rules["evidence_markers"]):
            _extend_unique(required_evidence_fields, items)
        if _contains_marker(heading, active_rules["gap_markers"]):
            _extend_unique(gap_markers, items)

    has_specific_requirements = bool(
        required_fields or required_tables or required_cards or required_case_patterns
    )
    if not has_specific_requirements:
        required_fields.append(template_name)
    if not required_evidence_fields:
        required_evidence_fields.extend(active_rules["default_evidence_fields"])

    return {
        "required_fields": required_fields,
        "required_tables": required_tables,
        "required_cards": required_cards,
        "required_card_headings": list(required_cards),
        "required_card_fields": required_card_fields,
        "required_case_patterns": required_case_patterns,
        "required_evidence_fields": required_evidence_fields,
        "gap_rules": {
            "markers": gap_markers,
            "status_enum": list(DEFAULT_REQUIREMENT_STATUSES),
        },
        "has_template_specific_requirements": has_specific_requirements,
    }


def _active_rules(rules: dict | None) -> dict:
    active = {key: list(value) for key, value in DEFAULT_RULES.items()}
    if rules:
        for key, value in rules.items():
            active[key] = list(value)
    return active


def _sections(text: str) -> list[dict]:
    sections: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        heading = _heading(line)
        if heading is not None:
            current = {"heading": heading, "lines": []}
            sections.append(current)
        elif current is not None:
            current["lines"].append(line)
    return sections


def _list_items(lines: Iterable[str]) -> list[str]:
    items: list[str] = []
    for line in lines:
        match = _BULLET_RE.match(line)
        if not match:
            continue
        item = match.group("item").strip()
        if item.startswith("[ ] ") or item.startswith("[x] ") or item.startswith("[X] "):
            item = item[4:].strip()
        _append_unique(items, item)
    return items


def _table_headers(lines: Iterable[str]) -> list[str]:
    headers: list[str] = []
    lines = list(lines)
    for index, line in enumerate(lines):
        if "|" not in line:
            continue
        cells = _table_cells(line)
        if not cells or _is_separator_row(cells):
            continue
        next_cells = _table_cells(lines[index + 1]) if index + 1 < len(lines) else []
        if next_cells and not _is_separator_row(next_cells):
            continue
        _append_unique(headers, "|".join(cells))
    return headers


def _table_cells(line: str) -> list[str]:
    if "|" not in line:
        return []
    return [cell.strip() for cell in line.strip().strip("|").split("|") if cell.strip()]


def _is_separator_row(cells: Iterable[str]) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def _contains_marker(value: str, markers: Iterable[str]) -> bool:
    return any(marker and marker in value for marker in markers)


def _extend_unique(target: list[str], values: Iterable[str]) -> None:
    for value in values:
        _append_unique(target, value)


def _append_unique(target: list[str], value: str) -> None:
    if value and value not in target:
        target.append(value)
