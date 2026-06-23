"""Agent registry for discovering and selecting agents."""

from typing import Any, Optional

from .base import AgentAdapter, AgentCapabilities


class AgentRegistry:
    """Registry for managing agent adapters."""

    def __init__(self, adapters: dict[str, AgentAdapter] | None = None):
        """Initialize registry with adapters.

        Args:
            adapters: Dict mapping agent_type to AgentAdapter instances
        """
        self._adapters: dict[str, AgentAdapter] = {}
        if adapters:
            for agent_type, adapter in adapters.items():
                self.register_adapter(agent_type, adapter)

    def register_adapter(self, agent_type: str, adapter: AgentAdapter) -> None:
        """Register an agent adapter.

        Args:
            agent_type: Agent type identifier (e.g., "codex")
            adapter: AgentAdapter instance
        """
        if not isinstance(adapter, AgentAdapter):
            raise TypeError(f"Expected AgentAdapter, got {type(adapter)}")
        self._adapters[agent_type] = adapter

    def get_adapter(self, agent_type: str) -> Optional[AgentAdapter]:
        """Get adapter by agent type.

        Args:
            agent_type: Agent type identifier

        Returns:
            AgentAdapter instance or None if not found
        """
        return self._adapters.get(agent_type)

    def get_available_adapters(
        self, stage: str, lane_id: str = ""
    ) -> list[tuple[str, AgentAdapter]]:
        """Get adapters available for a stage and optional lane.

        Args:
            stage: Stage identifier (e.g., "stage1")
            lane_id: Lane identifier (optional)

        Returns:
            List of (agent_type, adapter) tuples that support the stage/lane
        """
        result = []
        for agent_type, adapter in self._adapters.items():
            if not adapter.is_available():
                continue
            if not adapter.supports_stage(stage):
                continue
            if lane_id and not adapter.supports_lane(lane_id):
                continue
            result.append((agent_type, adapter))
        return result

    def select_best_adapter(
        self,
        stage: str,
        lane_id: str = "",
        preferred_agents: list[str] | None = None,
    ) -> tuple[str, AgentAdapter] | None:
        """Select best adapter based on preferences.

        Args:
            stage: Stage identifier
            lane_id: Lane identifier (optional)
            preferred_agents: List of preferred agent types in order

        Returns:
            Tuple of (agent_type, adapter) or None if none available
        """
        available = self.get_available_adapters(stage, lane_id)
        if not available:
            return None

        # If preferences given, use first available from preferences
        if preferred_agents:
            for pref_type in preferred_agents:
                for agent_type, adapter in available:
                    if agent_type == pref_type:
                        return (agent_type, adapter)

        # Otherwise return first available
        if available:
            return available[0]

        return None

    def resolve_dispatch_capability(
        self,
        stage: str,
        lane_id: str = "",
        selector: dict[str, Any] | None = None,
        forced_agent_type: str | None = None,
    ) -> dict[str, Any] | None:
        """Resolve the adapter and max parallelism for a dispatch target.

        Args:
            stage: Fallback stage identifier.
            lane_id: Fallback lane identifier.
            selector: Optional task/batch agent selector.
            forced_agent_type: Explicit agent type override.

        Returns:
            Dict with agent_type, adapter, capabilities, and max_parallel_tasks,
            or None when no usable adapter capability is available.
        """
        selector = selector if isinstance(selector, dict) else {}
        resolved_stage = selector.get("stage")
        if not isinstance(resolved_stage, str) or not resolved_stage:
            resolved_stage = stage
        resolved_lane = selector.get("lane_id")
        if not isinstance(resolved_lane, str):
            resolved_lane = lane_id
        preferred = selector.get("preferred_agents")
        if not (
            isinstance(preferred, list)
            and all(isinstance(item, str) and item for item in preferred)
        ):
            preferred = None

        if forced_agent_type:
            adapter = self.get_adapter(forced_agent_type)
            if not adapter or not adapter.is_available():
                return None
            if not adapter.supports_stage(resolved_stage):
                return None
            if resolved_lane and not adapter.supports_lane(resolved_lane):
                return None
            agent_type = forced_agent_type
        else:
            result = self.select_best_adapter(
                resolved_stage,
                resolved_lane,
                preferred_agents=preferred,
            )
            if not result:
                return None
            agent_type, adapter = result

        capabilities = adapter.get_capabilities()
        max_parallel = capabilities.get("max_parallel_tasks")
        if type(max_parallel) is not int or max_parallel <= 0:
            return None
        return {
            "agent_type": agent_type,
            "adapter": adapter,
            "capabilities": capabilities,
            "max_parallel_tasks": max_parallel,
        }

    def list_agents(self) -> list[str]:
        """List all registered agent types.

        Returns:
            List of agent type identifiers
        """
        return list(self._adapters.keys())

    def get_capabilities(self, agent_type: str) -> AgentCapabilities | None:
        """Get capabilities for an agent type.

        Args:
            agent_type: Agent type identifier

        Returns:
            AgentCapabilities dict or None if not found
        """
        adapter = self.get_adapter(agent_type)
        if adapter:
            return adapter.get_capabilities()
        return None
