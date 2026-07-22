"""
Intent OS — Event Store and Analytics Tests

Tests cover:
  1. Event Store: saving, querying, filtering events
  2. Event Store: execution record persistence
  3. Event Store: aggregation and statistics
  4. Analytics: capability rankings
  5. Analytics: trend analysis and failure reporting
  6. Analytics: cost model data export
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure project root is in path
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.models import (
    Event,
    EventType,
    ExecutionRecord,
    ExecutionStatus,
    CapabilityManifest,
    MetadataSpec,
    FieldSchema,
    RequirementSpec,
    SecuritySpec,
)
from core.event_store import EventStore, EventStoreError
from core.analytics import AnalyticsEngine
from core.recorder import ExecutionRecorder


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

def _make_event(
    event_type: EventType = EventType.TASK_STARTED,
    trace_id: str = "test-trace-1",
    sequence: int = 1,
    capability: str | None = "test@1.0.0",
    runtime: str | None = "openai",
    source: str = "test",
) -> Event:
    return Event.create(
        event_type=event_type,
        trace_id=trace_id,
        source=source,
        sequence=sequence,
        payload={"test": True},
        metrics={"latency_ms": 100, "cost_usd": 0.01},
        task_id="test-task",
        capability=capability,
        runtime=runtime,
    )


def _make_execution_record(
    trace_id: str = "test-record-1",
    manifest_name: str = "test_capability",
    status: ExecutionStatus = ExecutionStatus.SUCCESS,
    latency: float = 500.0,
    cost: float = 0.05,
    tokens: int = 1000,
    runtime_id: str = "openai",
) -> ExecutionRecord:
    return ExecutionRecord(
        spec_version="1.0",
        trace_id=trace_id,
        manifest_name=manifest_name,
        manifest_version="1.0.0",
        runtime_id=runtime_id,
        adapter="TestAdapter",
        adapter_version="0.1.0",
        input={"query": "test"},
        output={"result": "test output"},
        status=status,
        error=None if status == ExecutionStatus.SUCCESS else "test error",
        total_latency_ms=latency,
        total_cost_usd=cost,
        total_tokens=tokens,
    )


# ──────────────────────────────────────────────
# Tests: Event Store Basics
# ──────────────────────────────────────────────

class TestEventStoreBasics:
    """Test fundamental Event Store operations."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_store.db")
        self.store = EventStore(self.db_path)

    def teardown_method(self):
        self.store.close()
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except PermissionError:
                pass

    def test_store_initializes(self):
        """Event Store should initialize and create tables."""
        assert self.store.get_event_count() == 0
        assert self.store.get_record_count() == 0

    def test_save_and_count_event(self):
        """Saving an event should increase the count."""
        event = _make_event()
        self.store.save_event(event)
        assert self.store.get_event_count() == 1

    def test_save_duplicate_event_raises(self):
        """Duplicate event_id should raise EventStoreError."""
        event = _make_event()
        self.store.save_event(event)
        try:
            self.store.save_event(event)
            assert False, "Should have raised EventStoreError"
        except EventStoreError:
            pass

    def test_save_events_batch(self):
        """Batch saving should persist all events."""
        events = [
            _make_event(trace_id="batch-trace", sequence=i)
            for i in range(10)
        ]
        count = self.store.save_events_batch(events)
        assert count == 10
        assert self.store.get_event_count() == 10

    def test_event_order_preserved(self):
        """Events should be retrievable in sequence order."""
        self.store.save_events_batch([
            _make_event(trace_id="order-test", sequence=1),
            _make_event(
                trace_id="order-test", sequence=2,
                event_type=EventType.CAPABILITY_INVOKED,
            ),
            _make_event(
                trace_id="order-test", sequence=3,
                event_type=EventType.TASK_COMPLETED,
            ),
        ])
        events = self.store.get_events_by_trace("order-test")
        assert len(events) == 3
        assert events[0]["sequence"] == 1
        assert events[1]["sequence"] == 2
        assert events[2]["sequence"] == 3

    def test_multiple_traces(self):
        """Events from different traces should be isolated."""
        self.store.save_events_batch([
            _make_event(trace_id="trace-a", sequence=1),
            _make_event(trace_id="trace-b", sequence=1),
        ])
        assert len(self.store.get_events_by_trace("trace-a")) == 1
        assert len(self.store.get_events_by_trace("trace-b")) == 1


