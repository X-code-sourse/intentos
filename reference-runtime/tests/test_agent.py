"""Tests for Agent Store and agent CLI commands."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.agent_store import AgentStore, Agent, AgentStoreError


class TestAgentStore:
    """AgentStore CRUD operations."""

    def test_create_agent(self, tmp_path: Path) -> None:
        """Creating an agent returns a valid agent with a unique ID."""
        db = tmp_path / "test_agents.db"
        store = AgentStore(str(db))
        agent = store.create(name="Test Agent", description="A test")

        assert agent.agent_id.startswith("agent_")
        assert agent.name == "Test Agent"
        assert agent.description == "A test"
        assert agent.created_at is not None

    def test_create_defaults(self, tmp_path: Path) -> None:
        """Creating an agent with only name works."""
        db = tmp_path / "test_agents2.db"
        store = AgentStore(str(db))
        agent = store.create(name="Default Agent")

        assert agent.agent_id.startswith("agent_")
        assert agent.name == "Default Agent"
        assert agent.description == ""

    def test_get_agent(self, tmp_path: Path) -> None:
        """Getting an agent by ID returns the correct agent."""
        db = tmp_path / "test_agents3.db"
        store = AgentStore(str(db))
        created = store.create(name="Get Test")
        fetched = store.get(created.agent_id)

        assert fetched is not None
        assert fetched.agent_id == created.agent_id
        assert fetched.name == "Get Test"

    def test_get_nonexistent(self, tmp_path: Path) -> None:
        """Getting a non-existent agent returns None."""
        db = tmp_path / "test_agents4.db"
        store = AgentStore(str(db))
        assert store.get("nonexistent") is None

    def test_list_agents(self, tmp_path: Path) -> None:
        """Listing agents returns all registered agents."""
        db = tmp_path / "test_agents5.db"
        store = AgentStore(str(db))

        # No agents
        assert store.list() == []

        # After creating some
        store.create(name="Agent A")
        store.create(name="Agent B")
        agents = store.list()
        assert len(agents) == 2
        names = [a.name for a in agents]
        assert "Agent A" in names
        assert "Agent B" in names

    def test_get_by_name(self, tmp_path: Path) -> None:
        """Getting an agent by name works."""
        db = tmp_path / "test_agents6.db"
        store = AgentStore(str(db))
        store.create(name="Unique Name")
        agent = store.get_by_name("Unique Name")
        assert agent is not None
        assert agent.name == "Unique Name"

    def test_delete_agent(self, tmp_path: Path) -> None:
        """Deleting an agent removes it."""
        db = tmp_path / "test_agents7.db"
        store = AgentStore(str(db))
        agent = store.create(name="Delete Me")
        assert store.get(agent.agent_id) is not None
        assert store.delete(agent.agent_id) is True
        assert store.get(agent.agent_id) is None

    def test_delete_nonexistent(self, tmp_path: Path) -> None:
        """Deleting a non-existent agent returns False."""
        db = tmp_path / "test_agents8.db"
        store = AgentStore(str(db))
        assert store.delete("nonexistent") is False

    def test_record_execution_updates_last_seen(self, tmp_path: Path) -> None:
        """record_execution updates the last_seen_at timestamp."""
        db = tmp_path / "test_agents9.db"
        store = AgentStore(str(db))
        agent = store.create(name="Seen Agent")
        assert agent.last_seen_at is not None

        store.record_execution(agent.agent_id)
        updated = store.get(agent.agent_id)
        assert updated is not None
        assert updated.last_seen_at is not None


class TestAgentCLI:
    """Tests for the agent CLI commands."""

    def _run_cmd(self, cmd_func: Any, **kwargs: Any) -> str:
        """Run a CLI command and capture output."""
        import io
        import sys
        from types import SimpleNamespace

        args = SimpleNamespace(**kwargs)
        stdout = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = stdout
        try:
            cmd_func(args)
        finally:
            sys.stdout = old_stdout
        return stdout.getvalue()

    def test_create_output(self) -> None:
        """Agent create command prints agent details."""
        from commands.agent import cmd_agent

        output = self._run_cmd(
            cmd_agent,
            agent_action="create",
            name="CLI Agent",
            description="Created from CLI",
        )
        assert "Agent Registered" in output
        assert "CLI Agent" in output
        assert "agent_" in output

    def test_list_output_empty(self) -> None:
        """Agent list shows message when no agents exist."""
        # Mock empty store
        with patch("commands.agent.AgentStore") as mock_store_cls:
            mock_store = MagicMock()
            mock_store.list.return_value = []
            mock_store_cls.return_value = mock_store

            from commands.agent import cmd_agent
            output = self._run_cmd(cmd_agent, agent_action="list")
            assert "No agents registered" in output

    def test_get_nonexistent(self) -> None:
        """Agent get for non-existent ID shows message."""
        from commands.agent import cmd_agent

        output = self._run_cmd(cmd_agent, agent_action="get", agent_id="nonexistent")
        assert "Agent not found" in output


class TestAgentProfile:
    """v0.6.0 - Agent persona, traits, avatar."""

    def test_create_with_persona(self, tmp_path):
        """Creating an agent with persona stores it."""
        db = tmp_path / "test_persona.db"
        store = AgentStore(str(db))
        agent = store.create(name="P Test", persona="Financial analyst")
        assert agent.persona == "Financial analyst"
        fetched = store.get(agent.agent_id)
        assert fetched is not None
        assert fetched.persona == "Financial analyst"

    def test_create_with_traits(self, tmp_path):
        """Creating an agent with traits stores them."""
        db = tmp_path / "test_traits.db"
        store = AgentStore(str(db))
        agent = store.create(name="T Test", traits=["cautious", "analytical"])
        assert agent.traits == ["cautious", "analytical"]
        fetched = store.get(agent.agent_id)
        assert fetched is not None
        assert fetched.traits == ["cautious", "analytical"]

    def test_create_with_avatar(self, tmp_path):
        """Creating an agent with avatar stores it."""
        db = tmp_path / "test_avatar.db"
        store = AgentStore(str(db))
        agent = store.create(name="A Test", avatar=":chart:")
        assert agent.avatar == ":chart:"

    def test_set_persona(self, tmp_path):
        """set_persona updates the agent's persona."""
        db = tmp_path / "test_set_p.db"
        store = AgentStore(str(db))
        agent = store.create(name="SP Test")
        assert agent.persona == ""

        store.set_persona(agent.agent_id, "Senior developer")
        fetched = store.get(agent.agent_id)
        assert fetched is not None
        assert fetched.persona == "Senior developer"

    def test_add_trait(self, tmp_path):
        """add_trait appends a trait."""
        db = tmp_path / "test_add_t.db"
        store = AgentStore(str(db))
        agent = store.create(name="AT Test", traits=["cautious"])
        store.add_trait(agent.agent_id, "analytical")
        fetched = store.get(agent.agent_id)
        assert fetched is not None
        assert "analytical" in fetched.traits
        assert "cautious" in fetched.traits

    def test_add_trait_duplicate(self, tmp_path):
        """Adding an already-present trait is a no-op."""
        db = tmp_path / "test_add_t_dup.db"
        store = AgentStore(str(db))
        agent = store.create(name="AD Test", traits=["cautious"])
        store.add_trait(agent.agent_id, "cautious")
        fetched = store.get(agent.agent_id)
        assert fetched is not None
        assert fetched.traits == ["cautious"]

    def test_remove_trait(self, tmp_path):
        """remove_trait removes a trait."""
        db = tmp_path / "test_rm_t.db"
        store = AgentStore(str(db))
        agent = store.create(name="RT Test", traits=["cautious", "analytical"])
        store.remove_trait(agent.agent_id, "cautious")
        fetched = store.get(agent.agent_id)
        assert fetched is not None
        assert fetched.traits == ["analytical"]

    def test_remove_trait_absent(self, tmp_path):
        """Removing a non-existent trait is a no-op."""
        db = tmp_path / "test_rm_t_abs.db"
        store = AgentStore(str(db))
        agent = store.create(name="RA Test", traits=["cautious"])
        store.remove_trait(agent.agent_id, "bold")
        fetched = store.get(agent.agent_id)
        assert fetched is not None
        assert fetched.traits == ["cautious"]

    def test_update_persona_via_update_agent(self, tmp_path):
        """update_agent with persona= kwarg works."""
        db = tmp_path / "test_up_p.db"
        store = AgentStore(str(db))
        agent = store.create(name="UP Test")
        store.update_agent(agent.agent_id, persona="New persona")
        fetched = store.get(agent.agent_id)
        assert fetched is not None
        assert fetched.persona == "New persona"

    def test_update_traits_via_update_agent(self, tmp_path):
        """update_agent with traits= kwarg replaces traits."""
        db = tmp_path / "test_up_t.db"
        store = AgentStore(str(db))
        agent = store.create(name="UT Test", traits=["old"])
        store.update_agent(agent.agent_id, traits=["new1", "new2"])
        fetched = store.get(agent.agent_id)
        assert fetched is not None
        assert fetched.traits == ["new1", "new2"]


