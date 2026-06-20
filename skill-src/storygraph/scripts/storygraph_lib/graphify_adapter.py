from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any


REQUIRED_ARTIFACTS = ["graph.json", "GRAPH_REPORT.md", "graph.html"]
VALID_MODES = {"local-repo", "cli", "local-repo-or-cli"}


@dataclass(frozen=True)
class GraphifyResult:
    ok: bool
    graph_path: Path | None
    error: dict | None
    command: list[str]


class GraphifyAdapter:
    def __init__(
        self,
        graphify_repo: Path | None,
        command: object,
        timeout_seconds: object,
        mode: str = "local-repo-or-cli",
        config_error: dict | None = None,
    ):
        self.graphify_repo = Path(graphify_repo) if graphify_repo is not None else None
        self.command = command
        self.timeout_seconds = timeout_seconds
        self.mode = mode
        self.config_error = config_error

    def build_graph(self, source_path: Path, output_dir: Path) -> GraphifyResult:
        source_path = Path(source_path).resolve()
        output_dir = Path(output_dir).resolve()
        command_for_result = self._command_for_result()

        if self.config_error:
            return GraphifyResult(False, None, self.config_error, command_for_result)

        if self.mode not in VALID_MODES:
            return GraphifyResult(
                False,
                None,
                {
                    "code": "graphify_bad_command",
                    "field": "mode",
                    "mode": self.mode,
                    "message": "graphify mode is not supported",
                },
                command_for_result,
            )

        command, command_error = self._validated_command()
        if command_error:
            return GraphifyResult(False, None, command_error, command_for_result)

        timeout_seconds, timeout_error = _validated_timeout(self.timeout_seconds)
        if timeout_error:
            return GraphifyResult(False, None, timeout_error, command)

        cwd = self._resolve_cwd()
        if isinstance(cwd, dict):
            return GraphifyResult(False, None, cwd, command)

        output_dir.mkdir(parents=True, exist_ok=True)
        command = self._format_command(source_path, output_dir)

        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return GraphifyResult(
                False,
                None,
                {
                    "code": "graphify_timeout",
                    "timeout_seconds": timeout_seconds,
                    "stdout": (exc.stdout or "")[-4000:],
                    "stderr": (exc.stderr or "")[-4000:],
                },
                command,
            )
        except FileNotFoundError as exc:
            return GraphifyResult(
                False,
                None,
                {"code": "graphify_unavailable", "executable": command[0], "message": str(exc)},
                command,
            )
        except OSError as exc:
            return GraphifyResult(
                False,
                None,
                {"code": "graphify_unavailable", "executable": command[0], "message": str(exc)},
                command,
            )

        if completed.returncode != 0:
            return GraphifyResult(
                False,
                None,
                {
                    "code": "graphify_failed",
                    "returncode": completed.returncode,
                    "stderr": completed.stderr[-4000:],
                },
                command,
            )

        missing = [name for name in REQUIRED_ARTIFACTS if not (output_dir / name).exists()]
        if missing:
            return GraphifyResult(
                False,
                None,
                {
                    "code": "graphify_artifact_missing",
                    "missing": missing,
                    "stdout": completed.stdout[-4000:],
                },
                command,
            )

        return GraphifyResult(True, output_dir / "graph.json", None, command)

    def _resolve_cwd(self) -> Path | None | dict:
        if self.mode == "cli":
            return None

        if self.mode == "local-repo":
            if self.graphify_repo is None or not self.graphify_repo.exists():
                return {"code": "graphify_unavailable", "path": str(self.graphify_repo)}
            return self.graphify_repo

        if self.graphify_repo is None:
            return None
        if not self.graphify_repo.exists():
            return {"code": "graphify_unavailable", "path": str(self.graphify_repo)}
        return self.graphify_repo

    def _format_command(self, source_path: Path, output_dir: Path) -> list[str]:
        return [
            part.replace("{source}", str(source_path)).replace("{output_dir}", str(output_dir))
            for part in self._validated_command()[0]
        ]

    def _validated_command(self) -> tuple[list[str], dict | None]:
        if not isinstance(self.command, list):
            return [], {
                "code": "graphify_bad_command",
                "field": "command",
                "message": "graphify command must be a list of strings",
            }
        if not self.command:
            return [], {
                "code": "graphify_bad_command",
                "field": "command",
                "message": "graphify command must not be empty",
            }
        for part in self.command:
            if not isinstance(part, str) or not part:
                return [], {
                    "code": "graphify_bad_command",
                    "field": "command",
                    "message": "graphify command must contain only non-empty strings",
                }
        return list(self.command), None

    def _command_for_result(self) -> list[str]:
        return list(self.command) if isinstance(self.command, list) else []


def _validated_timeout(value: Any) -> tuple[int | None, dict | None]:
    if isinstance(value, bool):
        return None, _bad_timeout_error(value)
    try:
        timeout_seconds = int(value)
    except (TypeError, ValueError):
        return None, _bad_timeout_error(value)
    if timeout_seconds <= 0:
        return None, _bad_timeout_error(value)
    return timeout_seconds, None


def _bad_timeout_error(value: Any) -> dict:
    return {
        "code": "graphify_bad_command",
        "field": "timeout_seconds",
        "value": value,
        "message": "graphify timeout_seconds must be a positive integer",
    }
