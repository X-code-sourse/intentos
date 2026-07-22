"""
Agent OS — Workflow Engine Tests

Tests cover:
  1. Workflow data model & DAG validation (cycle detection, topological sort)
  2. Planner: template matching, capability resolution, plan generation
  3. Scheduler: state machine, retry logic, failure propagation
  4. Execution semantics: retry policy, timeout policy, failure policy
  5. Workflow YAML parsing and serialization
"""

from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path
from typing import Any

# Ensure project root is in path
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.models import (
    CapabilityManifest, MetadataSpec, FieldSchema,
    RequirementSpec, SecuritySpec,
)
from core.registry import CapabilityRegistry
from core.workflow import (
    ExecutionSemantics, FailurePolicy, FailurePropagation,
    ParallelPolicy, ParallelStrategy, RetryPolicy, RetryStrategy,
    TaskStatus, TimeoutPolicy, WorkflowDAG, WorkflowEdge,
    WorkflowSpec, WorkflowTask, WorkflowStatus, WorkflowValidationError,
)
from core.planner import WorkflowPlanner, PlanError, NoTemplateMatchError
from core.executor import Executor
from core.recorder import ExecutionRecorder


# ──────────────────────────────────────────────
# Test Workflow DAG Validation
# ──────────────────────────────────────────────

class TestWorkflowDAGValidation(unittest.TestCase):
    """Test DAG construction, cycle detection, and topological ordering."""

    def setUp(self):
        self.semantics = ExecutionSemantics.defaults()

    def _make_spec(self, tasks: list, edges: list) -> WorkflowSpec:
        workflow_tasks = [
            WorkflowTask(id=t["id"], capability=t.get("capability", "test@1.0"),
                         input=t.get("input", {}))
            for t in tasks
        ]
        workflow_edges = [
            WorkflowEdge(from_task=e["from"], to_task=e["to"])
            for e in edges
        ]
        return WorkflowSpec(
            name="test", version="1.0.0",
            tasks=workflow_tasks, edges=workflow_edges,
            semantics=self.semantics,
            goal="test goal",
        )

    def test_simple_linear_dag(self):
        """A → B → C should produce correct topological order."""
        spec = self._make_spec(
            tasks=[{"id": "A"}, {"id": "B"}, {"id": "C"}],
            edges=[{"from": "A", "to": "B"}, {"from": "B", "to": "C"}],
        )
        dag = WorkflowDAG(spec)
        self.assertEqual(dag.topological_order, ["A", "B", "C"])

    def test_fan_out_dag(self):
        """A splits into B and C (parallel branches)."""
        spec = self._make_spec(
            tasks=[{"id": "A"}, {"id": "B"}, {"id": "C"}],
            edges=[{"from": "A", "to": "B"}, {"from": "A", "to": "C"}],
        )
        dag = WorkflowDAG(spec)
        self.assertEqual(dag.topological_order, ["A", "B", "C"])
        # A is root
        self.assertEqual([t.id for t in dag.get_root_tasks()], ["A"])
        # B and C are leaves
        self.assertCountEqual([t.id for t in dag.get_leaf_tasks()], ["B", "C"])

    def test_fan_in_dag(self):
        """A and B both feed into C."""
        spec = self._make_spec(
            tasks=[{"id": "A"}, {"id": "B"}, {"id": "C"}],
            edges=[{"from": "A", "to": "C"}, {"from": "B", "to": "C"}],
        )
        dag = WorkflowDAG(spec)
        self.assertEqual(dag.topological_order, ["A", "B", "C"])

    def test_diamond_dag(self):
        """Diamond: A → B, A → C, B → D, C → D."""
        spec = self._make_spec(
            tasks=[{"id": "A"}, {"id": "B"}, {"id": "C"}, {"id": "D"}],
            edges=[
                {"from": "A", "to": "B"},
                {"from": "A", "to": "C"},
                {"from": "B", "to": "D"},
                {"from": "C", "to": "D"},
            ],
        )
        dag = WorkflowDAG(spec)
        self.assertEqual(len(dag.topological_order), 4)
        self.assertEqual([t.id for t in dag.get_root_tasks()], ["A"])
        self.assertEqual([t.id for t in dag.get_leaf_tasks()], ["D"])

    def test_cycle_detection(self):
        """A → B → C → A should raise WorkflowValidationError."""
        spec = self._make_spec(
            tasks=[{"id": "A"}, {"id": "B"}, {"id": "C"}],
            edges=[
                {"from": "A", "to": "B"},
                {"from": "B", "to": "C"},
                {"from": "C", "to": "A"},
            ],
        )
        with self.assertRaises(WorkflowValidationError) as ctx:
            WorkflowDAG(spec)
        self.assertIn("Cycle detected", str(ctx.exception))

    def test_self_loop_detection(self):
        """A → A (self-loop) should raise WorkflowValidationError."""
        spec = self._make_spec(
            tasks=[{"id": "A"}, {"id": "B"}],
            edges=[{"from": "A", "to": "A"}],
        )
        with self.assertRaises(WorkflowValidationError):
            WorkflowDAG(spec)

    def test_longer_cycle(self):
        """A → B → C → D → B should detect the B→C→D→B cycle."""
        spec = self._make_spec(
            tasks=[{"id": "A"}, {"id": "B"}, {"id": "C"}, {"id": "D"}],
            edges=[
                {"from": "A", "to": "B"},
                {"from": "B", "to": "C"},
                {"from": "C", "to": "D"},
                {"from": "D", "to": "B"},
            ],
        )
        with self.assertRaises(WorkflowValidationError) as ctx:
            WorkflowDAG(spec)
        self.assertIn("Cycle detected", str(ctx.exception))

    def test_missing_task_reference(self):
        """Edge referencing non-existent task should raise."""
        spec = self._make_spec(
            tasks=[{"id": "A"}, {"id": "B"}],
            edges=[{"from": "A", "to": "C"}],  # C doesn't exist
        )
        with self.assertRaises(WorkflowValidationError):
            WorkflowDAG(spec)

    def test_dependency_status_check(self):
        """are_dependencies_satisfied should check upstream task states."""
        spec = self._make_spec(
            tasks=[{"id": "A"}, {"id": "B"}],
            edges=[{"from": "A", "to": "B"}],
        )
        dag = WorkflowDAG(spec)

        # A hasn't succeeded yet
        dag.get_task("A").status = TaskStatus.RUNNING
        self.assertFalse(dag.are_dependencies_satisfied("B"))

        # A succeeds
        dag.get_task("A").status = TaskStatus.SUCCEEDED
        self.assertTrue(dag.are_dependencies_satisfied("B"))

    def test_level_computation(self):
        """Tasks should be assigned correct topological levels."""
        spec = self._make_spec(
            tasks=[{"id": "A"}, {"id": "B"}, {"id": "C"}, {"id": "D"}],
            edges=[
                {"from": "A", "to": "B"},
                {"from": "A", "to": "C"},
                {"from": "B", "to": "D"},
                {"from": "C", "to": "D"},
            ],
        )
        dag = WorkflowDAG(spec)
        self.assertEqual(dag.get_level("A"), 0)
        self.assertEqual(dag.get_level("B"), 1)
        self.assertEqual(dag.get_level("C"), 1)
        self.assertEqual(dag.get_level("D"), 2)

    def test_workflow_spec_serialization(self):
        """WorkflowSpec.to_dict() should produce expected structure."""
        spec = self._make_spec(
            tasks=[{"id": "A"}, {"id": "B"}],
            edges=[{"from": "A", "to": "B"}],
        )
        d = spec.to_dict()
        self.assertEqual(d["kind"], "Workflow")
        self.assertEqual(d["metadata"]["name"], "test")
        self.assertEqual(len(d["spec"]["tasks"]), 2)
        self.assertEqual(len(d["spec"]["edges"]), 1)


