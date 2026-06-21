import json
from pathlib import Path

import pytest

from storygraph_lib.config import load_config


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "skill-src" / "storygraph" / "config" / "storygraph.default.json"


@pytest.fixture
def default_config():
    return json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))


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
                "sample_policy": {
                    "mode": "default",
                    "options": ["字段"],
                    "limits": {"max_items": 6, "enabled": True},
                },
            }
        ),
        encoding="utf-8",
    )
    local.write_text(
        json.dumps(
            {
                "paths": {"template_dir": "E:/Templates"},
                "agent_policy": {"max_parallel": 2},
                "sample_policy": {"limits": {"max_items": 2}},
            }
        ),
        encoding="utf-8",
    )

    config = load_config(default, local_override=local)

    assert config["paths"]["template_dir"] == "E:/Templates"
    assert config["agent_policy"]["max_parallel"] == 2
    assert config["sample_policy"]["mode"] == "default"
    assert config["sample_policy"]["options"] == ["字段"]
    assert config["sample_policy"]["limits"]["max_items"] == 2
    assert config["sample_policy"]["limits"]["enabled"] is True
    assert "E:/Templates" not in default.read_text(encoding="utf-8")


def test_default_config_rejects_legacy_python_semantic_extraction_keys(default_config):
    legacy_keys = {
        "template_parser_rules",
        "template_graph_mappings",
        "supplemental_graph_policy",
        "evidence_matching_strategy",
    }
    assert legacy_keys.isdisjoint(default_config.keys())


def test_legacy_keys_only_appear_in_legacy_or_reject_config_tests():
    legacy_key_markers = (
        "template_parser_rules",
        "template_graph_mappings",
        "supplemental_graph_policy",
        "evidence_matching_strategy",
        "build_template_aware_graph",
    )
    allowed_test_name_markers = ("legacy", "reject")
    current_test = ""
    offenders = []

    for line_number, line in enumerate(Path(__file__).read_text(encoding="utf-8").splitlines(), start=1):
        if line.startswith("def test_"):
            current_test = line.split("(", 1)[0].removeprefix("def ")
        if any(marker in line for marker in legacy_key_markers) and not any(
            marker in current_test for marker in allowed_test_name_markers
        ):
            offenders.append((line_number, current_test, line.strip()))

    assert offenders == []


def test_stage1_agent_driven_config_contains_lanes_review_and_writer_policy(default_config):
    assert default_config["stage1_mode"] == "agent-driven"
    assert default_config["template_requirements_strategy"]["python_validate_only"] is True
    assert default_config["template_requirements_strategy"]["agent_role"]
    assert default_config["template_requirements_strategy"]["lane_id"]
    assert default_config["template_requirements_strategy"]["schema"]
    assert default_config["template_requirements_strategy"]["templates_per_packet"] == 5
    assert default_config["canonical_graph_writer"]["semantic_generation"] == "disabled"
    assert default_config["element_lanes"]
    assert all(
        "lane_id" in lane and "agent_role" in lane and "required" in lane and "schema" in lane
        for lane in default_config["element_lanes"]
    )
    assert default_config["review_policy"]["require_review_before_canonical_merge"] is True


def test_default_element_lanes_do_not_carry_legacy_artifact_paths(default_config):
    assert [
        lane.get("artifact_path")
        for lane in default_config["element_lanes"]
        if "artifact_path" in lane
    ] == []


def test_stage1_artifacts_include_agent_driven_output_dirs(default_config):
    required = {
        "requirements",
        "task_packet_dir",
        "chunk_text_dir",
        "lane_output_dir",
        "reviewed_bundle_dir",
        "merge_queue",
        "review_findings",
        "canonical_graph",
        "agent_run_ledger",
    }

    assert required.issubset(default_config["stage1_artifacts"])


def test_writer_policy_manages_agent_driven_stage1_outputs(default_config):
    managed = set(default_config["writer_policy"]["managed_outputs"])
    assert "coverage/review-findings.json" in managed
    assert "intermediate/merge-queue.json" in managed
    assert "requirements/template-requirements.json" in managed
    assert "intermediate/template-requirements-parts/*.json" in managed


def test_writer_policy_accepts_configured_stage1_artifact_samples(default_config, tmp_path):
    from storygraph_lib.output_writer import validate_managed_output_path

    artifacts = default_config["stage1_artifacts"]
    managed = default_config["writer_policy"]["managed_outputs"]
    samples = [
        f"{artifacts['task_packet_dir']}/chunk-0001/events.json",
        f"{artifacts['chunk_text_dir']}/chunk-0001.txt",
        f"{artifacts['lane_output_dir']}/chunk-0001/events/run-001.json",
        f"{artifacts['reviewed_bundle_dir']}/chunk-0001.json",
    ]

    for relative_path in samples:
        result = validate_managed_output_path(
            graph_dir=tmp_path / "mini_novel.storygraph",
            relative_path=relative_path,
            managed_outputs=managed,
        )
        assert result.ok is True


