from dataclasses import dataclass
from pathlib import Path
import subprocess


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
        command: list[str],
        timeout_seconds: int,
        mode: str = "local-repo-or-cli",
    ):
        self.graphify_repo = Path(graphify_repo) if graphify_repo is not None else None
        self.command = list(command)
        self.timeout_seconds = timeout_seconds
        self.mode = mode

    def build_graph(self, source_path: Path, output_dir: Path) -> GraphifyResult:
        source_path = Path(source_path).resolve()
        output_dir = Path(output_dir).resolve()

        if self.mode not in VALID_MODES:
            return GraphifyResult(
                False,
                None,
                {"code": "graphify_bad_mode", "mode": self.mode},
                list(self.command),
            )

        if not self.command:
            return GraphifyResult(
                False,
                None,
                {"code": "graphify_bad_command", "message": "graphify command must not be empty"},
                [],
            )

        cwd = self._resolve_cwd()
        if isinstance(cwd, dict):
            return GraphifyResult(False, None, cwd, list(self.command))

        output_dir.mkdir(parents=True, exist_ok=True)
        command = self._format_command(source_path, output_dir)

        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return GraphifyResult(
                False,
                None,
                {
                    "code": "graphify_timeout",
                    "timeout_seconds": self.timeout_seconds,
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
            for part in self.command
        ]
