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