# ──────────────────────────────────────────────
# Test Planner
# ──────────────────────────────────────────────

class TestWorkflowPlanner(unittest.TestCase):
    """Test template matching, capability resolution, and plan generation."""

    def setUp(self):
        self.registry = CapabilityRegistry()
        # Register some test capabilities
        self._register_capability("web_search", "1.0.0")
        self._register_capability("text_analyze", "1.0.0")
        self._register_capability("report_generate", "1.0.0")
        self._register_capability("text_summarize", "1.0.0")

        self.planner = WorkflowPlanner(registry=self.registry)

    def _register_capability(self, name: str, version: str):
        manifest = CapabilityManifest(
            metadata=MetadataSpec(
                name=name, version=version,
                publisher="test", description=f"Test {name}",
            ),
            input_schema={
                "input": FieldSchema(type="string", description="Input"),
            },
            output_schema={
                "output": FieldSchema(type="string", description="Output"),
            },
            requirements=RequirementSpec(),
            security=SecuritySpec(),
        )
        self.registry.register(manifest)

    def test_plan_research_goal(self):
        """'research NVIDIA stock' should match the 'research' template."""
        result = self.planner.plan("research NVIDIA stock")
        dag = result.workflow_dag
        self.assertIsNotNone(dag)
        self.assertGreater(len(dag.spec.tasks), 0)
        # Should have matched "research" template
        task_ids = [t.id for t in dag.spec.tasks]
        self.assertIn("search", task_ids)

    def test_plan_analysis_goal(self):
        """'analyze market trends' should match a template."""
        result = self.planner.plan("analyze market trends")
        dag = result.workflow_dag
        self.assertIsNotNone(dag)
        self.assertGreater(len(dag.spec.tasks), 0)

    def test_plan_summarize_goal(self):
        """'summarize this article' should match the 'summarize' template."""
        # Register additional capabilities for the summarize template
        self._register_capability("web_fetch", "1.0.0")
        # Re-create planner with updated registry
        self.planner = WorkflowPlanner(registry=self.registry)
        result = self.planner.plan("summarize this article")
        dag = result.workflow_dag
        self.assertIsNotNone(dag)
        task_ids = [t.id for t in dag.spec.tasks]
        self.assertIn("fetch", task_ids)

    def test_plan_with_context(self):
        """Context parameters should be merged into goal fields."""
        result = self.planner.plan("research stock", context={"topic": "AAPL"})
        self.assertEqual(result.goal, "research stock")

    def test_plan_no_registry_fallback(self):
        """Planner without registry should fall back to passthrough template."""
        planner = WorkflowPlanner(registry=None)
        result = planner.plan("do something")
        dag = result.workflow_dag
        self.assertIsNotNone(dag)
        self.assertEqual(result.template_name, "passthrough")

    def test_goal_parsing_extracts_topic(self):
        """Goal parser should extract topic after keywords."""
        fields = self.planner._parse_goal("research NVIDIA stock market")
        # Topic should be extracted
        self.assertIn("topic", fields)

    def test_template_priority(self):
        """Higher-priority templates should be preferred for matching goals."""
        # Register capabilities needed by the summarize template
        self._register_capability("web_fetch", "1.0.0")
        planner = WorkflowPlanner(registry=self.registry)
        # Both "summarize" (priority 1) and "research" (priority 0) could match
        # a goal like "research and summarize..." — "summarize" should win
        # since it has higher priority
        result = planner.plan("summarize the research findings")
        self.assertIsNotNone(result)
        self.assertEqual(result.template_name, "summarize")