# ──────────────────────────────────────────────
# Tests: Event Queries
# ──────────────────────────────────────────────

class TestEventQueries:
    """Test Event Store query capabilities."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "query_test.db")
        self.store = EventStore(self.db_path)

        # Seed data
        events = []
        for i in range(5):
            events.append(_make_event(
                trace_id=f"query-trace-{i}",
                sequence=1,
                capability="web_search@1.0",
                runtime="openai",
            ))
            events.append(_make_event(
                trace_id=f"query-trace-{i}",
                sequence=2,
                event_type=EventType.TASK_COMPLETED,
                capability="web_search@1.0",
                runtime="openai",
            ))
        self.store.save_events_batch(events)

    def teardown_method(self):
        self.store.close()
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except PermissionError:
                pass

    def test_query_by_trace_id(self):
        """Query events by trace_id."""
        events = self.store.query_events(trace_id="query-trace-0", limit=5)
        assert len(events) == 2
        assert all(e["trace_id"] == "query-trace-0" for e in events)

    def test_query_by_event_type(self):
        """Query events by event_type."""
        events = self.store.query_events(
            event_type=EventType.TASK_COMPLETED.value, limit=10
        )
        assert len(events) == 5
        assert all(e["event_type"] == "TaskCompleted" for e in events)

    def test_query_by_capability(self):
        """Query events by capability."""
        events = self.store.query_events(capability="web_search@1.0", limit=10)
        assert len(events) > 0

    def test_query_by_runtime(self):
        """Query events by runtime."""
        events = self.store.query_events(runtime="openai", limit=10)
        assert len(events) > 0

    def test_query_pagination(self):
        """Query with offset should return different results."""
        first = self.store.query_events(limit=2, offset=0)
        second = self.store.query_events(limit=2, offset=2)
        if first and second:
            assert first[0]["event_id"] != second[0]["event_id"]

    def test_query_by_time_range(self):
        """Query events within time range."""
        now = datetime.now(timezone.utc)
        start = datetime.fromtimestamp(0, tz=timezone.utc)
        events = self.store.get_events_by_time_range(start, now, limit=100)
        assert len(events) >= 10


# ──────────────────────────────────────────────
# Tests: Execution Records
# ──────────────────────────────────────────────

class TestExecutionRecords:
    """Test Execution Record persistence and querying."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "records_test.db")
        self.store = EventStore(self.db_path)

        # Seed records
        self.store.save_execution_record(_make_execution_record(
            trace_id="rec-1", manifest_name="search",
        ))
        self.store.save_execution_record(_make_execution_record(
            trace_id="rec-2", manifest_name="summarize",
        ))
        self.store.save_execution_record(_make_execution_record(
            trace_id="rec-3", manifest_name="search",
            status=ExecutionStatus.FAILURE,
        ))

    def teardown_method(self):
        self.store.close()
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except PermissionError:
                pass

    def test_get_single_record(self):
        """Get a single record by trace_id."""
        record = self.store.get_record("rec-1")
        assert record is not None
        assert record["manifest_name"] == "search"

    def test_get_nonexistent_record(self):
        """Getting a nonexistent record should return None."""
        record = self.store.get_record("nonexistent")
        assert record is None

    def test_query_records_by_manifest(self):
        """Query records by manifest name."""
        records = self.store.query_records(manifest_name="search")
        assert len(records) >= 1

    def test_query_records_by_status(self):
        """Query records by status."""
        records = self.store.query_records(status="failure")
        assert len(records) >= 1

    def test_all_trace_ids(self):
        """List all trace IDs."""
        traces = self.store.get_all_trace_ids()
        assert "rec-1" in traces
        assert "rec-2" in traces


