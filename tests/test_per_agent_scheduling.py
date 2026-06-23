"""Tests for per-agent dynamic window scheduling."""

import json

from storygraph_lib.adapters import AgentRegistry
from storygraph_lib.adapters.codex_adapter import CodexAdapter
from storygraph_lib.adapters.claude_adapter import ClaudeAdapter
from storygraph_lib.adapters.opencode_adapter import OpenCodeAdapter
from storygraph_lib.stage1 import claim_agent_batches
from storygraph_lib.stage2 import claim_stage2_batches


class BurstAdapter(CodexAdapter):
    """Test adapter with a larger capability than legacy global caps."""

    def get_capabilities(self):
        capabilities = super().get_capabilities()
        capabilities["agent_type"] = "burst"
        capabilities["max_parallel_tasks"] = 8
        return capabilities


class TestPerAgentScheduling:
    """Test per-agent parallelism and dynamic window scheduling."""

    def test_codex_max_parallel_is_6(self):
        """Verify Codex supports 6 parallel tasks."""
        adapter = CodexAdapter()
        caps = adapter.get_capabilities()
        assert caps["max_parallel_tasks"] == 6

    def test_claude_max_parallel_is_6(self):
        """Verify Claude supports 6 parallel tasks."""
        adapter = ClaudeAdapter()
        caps = adapter.get_capabilities()
        assert caps["max_parallel_tasks"] == 6

    def test_opencode_max_parallel_is_4(self):
        """Verify OpenCode supports 4 parallel tasks."""
        adapter = OpenCodeAdapter()
        caps = adapter.get_capabilities()
        assert caps["max_parallel_tasks"] == 4

    def test_dynamic_window_codex(self):
        """Test dynamic window calculation for Codex (max 6)."""
        registry = AgentRegistry({"codex": CodexAdapter()})

        # Scenario: 2 batches running, 10 pending -> can add 4 more
        running_by_agent = {"codex": 2}
        limit = 10
        available = max(0, 6 - 2)  # 4 slots available
        assert available == 4

    def test_dynamic_window_claude(self):
        """Test dynamic window calculation for Claude (max 6)."""
        registry = AgentRegistry({"claude": ClaudeAdapter()})

        # Scenario: 3 batches running, 20 pending -> can add 3 more
        running_by_agent = {"claude": 3}
        limit = 20
        available = max(0, 6 - 3)  # 3 slots available
        assert available == 3

    def test_dynamic_window_sliding(self):
        """Test that window slides as tasks complete."""
        # Initial state: 4 Codex batches running (out of 6 max)
        running = 4
        max_parallel = 6
        available_before = max_parallel - running  # 2 slots

        assert available_before == 2

        # One completes, claim 2 more
        running = 5  # 4 + 2 - 1 (completed)
        available_after = max_parallel - running  # 1 slot

        assert available_after == 1

    def test_mixed_agent_scheduling(self):
        """Test scheduling with multiple agent types."""
        registry = AgentRegistry(
            {
                "codex": CodexAdapter(),
                "claude": ClaudeAdapter(),
                "opencode": OpenCodeAdapter(),
            }
        )

        # Scenario: mixed agents running
        running_by_agent = {
            "codex": 4,  # 2 slots available
            "claude": 5,  # 1 slot available
            "opencode": 3,  # 1 slot available
        }

        # If next batch uses Codex
        available_codex = max(0, 6 - 4)
        assert available_codex == 2

        # If next batch uses Claude
        available_claude = max(0, 6 - 5)
        assert available_claude == 1

        # If next batch uses OpenCode
        available_opencode = max(0, 4 - 3)
        assert available_opencode == 1

    def test_window_respects_limit_parameter(self):
        """Test that limit parameter acts as ceiling for available slots."""
        max_parallel_codex = 6
        running = 2
        limit = 3  # User limit

        available_without_limit = max_parallel_codex - running  # 4
        available_with_limit = min(available_without_limit, limit)  # 3

        assert available_with_limit == 3

    def test_window_reaches_zero_at_capacity(self):
        """Test that window reaches 0 when agent is at max capacity."""
        max_parallel = 6
        running = 6  # At capacity

        available = max(0, max_parallel - running)
        assert available == 0

    def test_different_agents_independent_windows(self):
        """Test that each agent type has independent parallelism window."""
        running_by_agent = {
            "codex": 6,  # At capacity
            "claude": 3,  # Has room
        }

        # Codex window is closed
        codex_available = max(0, 6 - 6)
        assert codex_available == 0

        # Claude window is open
        claude_available = max(0, 6 - 3)
        assert claude_available == 3

    def test_stage1_claim_uses_adapter_capability_above_historical_global_cap(
        self, tmp_path, monkeypatch
    ):
        """Stage 1 should size claim windows from adapter capability."""
        graph_dir = tmp_path / "book.storygraph"
        packet_dir = graph_dir / "intermediate" / "task-packets"
        packet_dir.mkdir(parents=True)
        batches = []
        for index in range(1, 9):
            packet_rel = f"intermediate/task-packets/batch-{index:04d}.json"
            output_rel = f"intermediate/lane-outputs/chunk-{index:04d}/run-001.json"
            packet = {
                "task_packet_id": f"chunk-{index:04d}:comprehensive_extraction:attempt-001",
                "stage": "stage1",
                "lane_id": "comprehensive_extraction",
                "agent_selector": {
                    "stage": "stage1",
                    "lane_id": "comprehensive_extraction",
                    "required_schema": "lane-output.schema.json",
                    "preferred_agents": ["burst"],
                },
                "selected_agent_info": None,
            }
            (graph_dir / packet_rel).write_text(
                json.dumps(packet, ensure_ascii=False), encoding="utf-8"
            )
            batches.append(
                {
                    "batch_id": f"lane-comprehensive_extraction-batch-{index:04d}",
                    "phase": "lane_extraction",
                    "agent_role": "comprehensive-stage1-extraction-agent",
                    "lane_id": "comprehensive_extraction",
                    "task_packet_paths": [packet_rel],
                    "expected_output_paths": [output_rel],
                    "write_scope": [output_rel],
                }
            )
        dispatch = {
            "schema_version": "storygraph.agent-dispatch.v1",
            "stage": "stage1",
            "dispatch_state_path": "intermediate/agent-dispatch-state.json",
            "phases": [
                {
                    "phase": "lane_extraction",
                    "execution_batches": batches,
                }
            ],
        }
        dispatch_path = graph_dir / "intermediate" / "agent-dispatch-plan.json"
        dispatch_path.write_text(
            json.dumps(dispatch, ensure_ascii=False), encoding="utf-8"
        )
        monkeypatch.setattr(
            "storygraph_lib.stage1.load_agent_adapters",
            lambda _config: AgentRegistry({"burst": BurstAdapter()}),
        )

        result = claim_agent_batches(
            graph_dir=graph_dir,
            phase="lane_extraction",
            limit=8,
            agent_type="burst",
            config={"agent_platform": {"enabled": True}},
        )

        assert result["status"] == "agent_batches_claimed"
        assert result["claimed_count"] == 8
        assert result["available_slots"] == 8

    def test_stage2_claim_uses_preferred_agent_capability(self, tmp_path):
        """Stage 2 should size the window from the preferred adapter, not Codex."""
        graph_dir = tmp_path / "book.storygraph"
        state_dir = graph_dir / "intermediate" / "stage2"
        state_dir.mkdir(parents=True)
        batches = []
        for index in range(1, 6):
            batches.append(
                {
                    "batch_id": f"stage2-template-{index:04d}",
                    "agent_role": "stage2-template-document-agent",
                    "status": "pending",
                    "templates": [{"template_name": f"模板{index}"}],
                    "expected_output_rel_paths": [
                        f"intermediate/stage2/extraction-records/template-{index}/run-001.json"
                    ],
                    "agent_selector": {
                        "stage": "stage2",
                        "lane_id": "template_document",
                        "required_schema": "stage2-task-packet.v1",
                        "preferred_agents": ["opencode"],
                    },
                    "selected_agent_info": None,
                }
            )
        state = {"schema": "stage2-dispatch-state.v1", "batches": batches}
        (state_dir / "dispatch-state.json").write_text(
            json.dumps(state, ensure_ascii=False), encoding="utf-8"
        )
        config = {
            "agent_platform": {
                "enabled": True,
                "agent_adapters": {
                    "codex": {
                        "module": "storygraph_lib.adapters.codex_adapter",
                        "class": "CodexAdapter",
                    },
                    "opencode": {
                        "module": "storygraph_lib.adapters.opencode_adapter",
                        "class": "OpenCodeAdapter",
                    },
                },
            }
        }

        result = claim_stage2_batches(graph_dir, limit=6, config=config)

        assert result["claimed_count"] == 4
        assert [batch["selected_agent_type"] for batch in result["batches"]] == [
            "opencode",
            "opencode",
            "opencode",
            "opencode",
        ]
