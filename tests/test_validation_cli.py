import os
import subprocess
from pathlib import Path

from storygraph_lib.validation import validate_skill_tree


def test_validate_skill_tree_requires_core_directories(tmp_path):
    root = tmp_path / "storygraph"
    (root / "references").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "config").mkdir()
    (root / "agents").mkdir()
    (root / "SKILL.md").write_text("# StoryGraph\n", encoding="utf-8")
    (root / "agents" / "openai.yaml").write_text("name: storygraph\n", encoding="utf-8")
    (root / "config" / "storygraph.default.json").write_text("{}", encoding="utf-8")
    (root / "references" / "workflow.md").write_text("# Workflow\n", encoding="utf-8")
    (root / "references" / "graph-schema.md").write_text("# Graph Schema\n", encoding="utf-8")
    (root / "references" / "extraction-workflow.md").write_text("# Extraction Workflow\n", encoding="utf-8")
    (root / "scripts" / "storygraph.py").write_text("print('ok')\n", encoding="utf-8")
    (root / "scripts" / "sync-skill.ps1").write_text("Write-Output 'ok'\n", encoding="utf-8")
    result = validate_skill_tree(root)
    assert result.ok is True
    assert result.missing == []


def test_sync_clean_script_contains_destination_boundary_guard():
    script = Path("skill-src/storygraph/scripts/sync-skill.ps1").read_text(encoding="utf-8")
    assert "[IO.Path]::GetFullPath($Destination).TrimEnd('\\')" in script
    assert ".codex\\skills\\storygraph" in script
    assert "if ($Clean -and $destinationRoot -ne $expectedResolved)" in script
    assert "Remove-Item -LiteralPath $target -Recurse -Force" in script


def test_sync_clean_refuses_unexpected_destination(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "not-storygraph"
    source.mkdir()
    destination.mkdir()
    script = Path("skill-src/storygraph/scripts/sync-skill.ps1")
    result = __import__("subprocess").run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Source",
            str(source),
            "-Destination",
            str(destination),
            "-Clean",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Refusing to clean unexpected destination" in (result.stderr + result.stdout)


def test_sync_clean_refuses_unexpected_destination_without_creating_it(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "not-created"
    source.mkdir()
    script = Path("skill-src/storygraph/scripts/sync-skill.ps1")
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Source",
            str(source),
            "-Destination",
            str(destination),
            "-Clean",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Refusing to clean unexpected destination" in (result.stderr + result.stdout)
    assert not destination.exists()


def test_sync_without_clean_allows_custom_destination(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "custom-storygraph"
    (source / "scripts").mkdir(parents=True)
    (source / "SKILL.md").write_text("# StoryGraph\n", encoding="utf-8")
    script = Path("skill-src/storygraph/scripts/sync-skill.ps1")
    result = __import__("subprocess").run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Source",
            str(source),
            "-Destination",
            str(destination),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert (destination / "SKILL.md").exists()


def test_sync_without_clean_preserves_extra_destination_files(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "custom-storygraph"
    (source / "scripts").mkdir(parents=True)
    (source / "SKILL.md").write_text("# StoryGraph\n", encoding="utf-8")
    destination.mkdir()
    extra = destination / "README.local.md"
    extra.write_text("keep me\n", encoding="utf-8")
    script = Path("skill-src/storygraph/scripts/sync-skill.ps1")
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Source",
            str(source),
            "-Destination",
            str(destination),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert (destination / "SKILL.md").exists()
    assert extra.read_text(encoding="utf-8") == "keep me\n"


def test_sync_clean_preserves_local_config_in_default_install(tmp_path):
    source = tmp_path / "source"
    (source / "config").mkdir(parents=True)
    (source / "config" / "storygraph.default.json").write_text('{"managed": true}\n', encoding="utf-8")
    home = tmp_path / "home"
    destination = home / ".codex" / "skills" / "storygraph"
    (destination / "config").mkdir(parents=True)
    local_config = destination / "config" / "storygraph.local.json"
    local_config.write_text('{"local": true}\n', encoding="utf-8")
    (destination / "config" / "storygraph.default.json").write_text('{"old": true}\n', encoding="utf-8")
    script = Path("skill-src/storygraph/scripts/sync-skill.ps1")
    env = os.environ.copy()
    env["USERPROFILE"] = str(home)
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Source",
            str(source),
            "-Clean",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert local_config.read_text(encoding="utf-8") == '{"local": true}\n'
    assert (destination / "config" / "storygraph.default.json").read_text(encoding="utf-8") == (
        '{"managed": true}\n'
    )


def test_storygraph_script_version_flag_remains_supported():
    result = subprocess.run(
        ["python", "skill-src/storygraph/scripts/storygraph.py", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "storygraph 0.1.0"