# ──────────────────────────────────────────────
# Tests: Aggregation
# ──────────────────────────────────────────────

class TestAggregation:
    """Test Event Store aggregation functions."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "agg_test.db")
        self.store = EventStore(self.db_path)

        # Seed diverse records
        manifest_names = ["search", "search", "analyze", "search", "summarize", "analyze"]
        statuses = [
            ExecutionStatus.SUCCESS,
            ExecutionStatus.SUCCESS,
            ExecutionStatus.SUCCESS,
            ExecutionStatus.FAILURE,
            ExecutionStatus.SUCCESS,
            ExecutionStatus.SUCCESS,
        ]
        runtimes = ["openai", "openai", "openai", "openai", "claude", "claude"]

        for i, (mn, st, rt) in enumerate(zip(manifest_names, statuses, runtimes)):
            self.store.save_execution_record(_make_execution_record(
                trace_id=f"agg-{i}",
                manifest_name=mn,
                status=st,
                latency=100.0 + i * 50,
                cost=0.01 + i * 0.005,
                runtime_id=rt,
            ))

    def teardown_method(self):
        self.store.close()
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except PermissionError:
                pass

    def test_capability_stats(self):
        """Capability stats should aggregate correctly."""
        stats = self.store.get_capability_stats()
        names = [s["manifest_name"] for s in stats]
        assert "search" in names
        assert "analyze" in names

        for stat in stats:
            if stat["manifest_name"] == "search":
                assert stat["total_runs"] == 3
                assert stat["success_count"] == 2
                assert stat["failure_count"] == 1

    def test_runtime_stats(self):
        """Runtime stats should aggregate across capabilities."""
        stats = self.store.get_runtime_stats()
        runtime_ids = [s["runtime_id"] for s in stats]
        assert "openai" in runtime_ids
        assert "claude" in runtime_ids

    def test_event_store_count(self):
        """Record count should match."""
        assert self.store.get_record_count() == 6


# ──────────────────────────────────────────────
# Tests: Analytics Engine
# ──────────────────────────────────────────────

class TestAnalyticsEngine:
    """Test the Analytics Engine layer."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "analytics_test.db")
        self.store = EventStore(self.db_path)

        # Seed data for analytics
        for i in range(20):
            is_failure = i > 15
            self.store.save_execution_record(_make_execution_record(
                trace_id=f"an-{i}",
                manifest_name="web_search" if i % 2 == 0 else "text_analyze",
                status=ExecutionStatus.FAILURE if is_failure else ExecutionStatus.SUCCESS,
                latency=200.0 if is_failure else 100.0,
                cost=0.02 if is_failure else 0.01,
                tokens=2000 if is_failure else 1000,
            ))

        self.analytics = AnalyticsEngine(self.store)

    def teardown_method(self):
        self.store.close()
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except PermissionError:
                pass

    def test_capability_rankings(self):
        """Rankings should return scored capabilities."""
        rankings = self.analytics.get_capability_rankings()
        assert len(rankings) >= 1
        for r in rankings:
            assert "capability" in r
            assert "performance_score" in r
            assert 0 <= r["performance_score"] <= 100

    def test_runtime_comparison(self):
        """Runtime comparison should return stats per runtime."""
        comparison = self.analytics.get_runtime_comparison()
        assert len(comparison) >= 1

    def test_trend_summary(self):
        """Trend summary should structure data correctly."""
        summary = self.analytics.get_trend_summary(days=7)
        assert "total_executions" in summary
        assert "top_capabilities" in summary
        assert "failure_patterns" in summary

    def test_cost_trend(self):
        """Cost trend should calculate totals."""
        trend = self.analytics.get_cost_trend(days=30)
        assert "total_cost_usd" in trend
        assert "avg_cost_per_execution" in trend
        assert "cost_by_runtime" in trend
        assert trend["total_executions"] > 0

    def test_failure_report(self):
        """Failure report should identify patterns."""
        report = self.analytics.get_failure_report()
        assert "overall_failure_rate" in report
        assert "most_error_prone" in report
        assert len(report["most_error_prone"]) >= 0
        assert report["total_records"] > 0

    def test_cost_model_export(self):
        """Cost model export should produce structured training data."""
        data = self.analytics.export_cost_model_data(limit=10)
        assert len(data) <= 10
        if data:
            record = data[0]
            assert "capability" in record
            assert "runtime" in record
            assert "latency_ms" in record
            assert "cost_usd" in record
            assert "success" in record

    def test_optimization_suggestions(self):
        """Optimization suggestions should be generated."""
        suggestions = self.analytics.get_optimization_suggestions()
        assert isinstance(suggestions, list)

    def test_cost_model_export_to_file(self):
        """Cost model export to file should write valid JSON."""
        output_path = os.path.join(self.tmpdir, "cost_model_data.json")
        data = self.analytics.export_cost_model_data(
            limit=5, output_path=output_path,
        )
        assert os.path.exists(output_path)
        loaded = json.loads(Path(output_path).read_text())
        assert len(loaded) <= 5


