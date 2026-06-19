from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skill-src" / "storygraph"


def test_skill_source_structure_exists():
    required = [
        "SKILL.md",
        "agents/openai.yaml",
        "references/workflow.md",
        "references/graph-schema.md",
        "references/extraction-workflow.md",
        "scripts/storygraph.py",
        "scripts/storygraph_lib/__init__.py",
        "scripts/storygraph_lib/cli.py",
    ]
    missing = [path for path in required if not (SKILL / path).exists()]
    assert missing == []