def test_writer_policy_rejects_deeper_configured_stage1_artifact_paths(
    default_config, tmp_path
):
    from storygraph_lib.output_writer import validate_managed_output_path

    artifacts = default_config["stage1_artifacts"]
    managed = default_config["writer_policy"]["managed_outputs"]
    deeper_paths = [
        f"{artifacts['task_packet_dir']}/chunk-0001/deeper/events.json",
        f"{artifacts['chunk_text_dir']}/chunk-0001/deeper.txt",
        f"{artifacts['lane_output_dir']}/chunk-0001/events/deeper/run-001.json",
        f"{artifacts['reviewed_bundle_dir']}/chunk-0001/deeper.json",
    ]

    for relative_path in deeper_paths:
        result = validate_managed_output_path(
            graph_dir=tmp_path / "mini_novel.storygraph",
            relative_path=relative_path,
            managed_outputs=managed,
        )
        assert result.ok is False


def test_stage1_config_covers_graphify_adapter_and_status_enums(default_config):
    adapter = default_config["graphify_adapter"]
    assert adapter["input_strategy"] == "canonical-graph-or-graph-dir-only"
    assert adapter["failure_policy"] in adapter["allowed_failure_policies"]
    assert set(adapter["allowed_failure_policies"]) == {"degrade-visualization-and-query", "blocking"}

    enums = default_config["status_enums"]
    assert {"pending", "completed", "blocked", "failed", "needs_repair"}.issubset(enums["lane_output_statuses"])
    assert {"pending", "passed", "failed", "blocked"}.issubset(enums["reviewer_statuses"])
    assert {"open", "closed", "waived"}.issubset(enums["finding_statuses"])
    assert {"must_fix", "should_fix", "note"}.issubset(enums["finding_severities"])
    assert {"blocking", "rebuild_required", "degraded", "not_applicable"}.issubset(enums["structured_failure_statuses"])


def test_config_contract_rejects_legacy_stage1_semantic_switches():
    from storygraph_lib.config import validate_config_contract

    result = validate_config_contract(
        {
            "stages": {"build_template_aware_graph": True},
            "graphify_adapter": {"canonical_graph_policy": "merge-template-aware-supplements"},
        }
    )

    assert result.ok is False
    assert "legacy_semantic_config:stages.build_template_aware_graph" in result.errors
    assert (
        "legacy_semantic_config:graphify_adapter.canonical_graph_policy:"
        "merge-template-aware-supplements"
    ) in result.errors


def test_config_rejects_legacy_canonical_graph_policy_merge_template_aware_supplements():
    from storygraph_lib.config import validate_config_contract

    result = validate_config_contract(
        {"canonical_graph_policy": "merge-template-aware-supplements"}
    )

    assert result.ok is False
    assert (
        "legacy_semantic_config:canonical_graph_policy:"
        "merge-template-aware-supplements"
    ) in result.errors


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


@pytest.mark.parametrize(
    ("raw_config", "expected_error"),
    [
        ("[]", "config_shape_not_object"),
        ('{"child":' * 80 + "0" + "}" * 80, "config_too_deep"),
    ],
)
def test_config_boundary_bad_inputs_are_structured_failures(
    capsys, tmp_path, raw_config, expected_error
):
    from storygraph_lib.cli import main

    config = tmp_path / "storygraph.default.json"
    config.write_text(raw_config, encoding="utf-8")

    assert main(["config-check", "--config", str(config)]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is False
    assert payload["error"] == expected_error
    assert "message" not in payload


@pytest.mark.parametrize(
    ("raw_override", "expected_error"),
    [
        ("[]", "local_override_shape_not_object"),
        ('{"child":' * 80 + "0" + "}" * 80, "local_override_too_deep"),
    ],
)
def test_local_override_boundary_errors_do_not_leak_parser_exceptions(
    capsys, tmp_path, raw_override, expected_error
):
    from storygraph_lib.cli import main

    config = tmp_path / "storygraph.default.json"
    config.write_text(json.dumps({"graph_dir_suffix": ".storygraph"}), encoding="utf-8")
    local = tmp_path / "storygraph.local.json"
    local.write_text(raw_override, encoding="utf-8")

    assert main(["config-check", "--config", str(config), "--local-override", str(local)]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is False
    assert payload["error"] == expected_error
    assert "message" not in payload
