import json
import sys
from pathlib import Path

from storygraph_lib.graphify_adapter import GraphifyAdapter


def test_adapter_reports_unavailable_graphify_without_modifying_repo(tmp_path):
    adapter = GraphifyAdapter(
        graphify_repo=tmp_path / "missing",
        command=["python", "-c", "print('unused')"],
        timeout_seconds=5,
        mode="local-repo",
    )

    result = adapter.build_graph(source_path=tmp_path / "novel.txt", output_dir=tmp_path / "out")

    assert result.ok is False
    assert result.error["code"] == "graphify_unavailable"
    assert not (tmp_path / "missing").exists()


def test_adapter_local_repo_or_cli_fails_when_explicit_repo_is_missing(tmp_path):
    adapter = GraphifyAdapter(
        graphify_repo=tmp_path / "missing",
        command=["python", "-c", "print('would otherwise succeed')"],
        timeout_seconds=5,
        mode="local-repo-or-cli",
    )

    result = adapter.build_graph(source_path=tmp_path / "novel.txt", output_dir=tmp_path / "out")

    assert result.ok is False
    assert result.error["code"] == "graphify_unavailable"


def test_adapter_invokes_configured_external_command_and_requires_artifacts(tmp_path):
    repo = tmp_path / "graphify"
    repo.mkdir()
    script = repo / "fake_graphify.py"
    script.write_text(
        "\n".join(
            [
                "import json, pathlib, sys",
                "out = pathlib.Path(sys.argv[2])",
                "out.mkdir(parents=True, exist_ok=True)",
                "(out / 'graph.json').write_text(json.dumps({'nodes': [], 'edges': [], 'hyperedges': [], 'metadata': {'fake': True}}), encoding='utf-8')",
                "(out / 'GRAPH_REPORT.md').write_text('# Graph Report\\n', encoding='utf-8')",
                "(out / 'graph.html').write_text('<!doctype html><title>graph</title>', encoding='utf-8')",
            ]
        ),
        encoding="utf-8",
    )
    source = tmp_path / "novel.txt"
    source.write_text("正文", encoding="utf-8")
    adapter = GraphifyAdapter(
        graphify_repo=repo,
        command=[sys.executable, "fake_graphify.py", "{source}", "{output_dir}"],
        timeout_seconds=5,
        mode="local-repo-or-cli",
    )

    result = adapter.build_graph(source, tmp_path / "out")

    assert result.ok is True
    assert json.loads(result.graph_path.read_text(encoding="utf-8"))["metadata"]["fake"] is True
    assert (tmp_path / "out" / "GRAPH_REPORT.md").exists()
    assert (tmp_path / "out" / "graph.html").exists()


def test_adapter_local_repo_mode_resolves_relative_output_dir_from_caller_cwd(
    monkeypatch, tmp_path
):
    caller = tmp_path / "caller"
    caller.mkdir()
    repo = tmp_path / "graphify"
    repo.mkdir()
    script = repo / "fake_graphify.py"
    script.write_text(
        "\n".join(
            [
                "import json, pathlib, sys",
                "source = pathlib.Path(sys.argv[1])",
                "out = pathlib.Path(sys.argv[2])",
                "assert source.is_absolute()",
                "assert out.is_absolute()",
                "out.mkdir(parents=True, exist_ok=True)",
                "(out / 'graph.json').write_text(json.dumps({'metadata': {'absolute_out': True}}), encoding='utf-8')",
                "(out / 'GRAPH_REPORT.md').write_text('# Graph Report\\n', encoding='utf-8')",
                "(out / 'graph.html').write_text('<!doctype html><title>graph</title>', encoding='utf-8')",
            ]
        ),
        encoding="utf-8",
    )
    source = caller / "novel.txt"
    source.write_text("正文", encoding="utf-8")
    monkeypatch.chdir(caller)
    adapter = GraphifyAdapter(
        graphify_repo=repo,
        command=[sys.executable, "fake_graphify.py", "{source}", "{output_dir}"],
        timeout_seconds=5,
        mode="local-repo",
    )

    result = adapter.build_graph(Path("novel.txt"), Path("relative-out"))

    assert result.ok is True
    assert result.graph_path == caller / "relative-out" / "graph.json"
    assert (caller / "relative-out" / "GRAPH_REPORT.md").exists()
    assert not (repo / "relative-out").exists()


def test_adapter_cli_mode_does_not_require_local_repo(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text("正文", encoding="utf-8")
    command = [
        sys.executable,
        "-c",
        "import json,pathlib,sys; out=pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True); (out/'graph.json').write_text(json.dumps({'nodes': [], 'edges': [], 'hyperedges': [], 'metadata': {'cli': True}}), encoding='utf-8'); (out/'GRAPH_REPORT.md').write_text('# Graph Report\\n', encoding='utf-8'); (out/'graph.html').write_text('<!doctype html><title>graph</title>', encoding='utf-8')",
        "{source}",
        "{output_dir}",
    ]
    adapter = GraphifyAdapter(graphify_repo=None, command=command, timeout_seconds=5, mode="cli")

    result = adapter.build_graph(source, tmp_path / "out")

    assert result.ok is True


def test_adapter_command_exit_zero_but_missing_required_artifacts_is_structured_error(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text("正文", encoding="utf-8")
    command = [
        sys.executable,
        "-c",
        "import pathlib,sys; pathlib.Path(sys.argv[2]).mkdir(parents=True, exist_ok=True)",
        "{source}",
        "{output_dir}",
    ]
    adapter = GraphifyAdapter(graphify_repo=None, command=command, timeout_seconds=5, mode="cli")

    result = adapter.build_graph(source, tmp_path / "out")

    assert result.ok is False
    assert result.error["code"] == "graphify_artifact_missing"
    assert set(result.error["missing"]) == {"graph.json", "GRAPH_REPORT.md", "graph.html"}


def test_adapter_nonzero_exit_returns_failed_error_with_stderr_tail(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text("正文", encoding="utf-8")
    command = [
        sys.executable,
        "-c",
        "import sys; sys.stderr.write('boom'); raise SystemExit(7)",
        "{source}",
        "{output_dir}",
    ]
    adapter = GraphifyAdapter(graphify_repo=None, command=command, timeout_seconds=5, mode="cli")

    result = adapter.build_graph(source, tmp_path / "out")

    assert result.ok is False
    assert result.error["code"] == "graphify_failed"
    assert result.error["returncode"] == 7
    assert "boom" in result.error["stderr"]
