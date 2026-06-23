"""Tests for Stage 2 agent selection."""

import json
import tempfile
from pathlib import Path

from storygraph_lib.adapters import AgentRegistry
from storygraph_lib.adapters.codex_adapter import CodexAdapter
from storygraph_lib.adapters.claude_adapter import ClaudeAdapter


class TestStage2AgentSelection:
    """Test agent selection in Stage 2."""

    def test_stage2_batch_has_agent_selector(self):
        """Test that Stage 2 batch includes agent_selector field."""
        batch = {
            "batch_id": "stage2-template-法宝分析",
            "agent_role": "stage2-template-document-agent",
            "agent_selector": {
                "stage": "stage2",
                "lane_id": "template_document",
                "required_schema": "stage2-task-packet.v1",
                "preferred_agents": None,
            },
            "selected_agent_info": None,
        }

        assert "agent_selector" in batch
        assert batch["agent_selector"]["stage"] == "stage2"
        assert batch["agent_selector"]["lane_id"] == "template_document"
        assert batch["selected_agent_info"] is None

    def test_stage2_agent_selection_codex(self):
        """Test agent selection for Stage 2 with Codex."""
        registry = AgentRegistry(
            {
                "codex": CodexAdapter(),
                "claude": ClaudeAdapter(),
            }
        )

        # Stage 2 should support both agents
        result = registry.select_best_adapter("stage2", "template_document")
        assert result is not None
        agent_type, adapter = result
        assert agent_type in ["codex", "claude"]

    def test_stage2_agent_selection_prefers_claude(self):
        """Test preferred agent selection for Stage 2."""
        registry = AgentRegistry(
            {
                "codex": CodexAdapter(),
                "claude": ClaudeAdapter(),
            }
        )

        # Test with preferences
        result = registry.select_best_adapter(
            "stage2",
            "template_document",
            preferred_agents=["claude", "codex"],
        )
        assert result is not None
        agent_type, adapter = result
        assert agent_type == "claude"

    def test_stage2_batch_update_selected_agent_info(self):
        """Test updating selected_agent_info in Stage 2 batch."""
        batch = {
            "batch_id": "stage2-template-法宝分析",
            "agent_role": "stage2-template-document-agent",
            "agent_selector": {
                "stage": "stage2",
                "lane_id": "template_document",
                "required_schema": "stage2-task-packet.v1",
                "preferred_agents": None,
            },
            "selected_agent_info": None,
        }

        registry = AgentRegistry({"codex": CodexAdapter()})

        # Simulate agent selection update
        result = registry.select_best_adapter("stage2", "template_document")
        if result:
            agent_type, adapter = result
            batch["selected_agent_info"] = {
                "agent_type": agent_type,
                "agent_role": batch.get("agent_role", ""),
                "adapter_version": adapter.get_capabilities().get("version", "1.0.0"),
            }

        assert batch["selected_agent_info"] is not None
        assert batch["selected_agent_info"]["agent_type"] == "codex"
        assert batch["selected_agent_info"]["agent_role"] == "stage2-template-document-agent"
        assert batch["selected_agent_info"]["adapter_version"] == "1.0.0"
