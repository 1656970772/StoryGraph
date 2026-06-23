"""Codex agent adapter for StoryGraph."""

from .base import AgentAdapter, AgentCapabilities


class CodexAdapter(AgentAdapter):
    """Adapter for Codex agent - current primary agent."""

    def get_capabilities(self) -> AgentCapabilities:
        """Get Codex capabilities."""
        return {
            "agent_type": "codex",
            "supported_stages": ["stage1", "stage2"],
            "supported_lanes": [],
            "supported_schemas": [
                "lane-output.schema.json",
                "template-requirements.schema.json",
                "template-requirements-summary.schema.json",
                "stage2-task-packet.v1",
            ],
            "max_parallel_tasks": 6,
            "version": "1.0.0",
        }

    def validate_output(
        self, output: dict, schema: str
    ) -> tuple[bool, list[str]]:
        """Validate Codex output.

        For now, Codex uses the existing validation in lane_outputs.py.
        This method is a pass-through that returns success.
        Future: Add Codex-specific validation rules.
        """
        errors = []

        # Basic structure check
        if not isinstance(output, dict):
            errors.append("output_not_dict")
            return False, errors

        # Check required fields based on schema
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

        elif schema == "template-requirements.schema.json":
            if "templates" not in output:
                errors.append("missing_required_field:templates")

        elif schema == "stage2-task-packet.v1":
            required = ["batch_id", "agent_role", "templates"]
            for field in required:
                if field not in output:
                    errors.append(f"missing_required_field:{field}")

        return len(errors) == 0, errors

    def is_available(self) -> bool:
        """Check if Codex is available.

        Returns True for now. In future, could check API connectivity,
        environment variables, etc.
        """
        return True