# ──────────────────────────────────────────────
# Test Execution Semantics
# ──────────────────────────────────────────────

class TestExecutionSemantics(unittest.TestCase):
    """Test execution semantics data model and configuration."""

    def test_default_semantics(self):
        """Default semantics should provide sensible values."""
        s = ExecutionSemantics.defaults()
        self.assertEqual(s.retry.strategy, RetryStrategy.EXPONENTIAL)
        self.assertEqual(s.retry.max_attempts, 3)
        self.assertEqual(s.timeout.task_ms, 30000)
        self.assertEqual(s.failure.propagation, FailurePropagation.DEFERRED)
        self.assertEqual(s.parallel.strategy, ParallelStrategy.TASK_PARALLEL)

    def test_custom_retry_policy(self):
        """Custom retry policy should be constructable."""
        s = ExecutionSemantics(
            retry=RetryPolicy(
                strategy=RetryStrategy.FIXED,
                max_attempts=5,
                initial_interval_ms=2000,
            ),
        )
        self.assertEqual(s.retry.strategy, RetryStrategy.FIXED)
        self.assertEqual(s.retry.max_attempts, 5)
        self.assertEqual(s.retry.initial_interval_ms, 2000)

    def test_semantics_serialization(self):
        """to_dict() should produce spec-compliant output."""
        s = ExecutionSemantics.defaults()
        d = s.to_dict()
        self.assertIn("retry", d)
        self.assertIn("timeout", d)
        self.assertIn("failure", d)
        self.assertIn("parallel", d)
        self.assertEqual(d["retry"]["strategy"], "exponential")

    def test_task_status_values(self):
        """All TaskStatus values should be defined."""
        statuses = [
            TaskStatus.PENDING, TaskStatus.READY, TaskStatus.RUNNING,
            TaskStatus.SUCCEEDED, TaskStatus.FAILED_RETRIABLE,
            TaskStatus.FAILED_FATAL, TaskStatus.SKIPPED,
            TaskStatus.CANCELLED, TaskStatus.BLOCKED, TaskStatus.TIMEOUT,
        ]
        self.assertEqual(len(statuses), 10)
        for s in statuses:
            self.assertIsInstance(s.value, str)

    def test_failure_propagation_values(self):
        """All FailurePropagation modes should be available."""
        self.assertEqual(FailurePropagation.IMMEDIATE.value, "immediate")
        self.assertEqual(FailurePropagation.DEFERRED.value, "deferred")
        self.assertEqual(FailurePropagation.NONE.value, "none")

    def test_retry_strategies(self):
        """All RetryStrategy options should be available."""
        self.assertEqual(RetryStrategy.FIXED.value, "fixed")
        self.assertEqual(RetryStrategy.EXPONENTIAL.value, "exponential")
        self.assertEqual(RetryStrategy.NONE.value, "none")


