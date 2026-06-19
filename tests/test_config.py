import json
from pathlib import Path

from storygraph_lib.config import load_config


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "skill-src" / "storygraph" / "config" / "storygraph.default.json"


def _json_key_and_string_values(value, path="$"):
    if isinstance(value, str):
        yield (path, value)
    elif isinstance(value, dict):
        for key, nested in value.items():
            yield (f"{path}.{key}", key)
            yield from _json_key_and_string_values(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            yield from _json_key_and_string_values(nested, f"{path}[{index}]")


def test_default_config_is_portable_and_local_override_wins(tmp_path):
    default = tmp_path / "storygraph.default.json"
    local = tmp_path / "storygraph.local.json"
    default.write_text(
        json.dumps(
            {
                "graph_dir_suffix": ".storygraph",
                "paths": {"template_dir": None},
                "agent_policy": {"max_parallel": 6},
                "template_parser_rules": {"field_headings": ["字段"]},
            }
        ),
        encoding="utf-8",
    )
    local.write_text(
        json.dumps(
            {"paths": {"template_dir": "E:/Templates"}, "agent_policy": {"max_parallel": 2}}
        ),
        encoding="utf-8",
    )

    config = load_config(default, local_override=local)

    assert config["paths"]["template_dir"] == "E:/Templates"
    assert config["agent_policy"]["max_parallel"] == 2
    assert config["template_parser_rules"]["field_headings"] == ["字段"]
    assert "E:/Templates" not in default.read_text(encoding="utf-8")


def test_config_check_command_is_registered(capsys):
    from storygraph_lib.cli import main

    assert main(["config-check"]) == 0
    assert "graph_dir_suffix" in capsys.readouterr().out


def test_real_default_config_does_not_contain_local_paths_or_test_inputs():
    raw_config = DEFAULT_CONFIG.read_text(encoding="utf-8")
    config = json.loads(raw_config)
    banned_fragments = [
        "E:/AI_Projects",
        "E:\\AI_Projects",
        "E:\\\\AI_Projects",
        "E:/Github_Projects",
        "E:\\Github_Projects",
        "E:\\\\Github_Projects",
        "C:/Users",
        "C:\\Users",
        "C:\\\\Users",
        "凡人修仙传.txt",
        ".codex\\skills\\storygraph",
        ".codex\\\\skills\\\\storygraph",
        ".codex/skills/storygraph",
    ]
    subjects = [("raw json", raw_config), *_json_key_and_string_values(config)]

    offenders = [
        (location, fragment)
        for location, text in subjects
        for fragment in banned_fragments
        if fragment in text
    ]

    assert offenders == []


def test_cli_overrides_win_after_local_override_and_keep_uncovered_defaults(tmp_path):
    default = tmp_path / "storygraph.default.json"
    local = tmp_path / "storygraph.local.json"
    default.write_text(
        json.dumps(
            {
                "paths": {"template_dir": None, "graphify_repo": None},
                "agent_policy": {
                    "max_parallel": 6,
                    "enabled": True,
                    "write_conflict_policy": "single-writer",
                },
            }
        ),
        encoding="utf-8",
    )
    local.write_text(
        json.dumps(
            {
                "paths": {"template_dir": "local-templates"},
                "agent_policy": {"max_parallel": 2},
            }
        ),
        encoding="utf-8",
    )

    config = load_config(
        default,
        local_override=local,
        cli_overrides={
            "paths": {"template_dir": "cli-templates"},
            "agent_policy": {"max_parallel": 1},
        },
    )

    assert config["paths"]["template_dir"] == "cli-templates"
    assert config["agent_policy"]["max_parallel"] == 1
    assert config["paths"]["graphify_repo"] is None
    assert config["agent_policy"]["enabled"] is True
    assert config["agent_policy"]["write_conflict_policy"] == "single-writer"


def test_config_check_uses_local_override(capsys, tmp_path):
    from storygraph_lib.cli import main

    local = tmp_path / "storygraph.local.json"
    local.write_text(json.dumps({"graph_dir_suffix": ".local-storygraph"}), encoding="utf-8")

    assert main(["config-check", "--local-override", str(local)]) == 0
    assert ".local-storygraph" in capsys.readouterr().out


def test_config_check_rejects_missing_explicit_local_override(capsys, tmp_path):
    from storygraph_lib.cli import main

    missing = tmp_path / "storygraph.local.json"

    assert main(["config-check", "--local-override", str(missing)]) == 2
    captured = capsys.readouterr()
    assert "local_override_missing" in captured.out
