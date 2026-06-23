"""Tests for agent adapter framework."""

import pytest

from storygraph_lib.adapters import AgentRegistry
from storygraph_lib.adapters.base import AgentAdapter, AgentCapabilities
from storygraph_lib.adapters.codex_adapter import CodexAdapter
from storygraph_lib.adapters.claude_adapter import ClaudeAdapter
from storygraph_lib.adapters.opencode_adapter import OpenCodeAdapter
from storygraph_lib.config import load_agent_adapters


class TestAgentCapabilities:
    """Test AgentCapabilities type."""

    def test_codex_capabilities(self):
        adapter = CodexAdapter()
        caps = adapter.get_capabilities()
        assert caps["agent_type"] == "codex"
        assert "stage1" in caps["supported_stages"]
        assert "stage2" in caps["supported_stages"]
        assert "lane-output.schema.json" in caps["supported_schemas"]
        assert caps["max_parallel_tasks"] == 6

    def test_claude_capabilities(self):
        adapter = ClaudeAdapter()
        caps = adapter.get_capabilities()
        assert caps["agent_type"] == "claude"
        assert "stage1" in caps["supported_stages"]

    def test_opencode_capabilities(self):
        adapter = OpenCodeAdapter()
        caps = adapter.get_capabilities()
        assert caps["agent_type"] == "opencode"
        assert caps["max_parallel_tasks"] == 4


class TestAgentRegistry:
    """Test AgentRegistry."""

    def test_register_adapter(self):
        registry = AgentRegistry()
        adapter = CodexAdapter()
        registry.register_adapter("codex", adapter)
        assert registry.get_adapter("codex") is adapter

    def test_get_adapter_not_found(self):
        registry = AgentRegistry()
        assert registry.get_adapter("nonexistent") is None

    def test_initialize_with_adapters(self):
        adapters = {
            "codex": CodexAdapter(),
            "claude": ClaudeAdapter(),
        }
        registry = AgentRegistry(adapters)
        assert registry.get_adapter("codex") is not None
        assert registry.get_adapter("claude") is not None

    def test_list_agents(self):
        registry = AgentRegistry({
            "codex": CodexAdapter(),
            "claude": ClaudeAdapter(),
        })
        agents = registry.list_agents()
        assert "codex" in agents
        assert "claude" in agents

    def test_get_available_adapters_stage1(self):
        registry = AgentRegistry({
            "codex": CodexAdapter(),
            "claude": ClaudeAdapter(),
        })
        available = registry.get_available_adapters("stage1")
        assert len(available) == 2
        assert all(agent_type in ["codex", "claude"] for agent_type, _ in available)

    def test_get_available_adapters_with_lane(self):
        registry = AgentRegistry({
            "codex": CodexAdapter(),
            "claude": ClaudeAdapter(),
        })
        available = registry.get_available_adapters(
            "stage1", "comprehensive_extraction"
        )
        assert len(available) == 2

    def test_select_best_adapter_auto(self):
        registry = AgentRegistry({
            "codex": CodexAdapter(),
            "claude": ClaudeAdapter(),
        })
        result = registry.select_best_adapter("stage1")
        assert result is not None
        agent_type, adapter = result
        assert agent_type in ["codex", "claude"]

    def test_select_best_adapter_with_preferences(self):
        registry = AgentRegistry({
            "codex": CodexAdapter(),
            "claude": ClaudeAdapter(),
        })
        result = registry.select_best_adapter(
            "stage1", preferred_agents=["claude", "codex"]
        )
        assert result is not None
        agent_type, adapter = result
        assert agent_type == "claude"

    def test_select_best_adapter_no_available(self):
        registry = AgentRegistry()
        result = registry.select_best_adapter("nonexistent_stage")
        assert result is None

    def test_get_capabilities(self):
        registry = AgentRegistry({"codex": CodexAdapter()})
        caps = registry.get_capabilities("codex")
        assert caps is not None
        assert caps["agent_type"] == "codex"


class TestAgentValidation:
    """Test agent output validation."""

    def test_codex_validate_lane_output_valid(self):
        adapter = CodexAdapter()
        output = {
            "run_id": "run-001",
            "task_packet_id": "chunk-001:lane:attempt-001",
            "chunk_id": "chunk-001",
            "lane_id": "comprehensive_extraction",
            "agent_role": "agent",
            "model_or_agent_identity": "codex",
            "output_status": "completed",
            "produced_at": "2026-01-01T00:00:00Z",
            "extracted_nodes": [],
            "extracted_edges": [],
            "extracted_events": [],
            "extracted_evidence": [],
            "supports_templates": [],
            "uncertainties": [],
            "rejected_candidates": [],
            "structured_failures": [],
        }
        ok, errors = adapter.validate_output(output, "lane-output.schema.json")
        assert ok is True
        assert len(errors) == 0

    def test_codex_validate_lane_output_missing_field(self):
        adapter = CodexAdapter()
        output = {
            "run_id": "run-001",
            "task_packet_id": "chunk-001:lane:attempt-001",
            # Missing chunk_id
        }
        ok, errors = adapter.validate_output(output, "lane-output.schema.json")
        assert ok is False
        assert any("chunk_id" in err for err in errors)

    def test_codex_validate_output_not_dict(self):
        adapter = CodexAdapter()
        ok, errors = adapter.validate_output("not a dict", "lane-output.schema.json")
        assert ok is False
        assert "output_not_dict" in errors


class TestConfigLoading:
    """Test config loading with agent adapters."""

    def test_load_agent_adapters_default_config(self, tmp_path):
        config = {
            "agent_platform": {
                "enabled": True,
                "agent_adapters": {
                    "codex": {
                        "module": "storygraph_lib.adapters.codex_adapter",
                        "class": "CodexAdapter",
                        "config": {},
                    },
                    "claude": {
                        "module": "storygraph_lib.adapters.claude_adapter",
                        "class": "ClaudeAdapter",
                        "config": {},
                    },
                },
            }
        }
        registry = load_agent_adapters(config)
        assert registry.get_adapter("codex") is not None
        assert registry.get_adapter("claude") is not None

    def test_load_agent_adapters_disabled(self):
        config = {
            "agent_platform": {
                "enabled": False,
            }
        }
        registry = load_agent_adapters(config)
        assert len(registry.list_agents()) == 0

    def test_load_agent_adapters_missing_config(self):
        config = {}
        registry = load_agent_adapters(config)
        # Should return empty registry, not error
        assert isinstance(registry, AgentRegistry)

    def test_load_agent_adapters_invalid_module(self):
        config = {
            "agent_platform": {
                "enabled": True,
                "agent_adapters": {
                    "bad": {
                        "module": "nonexistent.module",
                        "class": "BadAdapter",
                        "config": {},
                    }
                },
            }
        }
        with pytest.raises(ValueError, match="Failed to load agent adapter"):
            load_agent_adapters(config)

    def test_load_agent_adapters_missing_module_or_class(self):
        config = {
            "agent_platform": {
                "enabled": True,
                "agent_adapters": {
                    "bad": {
                        "class": "NoModule",
                        "config": {},
                    }
                },
            }
        }
        with pytest.raises(ValueError, match="missing module or class name"):
            load_agent_adapters(config)
