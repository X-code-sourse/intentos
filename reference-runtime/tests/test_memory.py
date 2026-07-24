"""Tests for memory management (prune, conflict resolution, scoring)."""
from __future__ import annotations

from pathlib import Path

import pytest


class TestMemoryScore:
    """compute_memory_score() scoring."""

    def test_high_confidence_high_score(self) -> None:
        from core.experience_store import ExperienceStore
        score = ExperienceStore.compute_memory_score(0.9, 10, "2026-07-24T12:00:00")
        assert score > 0.5

    def test_low_confidence_low_score(self) -> None:
        from core.experience_store import ExperienceStore
        score = ExperienceStore.compute_memory_score(0.1, 0, "2025-01-01T12:00:00")
        assert score < 0.5

    def test_old_experience_not_higher(self) -> None:
        from core.experience_store import ExperienceStore
        newer = ExperienceStore.compute_memory_score(0.5, 0, "2026-07-23T12:00:00")
        older = ExperienceStore.compute_memory_score(0.5, 0, "2025-01-01T12:00:00")
        assert newer >= older

    def test_high_usage_increases_score(self) -> None:
        from core.experience_store import ExperienceStore
        low_use = ExperienceStore.compute_memory_score(0.5, 0, "2026-07-24T12:00:00")
        high_use = ExperienceStore.compute_memory_score(0.5, 20, "2026-07-24T12:00:00")
        assert high_use > low_use


class TestConflictResolution:
    """ExperienceStore.create() replaces lower-confidence experiences."""

    def test_create_replaces_lower_confidence(self, tmp_path: Path) -> None:
        from core.experience_store import ExperienceStore
        db = tmp_path / "test_cr1.db"
        store = ExperienceStore(str(db))
        store.create(agent_id="agent_test", type="failure_pattern",
                     observation="Old version", confidence=0.3,
                     structured_trigger="timeout error")
        store.create(agent_id="agent_test", type="failure_pattern",
                     observation="New better version", confidence=0.9,
                     structured_trigger="timeout error")
        results = store.list(agent_id="agent_test", limit=10)
        assert len(results) == 1
        assert results[0]["observation"] == "New better version"

    def test_create_keeps_higher_confidence(self, tmp_path: Path) -> None:
        from core.experience_store import ExperienceStore
        db = tmp_path / "test_cr2.db"
        store = ExperienceStore(str(db))
        store.create(agent_id="agent_test", type="failure_pattern",
                     observation="Better old version", confidence=0.9,
                     structured_trigger="rate limit error")
        store.create(agent_id="agent_test", type="failure_pattern",
                     observation="Worse new version", confidence=0.3,
                     structured_trigger="rate limit error")
        results = store.list(agent_id="agent_test", limit=10)
        assert len(results) == 1
        assert results[0]["confidence"] == 0.9

    def test_different_triggers_both_kept(self, tmp_path: Path) -> None:
        from core.experience_store import ExperienceStore
        db = tmp_path / "test_cr3.db"
        store = ExperienceStore(str(db))
        store.create(agent_id="agent_test", type="failure_pattern",
                     observation="Timeout error", confidence=0.7,
                     structured_trigger="timeout")
        store.create(agent_id="agent_test", type="success_strategy",
                     observation="DCF method", confidence=0.8,
                     structured_trigger="valuation")
        results = store.list(agent_id="agent_test", limit=10)
        assert len(results) == 2

    def test_no_trigger_does_not_conflict(self, tmp_path: Path) -> None:
        from core.experience_store import ExperienceStore
        db = tmp_path / "test_cr4.db"
        store = ExperienceStore(str(db))
        store.create(agent_id="agent_test", type="failure_pattern",
                     observation="First", confidence=0.3)
        store.create(agent_id="agent_test", type="failure_pattern",
                     observation="Second", confidence=0.9)
        results = store.list(agent_id="agent_test", limit=10)
        assert len(results) == 2


class TestPrune:
    """prune() removes low-value experiences."""

    def test_prune_below_min_score(self, tmp_path: Path) -> None:
        from core.experience_store import ExperienceStore
        db = tmp_path / "test_pr1.db"
        store = ExperienceStore(str(db))
        for i in range(3):
            store.create(agent_id="agent_test", type="failure_pattern",
                         observation=f"High {i}", confidence=0.9,
                         structured_trigger=f"trig_h{i}")
        for i in range(7):
            store.create(agent_id="agent_test", type="failure_pattern",
                         observation=f"Low {i}", confidence=0.05,
                         structured_trigger=f"trig_l{i}")
        result = store.prune("agent_test", keep=3, min_score=0.4, dry_run=True)
        assert result["deleted"] >= 5

    def test_prune_keeps_top_n(self, tmp_path: Path) -> None:
        from core.experience_store import ExperienceStore
        db = tmp_path / "test_pr2.db"
        store = ExperienceStore(str(db))
        for i in range(10):
            store.create(agent_id="agent_test", type="failure_pattern",
                         observation=f"Exp {i}", confidence=0.3 + i * 0.06,
                         structured_trigger=f"trig_{i}")
        result = store.prune("agent_test", keep=3, min_score=0.6, dry_run=True)
        assert result["kept"] <= 6

    def test_prune_execute(self, tmp_path: Path) -> None:
        from core.experience_store import ExperienceStore
        db = tmp_path / "test_pr3.db"
        store = ExperienceStore(str(db))
        for i in range(3):
            store.create(agent_id="agent_test", type="failure_pattern",
                         observation=f"Good {i}", confidence=0.9,
                         structured_trigger=f"trig_g{i}")
        for i in range(7):
            store.create(agent_id="agent_test", type="failure_pattern",
                         observation=f"Bad {i}", confidence=0.05,
                         structured_trigger=f"trig_b{i}")
        result = store.prune("agent_test", keep=3, min_score=0.4, dry_run=False)
        assert result["deleted"] >= 5
        remaining = store.list(agent_id="agent_test", limit=10)
        assert len(remaining) <= 5


class TestMemoryStats:
    """memory_stats() health report."""

    def test_stats_empty(self, tmp_path: Path) -> None:
        from core.experience_store import ExperienceStore
        db = tmp_path / "test_ms1.db"
        store = ExperienceStore(str(db))
        stats = store.memory_stats("agent_test")
        assert stats["total"] == 0

    def test_stats_with_experiences(self, tmp_path: Path) -> None:
        from core.experience_store import ExperienceStore
        db = tmp_path / "test_ms2.db"
        store = ExperienceStore(str(db))
        store.create(agent_id="agent_test", type="failure_pattern",
                     observation="Error 1", confidence=0.3)
        store.create(agent_id="agent_test", type="success_strategy",
                     observation="Success 1", confidence=0.9)
        stats = store.memory_stats("agent_test")
        assert stats["total"] == 2
        assert "failure_pattern" in stats["by_type"]
        assert "success_strategy" in stats["by_type"]
        assert stats["avg_confidence"] > 0.5
