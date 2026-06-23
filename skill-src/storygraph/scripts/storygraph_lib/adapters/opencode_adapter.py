"""OpenCode agent adapter for StoryGraph."""

from .base import AgentAdapter, AgentCapabilities


class OpenCodeAdapter(AgentAdapter):
    """Adapter for OpenCode agent."""

    def get_capabilities(self) -> AgentCapabilities:
        """Get OpenCode capabilities."""
        return {
            "agent_type": "opencode",
            "supported_stages": ["stage1", "stage2"],
            "supported_lanes": [
                "template_requirements",
                "comprehensive_extraction",
            ],
            "supported_schemas": [
                "lane-output.schema.json",
                "template-requirements.schema.json",
                "template-requirements-summary.schema.json",
                "stage2-task-packet.v1",
            ],
            "max_parallel_tasks": 4,
            "version": "1.0.0",
        }

    def validate_output(
        self, output: dict, schema: str
    ) -> tuple[bool, list[str]]:
        """Validate OpenCode output."""
        errors = []

        if not isinstance(output, dict):
            errors.append("output_not_dict")
            return False, errors

        # OpenCode output validation
        if schema == "lane-output.schema.json":
            required = [
                "run_id",
                "task_packet_id",
                "chunk_id",
                "lane_id",
                "agent_role",
                "model_or_agent_identity",
                "output_status",
                "produced_at",
            ]
            for field in required:
                if field not in output:
                    errors.append(f"missing_required_field:{field}")

        return len(errors) == 0, errors

    def is_available(self) -> bool:
        """Check if OpenCode is available."""
        return True