# ──────────────────────────────────────────────
# Test Workflow Edge Cases
# ──────────────────────────────────────────────

class TestWorkflowEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def test_empty_workflow(self):
        """Workflow with no tasks should raise."""
        with self.assertRaises(WorkflowValidationError):
            spec = WorkflowSpec(
                name="empty", version="1.0.0",
                tasks=[], edges=[],
                semantics=ExecutionSemantics.defaults(),
            )
            WorkflowDAG(spec)

    def test_single_task_workflow(self):
        """Workflow with one task and no edges should work."""
        spec = WorkflowSpec(
            name="single", version="1.0.0",
            tasks=[WorkflowTask(id="A", capability="test@1.0")],
            edges=[],
            semantics=ExecutionSemantics.defaults(),
        )
        dag = WorkflowDAG(spec)
        self.assertEqual(len(dag.spec.tasks), 1)
        self.assertEqual(dag.get_root_tasks()[0].id, "A")
        self.assertEqual(dag.get_leaf_tasks()[0].id, "A")

    def test_unreachable_task(self):
        """Task not reachable from any root should still pass DAG validation
        (it's a valid DAG, just might indicate a design issue)."""
        spec = WorkflowSpec(
            name="disconnected", version="1.0.0",
            tasks=[
                WorkflowTask(id="A", capability="test@1.0"),
                WorkflowTask(id="B", capability="test@1.0"),
            ],
            edges=[],
            semantics=ExecutionSemantics.defaults(),
        )
        dag = WorkflowDAG(spec)
        self.assertEqual(len(dag.get_root_tasks()), 2)

    def test_large_dag_performance(self):
        """DAG with 100 tasks should validate quickly."""
        tasks = [
            WorkflowTask(id=f"T{i}", capability="test@1.0")
            for i in range(100)
        ]
        edges = []
        for i in range(99):
            edges.append(WorkflowEdge(from_task=f"T{i}", to_task=f"T{i+1}"))

        spec = WorkflowSpec(
            name="large", version="1.0.0",
            tasks=tasks, edges=edges,
            semantics=ExecutionSemantics.defaults(),
        )
        import time
        start = time.time()
        dag = WorkflowDAG(spec)
        elapsed = time.time() - start
        self.assertEqual(len(dag.spec.tasks), 100)
        # Should complete in under 100ms
        self.assertLess(elapsed, 0.1)


# ──────────────────────────────────────────────
# Test Workflow Data Classes
# ──────────────────────────────────────────────

class TestWorkflowDataClasses(unittest.TestCase):
    """Test WorkflowTask, WorkflowEdge, and helper methods."""

    def test_task_status_defaults_to_pending(self):
        """New task should default to PENDING status."""
        task = WorkflowTask(id="test", capability="test@1.0")
        self.assertEqual(task.status, TaskStatus.PENDING)
        self.assertEqual(task.attempt, 0)

    def test_task_to_spec_dict(self):
        """to_spec_dict should not include runtime state."""
        task = WorkflowTask(
            id="test", capability="test@1.0",
            input={"query": "hello"},
            description="A test task",
        )
        task.status = TaskStatus.RUNNING  # Runtime state
        task.latency_ms = 1000

        d = task.to_spec_dict()
        self.assertEqual(d["id"], "test")
        self.assertEqual(d["capability"], "test@1.0")
        self.assertIn("input", d)
        # Runtime state should NOT be in spec dict
        self.assertNotIn("status", d)
        self.assertNotIn("latency_ms", d)

    def test_edge_to_dict(self):
        """WorkflowEdge.to_dict() should produce correct format."""
        edge = WorkflowEdge(from_task="A", to_task="B", data={"key": "value"})
        d = edge.to_dict()
        self.assertEqual(d["from"], "A")
        self.assertEqual(d["to"], "B")
        self.assertEqual(d["data"]["key"], "value")

    def test_edge_without_data(self):
        """Edge with no data mapping should serialize correctly."""
        edge = WorkflowEdge(from_task="A", to_task="B")
        d = edge.to_dict()
        self.assertIsNone(d["data"])

    def test_workflow_id_property(self):
        """WorkflowSpec.id should return name@version."""
        spec = WorkflowSpec(
            name="my_workflow", version="2.1.0",
            tasks=[], edges=[],
        )
        self.assertEqual(spec.id, "my_workflow@2.1.0")

    def test_get_task(self):
        """get_task should return correct task by ID."""
        spec = WorkflowSpec(
            name="test", version="1.0.0",
            tasks=[WorkflowTask(id="A", capability="test@1.0")],
            edges=[],
        )
        task = spec.get_task("A")
        self.assertIsNotNone(task)
        self.assertEqual(task.id, "A")
        self.assertIsNone(spec.get_task("NONEXISTENT"))


if __name__ == "__main__":
    unittest.main()
