"""Tests for Context Retrieval (SPEC-0010 P1+P2)."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.event_store import EventStore
from core.experience_store import ExperienceStore
from core.context_retrieval import (
    RetrievedContext,
    retrieve_context,
    format_retrieved_context,
    _extract_keywords,
)


def _init_db(db_path: Path) -> None:
    """Create execution_records table via EventStore init."""
    EventStore(str(db_path))


def _seed_record(db_path: Path, agent_id: str, manifest: str,
                 status: str = "success", runtime: str = "claude") -> None:
    """Insert an execution_record for capability aggregation."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """INSERT INTO execution_records
               (trace_id, spec_version, manifest_name, manifest_version,
                runtime_id, adapter, adapter_version, status, agent_id, created_at)
               VALUES (?, '1.0', ?, '1.0', ?, 'test', '1.0', ?, ?, ?)""",
            (str(uuid.uuid4()), manifest, runtime, status, agent_id,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


class TestKeywordExtraction:
    """_extract_keywords helper."""

    def test_extracts_words(self) -> None:
        words = _extract_keywords("analyze Nvidia quarterly earnings")
        assert "analyze" in words
        assert "nvidia" in words
        assert "quarterly" in words
        assert "earnings" in words

    def test_skips_short_words(self) -> None:
        words = _extract_keywords("a an of to is")
        assert words == []

    def test_handles_empty(self) -> None:
        assert _extract_keywords("") == []


class TestRetrieveContext:
    """retrieve_context() with experiences."""

    def test_retrieve_exact_match(self, tmp_path: Path) -> None:
        """Query matching experience structured_trigger."""
        db = tmp_path / "test_ret_exact.db"
        exp_store = ExperienceStore(str(db))
        exp_store.create(agent_id="agent_test", type="success_strategy",
                         observation="Always check FCF before valuation",
                         structured_trigger="earnings analysis",
                         confidence=0.9)
        results = retrieve_context("agent_test", "earnings analysis", db_path=str(db))
        assert len(results) >= 1
        assert "FCF" in results[0].content

    def test_retrieve_partial_match(self, tmp_path: Path) -> None:
        """Query partially matching experience content."""
        db = tmp_path / "test_ret_part.db"
        exp_store = ExperienceStore(str(db))
        exp_store.create(agent_id="agent_test", type="failure_pattern",
                         observation="API timeout during market open hours",
                         structured_trigger="api timeout",
                         confidence=0.8)
        results = retrieve_context("agent_test", "timeout api", db_path=str(db))
        assert len(results) >= 1

    def test_retrieve_no_match(self, tmp_path: Path) -> None:
        """Query matching nothing returns empty list."""
        db = tmp_path / "test_ret_none.db"
        exp_store = ExperienceStore(str(db))
        exp_store.create(agent_id="agent_test", type="failure_pattern",
                         observation="Database connection error",
                         confidence=0.7)
        results = retrieve_context("agent_test", "quantum physics", db_path=str(db))
        assert len(results) == 0

    def test_retrieve_capability(self, tmp_path: Path) -> None:
        """Query matching capability name."""
        db = tmp_path / "test_ret_cap.db"
        _init_db(db)
        for _ in range(5):
            _seed_record(db, "agent_test", "earnings_analysis", "success")
        results = retrieve_context("agent_test", "earnings", db_path=str(db))
        assert len(results) >= 1
        cap_results = [r for r in results if r.source == "capability"]
        assert len(cap_results) >= 1
        assert "earnings_analysis" in cap_results[0].source_id

    def test_retrieve_empty_query(self, tmp_path: Path) -> None:
        """Empty query returns recent experiences as fallback."""
        db = tmp_path / "test_ret_empty.db"
        exp_store = ExperienceStore(str(db))
        exp_store.create(agent_id="agent_test", type="success_strategy",
                         observation="Test experience for fallback",
                         confidence=0.5)
        results = retrieve_context("agent_test", "", db_path=str(db))
        assert len(results) >= 1

    def test_retrieve_max_results(self, tmp_path: Path) -> None:
        """max_results parameter limits results."""
        db = tmp_path / "test_ret_max.db"
        exp_store = ExperienceStore(str(db))
        for i in range(5):
            exp_store.create(agent_id="agent_test", type="failure_pattern",
                             observation=f"Error pattern {i}",
                             structured_trigger="error", confidence=0.5)
        results = retrieve_context("agent_test", "error", max_results=2, db_path=str(db))
        assert len(results) == 2


class TestFormatRetrievedContext:
    """format_retrieved_context()."""

    def test_format_empty(self) -> None:
        assert format_retrieved_context([]) is None

    def test_format_with_results(self) -> None:
        results = [
            RetrievedContext(source="capability", relevance_score=0.9,
                             content="Financial Analysis: 92% (3200 tasks)",
                             confidence=0.92, source_id="financial_analysis"),
            RetrievedContext(source="experience", relevance_score=0.8,
                             content="Always check FCF before valuation",
                             confidence=0.85, source_id="exp_123"),
        ]
        text = format_retrieved_context(results)
        assert text is not None
        assert "Relevant capabilities" in text
        assert "Financial Analysis" in text
        assert "Relevant experience" in text
        assert "FCF" in text


class TestRetrievedContext:
    """RetrievedContext dataclass."""

    def test_create(self) -> None:
        rc = RetrievedContext(source="capability", relevance_score=0.9,
                              content="test", confidence=0.8, source_id="cap_1")
        assert rc.source == "capability"
        assert rc.relevance_score == 0.9
        assert rc.confidence == 0.8

    def test_defaults(self) -> None:
        rc = RetrievedContext(source="experience", relevance_score=0.5, content="test")
        assert rc.confidence == 0.0
        assert rc.source_id == ""
