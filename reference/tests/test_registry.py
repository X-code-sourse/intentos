"""Tests for Registry (RFC-0300)."""

from agentos.registry import Registry, CapabilityManifest
from agentos.registry.manifest import CapabilityManifest as CM, load_manifest_from_yaml
from agentos.registry.workflows import WorkflowIndex


class TestCapabilityManifest:
    def test_create(self):
        m = CapabilityManifest(task_type="echo")
        assert m.task_type == "echo"
        assert m.enabled is True

    def test_with_fn(self):
        def fn(t, c): return t
        m = CapabilityManifest(task_type="e", fn=fn)
        assert m.fn is not None


class TestRegistry:
    def test_register_and_resolve(self):
        r = Registry()
        r.register("echo", lambda t, c: t, display_name="Echo")
        m = r.resolve("echo")
        assert m is not None
        assert m.task_type == "echo"

    def test_register_manifest(self):
        r = Registry()
        m = CM(task_type="x")
        r.register_manifest("x", m)
        assert r.resolve("x") is m

    def test_list_and_count(self):
        r = Registry()
        r.register("a", lambda t, c: 1)
        r.register("b", lambda t, c: 2)
        assert r.count == 2
        assert len(r.list()) == 2

    def test_find_by_type(self):
        r = Registry()
        r.register("search", lambda t, c: None)
        m = r.find_by_type("search")
        assert m is not None
        assert m.task_type == "search"

    def test_get_alias(self):
        r = Registry()
        r.register("x", lambda t, c: None)
        assert r.get("x") is r.resolve("x")

    def test_list_enabled(self):
        r = Registry()
        r.register("a", lambda t, c: 1)
        m = CM(task_type="b", enabled=False, fn=lambda t, c: 2)
        r.register_manifest("b", m)
        assert len(r.list()) == 2
        assert len(r.list_enabled()) == 1

    def test_load_builtins(self):
        r = Registry()
        r.load_builtins()
        assert r.count >= 5
        assert r.resolve("search") is not None
        assert r.resolve("report") is not None

    def test_engine_integration(self):
        """Registry-backed pool can execute capabilities."""
        from agentos.execution_engine import ExecutionEngine
        from agentos.models import Plan, PlannedTask
        from agentos.backbone.bus import EventBus

        r = Registry()
        r.load_builtins()
        engine = ExecutionEngine(bus=EventBus(), registry=r)
        plan = Plan(workflow_id="t", tasks=[
            PlannedTask(id="t1", type="search", params={"query": "x"}, depends_on=[]),
        ])
        result = engine.execute(plan)
        assert result.status == "completed"
        assert result.task_results["t1"].status == "completed"

    def test_snapshot(self):
        r = Registry()
        r.load_builtins()
        snap = r.snapshot()
        assert "capabilities" in snap
        assert len(snap["capabilities"]) >= 5


class TestWorkflowIndex:
    def test_track_and_resolve(self):
        idx = WorkflowIndex()
        idx.track("wf1", task_count=3, capability_types={"search", "llm"})
        m = idx.resolve("wf1")
        assert m is not None
        assert m["task_count"] == 3
        assert "search" in m["capability_types"]

    def test_reverse_index(self):
        idx = WorkflowIndex()
        idx.track("wf1", capability_types={"search", "llm"})
        idx.track("wf2", capability_types={"search", "report"})
        assert len(idx.workflows_using("search")) == 2
        assert len(idx.workflows_using("llm")) == 1

    def test_list(self):
        idx = WorkflowIndex()
        idx.track("a"); idx.track("b")
        assert len(idx.list()) == 2
        assert idx.count == 2
