import json
from pathlib import Path


def test_default_config_uses_agent_template_requirements_strategy():
    root = Path(__file__).resolve().parents[1]
    default_config = root / "skill-src" / "storygraph" / "config" / "storygraph.default.json"
    config = json.loads(default_config.read_text(encoding="utf-8"))

    assert "template_parser_rules" not in config
    assert config["template_requirements_strategy"]["python_validate_only"] is True
