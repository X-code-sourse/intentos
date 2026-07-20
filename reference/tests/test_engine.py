"""Tests for ExecutionEngine (RFC-0102)."""

from agentos.models import Plan, PlannedTask, TaskState


class TestEnginePlan:
    """Plan execution flow."""

    def test_execute_single_task(self, engine):
        plan = Plan(workflow_id="test", tasks=[
            PlannedTask(id="t1", type="echo", params={}, depends_on=[]),
        ])
        engine.pool.register("echo", lambda t, c: "ok")
        result = engine.execute(plan)
        assert result.status == "completed"
        assert len(result.task_results) == 1
        assert result.task_results["t1"].status == "completed"

    def test_execute_dag(self, engine):
        plan = Plan(workflow_id="test", tasks=[
            PlannedTask(id="t1", type="echo", params={}, depends_on=[]),
            PlannedTask(id="t2", type="echo", params={}, depends_on=["t1"]),
            PlannedTask(id="t3", type="echo", params={}, depends_on=["t1"]),
            PlannedTask(id="t4", type="echo", params={}, depends_on=["t2", "t3"]),
        ])
        engine.pool.register("echo", lambda t, c: "ok")
        result = engine.execute(plan)
        assert result.status == "completed"
        assert len(result.task_results) == 4
        for tr in result.task_results.values():
            assert tr.status == "completed", f"{tr.task_id}: {tr.status}"

    def test_execute_failure_propagation(self, engine):
        plan = Plan(workflow_id="test", tasks=[
            PlannedTask(id="t1", type="good", params={}, depends_on=[]),
            PlannedTask(id="t2", type="bad", params={}, depends_on=["t1"]),
        ])
        engine.pool.register("good", lambda t, c: "ok")
        engine.pool.register("bad", lambda t, c: (_ for _ in ()).throw(ValueError("fail")))
        result = engine.execute(plan)
        assert result.status == "partial"
        assert result.task_results["t1"].status == "completed"
        assert result.task_results["t2"].status == "failed"


class TestTaskStateMachine:
    """6-state machine transitions."""

    def test_state_history(self, engine):
        plan = Plan(workflow_id="test", tasks=[
            PlannedTask(id="t1", type="echo", params={}, depends_on=[]),
        ])
        engine.pool.register("echo", lambda t, c: "ok")
        result = engine.execute(plan)
        tr = result.task_results["t1"]
        assert len(tr.state_history) >= 3  # created, queued, running, completed
        assert tr.status == "completed"

    def test_invalid_transition_blocks(self):
        from agentos.models import TaskResult, StateTransition, TaskState
        tr = TaskResult("t1")
        tr.state_history.append(StateTransition(from_state=None, to_state=TaskState.CREATED))
        tr.transition_to(TaskState.QUEUED, "")
        tr.transition_to(TaskState.RUNNING, "")
        tr.transition_to(TaskState.COMPLETED, "")
        import pytest
        with pytest.raises(ValueError):
            tr.transition_to(TaskState.RUNNING, "invalid")

    def test_failed_to_retry(self):
        from agentos.models import TaskResult, StateTransition, TaskState
        tr = TaskResult("t1")
        tr.state_history.append(StateTransition(from_state=None, to_state=TaskState.CREATED))
        tr.transition_to(TaskState.QUEUED, "")
        tr.transition_to(TaskState.RUNNING, "")
        tr.transition_to(TaskState.FAILED, "err")
        assert tr.status == "failed"
        tr.transition_to(TaskState.RETRY_QUEUED, "retry")
        assert tr.status == "retry_queued"
