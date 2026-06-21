from __future__ import annotations

import re
from pathlib import Path

from .templates import TemplateFile, discover_templates


HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")


def discover_stage2_templates(template_dir: Path, config: dict) -> list[dict]:
    discovery_config = config.get("template_discovery", {})
    discovery = discover_templates(
        Path(template_dir),
        glob=discovery_config.get("glob", "*模板.md"),
        readme_index_file=discovery_config.get("readme_index_file", "README.md"),
        exclude_files=discovery_config.get("exclude_files", []),
        readme_missing_policy=discovery_config.get("readme_missing_policy", "warn"),
    )
    return [_template_payload(template) for template in discovery.templates]


def assert_templates_match_stage1_cache(
    templates: list[dict], stage1_cache: dict
) -> list[str]:
    cached = stage1_cache.get("templates")
    if not isinstance(cached, list):
        return ["stage1_input_cache.templates_missing"]
    cached_by_name = {
        item.get("template_name"): item.get("template_file")
        for item in cached
        if isinstance(item, dict)
    }
    errors = []
    for template in templates:
        cached_file = cached_by_name.get(template["template_name"])
        if cached_file is None:
            errors.append(f"template_not_in_stage1_cache:{template['template_name']}")
        elif Path(cached_file).name != template["template_file"]:
            errors.append(f"template_file_mismatch:{template['template_name']}")
    return errors


def _template_payload(template: TemplateFile) -> dict:
    return {
        "template_name": template.name,
        "template_file": template.path.name,
        "template_path": str(template.path),
        "template_sha256": template.file_hash,
        "template_headings": extract_headings(template.text),
    }


def extract_headings(text: str) -> list[str]:
    headings = []
    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            headings.append(match.group(1).strip())
    return headings