class TestAgentPackage:
    """v0.7.0 - Agent export/import (.agent package)."""

    def test_export_basic(self, tmp_path):
        """Exporting an agent produces valid .agent JSON."""
        from core.agent_store import AgentStore
        from core.agent_package import export_agent

        db = tmp_path / "test_export.db"
        store = AgentStore(str(db))
        agent = store.create(name="Test Agent", persona="Analyst",
                             traits=["cautious"], avatar=":chart:")
        pkg = export_agent(agent.agent_id, db_path=str(db))

        assert pkg["spec_version"] == "1.0"
        assert pkg["format"] == "intent-os-agent-v1"
        assert pkg["identity"]["name"] == "Test Agent"
        assert pkg["identity"]["persona"] == "Analyst"
        assert pkg["identity"]["traits"] == ["cautious"]
        assert pkg["identity"]["avatar"] == ":chart:"

    def test_export_no_experiences(self, tmp_path):
        """Export works when agent has no experiences."""
        from core.agent_store import AgentStore
        from core.agent_package import export_agent

        db = tmp_path / "test_exp_empty.db"
        store = AgentStore(str(db))
        agent = store.create(name="No Exp Agent")
        pkg = export_agent(agent.agent_id, db_path=str(db))
        assert pkg["experiences"] == []

    def test_export_reputation_empty(self, tmp_path):
        """Export works when agent has no executions (reputation = zeros)."""
        from core.agent_store import AgentStore
        from core.agent_package import export_agent

        db = tmp_path / "test_rep_empty.db"
        store = AgentStore(str(db))
        agent = store.create(name="No Exec Agent")
        pkg = export_agent(agent.agent_id, db_path=str(db))
        assert pkg["reputation"]["total_executions"] == 0
        assert pkg["reputation"]["success_rate"] == 0.0

    def test_import_roundtrip(self, tmp_path):
        """Export then import creates a new agent with same identity."""
        from core.agent_store import AgentStore
        from core.agent_package import export_agent, import_agent

        db = tmp_path / "test_rt.db"
        store = AgentStore(str(db))
        agent = store.create(name="Roundtrip Agent", persona="Tester",
                             traits=["careful", "fast"], avatar=":bug:")

        pkg = export_agent(agent.agent_id, db_path=str(db))
        new_id = import_agent(pkg, db_path=str(db))

        # Verify new agent has same identity but different ID
        assert new_id != agent.agent_id
        new_agent = store.get(new_id)
        assert new_agent is not None
        assert new_agent.name == "Roundtrip Agent"
        assert new_agent.persona == "Tester"
        assert new_agent.traits == ["careful", "fast"]
        assert new_agent.avatar == ":bug:"

    def test_import_with_name_override(self, tmp_path):
        """Import with name_override changes the agent's name."""
        from core.agent_store import AgentStore
        from core.agent_package import export_agent, import_agent

        db = tmp_path / "test_name_ovr.db"
        store = AgentStore(str(db))
        agent = store.create(name="Original Name", persona="Worker")
        pkg = export_agent(agent.agent_id, db_path=str(db))

        new_id = import_agent(pkg, name_override="New Name", db_path=str(db))
        imported = store.get(new_id)
        assert imported is not None
        assert imported.name == "New Name"
        assert imported.persona == "Worker"

    def test_import_invalid_format(self, tmp_path):
        """Importing invalid data raises ValueError."""
        from core.agent_package import import_agent

        import pytest
        with pytest.raises(ValueError, match="Unsupported"):
            import_agent({"spec_version": "999"})

    def test_import_bad_format_field(self, tmp_path):
        """Importing wrong format value raises ValueError."""
        from core.agent_package import import_agent

        import pytest
        with pytest.raises(ValueError, match="Unknown"):
            import_agent({"spec_version": "1.0", "format": "unknown-format",
                          "identity": {"name": "x"}})

    def test_import_experiences(self, tmp_path):
        """Importing an agent with experiences preserves them."""
        from core.agent_store import AgentStore
        from core.experience_store import ExperienceStore
        from core.agent_package import import_agent

        pkg = {
            "spec_version": "1.0",
            "format": "intent-os-agent-v1",
            "exported_at": "2026-07-24T12:00:00Z",
            "identity": {"name": "Exp Agent", "persona": "Test"},
            "reputation": {},
            "experiences": [
                {"type": "failure_pattern", "observation": "API timed out",
                 "recommendation": "Retry with backoff", "confidence": 0.8},
                {"type": "success_strategy", "observation": "Use caching",
                 "recommendation": "Cache results for 5 min", "confidence": 0.6},
            ],
        }
        new_id = import_agent(pkg)
        exp_store = ExperienceStore()
        exps = exp_store.list(agent_id=new_id, limit=10)
        assert len(exps) == 2
        types = {e["type"] for e in exps}
        assert "failure_pattern" in types
        assert "success_strategy" in types
