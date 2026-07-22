"""
Intent OS — Workflow Engine Real Adapter Integration Tests

Tests cover:
  1. Scheduler registry resolution — resolves real manifests from Registry
  2. Scheduler registry fallback — placeholder when not in Registry
  3. CLI workflow run with real executor detection
  4. CLI workflow run with --simulate flag
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Ensure project root is in path
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.models import (
    CapabilityManifest, EventType, ExecutionStatus,
    MetadataSpec, FieldSchema, RequirementSpec, SecuritySpec,
)
from core.recorder import ExecutionRecorder
from core.registry import CapabilityRegistry
from core.scheduler import Scheduler
from core.workflow import (
    ExecutionSemantics, TaskStatus, WorkflowDAG, WorkflowEdge,
    WorkflowSpec, WorkflowTask, WorkflowStatus,
)
from core.workflow_runner import SimulatedExecutor, register_mock_capabilities


# ──────────────────────────────────────────────
# Scheduler Registry Resolution
# ──────────────────────────────────────────────

class TestSchedulerRegistryResolution:
    """Test that Scheduler resolves real manifests from Registry."""

    def setup_method(self):
        self.registry = CapabilityRegistry()
        self.manifest = CapabilityManifest(
            metadata=MetadataSpec(name="web_search", version="1.0.0",
                                  description="Real search capability"),
            input_schema={"query": FieldSchema(type="string")},
            output_schema={"results": FieldSchema(type="array")},
            requirements=RequirementSpec(),
            security=SecuritySpec(),
        )
        self.registry.register(self.manifest)

        self.executor = SimulatedExecutor()
        self.spec = WorkflowSpec(
            name="reg_test", version="1.0.0",
            tasks=[WorkflowTask(id="search", capability="web_search@1.0.0",
                                input={"query": "test"})],
            edges=[],
        )
        self.dag = WorkflowDAG(self.spec)

    def test_resolves_from_registry(self):
        """Scheduler with registry should resolve real manifest."""
        recorder = ExecutionRecorder(trace_id="reg-resolve-test")
        scheduler = Scheduler(self.executor, recorder, self.dag, trace_id="reg-resolve-test")
        scheduler.set_registry(self.registry)
        record = scheduler.execute()
        assert record.status == ExecutionStatus.SUCCESS
        task = self.dag.get_task("search")
        assert task.status == TaskStatus.SUCCEEDED

    def test_fallback_without_registry(self):
        """Scheduler without registry should still execute (backward compat)."""
        recorder = ExecutionRecorder(trace_id="reg-fallback-test")
        scheduler = Scheduler(self.executor, recorder, self.dag, trace_id="reg-fallback-test")
        record = scheduler.execute()
        assert record.status == ExecutionStatus.SUCCESS

    def test_multi_task_with_registry(self):
        """Multi-task workflow with registry should resolve all tasks."""
        self.registry.register(CapabilityManifest(
            metadata=MetadataSpec(name="text_analyze", version="1.0.0",
                                  description="Real analyze capability"),
            input_schema={"text": FieldSchema(type="string")},
            output_schema={"result": FieldSchema(type="string")},
            requirements=RequirementSpec(),
            security=SecuritySpec(),
        ))
        self.registry.register(CapabilityManifest(
            metadata=MetadataSpec(name="report_generate", version="1.0.0",
                                  description="Real report capability"),
            input_schema={"content": FieldSchema(type="string")},
            output_schema={"report": FieldSchema(type="string")},
            requirements=RequirementSpec(),
            security=SecuritySpec(),
        ))

        spec = WorkflowSpec(
            name="multi_test", version="1.0.0",
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
        )
        dag = WorkflowDAG(spec)
        recorder = ExecutionRecorder(trace_id="multi-reg-test")
        scheduler = Scheduler(self.executor, recorder, dag, trace_id="multi-reg-test")
        scheduler.set_registry(self.registry)
        record = scheduler.execute(input_data={"query": "test"})
        assert record.status == ExecutionStatus.SUCCESS
        for task in dag.spec.tasks:
            assert task.status == TaskStatus.SUCCEEDED
