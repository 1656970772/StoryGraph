import json

from storygraph_lib.config import load_config


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
