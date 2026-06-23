"""Base adapter interface for agents."""

from abc import ABC, abstractmethod
from typing import TypedDict


class AgentCapabilities(TypedDict):
    """Agent capability declaration."""
    agent_type: str  # e.g., "codex", "claude", "opencode"
    supported_stages: list[str]  # ["stage1", "stage2", ...]
    supported_lanes: list[str]  # lane_id list, empty means all
    supported_schemas: list[str]  # output schema names
    max_parallel_tasks: int  # max parallel tasks per agent
    version: str


class AgentAdapter(ABC):
    """Base class for agent adapters."""

    def __init__(self, config: dict | None = None):
        """Initialize adapter with configuration.

        Args:
            config: Adapter-specific configuration dict
        """
        self.config = config or {}

    @abstractmethod
    def get_capabilities(self) -> AgentCapabilities:
        """Get agent capabilities.

        Returns:
            AgentCapabilities dict declaring what this agent supports
        """
        pass

    @abstractmethod
    def validate_output(
        self, output: dict, schema: str
    ) -> tuple[bool, list[str]]:
        """Validate agent output against schema.

        Args:
            output: The output dict from agent
            schema: Expected schema name (e.g., "lane-output.schema.json")

        Returns:
            Tuple of (is_valid, error_list)
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if agent is available for dispatch.

        Returns:
            True if agent can be dispatched, False otherwise
        """
        pass

    def supports_stage(self, stage: str) -> bool:
        """Check if adapter supports a stage."""
        caps = self.get_capabilities()
        return stage in caps["supported_stages"]

    def supports_lane(self, lane_id: str) -> bool:
        """Check if adapter supports a lane."""
        caps = self.get_capabilities()
        supported = caps["supported_lanes"]
        return not supported or lane_id in supported

    def supports_schema(self, schema: str) -> bool:
        """Check if adapter supports a schema."""
        caps = self.get_capabilities()
        return schema in caps["supported_schemas"]