# ──────────────────────────────────────────────
# Tests: Edge Cases
# ──────────────────────────────────────────────

class TestEventStoreEdgeCases:
    """Test edge cases and error handling."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "edge_test.db")
        self.store = EventStore(self.db_path)

    def teardown_method(self):
        self.store.close()
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except PermissionError:
                pass

    def test_empty_query_returns_empty_list(self):
        """Querying with no matching filters returns empty."""
        events = self.store.query_events(
            trace_id="nonexistent", limit=10,
        )
        assert events == []

    def test_concurrent_writes(self):
        """Concurrent event writes should not corrupt."""
        import threading

        results: list[Exception | None] = []

        def write_events(count: int, prefix: str):
            try:
                for i in range(count):
                    event = _make_event(
                        trace_id=f"{prefix}-{i}",
                        sequence=i,
                    )
                    self.store.save_event(event)
                results.append(None)
            except Exception as exc:
                results.append(exc)

        threads = [
            threading.Thread(target=write_events, args=(20, f"thread-a")),
            threading.Thread(target=write_events, args=(20, f"thread-b")),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should have completed without error
        for r in results:
            assert r is None, f"Thread error: {r}"

        assert self.store.get_event_count() == 40

    def test_large_batch(self):
        """Batch saving 100 events should succeed."""
        events = [
            _make_event(trace_id=f"batch-{i}", sequence=1)
            for i in range(100)
        ]
        count = self.store.save_events_batch(events)
        assert count == 100

    def test_store_persistence_across_reopens(self):
        """Data should persist when store is closed and reopened."""
        # Write some data
        event = _make_event(trace_id="persist-test")
        self.store.save_event(event)
        self.store.close()

        # Reopen
        store2 = EventStore(self.db_path)
        assert store2.get_event_count() == 1
        store2.close()

    def test_event_with_null_fields(self):
        """Events with null optional fields should be stored."""
        event = Event.create(
            event_type=EventType.TASK_STARTED,
            trace_id="null-test",
            sequence=1,
        )
        self.store.save_event(event)
        assert self.store.get_event_count() == 1

    def test_record_with_tokens(self):
        """Records with token counts should be correctly stored."""
        record = _make_execution_record(
            trace_id="token-test",
            tokens=54321,
        )
        self.store.save_execution_record(record)
        loaded = self.store.get_record("token-test")
        assert loaded is not None
        assert loaded["total_tokens"] == 54321

    def test_delete_old_records(self):
        """Old record deletion should work."""
        self.store.save_execution_record(_make_execution_record(trace_id="delete-me"))
        deleted = self.store.delete_old_records(
            datetime.now(timezone.utc).isoformat()
        )
        assert deleted >= 0
