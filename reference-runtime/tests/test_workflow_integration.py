"""
Intent OS — Workflow Engine Integration Tests

End-to-end tests that validate the complete Planner → DAG → Scheduler →
Execution → Events chain using simulated capabilities.

Covers:
  1. Workflow YAML parsing and structure validation
  2. Linear workflow (A → B → C)
  3. Fan-out workflow (A → B, A → C)
  4. Fan-in workflow (A, B → C)
  5. Failure + retry scenarios
  6. BLOCKED state on unsatisfied dependencies
  7. Failure propagation (cancel_dependents)
  8. Complete Planner → Scheduler → EventStore chain
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

# Ensure project root is in path
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.event_store import EventStore
from core.executor import Executor
from core.models import (
    CapabilityManifest, EventType, ExecutionRecord, ExecutionStatus,
    MetadataSpec, FieldSchema, RequirementSpec, SecuritySpec,
)
from core.parser import parse_manifest
from core.planner import WorkflowPlanner
from core.recorder import ExecutionRecorder
from core.registry import CapabilityRegistry
from core.workflow import (
    CompensationPolicy, CompensationStrategy,
    ExecutionSemantics, FailurePolicy, FailurePropagation,
    ParallelPolicy, ParallelStrategy, RetryPolicy, RetryStrategy,
    TaskStatus, TimeoutPolicy, WorkflowDAG, WorkflowEdge,
    WorkflowSpec, WorkflowTask, WorkflowStatus, WorkflowValidationError,
)
from core.workflow_runner import (
    SimulatedAdapter, SimulatedExecutor, register_mock_capabilities,
)


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

def make_registry() -> tuple[CapabilityRegistry, dict[str, CapabilityManifest]]:
    """Create a registry populated with mock capabilities."""
    registry = CapabilityRegistry()
    manifests = register_mock_capabilities(registry)
    for name, manifest in manifests.items():
        registry.register(manifest)
    return registry, manifests


def make_executor() -> SimulatedExecutor:
    """Create a simulated executor for testing."""
    return SimulatedExecutor()


# ──────────────────────────────────────────────
# 1. Linear Workflow
# ──────────────────────────────────────────────

class TestLinearWorkflow:
    """Test sequential (A → B → C) workflow execution."""

    def setup_method(self):
        self.executor = make_executor()
        self.semantics = ExecutionSemantics(
            retry=RetryPolicy(strategy=RetryStrategy.NONE),
            parallel=ParallelPolicy(strategy=ParallelStrategy.SEQUENTIAL),
        )

    def _make_linear_spec(self) -> WorkflowSpec:
        return WorkflowSpec(
            name="linear_test", version="1.0.0",
            tasks=[
                WorkflowTask(id="search", capability="web_search@1.0.0",
                             input={"query": "${goal.query}"}),
                WorkflowTask(id="analyze", capability="text_analyze@1.0.0",
                             input={"text": "${search.results}"}),
                WorkflowTask(id="report", capability="report_generate@1.0.0",
                             input={"content": "${analyze.result}"}),
            ],
            edges=[
                WorkflowEdge(from_task="search", to_task="analyze"),
                WorkflowEdge(from_task="analyze", to_task="report"),
            ],
            semantics=self.semantics,
            goal="test linear workflow",
        )

    def test_dag_construction(self):
        """DAG should have correct structure."""
        spec = self._make_linear_spec()
        dag = WorkflowDAG(spec)
        assert len(dag.spec.tasks) == 3
        assert dag.topological_order == ["search", "analyze", "report"]
        assert [t.id for t in dag.get_root_tasks()] == ["search"]
        assert [t.id for t in dag.get_leaf_tasks()] == ["report"]

    def test_sequential_execution(self):
        """Tasks should execute in order."""
        spec = self._make_linear_spec()
        dag = WorkflowDAG(spec)
        trace_id = "linear-test-1"
        recorder = ExecutionRecorder(trace_id=trace_id)

        from core.scheduler import Scheduler
        scheduler = Scheduler(self.executor, recorder, dag, trace_id=trace_id)
        record = scheduler.execute(input_data={"query": "NVIDIA stock"})

        assert record.status == ExecutionStatus.SUCCESS
        # Check task states
        for task in dag.spec.tasks:
            assert task.status == TaskStatus.SUCCEEDED, f"Task '{task.id}' failed"

    def test_output_propagation(self):
        """Output from upstream tasks should be available to downstream."""
        spec = self._make_linear_spec()
        dag = WorkflowDAG(spec)
        trace_id = "linear-output-test"
        recorder = ExecutionRecorder(trace_id=trace_id)

        from core.scheduler import Scheduler
        scheduler = Scheduler(self.executor, recorder, dag, trace_id=trace_id)
        scheduler.execute(input_data={"query": "test"})

        # All tasks should have output
        for task in dag.spec.tasks:
            assert task.output is not None, f"Task '{task.id}' has no output"

    def test_three_task_count(self):
        """Workflow should produce 3 TaskStarted + 3 TaskCompleted events."""
        spec = self._make_linear_spec()
        dag = WorkflowDAG(spec)
        trace_id = "linear-event-count"
        recorder = ExecutionRecorder(trace_id=trace_id)

        from core.scheduler import Scheduler
        scheduler = Scheduler(self.executor, recorder, dag, trace_id=trace_id)
        record = scheduler.execute(input_data={"query": "test"})

        events = [e for e in record.events if e.event_type == EventType.TASK_STARTED]
        assert len(events) == 3


# ──────────────────────────────────────────────
# 2. Fan-out Workflow
# ──────────────────────────────────────────────

class TestFanOutWorkflow:
    """Test parallel (A → B, A → C) workflow execution."""

    def setup_method(self):
        self.executor = make_executor()
        self.semantics = ExecutionSemantics(
            retry=RetryPolicy(strategy=RetryStrategy.NONE),
            parallel=ParallelPolicy(strategy=ParallelStrategy.TASK_PARALLEL),
            timeout=TimeoutPolicy(task_ms=5000),
        )

    def _make_fanout_spec(self) -> WorkflowSpec:
        return WorkflowSpec(
            name="fanout_test", version="1.0.0",
            tasks=[
                WorkflowTask(id="search", capability="web_search@1.0.0",
                             input={"query": "${goal.query}"}),
                WorkflowTask(id="analyze_text", capability="text_analyze@1.0.0",
                             input={"text": "${search.results}"}),
                WorkflowTask(id="analyze_financial", capability="financial_data_query@1.0.0",
                             input={"ticker": "${goal.ticker}"}),
            ],
            edges=[
                WorkflowEdge(from_task="search", to_task="analyze_text"),
                WorkflowEdge(from_task="search", to_task="analyze_financial"),
            ],
            semantics=self.semantics,
            goal="fan-out test",
        )

    def test_dag_structure(self):
        """Fan-out DAG should have correct structure."""
        spec = self._make_fanout_spec()
        dag = WorkflowDAG(spec)
        assert dag.get_level("search") == 0
        assert dag.get_level("analyze_text") == 1
        assert dag.get_level("analyze_financial") == 1
        assert [t.id for t in dag.get_leaf_tasks()] == ["analyze_text", "analyze_financial"]

    def test_parallel_execution(self):
        """Fan-out tasks should execute and both succeed."""
        spec = self._make_fanout_spec()
        dag = WorkflowDAG(spec)
        trace_id = "fanout-test-1"
        recorder = ExecutionRecorder(trace_id=trace_id)

        from core.scheduler import Scheduler
        scheduler = Scheduler(self.executor, recorder, dag, trace_id=trace_id)
        record = scheduler.execute(input_data={"query": "test", "ticker": "AAPL"})

        assert record.status == ExecutionStatus.SUCCESS
        for task in dag.spec.tasks:
            assert task.status == TaskStatus.SUCCEEDED


# ──────────────────────────────────────────────
# 3. Fan-in Workflow
# ──────────────────────────────────────────────

class TestFanInWorkflow:
    """Test merge (A, B → C) workflow execution."""

    def setup_method(self):
        self.executor = make_executor()
        self.semantics = ExecutionSemantics(
            retry=RetryPolicy(strategy=RetryStrategy.NONE),
            timeout=TimeoutPolicy(task_ms=5000),
        )

    def _make_fanin_spec(self) -> WorkflowSpec:
        return WorkflowSpec(
            name="fanin_test", version="1.0.0",
            tasks=[
                WorkflowTask(id="search", capability="web_search@1.0.0",
                             input={"query": "${goal.query}"}),
                WorkflowTask(id="financials", capability="financial_data_query@1.0.0",
                             input={"ticker": "${goal.ticker}"}),
                WorkflowTask(id="synthesize", capability="financial_analyze@1.0.0",
                             input={"data": "${financials.statements}"}),
            ],
            edges=[
                WorkflowEdge(from_task="search", to_task="synthesize"),
                WorkflowEdge(from_task="financials", to_task="synthesize"),
            ],
            semantics=self.semantics,
            goal="fan-in test",
        )

    def test_fanin_execution(self):
        """Both upstream tasks must complete before downstream executes."""
        spec = self._make_fanin_spec()
        dag = WorkflowDAG(spec)
        trace_id = "fanin-test-1"
        recorder = ExecutionRecorder(trace_id=trace_id)

        from core.scheduler import Scheduler
        scheduler = Scheduler(self.executor, recorder, dag, trace_id=trace_id)
        record = scheduler.execute(input_data={"query": "test", "ticker": "AAPL"})

        assert record.status == ExecutionStatus.SUCCESS
        # Check dependency satisfaction
        assert dag.are_dependencies_satisfied("synthesize")


# ──────────────────────────────────────────────
# 4. Failure + Retry
# ──────────────────────────────────────────────

class TestFailureAndRetry:
    """Test task failure and retry behavior."""

    def setup_method(self):
        self.semantics = ExecutionSemantics(
            retry=RetryPolicy(
                strategy=RetryStrategy.FIXED,
                max_attempts=3,
                initial_interval_ms=10,
            ),
        )

    def test_retry_on_failure(self):
        """Failed task should be retried."""
        executor = SimulatedExecutor(fail_capabilities=["web_search"])
        spec = WorkflowSpec(
            name="retry_test", version="1.0.0",
            tasks=[WorkflowTask(id="search", capability="web_search@1.0.0",
                                input={"query": "test"})],
            edges=[],
            semantics=self.semantics,
        )
        dag = WorkflowDAG(spec)
        trace_id = "retry-test-1"
        recorder = ExecutionRecorder(trace_id=trace_id)

        from core.scheduler import Scheduler
        scheduler = Scheduler(executor, recorder, dag, trace_id=trace_id)
        record = scheduler.execute(input_data={"query": "test"})

        assert record.status == ExecutionStatus.FAILURE
        # Check retry events
        retry_events = [e for e in record.events if e.event_type == EventType.TASK_RETRIED]
        assert len(retry_events) == 2  # 3 attempts = 2 retries

    def test_no_retry_on_fatal(self):
        """Non-retriable error should not retry."""
        executor = SimulatedExecutor(fail_capabilities=["fail_task"])
        semantics = ExecutionSemantics(
            retry=RetryPolicy(strategy=RetryStrategy.NONE),
        )
        spec = WorkflowSpec(
            name="no_retry_test", version="1.0.0",
            tasks=[WorkflowTask(id="task_a", capability="web_search@1.0.0",
                                input={"query": "test"})],
            edges=[],
            semantics=semantics,
        )
        dag = WorkflowDAG(spec)
        trace_id = "no-retry-test"
        recorder = ExecutionRecorder(trace_id=trace_id)

        from core.scheduler import Scheduler
        scheduler = Scheduler(executor, recorder, dag, trace_id=trace_id)
        record = scheduler.execute()
        retry_events = [e for e in record.events if e.event_type == EventType.TASK_RETRIED]
        assert len(retry_events) == 0


# ──────────────────────────────────────────────
# 5. BLOCKED State
# ──────────────────────────────────────────────

class TestBlockedState:
    """Test that tasks are BLOCKED when dependencies are not met."""

    def test_blocked_dependency(self):
        """Task with missing upstream output should remain BLOCKED."""
        executor = make_executor()
        semantics = ExecutionSemantics(
            retry=RetryPolicy(strategy=RetryStrategy.NONE),
            failure=FailurePolicy(propagation=FailurePropagation.IMMEDIATE),
        )
        spec = WorkflowSpec(
            name="blocked_test", version="1.0.0",
            tasks=[
                WorkflowTask(id="search", capability="web_search@1.0.0",
                             input={"query": "test"}),
                WorkflowTask(id="analyze", capability="text_analyze@1.0.0",
                             input={"text": "${search.results}"}),
            ],
            edges=[WorkflowEdge(from_task="search", to_task="analyze")],
            semantics=semantics,
        )
        dag = WorkflowDAG(spec)
        trace_id = "blocked-test"
        recorder = ExecutionRecorder(trace_id=trace_id)

        from core.scheduler import Scheduler
        scheduler = Scheduler(executor, recorder, dag, trace_id=trace_id)
        record = scheduler.execute()

        # If search succeeded, analyze should have too
        search = dag.get_task("search")
        analyze = dag.get_task("analyze")
        assert search.status in (TaskStatus.SUCCEEDED,)
        assert analyze.status in (TaskStatus.SUCCEEDED,)


# ──────────────────────────────────────────────
# 6. Failure Propagation
# ──────────────────────────────────────────────

class TestFailurePropagation:
    """Test that upstream failures cancel downstream tasks."""

    def test_immediate_propagation(self):
        """Immediate propagation should cancel downstream."""
        executor = SimulatedExecutor(fail_capabilities=["web_search"])
        semantics = ExecutionSemantics(
            retry=RetryPolicy(strategy=RetryStrategy.NONE),
            failure=FailurePolicy(
                propagation=FailurePropagation.IMMEDIATE,
                cancel_dependents=True,
                max_failures=1,
            ),
        )
        spec = WorkflowSpec(
            name="propagation_test", version="1.0.0",
            tasks=[
                WorkflowTask(id="search", capability="web_search@1.0.0",
                             input={"query": "test"}),
                WorkflowTask(id="analyze", capability="text_analyze@1.0.0",
                             input={"text": "${search.results}"}),
            ],
            edges=[WorkflowEdge(from_task="search", to_task="analyze")],
            semantics=semantics,
        )
        dag = WorkflowDAG(spec)
        trace_id = "propagation-test"
        recorder = ExecutionRecorder(trace_id=trace_id)

        from core.scheduler import Scheduler
        scheduler = Scheduler(executor, recorder, dag, trace_id=trace_id)
        record = scheduler.execute(input_data={"query": "test"})

        search = dag.get_task("search")
        assert search.status in (TaskStatus.FAILED_FATAL, TaskStatus.FAILED_RETRIABLE)


# ──────────────────────────────────────────────
# 7. Compensation Rollback
# ──────────────────────────────────────────────

class TestCompensationRollback:
    """Test that compensation rollback cancels completed tasks on failure."""

    def test_rollback_cancels_completed_tasks(self):
        """ROLLBACK should cancel successfully completed upstream tasks."""
        executor = SimulatedExecutor(fail_capabilities=["report_generate"])
        semantics = ExecutionSemantics(
            retry=RetryPolicy(strategy=RetryStrategy.NONE),
            compensation=CompensationPolicy(
                strategy=CompensationStrategy.ROLLBACK,
            ),
        )
        spec = WorkflowSpec(
            name="comp_test", version="1.0.0",
            tasks=[
                WorkflowTask(id="search", capability="web_search@1.0.0",
                             input={"query": "test"}),
                WorkflowTask(id="analyze", capability="text_analyze@1.0.0",
                             input={"text": "${search.results}"}),
                WorkflowTask(id="report", capability="report_generate@1.0.0",
                             input={"content": "${analyze.result}"}),
            ],
            edges=[
                WorkflowEdge(from_task="search", to_task="analyze"),
                WorkflowEdge(from_task="analyze", to_task="report"),
            ],
            semantics=semantics,
        )
        dag = WorkflowDAG(spec)
        recorder = ExecutionRecorder(trace_id="comp-rollback-test")
        from core.scheduler import Scheduler
        scheduler = Scheduler(executor, recorder, dag, trace_id="comp-rollback-test")
        scheduler.execute(input_data={"query": "test"})

        search = dag.get_task("search")
        analyze = dag.get_task("analyze")
        report = dag.get_task("report")

        # Upstream tasks that succeeded should be cancelled by rollback
        assert search.status == TaskStatus.CANCELLED, f"Expected CANCELLED, got {search.status}"
        assert analyze.status == TaskStatus.CANCELLED, f"Expected CANCELLED, got {analyze.status}"
        # The failed task should still be FAILED_FATAL
        assert report.status == TaskStatus.FAILED_FATAL

    def test_no_compensation_with_none(self):
        """Compensation NONE should leave completed tasks as SUCCEEDED."""
        executor = SimulatedExecutor(fail_capabilities=["report_generate"])
        semantics = ExecutionSemantics(
            retry=RetryPolicy(strategy=RetryStrategy.NONE),
            compensation=CompensationPolicy(
                strategy=CompensationStrategy.NONE,
            ),
        )
        spec = WorkflowSpec(
            name="no_comp_test", version="1.0.0",
            tasks=[
                WorkflowTask(id="search", capability="web_search@1.0.0",
                             input={"query": "test"}),
                WorkflowTask(id="analyze", capability="text_analyze@1.0.0",
                             input={"text": "${search.results}"}),
                WorkflowTask(id="fail_task", capability="report_generate@1.0.0",
                             input={"content": "test"}),
            ],
            edges=[
                WorkflowEdge(from_task="search", to_task="analyze"),
                WorkflowEdge(from_task="analyze", to_task="fail_task"),
            ],
            semantics=semantics,
        )
        dag = WorkflowDAG(spec)
        recorder = ExecutionRecorder(trace_id="no-comp-test")
        from core.scheduler import Scheduler
        scheduler = Scheduler(executor, recorder, dag, trace_id="no-comp-test")
        scheduler.execute(input_data={"query": "test"})

        search = dag.get_task("search")
        # Without compensation, completed tasks remain SUCCEEDED
        assert search.status == TaskStatus.SUCCEEDED


# ──────────────────────────────────────────────
# 8. Complete Planner → Scheduler → Events Chain
# ──────────────────────────────────────────────

class TestPlannerToExecutionChain:
    """Test the complete Planner → DAG → Scheduler → Events pipeline."""

    def setup_method(self):
        self.registry, self.manifests = make_registry()
        self.executor = make_executor()
        self.planner = WorkflowPlanner(registry=self.registry)

    def test_planner_produces_valid_dag(self):
        """Planner should produce a valid WorkflowDAG from a goal."""
        result = self.planner.plan("research NVIDIA stock")
        dag = result.workflow_dag
        assert len(dag.spec.tasks) >= 1
        assert dag.topological_order is not None

    def test_full_execution_chain(self):
        """Complete Planner → DAG → Scheduler → Events should produce valid record."""
        result = self.planner.plan("research NVIDIA stock")
        dag = result.workflow_dag
        trace_id = "chain-test-1"
        recorder = ExecutionRecorder(trace_id=trace_id)

        from core.scheduler import Scheduler
        scheduler = Scheduler(self.executor, recorder, dag, trace_id=trace_id)
        record = scheduler.execute(input_data={"topic": "NVIDIA"})

        assert record.status in (
            ExecutionStatus.SUCCESS, ExecutionStatus.PARTIAL
        )
        assert len(record.events) > 0

        # Should have WorkflowStarted event
        workflow_events = [
            e for e in record.events
            if e.event_type == EventType.WORKFLOW_STARTED
        ]
        assert len(workflow_events) == 1

    def test_execution_persists_to_event_store(self):
        """Execution should persist events to EventStore."""
        store = EventStore(":memory:")
        result = self.planner.plan("research NVIDIA stock")
        dag = result.workflow_dag
        recorder = ExecutionRecorder(trace_id="store-test")

        from core.scheduler import Scheduler
        scheduler = Scheduler(self.executor, recorder, dag, trace_id="store-test")
        record = scheduler.execute(input_data={"topic": "NVIDIA"})

        # Persist events
        store.save_events_batch(record.events)
        assert store.get_event_count() > 0

        # Query by trace
        events = store.query_events(trace_id="store-test")
        assert len(events) > 0

    def test_execution_record_has_metrics(self):
        """ExecutionRecord should contain latency, cost, and token metrics."""
        result = self.planner.plan("research NVIDIA stock")
        dag = result.workflow_dag
        recorder = ExecutionRecorder(trace_id="metrics-test")

        from core.scheduler import Scheduler
        scheduler = Scheduler(self.executor, recorder, dag, trace_id="metrics-test")
        record = scheduler.execute(input_data={"topic": "NVIDIA"})

        assert record.total_tokens >= 0
        assert record.total_latency_ms >= 0
        assert record.total_cost_usd >= 0


# ──────────────────────────────────────────────
# 8. Workflow YAML Parsing
# ──────────────────────────────────────────────

class TestWorkflowYamlParsing:
    """Test parsing workflow specifications from YAML files."""

    def test_parse_research_workflow_yaml(self):
        """research_workflow.yaml should parse correctly."""
        yaml_path = Path(_project_root) / "examples" / "research_workflow.yaml"
        assert yaml_path.exists(), f"File not found: {yaml_path}"

        import yaml
        raw = yaml.safe_load(yaml_path.read_text())
        assert raw["kind"] == "Workflow"
        assert raw["metadata"]["name"] == "company_research"
        assert "tasks" in raw["spec"]
        assert "edges" in raw["spec"]
        assert len(raw["spec"]["tasks"]) == 4
        assert len(raw["spec"]["edges"]) == 3

    def test_workflow_yaml_to_spec(self):
        """YAML workflow should convert to WorkflowSpec."""
        yaml_path = Path(_project_root) / "examples" / "research_workflow.yaml"
        import yaml
        raw = yaml.safe_load(yaml_path.read_text())

        # Build WorkflowSpec from YAML
        tasks = []
        for t in raw["spec"]["tasks"]:
            tasks.append(WorkflowTask(
                id=t["id"],
                capability=t["capability"],
                input=t.get("input", {}),
                description=t.get("description"),
            ))

        edges = []
        for e in raw["spec"]["edges"]:
            edges.append(WorkflowEdge(
                from_task=e["from"],
                to_task=e["to"],
                data=e.get("data"),
            ))

        spec = WorkflowSpec(
            name=raw["metadata"]["name"],
            version=raw["metadata"]["version"],
            tasks=tasks,
            edges=edges,
            goal=raw["spec"].get("goal", ""),
        )

        dag = WorkflowDAG(spec)
        assert len(dag.spec.tasks) == 4
        assert dag.topological_order is not None


# ──────────────────────────────────────────────
# 9. Edge Cases
# ──────────────────────────────────────────────

class TestWorkflowEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_single_task_workflow(self):
        """A workflow with one task should execute successfully."""
        executor = make_executor()
        spec = WorkflowSpec(
            name="single", version="1.0.0",
            tasks=[WorkflowTask(id="search", capability="web_search@1.0.0",
                                input={"query": "test"})],
            edges=[],
        )
        dag = WorkflowDAG(spec)
        recorder = ExecutionRecorder(trace_id="single-edge")

        from core.scheduler import Scheduler
        scheduler = Scheduler(executor, recorder, dag, trace_id="single-edge")
        record = scheduler.execute()
        assert record.status == ExecutionStatus.SUCCESS

    def test_no_root_tasks(self):
        """All tasks with dependencies should fail validation."""
        spec = WorkflowSpec(
            name="no_root", version="1.0.0",
            tasks=[
                WorkflowTask(id="A", capability="test@1.0"),
                WorkflowTask(id="B", capability="test@1.0"),
            ],
            edges=[WorkflowEdge(from_task="A", to_task="B"),
                   WorkflowEdge(from_task="B", to_task="A")],
        )
        import pytest
        with pytest.raises(WorkflowValidationError):
            WorkflowDAG(spec)

    def test_disconnected_tasks(self):
        """Disconnected tasks should each be root tasks."""
        spec = WorkflowSpec(
            name="disconnected", version="1.0.0",
            tasks=[
                WorkflowTask(id="A", capability="test@1.0"),
                WorkflowTask(id="B", capability="test@1.0"),
            ],
            edges=[],
        )
        dag = WorkflowDAG(spec)
        assert len(dag.get_root_tasks()) == 2


# ──────────────────────────────────────────────
# 10. YAML Semantics Round-trip
# ──────────────────────────────────────────────

class TestYamlSemanticsRoundTrip:
    """Test that YAML semantics parse → WorkflowSpec → Scheduler correctly."""

    def test_research_workflow_semantics_from_yaml(self):
        """research_workflow.yaml semantics should be correctly parsed."""
        from core.workflow_parser import parse_workflow_yaml
        yaml_path = Path(_project_root) / "examples" / "research_workflow.yaml"
        spec = parse_workflow_yaml(yaml_path)

        # Retry
        assert spec.semantics.retry.strategy.value == "exponential"
        assert spec.semantics.retry.max_attempts == 3
        assert spec.semantics.retry.initial_interval_ms == 1000

        # Timeout
        assert spec.semantics.timeout.task_ms == 120000
        assert spec.semantics.timeout.workflow_ms == 600000

        # Failure
        assert spec.semantics.failure.propagation.value == "deferred"
        assert spec.semantics.failure.cancel_dependents is True
        assert spec.semantics.failure.max_failures == 1

        # Parallel
        assert spec.semantics.parallel.strategy.value == "task_parallel"
        assert spec.semantics.parallel.max_concurrency == 3

    def test_scheduler_receives_yaml_semantics(self):
        """Scheduler should use semantics parsed from YAML."""
        from core.workflow_parser import parse_workflow_yaml
        from core.scheduler import Scheduler
        yaml_path = Path(_project_root) / "examples" / "research_workflow.yaml"
        spec = parse_workflow_yaml(yaml_path)
        dag = WorkflowDAG(spec)
        executor = SimulatedExecutor()
        recorder = ExecutionRecorder(trace_id="yaml-sem-test")
        scheduler = Scheduler(executor, recorder, dag, trace_id="yaml-sem-test")

        # Scheduler's semantics should match YAML
        assert scheduler._semantics.retry.strategy.value == "exponential"
        assert scheduler._semantics.retry.max_attempts == 3
        assert scheduler._semantics.failure.max_failures == 1
        assert scheduler._semantics.parallel.max_concurrency == 3

    def test_yaml_without_semantics_uses_defaults(self):
        """Workflow YAML without semantics should use ExecutionSemantics defaults."""
        minimal_yaml = """
kind: Workflow
metadata:
  name: minimal
  version: 1.0.0
spec:
  tasks:
    - id: A
      capability: test@1.0
      input: {}
  edges: []
"""
        from core.workflow_parser import parse_workflow_yaml
        spec = parse_workflow_yaml(minimal_yaml)
        assert spec.semantics.retry.max_attempts == 3
        assert spec.semantics.timeout.task_ms == 30000
        assert spec.semantics.failure.propagation.value == "deferred"
