from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


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


class TemplateRequirementMatrixLegacyError(ValueError):
    def __init__(self):
        self.code = "legacy_requirement_matrix_disabled"
        super().__init__(self.code)

    def to_dict(self) -> dict:
        return {"ok": False, "error": self.code}


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
    raise TemplateRequirementMatrixLegacyError()


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
