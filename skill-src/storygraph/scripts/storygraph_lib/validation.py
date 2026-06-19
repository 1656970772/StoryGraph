from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    missing: list[str]


def validate_skill_tree(root: Path) -> ValidationResult:
    required = [
        "SKILL.md",
        "agents/openai.yaml",
        "config/storygraph.default.json",
        "references/workflow.md",
        "references/graph-schema.md",
        "references/extraction-workflow.md",
        "scripts/storygraph.py",
        "scripts/sync-skill.ps1",
    ]
    missing = [item for item in required if not (root / item).exists()]
    return ValidationResult(ok=not missing, missing=missing)
