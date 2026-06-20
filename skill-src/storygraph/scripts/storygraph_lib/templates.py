from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .template_rules import DEFAULT_REQUIREMENT_STATUSES, parse_template_requirements


@dataclass(frozen=True)
class TemplateFile:
    name: str
    path: Path
    file_hash: str
    text: str


@dataclass(frozen=True)
class TemplateDiscovery:
    templates: list[TemplateFile]
    warnings: list[dict]


class TemplateDiscoveryError(ValueError):
    def __init__(self, code: str, path: Path | None = None, file: str | None = None):
        self.code = code
        self.path = path
        self.file = file
        super().__init__(code)

    def to_dict(self) -> dict:
        payload = {"ok": False, "error": self.code}
        if self.path is not None:
            payload["path"] = str(self.path)
        if self.file is not None:
            payload["file"] = self.file
        return payload


def discover_templates(
    template_dir: Path,
    glob: str = "*模板.md",
    readme_index_file: str = "README.md",
    exclude_files: list[str] | None = None,
    readme_missing_policy: str = "warn",
) -> TemplateDiscovery:
    template_dir = Path(template_dir)
    if not template_dir.is_dir():
        raise TemplateDiscoveryError("template_dir_missing", path=template_dir)
    excluded = set(exclude_files or [])
    if readme_index_file:
        excluded.add(readme_index_file)
    files = sorted(
        [path for path in template_dir.glob(glob) if path.is_file() and path.name not in excluded],
        key=lambda path: path.name,
    )
    templates = [_template_file(path) for path in files]
    warnings = _readme_missing_warnings(
        template_dir,
        readme_index_file,
        {path.name for path in files},
        readme_missing_policy,
    )
    return TemplateDiscovery(templates=templates, warnings=warnings)


def build_requirement_matrix(
    templates: list[TemplateFile],
    rules: dict | None,
    mappings: dict | None,
    status_enums: dict | list | None = None,
    output_language: str = "zh-CN",
) -> dict:
    mappings = mappings or {}
    requirement_statuses = _requirement_statuses(status_enums)
    records = []
    for template in templates:
        parsed = parse_template_requirements(template.name, template.text, rules)
        parsed["gap_rules"]["status_enum"] = requirement_statuses
        mapping, mapping_source = _resolve_mapping(template.name, parsed, mappings)
        records.append(
            {
                "name": template.name,
                "template_name": template.name,
                "template_file": template.path.name,
                "template_file_hash": template.file_hash,
                "template_status": "parsed",
                "path": str(template.path),
                "file_hash": template.file_hash,
                "output_language": output_language,
                "required_sections": _required_sections(parsed),
                "required_entity_types": mapping["graph_node_mapping"],
                "required_event_types": mapping["graph_event_mapping"],
                "required_relation_types": mapping["graph_relation_mapping"],
                "output_sections": _output_sections(parsed),
                "coverage_rules": _coverage_rules(parsed),
                "required_fields": parsed["required_fields"],
                "required_tables": parsed["required_tables"],
                "required_cards": parsed["required_cards"],
                "required_card_headings": parsed["required_card_headings"],
                "required_card_fields": parsed["required_card_fields"],
                "required_case_patterns": parsed["required_case_patterns"],
                "required_evidence_fields": parsed["required_evidence_fields"],
                "gap_rules": parsed["gap_rules"],
                "graph_node_mapping": mapping["graph_node_mapping"],
                "graph_event_mapping": mapping["graph_event_mapping"],
                "graph_relation_mapping": mapping["graph_relation_mapping"],
                "mapping_source": mapping_source,
            }
        )
    return {"template_count": len(records), "templates": records}


def _template_file(path: Path) -> TemplateFile:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise TemplateDiscoveryError("template_encoding_error", path=path, file=path.name) from exc
    except OSError as exc:
        raise TemplateDiscoveryError("template_discovery_failed", path=path, file=path.name) from exc
    return TemplateFile(
        name=_strip_template_suffix(path.stem),
        path=path,
        file_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        text=text,
    )


