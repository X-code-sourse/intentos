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
    """19-state machine per RFC-0001 §3."""

    def _check(self, from_s: TaskState, to_s: TaskState, expect: bool):
        ok = from_s.can_transition_to(to_s)
        tag = "✓" if ok == expect else "✗"
        print(f"    {tag} {from_s.value:22s} → {to_s.value:22s}  (expect={expect}, got={ok})")
        assert ok == expect, f"{from_s.value}→{to_s.value}: expected {expect}, got {ok}"

    def test_all_19_states_defined(self):
        values = {s.value for s in TaskState}
        expected = {
            "created", "queued", "assigned", "running", "waiting_review",
            "reviewed", "review_failed", "completed", "completed_with_warning",
            "partial", "failed", "retry_queued", "replan_requested",
            "cancel_queued", "cancelled", "skipped", "archived",
            "pending_review", "pending_queued",
        }
        missing = expected - values
        extra = values - expected
        assert not missing, f"Missing states: {missing}"
        assert not extra, f"Unexpected states: {extra}"

    def test_terminal_states_block_outgoing(self):
        terminal = [TaskState.COMPLETED, TaskState.COMPLETED_WITH_WARNING,
                    TaskState.PARTIAL, TaskState.CANCELLED, TaskState.SKIPPED,
                    TaskState.ARCHIVED]
        for ts in terminal:
            for other in TaskState:
                if ts == other:
                    continue
                # Terminal states can only reach ARCHIVED (T20, T20.5, T18.5, T21, T22)
                if other == TaskState.ARCHIVED:
                    continue
                assert not ts.can_transition_to(other), f"{ts}→{other} should block"

    def test_t1_created_to_queued(self):
        self._check(TaskState.CREATED, TaskState.QUEUED, True)

    def test_t2_t25_queued_to_assigned_or_skipped(self):
        self._check(TaskState.QUEUED, TaskState.ASSIGNED, True)
        self._check(TaskState.QUEUED, TaskState.SKIPPED, True)

    def test_t3_assigned_to_running(self):
        self._check(TaskState.ASSIGNED, TaskState.RUNNING, True)

    def test_t4_t45_t5_t6_t24_running_transitions(self):
        self._check(TaskState.RUNNING, TaskState.WAITING_REVIEW, True)
        self._check(TaskState.RUNNING, TaskState.PARTIAL, True)
        self._check(TaskState.RUNNING, TaskState.FAILED, True)
        self._check(TaskState.RUNNING, TaskState.CANCEL_QUEUED, True)

    def test_t7_t75_t23_waiting_review(self):
        self._check(TaskState.WAITING_REVIEW, TaskState.REVIEWED, True)
        self._check(TaskState.WAITING_REVIEW, TaskState.PENDING_REVIEW, True)
        self._check(TaskState.WAITING_REVIEW, TaskState.REVIEW_FAILED, True)

    def test_t8_t9_t10_reviewed(self):
        self._check(TaskState.REVIEWED, TaskState.COMPLETED, True)
        self._check(TaskState.REVIEWED, TaskState.COMPLETED_WITH_WARNING, True)
        self._check(TaskState.REVIEWED, TaskState.REVIEW_FAILED, True)

    def test_t11_t12_review_failed(self):
        self._check(TaskState.REVIEW_FAILED, TaskState.RETRY_QUEUED, True)
        self._check(TaskState.REVIEW_FAILED, TaskState.FAILED, True)

    def test_t20_t205_archive_from_completed(self):
        self._check(TaskState.COMPLETED, TaskState.ARCHIVED, True)
        self._check(TaskState.COMPLETED_WITH_WARNING, TaskState.ARCHIVED, True)

    def test_t185_partial_to_archived(self):
        self._check(TaskState.PARTIAL, TaskState.ARCHIVED, True)

    def test_t13_t14_t15_failed_transitions(self):
        self._check(TaskState.FAILED, TaskState.RETRY_QUEUED, True)
        self._check(TaskState.FAILED, TaskState.REPLAN_REQUESTED, True)
        self._check(TaskState.FAILED, TaskState.CANCELLED, True)

    def test_t19_retry_queued_to_queued(self):
        self._check(TaskState.RETRY_QUEUED, TaskState.QUEUED, True)

    def test_t16_t17_replan_transitions(self):
        self._check(TaskState.REPLAN_REQUESTED, TaskState.CANCEL_QUEUED, True)
        self._check(TaskState.REPLAN_REQUESTED, TaskState.ARCHIVED, True)

    def test_t18_cancel_queued_to_cancelled(self):
        self._check(TaskState.CANCEL_QUEUED, TaskState.CANCELLED, True)

    def test_t21_t22_archive_from_terminal(self):
        self._check(TaskState.CANCELLED, TaskState.ARCHIVED, True)
        self._check(TaskState.SKIPPED, TaskState.ARCHIVED, True)

    def test_t26_t27_pending_cycle(self):
        self._check(TaskState.PENDING_REVIEW, TaskState.PENDING_QUEUED, True)
        self._check(TaskState.PENDING_QUEUED, TaskState.QUEUED, True)

    def test_invalid_transitions_blocked(self):
        # CREATED can only go to QUEUED
        for s in TaskState:
            if s == TaskState.QUEUED:
                continue
            assert not TaskState.CREATED.can_transition_to(s), f"CREATED→{s} should block"
        # QUEUED cannot go to RUNNING or COMPLETED directly
        assert not TaskState.QUEUED.can_transition_to(TaskState.RUNNING)
        # COMPLETED cannot go to anything but ARCHIVED
        for s in TaskState:
            if s == TaskState.ARCHIVED:
                continue
            assert not TaskState.COMPLETED.can_transition_to(s), f"COMPLETED→{s} should block"

    def test_engine_uses_assigned_state(self, engine):
        from agentos.models import Plan, PlannedTask
        plan = Plan(workflow_id="test", tasks=[
            PlannedTask(id="t1", type="echo", params={}, depends_on=[]),
        ])
        engine.pool.register("echo", lambda t, c: "ok")
        result = engine.execute(plan)
        tr = result.task_results["t1"]
        state_names = [h.to_state.value for h in tr.state_history]
        assert "assigned" in state_names, f"missing ASSIGNED: {state_names}"
        assert "running" in state_names
        assert state_names.index("assigned") < state_names.index("running")
