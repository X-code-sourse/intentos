"""Tests for Capability Context (SPEC-0010 Layer 2)."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.event_store import EventStore
from core.capability_context import (
    CapabilityProfile,
    ProvenPattern,
    compute_capability_profile,
    _level_from_stats,
)


def _init_db(db_path: Path) -> None:
    """Create the execution_records table via EventStore init."""
    EventStore(str(db_path))


def _seed(db_path: Path, agent_id: str, manifest: str,
          status: str = "success", cost: float = 0.1,
          tokens: int = 1000, runtime: str = "claude") -> None:
    """Insert a row into execution_records for testing."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """INSERT INTO execution_records
               (trace_id, spec_version, manifest_name, manifest_version,
                runtime_id, adapter, adapter_version, status,
                total_cost_usd, total_tokens, agent_id, created_at)
               VALUES (?, '1.0', ?, '1.0', ?, 'test', '1.0', ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                manifest,
                runtime,
                status,
                cost,
                tokens,
                agent_id,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


class TestCapabilityContext:
    """compute_capability_profile aggregation."""

    def test_empty_agent(self, tmp_path: Path) -> None:
        db = tmp_path / "test_empty.db"
        profiles = compute_capability_profile("agent_nonexistent", db_path=str(db))
        assert profiles == []

    def test_single_capability(self, tmp_path: Path) -> None:
        db = tmp_path / "test_single.db"
        _init_db(db)
        _seed(db, "agent_test", "financial_analysis", "success")
        _seed(db, "agent_test", "financial_analysis", "success")
        _seed(db, "agent_test", "financial_analysis", "failure")
        profiles = compute_capability_profile("agent_test", db_path=str(db))
        assert len(profiles) == 1
        p = profiles[0]
        assert p.name == "financial_analysis"
        assert p.total_tasks == 3
        assert p.success_rate == pytest.approx(2 / 3, rel=1e-4)

    def test_multiple_capabilities(self, tmp_path: Path) -> None:
        db = tmp_path / "test_multi.db"
        _init_db(db)
        for _ in range(10):
            _seed(db, "agent_test", "earnings_analysis", "success")
        for _ in range(3):
            _seed(db, "agent_test", "dcf_valuation", "success")
        profiles = compute_capability_profile("agent_test", db_path=str(db))
        assert len(profiles) == 2
        names = {p.name for p in profiles}
        assert "earnings_analysis" in names
        assert "dcf_valuation" in names

    def test_success_rate(self, tmp_path: Path) -> None:
        db = tmp_path / "test_rate.db"
        _init_db(db)
        for _ in range(8):
            _seed(db, "agent_test", "analysis", "success")
        _seed(db, "agent_test", "analysis", "failure")
        _seed(db, "agent_test", "analysis", "failure")
        profiles = compute_capability_profile("agent_test", db_path=str(db))
        assert len(profiles) == 1
        assert profiles[0].success_rate == pytest.approx(0.8, rel=1e-4)

    def test_below_minimum_samples(self, tmp_path: Path) -> None:
        db = tmp_path / "test_min.db"
        _init_db(db)
        _seed(db, "agent_test", "rare_task", "success")
        _seed(db, "agent_test", "rare_task", "success")
        profiles = compute_capability_profile("agent_test", db_path=str(db), min_samples=3)
        assert len(profiles) == 0

    def test_cost_and_tokens(self, tmp_path: Path) -> None:
        db = tmp_path / "test_cost.db"
        _init_db(db)
        for _ in range(3):
            _seed(db, "agent_test", "analysis", "success", cost=0.5, tokens=5000)
        profiles = compute_capability_profile("agent_test", db_path=str(db))
        assert len(profiles) == 1
        p = profiles[0]
        assert p.total_cost_usd == pytest.approx(1.5, rel=1e-4)
        assert p.total_tokens == 15000

    def test_preferred_models(self, tmp_path: Path) -> None:
        db = tmp_path / "test_model.db"
        _init_db(db)
        for _ in range(5):
            _seed(db, "agent_test", "analysis", runtime="claude-sonnet-4")
        for _ in range(3):
            _seed(db, "agent_test", "analysis", runtime="gpt-4o")
        profiles = compute_capability_profile("agent_test", db_path=str(db))
        assert len(profiles) == 1
        assert "claude-sonnet-4" in profiles[0].preferred_models

    def test_different_agents_isolated(self, tmp_path: Path) -> None:
        db = tmp_path / "test_iso.db"
        _init_db(db)
        for _ in range(10):
            _seed(db, "agent_a", "analysis", "success")
        for _ in range(10):
            _seed(db, "agent_b", "research", "success")
        profiles_a = compute_capability_profile("agent_a", db_path=str(db))
        profiles_b = compute_capability_profile("agent_b", db_path=str(db))
        assert len(profiles_a) == 1
        assert profiles_a[0].name == "analysis"
        assert profiles_b[0].name == "research"


class TestLevelFromStats:
    """_level_from_stats proficiency classification."""

    def test_expert(self) -> None:
        assert _level_from_stats(1000, 0.95) == "expert"

    def test_proficient(self) -> None:
        assert _level_from_stats(100, 0.85) == "proficient"

    def test_practitioner(self) -> None:
        assert _level_from_stats(10, 0.70) == "practitioner"

    def test_low_tasks_expert_rate(self) -> None:
        assert _level_from_stats(5, 1.0) == "practitioner"


class TestProvenPattern:
    """ProvenPattern dataclass."""

    def test_create_pattern(self) -> None:
        p = ProvenPattern(task_type="earnings_analysis", success_rate=0.94, sample_count=850)
        assert p.task_type == "earnings_analysis"
        assert p.success_rate == 0.94
        assert p.sample_count == 850

    def test_defaults(self) -> None:
        p = ProvenPattern(task_type="test")
        assert p.success_rate == 0.0
        assert p.sample_count == 0


class TestCapabilityProfile:
    """CapabilityProfile dataclass."""

    def test_create_profile(self) -> None:
        p = CapabilityProfile(name="analysis", level="expert", total_tasks=500)
        assert p.name == "analysis"
        assert p.level == "expert"
        assert p.total_tasks == 500

    def test_with_patterns(self) -> None:
        patterns = [
            ProvenPattern(task_type="earnings", success_rate=0.9, sample_count=100),
            ProvenPattern(task_type="dcf", success_rate=0.8, sample_count=50),
        ]
        p = CapabilityProfile(name="finance", proven_patterns=patterns)
        assert len(p.proven_patterns) == 2
        assert p.proven_patterns[0].task_type == "earnings"
