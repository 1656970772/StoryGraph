import json
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from .adapters import AgentAdapter, AgentRegistry


LEGACY_SEMANTIC_CONFIG_KEYS = {
    "template_parser_rules",
    "template_graph_mappings",
    "supplemental_graph_policy",
    "evidence_matching_strategy",
}
LEGACY_STAGE_KEYS = {
    ("stages", "build_template_aware_graph"),
}
LEGACY_GRAPHIFY_CANONICAL_POLICIES = {
    "merge-template-aware-supplements",
}
MAX_CONFIG_JSON_DEPTH = 64


@dataclass(frozen=True)
class ConfigContractResult:
    ok: bool
    errors: list[str]


class ConfigLoadError(ValueError):
    def __init__(
        self,
        code: str,
        path: Path,
        *,
        line: int | None = None,
        column: int | None = None,
        source: str = "config",
    ):
        self.code = code
        self.path = Path(path)
        self.line = line
        self.column = column
        self.source = source
        super().__init__(code)

    def to_dict(self) -> dict:
        payload = {
            "ok": False,
            "error": self.code,
            "path": str(self.path),
            "source": self.source,
        }
        if self.line is not None:
            payload["line"] = self.line
        if self.column is not None:
            payload["column"] = self.column
        return payload


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(
    default_path: Path,
    local_override: Path | None = None,
    cli_overrides: dict | None = None,
) -> dict:
    config = _read_config_json(default_path, source="default_config")
    if local_override and local_override.exists():
        config = _deep_merge(config, _read_config_json(local_override, source="local_override"))
    if cli_overrides:
        config = _deep_merge(config, cli_overrides)
    return config


def validate_config_contract(config: dict) -> ConfigContractResult:
    errors = [
        f"legacy_semantic_config:{key}"
        for key in sorted(LEGACY_SEMANTIC_CONFIG_KEYS)
        if key in config
    ]
    for section, key in sorted(LEGACY_STAGE_KEYS):
        if isinstance(config.get(section), dict) and key in config[section]:
            errors.append(f"legacy_semantic_config:{section}.{key}")

    canonical_policy = config.get("canonical_graph_policy")
    if canonical_policy in LEGACY_GRAPHIFY_CANONICAL_POLICIES:
        errors.append(f"legacy_semantic_config:canonical_graph_policy:{canonical_policy}")

    graphify_adapter = config.get("graphify_adapter")
    if isinstance(graphify_adapter, dict):
        adapter_canonical_policy = graphify_adapter.get("canonical_graph_policy")
        if adapter_canonical_policy in LEGACY_GRAPHIFY_CANONICAL_POLICIES:
            errors.append(
                "legacy_semantic_config:graphify_adapter.canonical_graph_policy:"
                f"{adapter_canonical_policy}"
            )
    return ConfigContractResult(ok=not errors, errors=errors)


def _read_config_json(path: Path, source: str) -> dict:
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise ConfigLoadError("config_encoding_error", path, source=source) from exc
    except json.JSONDecodeError as exc:
        raise ConfigLoadError(
            "config_json_error",
            path,
            line=exc.lineno,
            column=exc.colno,
            source=source,
        ) from exc
    except RecursionError as exc:
        raise ConfigLoadError(
            _config_error_code(source, "too_deep"),
            path,
            source=source,
        ) from exc

    if _json_too_deep(payload, MAX_CONFIG_JSON_DEPTH):
        raise ConfigLoadError(_config_error_code(source, "too_deep"), path, source=source)
    if not isinstance(payload, dict):
        raise ConfigLoadError(_config_error_code(source, "shape_not_object"), path, source=source)
    return payload


def _config_error_code(source: str, suffix: str) -> str:
    prefix = "local_override" if source == "local_override" else "config"
    return f"{prefix}_{suffix}"


def _json_too_deep(value, max_depth: int) -> bool:
    stack = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        if depth > max_depth:
            return True
        if isinstance(item, dict):
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
    return False


def load_agent_adapters(config: dict) -> AgentRegistry:
    """Load agent adapters from config.

    Args:
        config: Configuration dict with agent_platform section

    Returns:
        AgentRegistry with loaded adapters

    Raises:
        ValueError: If adapter loading fails
    """
    agent_config = config.get("agent_platform", {})
    adapters: dict[str, AgentAdapter] = {}

    if not agent_config.get("enabled", True):
        # Return empty registry if agent_platform is disabled
        return AgentRegistry()

    adapter_configs = agent_config.get("agent_adapters", {})
    for agent_type, adapter_spec in adapter_configs.items():
        module_name = adapter_spec.get("module")
        class_name = adapter_spec.get("class")
        adapter_config = adapter_spec.get("config", {})

        if not module_name or not class_name:
            raise ValueError(
                f"Agent adapter {agent_type} missing module or class name"
            )

        try:
            module = import_module(module_name)
            adapter_class = getattr(module, class_name)
            adapters[agent_type] = adapter_class(adapter_config)
        except (ImportError, AttributeError) as exc:
            raise ValueError(
                f"Failed to load agent adapter {agent_type} from {module_name}.{class_name}: {exc}"
            ) from exc

    return AgentRegistry(adapters)