def _strip_template_suffix(stem: str) -> str:
    return stem[:-2] if stem.endswith("模板") else stem


def _readme_missing_warnings(
    template_dir: Path,
    readme_index_file: str,
    actual_files: set[str],
    readme_missing_policy: str,
) -> list[dict]:
    if not readme_index_file:
        return []
    if readme_missing_policy == "ignore":
        return []
    readme = template_dir / readme_index_file
    if not readme.exists():
        return []
    warnings = []
    try:
        readme_text = readme.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise TemplateDiscoveryError(
            "template_encoding_error", path=readme, file=readme.name
        ) from exc
    except OSError as exc:
        raise TemplateDiscoveryError(
            "template_discovery_failed", path=readme, file=readme.name
        ) from exc
    for file_name in _readme_template_items(readme_text):
        if file_name not in actual_files:
            if readme_missing_policy == "error":
                raise TemplateDiscoveryError("missing_template_file", file=file_name)
            warnings.append({"code": "missing_template_file", "file": file_name})
    return warnings


def _readme_template_items(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        match = re.search(r"([^/\\\]\)\s]+模板\.md)", line)
        if match and match.group(1) not in items:
            items.append(match.group(1))
    return items


def _resolve_mapping(template_name: str, parsed: dict, mappings: dict) -> tuple[dict, str]:
    if template_name in mappings:
        mapping = _copy_mapping(mappings[template_name])
        _validate_mapping(template_name, mapping)
        return mapping, "configured"

    if parsed.get("has_template_specific_requirements"):
        mapping = {
            "graph_node_mapping": [f"{template_name}.node"],
            "graph_event_mapping": [f"{template_name}.event"],
            "graph_relation_mapping": [f"{template_name}.relation"],
        }
        _validate_mapping(template_name, mapping)
        return mapping, "template_parse_result"

    mapping = _copy_mapping(mappings.get("default_mapping", {}))
    _validate_mapping(template_name, mapping)
    return mapping, "default_mapping"


def _copy_mapping(mapping: dict) -> dict:
    return {
        "graph_node_mapping": list(mapping.get("graph_node_mapping", [])),
        "graph_event_mapping": list(mapping.get("graph_event_mapping", [])),
        "graph_relation_mapping": list(mapping.get("graph_relation_mapping", [])),
    }


def _validate_mapping(template_name: str, mapping: dict) -> None:
    for key in ("graph_node_mapping", "graph_event_mapping", "graph_relation_mapping"):
        if not mapping.get(key):
            raise ValueError(f"{template_name} requires non-empty {key}")


def _required_sections(parsed: dict) -> list[str]:
    sections = []
    if parsed["required_fields"]:
        sections.append("fields")
    if parsed["required_tables"]:
        sections.append("tables")
    if parsed["required_cards"] or parsed["required_card_fields"]:
        sections.append("cards")
    if parsed["required_case_patterns"]:
        sections.append("case_patterns")
    if parsed["required_evidence_fields"]:
        sections.append("evidence")
    if parsed["gap_rules"]:
        sections.append("gap_rules")
    return sections


def _output_sections(parsed: dict) -> list[str]:
    sections = ["requirement_matrix", "evidence_requirements", "gap_report"]
    if parsed["required_cards"] or parsed["required_card_fields"]:
        sections.append("card_outputs")
    if parsed["required_tables"]:
        sections.append("table_outputs")
    return sections


def _coverage_rules(parsed: dict) -> dict:
    return {
        "required_evidence_fields": parsed["required_evidence_fields"],
        "gap_rules": parsed["gap_rules"],
        "requirement_statuses": parsed["gap_rules"]["status_enum"],
    }


def _requirement_statuses(status_enums: dict | list | None) -> list[str]:
    if isinstance(status_enums, dict):
        values = status_enums.get("requirement_statuses") or DEFAULT_REQUIREMENT_STATUSES
        return list(values)
    if status_enums:
        return list(status_enums)
    return list(DEFAULT_REQUIREMENT_STATUSES)
