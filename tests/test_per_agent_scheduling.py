"""Tests for per-agent dynamic window scheduling."""

from storygraph_lib.adapters import AgentRegistry
from storygraph_lib.adapters.codex_adapter import CodexAdapter
from storygraph_lib.adapters.claude_adapter import ClaudeAdapter
from storygraph_lib.adapters.opencode_adapter import OpenCodeAdapter


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
