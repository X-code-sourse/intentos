"""Tests for backbone Event Bus integration (RFC-0500)."""

import pytest
from agentos.backbone.bus import EventBus
from agentos.backbone.event import Event


class TestEventBus:
    """Core publish/subscribe behavior."""

    def test_publish_subscribe_exact(self, bus: EventBus):
        received = []
        bus.subscribe("test:event", lambda e: received.append(e))
        event = Event.new("test:event", {"x": 1})
        bus.publish(event)
        assert len(received) == 1
        assert received[0].event_type == "test:event"
        assert received[0].payload == {"x": 1}

    def test_publish_subscribe_prefix(self, bus: EventBus):
        """backbone.bus uses prefix matching, not exact."""
        received = []
        bus.subscribe("test", lambda e: received.append(e))
        bus.publish(Event.new("test:alpha", {}))
        bus.publish(Event.new("test:beta", {}))
        assert len(received) == 2

    def test_no_match(self, bus: EventBus):
        received = []
        bus.subscribe("other", lambda e: received.append(e))
        bus.publish(Event.new("test:event", {}))
        assert len(received) == 0

    def test_unsubscribe(self, bus: EventBus):
        received = []
        cb = lambda e: received.append(e)
        bus.subscribe("test", cb)
        bus.publish(Event.new("test:a", {}))
        assert len(received) == 1
        bus.unsubscribe("test", cb)
        bus.publish(Event.new("test:b", {}))
        assert len(received) == 1  # unchanged

    def test_dead_letter(self, bus: EventBus):
        """Subscriber that raises should land in dead-letter queue."""
        def failing_cb(event):
            raise ValueError("oops")
        bus.subscribe("fail", failing_cb)
        dead = bus.publish(Event.new("fail:now", {}))
        assert len(dead) == 1
        assert "oops" in dead[0].attempts[0]["error"]
        assert len(bus.dead_letter_queue) == 1

    def test_multiple_subscribers(self, bus: EventBus):
        r1, r2 = [], []
        bus.subscribe("evt", lambda e: r1.append(1))
        bus.subscribe("evt", lambda e: r2.append(2))
        bus.publish(Event.new("evt:go", {}))
        assert len(r1) == 1
        assert len(r2) == 1


class TestBackboneIntegration:
    """E2E integration: backbone EventBus used throughout pipeline."""

    def test_engine_publishes_execution_completed(self, engine, stock_plan):
        events = []
        engine.bus.subscribe("Execution:Completed", lambda e: events.append(e))
        engine.bus.subscribe("Execution:Failed", lambda e: events.append(e))
        engine.execute(stock_plan)
        assert len(events) == 1
        assert events[0].payload["execution_result"].status == "completed"

    def test_engine_publishes_task_events(self, engine, stock_plan):
        events = []
        for et in ("Task:Created", "Task:Queued", "Task:Running",
                   "Task:Completed", "Task:Failed"):
            engine.bus.subscribe(et, lambda e: events.append(e.event_type))
        engine.execute(stock_plan)
        assert any("Task:Created" in str(e) for e in events)
        assert any("Task:Completed" in str(e) for e in events)

    def test_reviewer_publishes_review_passed(self, bus, engine, stock_plan):
        review_events = []
        bus.subscribe("Review:", lambda e: review_events.append(e))
        er = engine.execute(stock_plan)
        from agentos.reviewer import review as do_review
        do_review(er, bus=bus)
        assert len(review_events) >= 1
        types = {e.event_type for e in review_events}
        assert "Review:Passed" in types or "Review:Failed" in types

    def test_workflow_loaded_event(self, bus):
        from agentos.workflow_loader import load_from_path
        from pathlib import Path
        events = []
        bus.subscribe("workflow", lambda e: events.append(e))
        path = Path(__file__).parent.parent.parent / "examples" / "workflows" / "stock_research.yaml"
        load_from_path(path, bus=bus)
        assert len(events) == 1
        assert events[0].event_type == "workflow.loaded"

    def test_plan_ready_event(self, bus):
        from agentos.workflow_loader import load_from_path
        from agentos.planner import plan as do_plan
        from pathlib import Path
        events = []
        bus.subscribe("plan", lambda e: events.append(e))
        wf = load_from_path(Path(__file__).parent.parent.parent / "examples" / "workflows" / "stock_research.yaml")
        do_plan(wf, bus=bus, extra_params={"query": "t"})
        assert len(events) >= 1
        assert events[-1].event_type == "plan.ready"
