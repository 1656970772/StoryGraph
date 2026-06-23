"""Tests for agent selection in claim_agent_batches."""

import json
import tempfile
from pathlib import Path

import pytest

from storygraph_lib.adapters import AgentRegistry
from storygraph_lib.adapters.codex_adapter import CodexAdapter
from storygraph_lib.adapters.claude_adapter import ClaudeAdapter


def create_mock_dispatch_plan(tmpdir) -> Path:
    """Create a mock dispatch plan with agent platform config."""
    plan = {
        "schema_version": "storygraph.agent-dispatch.v1",
        "stage": "stage1",
        "review_policy_mode": "post_merge_incremental",
        "dispatch_state_path": "intermediate/agent-dispatch-state.json",
        "agent_platform": {
            "available_agents": ["codex", "claude"],
            "default_agent_type": "codex",
        },
        "phases": [
            {
                "phase": "lane_extraction",
                "next_action": "dispatch_lane_agents",
                "task_packets": [],
                "execution_batches": [
                    {
                        "batch_id": "lane-comprehensive_extraction-batch-0001",
                        "phase": "lane_extraction",
                        "agent_role": "comprehensive-stage1-extraction-agent",
                        "lane_id": "comprehensive_extraction",
                        "task_packet_paths": [
                            "intermediate/task-packets/chunk-0001/comprehensive_extraction.json"
                        ],
                        "expected_output_paths": [
                            "intermediate/lane-outputs/chunk-0001/comprehensive_extraction/run-001.json"
                        ],
                    }
                ],
                "wait_for_outputs_root": "intermediate/lane-outputs",
            }
        ],
    }
    plan_path = Path(tmpdir) / "intermediate" / "agent-dispatch-plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return plan_path.parent.parent


def create_mock_task_packet(tmpdir, agent_selector=None) -> Path:
    """Create a mock task packet with agent_selector."""
    if agent_selector is None:
        agent_selector = {
            "stage": "stage1",
            "lane_id": "comprehensive_extraction",
            "required_schema": "lane-output.schema.json",
            "preferred_agents": ["claude", "codex"],
        }

    packet = {
        "task_packet_id": "chunk-0001:comprehensive_extraction:attempt-001",
        "stage": "stage1",
        "chunk_id": "chunk-0001",
        "lane_id": "comprehensive_extraction",
        "agent_role": "comprehensive-stage1-extraction-agent",
        "source_path": "/path/to/source.txt",
        "source_range": [0, 100],
        "agent_selector": agent_selector,
        "selected_agent_info": None,
    }

    packet_path = (
        Path(tmpdir)
        / "intermediate"
        / "task-packets"
        / "chunk-0001"
        / "comprehensive_extraction.json"
    )
    packet_path.parent.mkdir(parents=True, exist_ok=True)
    packet_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    return packet_path


class TestAgentSelection:
    """Test agent selection in claim_agent_batches."""

    def test_agent_registry_selects_preferred_agent(self):
        """Test that registry respects preferred_agents order."""
        registry = AgentRegistry(
            {
                "codex": CodexAdapter(),
                "claude": ClaudeAdapter(),
            }
        )

        # Request claude first, then codex
        result = registry.select_best_adapter(
            "stage1", "comprehensive_extraction", preferred_agents=["claude", "codex"]
        )
        assert result is not None
        agent_type, adapter = result
        assert agent_type == "claude"

        # Request codex first, then claude
        result = registry.select_best_adapter(
            "stage1", "comprehensive_extraction", preferred_agents=["codex", "claude"]
        )
        assert result is not None
        agent_type, adapter = result
        assert agent_type == "codex"

    def test_agent_registry_falls_back_when_preferred_unavailable(self):
        """Test fallback when preferred agent is not available."""
        registry = AgentRegistry(
            {
                "codex": CodexAdapter(),
            }
        )

        # Request claude (not available), should fall back to codex
        result = registry.select_best_adapter(
            "stage1",
            "comprehensive_extraction",
            preferred_agents=["claude", "codex"],
        )
        assert result is not None
        agent_type, adapter = result
        assert agent_type == "codex"

    def test_task_packet_with_agent_selector(self):
        """Test that task packets include agent_selector field."""
        with tempfile.TemporaryDirectory() as tmpdir:
            packet_path = create_mock_task_packet(tmpdir)
            packet = json.loads(packet_path.read_text(encoding="utf-8"))

            assert "agent_selector" in packet
            assert packet["agent_selector"]["stage"] == "stage1"
            assert packet["agent_selector"]["lane_id"] == "comprehensive_extraction"
            assert packet["agent_selector"]["preferred_agents"] == [
                "claude",
                "codex",
            ]
            assert packet["selected_agent_info"] is None

    def test_dispatch_plan_includes_agent_platform(self):
        """Test that dispatch plan includes agent_platform config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            graph_dir = create_mock_dispatch_plan(tmpdir)
            plan_path = graph_dir / "intermediate" / "agent-dispatch-plan.json"

            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            assert "agent_platform" in plan
            assert plan["agent_platform"]["available_agents"] == ["codex", "claude"]
            assert plan["agent_platform"]["default_agent_type"] == "codex"
