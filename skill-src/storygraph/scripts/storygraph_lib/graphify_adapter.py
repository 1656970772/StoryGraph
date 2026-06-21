from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any


REQUIRED_ARTIFACTS = ["graph.json", "GRAPH_REPORT.md", "graph.html"]
VALID_MODES = {"local-repo", "cli", "local-repo-or-cli"}
VALID_FAILURE_POLICIES = {"degrade-visualization-and-query", "blocking"}
VALID_INPUT_STRATEGIES = {"canonical-graph-or-graph-dir-only"}


@dataclass(frozen=True)
class GraphifyResult:
    ok: bool
    graph_path: Path | None
    error: dict | None
    command: list[str]
    status: str = "success"
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class GraphifyCommandResult:
    ok: bool
    command: list[str]
    errors: list[str]
    error: dict | None = None


@dataclass(frozen=True)
class GraphifyOutputDecodeResult:
    ok: bool
    status: str
    payload: dict | None
    stdout: str
    stderr: str
    errors: list[str]
    warnings: list[str]


class GraphifyAdapter:
    def __init__(
        self,
        graphify_repo: Path | None,
        command: object,
        timeout_seconds: object,
        mode: str = "local-repo-or-cli",
        failure_policy: str = "blocking",
        input_strategy: str = "canonical-graph-or-graph-dir-only",
        config_error: dict | None = None,
    ):
        self.graphify_repo = Path(graphify_repo) if graphify_repo is not None else None
        self.command = command
        self.timeout_seconds = timeout_seconds
        self.mode = mode
        self.failure_policy = failure_policy
        self.input_strategy = input_strategy
        self.config_error = config_error

    def build_graph(
        self,
        canonical_graph_path: Path | None,
        output_dir: Path,
        *,
        graph_dir: Path | None = None,
    ) -> GraphifyResult:
        output_dir = Path(output_dir).resolve()
        command_for_result = self._command_for_result()

        if self.config_error:
            return GraphifyResult(
                False, None, self.config_error, command_for_result, status="failed"
            )

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
                status="failed",
            )

        if self.failure_policy not in VALID_FAILURE_POLICIES:
            return GraphifyResult(
                False,
                None,
                {
                    "code": "graphify_bad_command",
                    "field": "failure_policy",
                    "failure_policy": self.failure_policy,
                    "message": "graphify failure_policy is not supported",
                },
                command_for_result,
                status="failed",
            )

        if self.input_strategy not in VALID_INPUT_STRATEGIES:
            return GraphifyResult(
                False,
                None,
                {
                    "code": "graphify_bad_command",
                    "field": "input_strategy",
                    "input_strategy": self.input_strategy,
                    "message": "graphify input_strategy is not supported",
                },
                command_for_result,
                status="failed",
            )

        command, command_error = self._validated_command()
        if command_error:
            return GraphifyResult(
                False, None, command_error, command_for_result, status="failed"
            )

        timeout_seconds, timeout_error = _validated_timeout(self.timeout_seconds)
        if timeout_error:
            return GraphifyResult(False, None, timeout_error, command, status="failed")

        cwd = self._resolve_cwd()
        if isinstance(cwd, dict):
            return GraphifyResult(False, None, cwd, command, status="failed")

        output_dir.mkdir(parents=True, exist_ok=True)
        command_result = _build_graphify_command(
            command=command,
            input_strategy=self.input_strategy,
            source_path=None,
            canonical_graph_path=canonical_graph_path,
            graph_dir=graph_dir,
            output_dir=output_dir,
        )
        if not command_result.ok:
            return GraphifyResult(
                False, None, command_result.error, command_result.command, status="failed"
            )
        command = command_result.command

        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return GraphifyResult(
                False,
                None,
                {
                    "code": "graphify_timeout",
                    "timeout_seconds": timeout_seconds,
                    "stdout": _tail_text(exc.stdout),
                    "stderr": _tail_text(exc.stderr),
                },
                command,
                status="failed",
            )
        except FileNotFoundError as exc:
            return GraphifyResult(
                False,
                None,
                {"code": "graphify_unavailable", "executable": command[0], "message": str(exc)},
                command,
                status="failed",
            )
        except OSError as exc:
            return GraphifyResult(
                False,
                None,
                {"code": "graphify_unavailable", "executable": command[0], "message": str(exc)},
                command,
                status="failed",
            )

        if completed.returncode != 0:
            return GraphifyResult(
                False,
                None,
                {
                    "code": "graphify_failed",
                    "returncode": completed.returncode,
                    "stderr": _tail_text(completed.stderr),
                },
                command,
                status="failed",
            )

        missing = [name for name in REQUIRED_ARTIFACTS if not (output_dir / name).exists()]
        if missing:
            return GraphifyResult(
                False,
                None,
                {
                    "code": "graphify_artifact_missing",
                    "missing": missing,
                    "stdout": _tail_text(completed.stdout),
                },
                command,
                status="failed",
            )

        decoded = decode_graphify_output(
            stdout=completed.stdout,
            stderr=completed.stderr,
            failure_policy=self.failure_policy,
        )
        if not decoded.ok:
            if decoded.status == "degraded":
                return GraphifyResult(
                    True,
                    output_dir / "graph.json",
                    None,
                    command,
                    status="degraded",
                    warnings=tuple(decoded.warnings or decoded.errors),
                )
            return GraphifyResult(
                False,
                None,
                {
                    "code": decoded.errors[0] if decoded.errors else "graphify_failed",
                    "errors": decoded.errors,
                    "stdout": decoded.stdout,
                    "stderr": decoded.stderr,
                },
                command,
                status="failed",
                warnings=tuple(decoded.warnings),
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

    def _validated_command(self) -> tuple[list[str], dict | None]:
        return _validated_command(self.command)

    def _command_for_result(self) -> list[str]:
        return list(self.command) if isinstance(self.command, list) else []


def _validated_timeout(value: Any) -> tuple[int | None, dict | None]:
    if isinstance(value, bool) or not isinstance(value, int):
        return None, _bad_timeout_error(value)
    if value <= 0:
        return None, _bad_timeout_error(value)
    return value, None


def _tail_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")[-4000:]
    return value[-4000:]


def _bad_timeout_error(value: Any) -> dict:
    return {
        "code": "graphify_bad_command",
        "field": "timeout_seconds",
        "value": value,
        "message": "graphify timeout_seconds must be a positive integer",
    }


def build_graphify_command(
    *,
    source_path: Path | None = None,
    canonical_graph_path: Path | None = None,
    graph_dir: Path | None = None,
    output_dir: Path | None = None,
    config: dict,
) -> GraphifyCommandResult:
    adapter_config = config.get("graphify_adapter", {})
    if not isinstance(adapter_config, dict):
        error = {
            "code": "graphify_bad_command",
            "field": "graphify_adapter",
            "message": "graphify_adapter must be an object",
        }
        return GraphifyCommandResult(False, [], [error["code"]], error)

    command, command_error = _validated_command(adapter_config.get("command", []))
    if command_error:
        return GraphifyCommandResult(False, [], [command_error["code"]], command_error)

    return _build_graphify_command(
        command=command,
        input_strategy=adapter_config.get(
            "input_strategy", "canonical-graph-or-graph-dir-only"
        ),
        source_path=source_path,
        canonical_graph_path=canonical_graph_path,
        graph_dir=graph_dir,
        output_dir=output_dir,
    )


def _build_graphify_command(
    *,
    command: list[str],
    input_strategy: object,
    source_path: Path | None,
    canonical_graph_path: Path | None,
    graph_dir: Path | None,
    output_dir: Path | None,
) -> GraphifyCommandResult:
    errors: list[str] = []

    if input_strategy not in VALID_INPUT_STRATEGIES:
        errors.append("graphify_bad_input_strategy")

    if any("{source}" in part for part in command):
        errors.append("graphify_source_input_rejected")

    if source_path is not None and canonical_graph_path is None and graph_dir is None:
        errors.append("graphify_source_input_rejected")

    canonical_path = Path(canonical_graph_path).resolve() if canonical_graph_path else None
    graph_root = Path(graph_dir).resolve() if graph_dir else None
    output_root = Path(output_dir).resolve() if output_dir else None

    if canonical_path is None and graph_root is None:
        errors.append("graphify_input_missing")

    if output_root is None:
        errors.append("graphify_output_dir_missing")

    if canonical_path is None and any("{canonical_graph}" in part for part in command):
        errors.append("graphify_canonical_graph_missing")
    if graph_root is None and any("{graph_dir}" in part for part in command):
        errors.append("graphify_graph_dir_missing")

    errors = _dedupe(errors)
    if errors:
        error = {
            "code": errors[0],
            "errors": errors,
            "message": "graphify adapter input must be canonical graph or graph dir",
        }
        return GraphifyCommandResult(False, [], errors, error)

    active_input = canonical_path or graph_root
    replacements = {
        "{canonical_graph}": str(canonical_path or ""),
        "{graph_dir}": str(graph_root or ""),
        "{input}": str(active_input),
        "{output_dir}": str(output_root),
    }
    formatted = list(command)
    for placeholder, value in replacements.items():
        formatted = [part.replace(placeholder, value) for part in formatted]
    return GraphifyCommandResult(True, formatted, [], None)


def _validated_command(command: object) -> tuple[list[str], dict | None]:
    if not isinstance(command, list):
        return [], {
            "code": "graphify_bad_command",
            "field": "command",
            "message": "graphify command must be a list of strings",
        }
    if not command:
        return [], {
            "code": "graphify_bad_command",
            "field": "command",
            "message": "graphify command must not be empty",
        }
    for part in command:
        if not isinstance(part, str) or not part:
            return [], {
                "code": "graphify_bad_command",
                "field": "command",
                "message": "graphify command must contain only non-empty strings",
            }
    return list(command), None


def decode_graphify_output(
    *,
    stdout: bytes | str,
    stderr: bytes | str,
    failure_policy: str,
    max_stderr_bytes: int = 65536,
) -> GraphifyOutputDecodeResult:
    errors: list[str] = []
    warnings: list[str] = []
    stdout_text = ""
    stderr_text = ""

    try:
        stdout_text = _strict_decode(stdout)
        stderr_text = _strict_decode(stderr)
    except UnicodeDecodeError:
        errors.append("subprocess_output_decode_error")
        stdout_text = _tail_text(stdout)
        stderr_text = _tail_text(stderr)

    if isinstance(stderr, bytes) and len(stderr) > max_stderr_bytes:
        errors.append("subprocess_stderr_too_large")
        stderr_text = _tail_text(stderr)
    elif isinstance(stderr, str) and len(stderr.encode("utf-8")) > max_stderr_bytes:
        errors.append("subprocess_stderr_too_large")
        stderr_text = stderr[-4000:]

    payload = None
    if stdout_text.strip() and "subprocess_output_decode_error" not in errors:
        try:
            decoded_payload = json.loads(stdout_text)
        except json.JSONDecodeError:
            errors.append("subprocess_stdout_not_json")
        else:
            if isinstance(decoded_payload, dict):
                payload = decoded_payload
            else:
                errors.append("subprocess_stdout_not_json")

    if errors:
        status = (
            "degraded"
            if failure_policy == "degrade-visualization-and-query"
            else "failed"
        )
        if status == "degraded":
            warnings = _dedupe([*warnings, *errors])
        return GraphifyOutputDecodeResult(
            ok=False,
            status=status,
            payload=payload,
            stdout=stdout_text,
            stderr=stderr_text,
            errors=_dedupe(errors),
            warnings=warnings,
        )

    return GraphifyOutputDecodeResult(
        ok=True,
        status="success",
        payload=payload,
        stdout=stdout_text,
        stderr=stderr_text,
        errors=[],
        warnings=warnings,
    )


def _strict_decode(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="strict")
    return value


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
