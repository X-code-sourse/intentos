"""
Intent OS — Security-Aware Executor Integration Tests

Integration tests that verify the Executor's interaction with the SecurityManager.
Covers backward compatibility, ALLOW/DENY paths, policy-driven risk evaluation,
and DAG condition evaluation with security-related conditions.

Test patterns follow test_security.py (real PolicyStore, optional mock EventStore).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

# Ensure project root is in path
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest

from core.executor import Executor, ExecutionError
from core.models import (
    CapabilityManifest,
    ExecutionStatus,
    FieldSchema,
    MetadataSpec,
    RequirementSpec,
    SecuritySpec as ModelSecuritySpec,
    SecurityRisk as ModelSecurityRisk,
)
from core.security import (
    EvaluationResult,
    Policy,
    PolicyStore,
    SecurityDecision,
    SecurityManager,
    SecurityRisk,
)
from core.workflow import (
    WorkflowDAG,
    WorkflowEdge,
    WorkflowSpec,
    WorkflowTask,
)


# ====================================================================
# Fixtures
# ====================================================================

@pytest.fixture
def db_path() -> str:
    """Provide a temporary SQLite database path, cleaned up after the test."""
    path = tempfile.mktemp(suffix=".db")
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def store(db_path: str) -> PolicyStore:
    """Provide a clean PolicyStore backed by a temp DB."""
    return PolicyStore(db_path)


@pytest.fixture
def security_manager(store: PolicyStore) -> SecurityManager:
    """Provide a SecurityManager with no event store."""
    return SecurityManager(policy_store=store, event_store=None)


# ====================================================================
# Helpers
# ====================================================================

def _make_manifest(
    name: str = "test_cap",
    version: str = "1.0.0",
    description: str = "A test capability",
    input_fields: dict[str, FieldSchema] | None = None,
    output_fields: dict[str, FieldSchema] | None = None,
    security: ModelSecuritySpec | None = None,
) -> CapabilityManifest:
    """Build a CapabilityManifest with sensible defaults for testing."""
    return CapabilityManifest(
        metadata=MetadataSpec(
            name=name, version=version, publisher="test", description=description,
        ),
        input_schema=input_fields or {"text": FieldSchema(type="string")},
        output_schema=output_fields or {"summary": FieldSchema(type="string")},
        requirements=RequirementSpec(),
        security=security or ModelSecuritySpec(),
    )


def _make_adapter(
    name: str = "mock_adapter",
    version: str = "0.1.0",
    default_model: str = "mock-model",
) -> MagicMock:
    """Create a mock adapter that behaves like a real AdapterBase instance."""
    adapter = MagicMock()
    adapter.name = name
    adapter.version = version
    adapter.default_model = default_model
    adapter.execute.return_value = {"summary": "mock output"}
    return adapter


# ====================================================================
# 1. Executor without security_manager — backward compatibility
# ====================================================================

class TestExecutorNoSecurityManager:
    """Executor functions normally when no security_manager is set."""

    def test_execute_without_security_manager(self):
        """execute() succeeds when security_manager is None (default)."""
        exe = Executor()
        adapter = _make_adapter(name="mock")
        exe.register_adapter("mock", adapter)
        manifest = _make_manifest()

        record = exe.execute(manifest, {"text": "hello"})

        assert record.status == ExecutionStatus.SUCCESS
        assert record.output == {"summary": "mock output"}

    def test_default_constructor_has_no_security_manager(self):
        """Executor() has no security_manager by default."""
        exe = Executor()
        assert exe._security_manager is None

    def test_set_security_manager_to_none(self):
        """Explicitly setting security_manager to None works."""
        exe = Executor()
        exe.set_security_manager(None)
        assert exe._security_manager is None

    def test_execute_with_none_security_manager_still_succeeds(self):
        """Explicit set_security_manager(None) does not break execute()."""
        exe = Executor()
        exe.set_security_manager(None)
        adapter = _make_adapter(name="mock")
        exe.register_adapter("mock", adapter)
        manifest = _make_manifest()

        record = exe.execute(manifest, {"text": "hello"})
        assert record.status == ExecutionStatus.SUCCESS


# ====================================================================
# 2. Executor with security_manager that returns ALLOW
# ====================================================================

class TestExecutorSecurityAllow:
    """Executor proceeds normally when security_manager returns ALLOW."""

    def test_allow_proceeds_with_execution(self):
        """ALLOW decision from security_manager does not block execution."""
        mock_mgr = MagicMock()
        mock_mgr.evaluate.return_value = EvaluationResult(
            decision=SecurityDecision.ALLOW,
            rationale="Policy permits this capability",
            policy_id="pol-allow",
            risk_level="low",
            capability_name="test_cap",
        )
        exe = Executor()
        exe.set_security_manager(mock_mgr)
        adapter = _make_adapter(name="mock")
        adapter.execute.return_value = {"summary": "allowed output"}
        exe.register_adapter("mock", adapter)
        manifest = _make_manifest()

        record = exe.execute(manifest, {"text": "hello"})

        assert record.status == ExecutionStatus.SUCCESS
        assert record.output == {"summary": "allowed output"}

    def test_allow_calls_evaluate_with_capability_info(self):
        """SecurityManager.evaluate is called with the capability name and risk."""
        mock_mgr = MagicMock()
        mock_mgr.evaluate.return_value = EvaluationResult(
            decision=SecurityDecision.ALLOW,
            rationale="OK",
            policy_id="pol-1",
            risk_level="low",
            capability_name="test_cap",
        )
        exe = Executor()
        exe.set_security_manager(mock_mgr)
        adapter = _make_adapter(name="mock")
        exe.register_adapter("mock", adapter)
        manifest = _make_manifest(name="test_cap")

        exe.execute(manifest, {"text": "hello"})

        mock_mgr.evaluate.assert_called_once()
        # evaluate is called with keyword args
        kwargs = mock_mgr.evaluate.call_args[1]
        assert kwargs.get("capability_name") == "test_cap"
        assert "risk_level" in kwargs

    def test_allow_with_low_risk_default(self):
        """Default SecuritySpec has LOW risk, which passes through ALLOW."""
        mock_mgr = MagicMock()
        mock_mgr.evaluate.return_value = EvaluationResult(
            decision=SecurityDecision.ALLOW,
            rationale="Low risk permitted",
            policy_id="pol-low",
            risk_level="low",
            capability_name="test_cap",
        )
        exe = Executor()
        exe.set_security_manager(mock_mgr)
        adapter = _make_adapter(name="mock")
        exe.register_adapter("mock", adapter)
        manifest = _make_manifest()

        record = exe.execute(manifest, {"text": "hello"})
        assert record.status == ExecutionStatus.SUCCESS

    def test_allow_when_manifest_has_no_security_spec(self):
        """Manifest with security=None still works when security_manager is set."""
        mock_mgr = MagicMock()
        mock_mgr.evaluate.return_value = EvaluationResult(
            decision=SecurityDecision.ALLOW,
            rationale="Permitted (default risk)",
            policy_id="pol-default",
            risk_level="medium",
            capability_name="test_cap",
        )
        exe = Executor()
        exe.set_security_manager(mock_mgr)
        adapter = _make_adapter(name="mock")
        exe.register_adapter("mock", adapter)
        manifest = _make_manifest(security=None)

        record = exe.execute(manifest, {"text": "hello"})
        assert record.status == ExecutionStatus.SUCCESS

    def test_allow_with_security_spec_medium_risk(self):
        """Medium risk manifest with ALLOW decision works correctly."""
        mock_mgr = MagicMock()
        mock_mgr.evaluate.return_value = EvaluationResult(
            decision=SecurityDecision.ALLOW,
            rationale="Medium risk permitted",
            policy_id="pol-medium",
            risk_level="medium",
            capability_name="test_cap",
        )
        exe = Executor()
        exe.set_security_manager(mock_mgr)
        adapter = _make_adapter(name="mock")
        exe.register_adapter("mock", adapter)
        manifest = _make_manifest(
            security=ModelSecuritySpec(risk=ModelSecurityRisk.MEDIUM),
        )

        record = exe.execute(manifest, {"text": "hello"})
        assert record.status == ExecutionStatus.SUCCESS


# ====================================================================
# 3. Executor with security_manager that returns DENY
# ====================================================================

class TestExecutorSecurityDeny:
    """Executor raises ExecutionError when security_manager returns DENY."""

    def test_deny_raises_execution_error(self):
        """DENY decision raises ExecutionError with the rationale."""
        mock_mgr = MagicMock()
        mock_mgr.evaluate.return_value = EvaluationResult(
            decision=SecurityDecision.DENY,
            rationale="Capability is explicitly blocked",
            policy_id="pol-deny",
            risk_level="high",
            capability_name="test_cap",
        )
        exe = Executor()
        exe.set_security_manager(mock_mgr)
        adapter = _make_adapter(name="mock")
        exe.register_adapter("mock", adapter)
        manifest = _make_manifest()

        with pytest.raises(ExecutionError) as exc_info:
            exe.execute(manifest, {"text": "hello"})

        assert "Security policy denied" in str(exc_info.value)
        assert "explicitly blocked" in str(exc_info.value)

    def test_deny_prevents_adapter_execution(self):
        """When DENY is returned, the adapter is never called."""
        mock_mgr = MagicMock()
        mock_mgr.evaluate.return_value = EvaluationResult(
            decision=SecurityDecision.DENY,
            rationale="Blocked",
            policy_id="pol-block",
            risk_level="high",
            capability_name="test_cap",
        )
        exe = Executor()
        exe.set_security_manager(mock_mgr)
        adapter = _make_adapter(name="mock")
        exe.register_adapter("mock", adapter)
        manifest = _make_manifest()

        with pytest.raises(ExecutionError):
            exe.execute(manifest, {"text": "hello"})

        adapter.execute.assert_not_called()

    def test_deny_with_policy_id_none(self):
        """DENY from no matching policy (policy_id=None) still raises."""
        mock_mgr = MagicMock()
        mock_mgr.evaluate.return_value = EvaluationResult(
            decision=SecurityDecision.DENY,
            rationale="No matching policy",
            policy_id=None,
            risk_level="medium",
            capability_name="test_cap",
        )
        exe = Executor()
        exe.set_security_manager(mock_mgr)
        adapter = _make_adapter(name="mock")
        exe.register_adapter("mock", adapter)
        manifest = _make_manifest()

        with pytest.raises(ExecutionError) as exc_info:
            exe.execute(manifest, {"text": "hello"})

        assert "Security policy denied" in str(exc_info.value)
        assert "No matching policy" in str(exc_info.value)

    def test_deny_with_high_risk_manifest(self):
        """DENY blocks a high-risk manifest before adapter invocation."""
        mock_mgr = MagicMock()
        mock_mgr.evaluate.return_value = EvaluationResult(
            decision=SecurityDecision.DENY,
            rationale="High risk blocked",
            policy_id="pol-deny-high",
            risk_level="high",
            capability_name="test_cap",
        )
        exe = Executor()
        exe.set_security_manager(mock_mgr)
        adapter = _make_adapter(name="mock")
        exe.register_adapter("mock", adapter)
        manifest = _make_manifest(
            security=ModelSecuritySpec(risk=ModelSecurityRisk.HIGH),
        )

        with pytest.raises(ExecutionError, match="Security policy denied"):
            exe.execute(manifest, {"text": "hello"})

        adapter.execute.assert_not_called()


# ====================================================================
# 4. Manifests with security.risk=critical are denied by blocking policy
# ====================================================================

class TestCriticalRiskBlocked:
    """Integration: a real SecurityManager + PolicyStore denies critical-risk
    capabilities when a policy blocks critical-level operations."""

    def test_critical_risk_requires_review(self, store: PolicyStore):
        """Critical risk with require_review_for: ['critical'] raises
        ExecutionError with 'Security review required'."""
        store.upsert(Policy(
            policy_id="pol-block-critical",
            target_patterns=["*"],
            review_rules={"require_review_for": ["critical"]},
        ))
        mgr = SecurityManager(policy_store=store, event_store=None)
        exe = Executor()
        exe.set_security_manager(mgr)
        adapter = _make_adapter(name="mock")
        exe.register_adapter("mock", adapter)
        manifest = _make_manifest(
            security=ModelSecuritySpec(risk=ModelSecurityRisk.CRITICAL),
        )

        with pytest.raises(ExecutionError) as exc_info:
            exe.execute(manifest, {"text": "hello"})

        assert "Security review required" in str(exc_info.value)

    def test_critical_risk_adapter_not_called(self, store: PolicyStore):
        """When critical risk is blocked, the adapter is never invoked."""
        store.upsert(Policy(
            policy_id="pol-block-critical",
            target_patterns=["*"],
            review_rules={"require_review_for": ["critical"]},
        ))
        mgr = SecurityManager(policy_store=store, event_store=None)
        exe = Executor()
        exe.set_security_manager(mgr)
        adapter = _make_adapter(name="mock")
        exe.register_adapter("mock", adapter)
        manifest = _make_manifest(
            security=ModelSecuritySpec(risk=ModelSecurityRisk.CRITICAL),
        )

        with pytest.raises(ExecutionError):
            exe.execute(manifest, {"text": "hello"})

        adapter.execute.assert_not_called()

    def test_critical_risk_evaluation_result(self, store: PolicyStore):
        """The EvaluationResult for a blocked critical-risk capability
        has risk_level='critical' and decision=REQUIRE_REVIEW."""
        store.upsert(Policy(
            policy_id="pol-block-critical",
            target_patterns=["*"],
            review_rules={"require_review_for": ["critical"]},
        ))
        mgr = SecurityManager(policy_store=store, event_store=None)
        result = mgr.evaluate({"name": "test_cap", "risk": "critical"})

        assert result.risk_level == "critical"
        assert result.decision == SecurityDecision.REQUIRE_REVIEW
        assert result.capability_name == "test_cap"

    def test_explicit_deny_rule_blocks_critical(self, store: PolicyStore):
        """An explicit deny rule matching all capabilities also blocks
        critical-risk manifests."""
        store.upsert(Policy(
            policy_id="pol-deny-all",
            target_patterns=["*"],
            review_rules={"deny": ["*"]},
        ))
        mgr = SecurityManager(policy_store=store, event_store=None)
        exe = Executor()
        exe.set_security_manager(mgr)
        adapter = _make_adapter(name="mock")
        exe.register_adapter("mock", adapter)
        manifest = _make_manifest(
            security=ModelSecuritySpec(risk=ModelSecurityRisk.CRITICAL),
        )

        with pytest.raises(ExecutionError) as exc_info:
            exe.execute(manifest, {"text": "hello"})

        assert "Security policy denied" in str(exc_info.value)

    def test_risk_override_elevates_to_critical(self, store: PolicyStore):
        """A risk override that elevates medium to critical triggers review."""
        store.upsert(Policy(
            policy_id="pol-override",
            target_patterns=["file.*"],
            risk_overrides={"file.delete": "critical"},
            review_rules={"require_review_for": ["critical"]},
        ))
        mgr = SecurityManager(policy_store=store, event_store=None)
        exe = Executor()
        exe.set_security_manager(mgr)
        adapter = _make_adapter(name="mock")
        exe.register_adapter("mock", adapter)
        # manifest name matches the risk-override pattern
        manifest = _make_manifest(
            name="file.delete",
            security=ModelSecuritySpec(risk=ModelSecurityRisk.MEDIUM),
        )

        with pytest.raises(ExecutionError) as exc_info:
            exe.execute(manifest, {"text": "hello"})

        assert "Security review required" in str(exc_info.value)


# ====================================================================
# 5. Manifests with security.risk=low pass through a blocking policy
# ====================================================================

class TestLowRiskPasses:
    """Integration: low-risk capabilities pass through policies that
    only block critical or high risk levels."""

    def test_low_risk_passes_require_review_policy(self, store: PolicyStore):
        """Low risk is not in require_review_for: ['critical'], so execution
        proceeds normally."""
        store.upsert(Policy(
            policy_id="pol-block-critical",
            target_patterns=["*"],
            review_rules={"require_review_for": ["critical"]},
        ))
        mgr = SecurityManager(policy_store=store, event_store=None)
        exe = Executor()
        exe.set_security_manager(mgr)
        adapter = _make_adapter(name="mock")
        adapter.execute.return_value = {"summary": "low risk output"}
        exe.register_adapter("mock", adapter)
        manifest = _make_manifest(
            security=ModelSecuritySpec(risk=ModelSecurityRisk.LOW),
        )

        record = exe.execute(manifest, {"text": "hello"})

        assert record.status == ExecutionStatus.SUCCESS
        assert record.output == {"summary": "low risk output"}

    def test_low_risk_evaluates_to_allow(self, store: PolicyStore):
        """The EvaluationResult for low-risk against a critical-blocking
        policy is ALLOW with risk_level='low'."""
        store.upsert(Policy(
            policy_id="pol-block-critical",
            target_patterns=["*"],
            review_rules={"require_review_for": ["critical"]},
        ))
        mgr = SecurityManager(policy_store=store, event_store=None)
        result = mgr.evaluate({"name": "test_cap", "risk": "low"})

        assert result.decision == SecurityDecision.ALLOW
        assert result.risk_level == "low"

    def test_medium_risk_not_blocked_by_critical_only_policy(self, store: PolicyStore):
        """Medium risk passes through a policy that only requires review
        for critical level."""
        store.upsert(Policy(
            policy_id="pol-block-critical",
            target_patterns=["*"],
            review_rules={"require_review_for": ["critical"]},
        ))
        mgr = SecurityManager(policy_store=store, event_store=None)
        exe = Executor()
        exe.set_security_manager(mgr)
        adapter = _make_adapter(name="mock")
        adapter.execute.return_value = {"summary": "medium output"}
        exe.register_adapter("mock", adapter)
        manifest = _make_manifest(
            security=ModelSecuritySpec(risk=ModelSecurityRisk.MEDIUM),
        )

        record = exe.execute(manifest, {"text": "hello"})
        assert record.status == ExecutionStatus.SUCCESS

    def test_high_risk_blocked_by_broad_policy(self, store: PolicyStore):
        """High risk is blocked when require_review_for includes 'high'."""
        store.upsert(Policy(
            policy_id="pol-block-high",
            target_patterns=["*"],
            review_rules={"require_review_for": ["high", "critical"]},
        ))
        mgr = SecurityManager(policy_store=store, event_store=None)
        exe = Executor()
        exe.set_security_manager(mgr)
        adapter = _make_adapter(name="mock")
        exe.register_adapter("mock", adapter)
        manifest = _make_manifest(
            security=ModelSecuritySpec(risk=ModelSecurityRisk.HIGH),
        )

        with pytest.raises(ExecutionError) as exc_info:
            exe.execute(manifest, {"text": "hello"})

        assert "Security review required" in str(exc_info.value)

    def test_low_risk_blocked_by_explicit_deny(self, store: PolicyStore):
        """Explicit deny rule overrides low risk — even low-risk capabilities
        are blocked when a matching deny rule exists."""
        store.upsert(Policy(
            policy_id="pol-deny-all",
            target_patterns=["*"],
            review_rules={"deny": ["*"]},
        ))
        mgr = SecurityManager(policy_store=store, event_store=None)
        exe = Executor()
        exe.set_security_manager(mgr)
        adapter = _make_adapter(name="mock")
        exe.register_adapter("mock", adapter)
        manifest = _make_manifest(
            security=ModelSecuritySpec(risk=ModelSecurityRisk.LOW),
        )

        with pytest.raises(ExecutionError) as exc_info:
            exe.execute(manifest, {"text": "hello"})

        assert "Security policy denied" in str(exc_info.value)

    def test_low_risk_evaluated_correctly_by_manager(self, store: PolicyStore):
        """Direct SecurityManager evaluation confirms low risk = ALLOW
        under a policy that only blocks critical."""
        store.upsert(Policy(
            policy_id="pol-block-critical",
            target_patterns=["*"],
            review_rules={"require_review_for": ["critical"]},
        ))
        mgr = SecurityManager(policy_store=store, event_store=None)

        result = mgr.evaluate({"name": "safe.op", "risk": "low"})
        assert result.decision == SecurityDecision.ALLOW
        assert result.policy_id == "pol-block-critical"

    def test_risk_not_in_require_review_for_passes(self, store: PolicyStore):
        """Risk level not listed in require_review_for is allowed."""
        store.upsert(Policy(
            policy_id="pol-specific",
            target_patterns=["*"],
            review_rules={"require_review_for": ["critical"]},
        ))
        mgr = SecurityManager(policy_store=store, event_store=None)
        exe = Executor()
        exe.set_security_manager(mgr)
        adapter = _make_adapter(name="mock")
        adapter.execute.return_value = {"summary": "safe output"}
        exe.register_adapter("mock", adapter)

        for risk_level in [ModelSecurityRisk.LOW, ModelSecurityRisk.MEDIUM]:
            manifest = _make_manifest(
                name=f"cap.{risk_level.value}",
                security=ModelSecuritySpec(risk=risk_level),
            )
            record = exe.execute(manifest, {"text": "hello"})
            assert record.status == ExecutionStatus.SUCCESS, (
                f"{risk_level.value} should pass"
            )
            adapter.execute.assert_called()  # at least once by now


# ====================================================================
# 6. WorkflowDAG.evaluate_condition on security aspects
# ====================================================================

class TestDagEvaluateConditionSecurity:
    """WorkflowDAG.evaluate_condition works with security-related conditions
    such as vulnerability counts, risk levels, and approval status."""

    # ── Condition boundary cases ──

    def test_condition_none_returns_true(self):
        """None or empty condition always returns True (backward compat)."""
        dag = self._make_security_dag()
        assert dag.evaluate_condition(None, {}) is True
        assert dag.evaluate_condition("", {}) is True
        assert dag.evaluate_condition("  ", {}) is True

    # ── Vulnerability scan conditions ──

    def test_zero_vulnerabilities_allows_deploy(self):
        """Condition ${security_scan.vulnerabilities} == 0 is True
        when no vulnerabilities exist."""
        dag = self._make_security_dag()
        task_outputs = {
            "security_scan": {"vulnerabilities": 0, "critical": 0, "high": 0},
        }
        result = dag.evaluate_condition(
            "${security_scan.vulnerabilities} == 0",
            task_outputs,
        )
        assert result is True

    def test_vulnerabilities_present_block_deploy(self):
        """Condition ${security_scan.vulnerabilities} == 0 is False
        when vulnerabilities exist."""
        dag = self._make_security_dag()
        task_outputs = {
            "security_scan": {"vulnerabilities": 3, "critical": 1, "high": 2},
        }
        result = dag.evaluate_condition(
            "${security_scan.vulnerabilities} == 0",
            task_outputs,
        )
        assert result is False

    def test_critical_vulnerabilities_blocks_deploy(self):
        """Numeric greater-than check on critical vulnerabilities."""
        dag = self._make_security_dag()
        # critical > 0 → block
        assert dag.evaluate_condition(
            "${security_scan.critical} > 0",
            {"security_scan": {"critical": 2, "high": 0}},
        ) is True
        # critical == 0 → allow
        assert dag.evaluate_condition(
            "${security_scan.critical} > 0",
            {"security_scan": {"critical": 0, "high": 1}},
        ) is False

    # ── Risk level conditions ──

    def test_risk_level_equals_low_allows_proceed(self):
        """Condition ${risk_assessment.risk_level} == 'low' is True
        when the assessed risk is low."""
        dag = self._make_security_dag()
        task_outputs = {"risk_assessment": {"risk_level": "low", "score": 15}}
        result = dag.evaluate_condition(
            "${risk_assessment.risk_level} == 'low'",
            task_outputs,
        )
        assert result is True

    def test_risk_level_high_blocks_proceed(self):
        """Condition ${risk_assessment.risk_level} == 'low' is False
        when the assessed risk is high."""
        dag = self._make_security_dag()
        task_outputs = {"risk_assessment": {"risk_level": "high", "score": 85}}
        result = dag.evaluate_condition(
            "${risk_assessment.risk_level} == 'low'",
            task_outputs,
        )
        assert result is False

    def test_risk_level_not_equals_low(self):
        """Inequality check on risk level."""
        dag = self._make_security_dag()
        assert dag.evaluate_condition(
            "${risk_assessment.risk_level} != 'low'",
            {"risk_assessment": {"risk_level": "high"}},
        ) is True
        assert dag.evaluate_condition(
            "${risk_assessment.risk_level} != 'low'",
            {"risk_assessment": {"risk_level": "low"}},
        ) is False

    # ── Approval conditions ──

    def test_approval_status_allows_deploy(self):
        """Condition ${approval.status} == 'approved' gates on approval."""
        dag = self._make_security_dag()
        # Approved
        assert dag.evaluate_condition(
            "${approval.status} == 'approved'",
            {"approval": {"status": "approved", "reviewed_by": "admin"}},
        ) is True
        # Not approved
        assert dag.evaluate_condition(
            "${approval.status} == 'approved'",
            {"approval": {"status": "pending", "reviewed_by": None}},
        ) is False

    def test_approval_not_equals_pending(self):
        """Inequality check on approval status acts as an approval gate."""
        dag = self._make_security_dag()
        # When status is not "pending", treat as approved
        assert dag.evaluate_condition(
            "${approval.status} != 'pending'",
            {"approval": {"status": "approved", "reviewed_by": "admin"}},
        ) is True
        # When status is still "pending", condition fails
        assert dag.evaluate_condition(
            "${approval.status} != 'pending'",
            {"approval": {"status": "pending", "reviewed_by": None}},
        ) is False

    # ── Compliance conditions ──

    def test_compliance_checks_pass(self):
        """Condition ${compliance.checks_passed} > 0 gates on compliance."""
        dag = self._make_security_dag()
        assert dag.evaluate_condition(
            "${compliance.checks_passed} > 0",
            {"compliance": {"checks_passed": 5, "total": 5}},
        ) is True

    def test_compliance_checks_fail(self):
        """Condition fails when no compliance checks pass."""
        dag = self._make_security_dag()
        assert dag.evaluate_condition(
            "${compliance.checks_passed} > 0",
            {"compliance": {"checks_passed": 0, "total": 5}},
        ) is False

    # ── Existence checks ──

    def test_security_field_exists(self):
        """The 'exists' operator works on security-related fields."""
        dag = self._make_security_dag()
        # Field exists (even if falsy value like 0)
        assert dag.evaluate_condition(
            "${security_scan.critical} exists",
            {"security_scan": {"critical": 0}},
        ) is True
        # Field does not exist
        assert dag.evaluate_condition(
            "${security_scan.nonexistent} exists",
            {"security_scan": {"critical": 0}},
        ) is False

    def test_security_field_not_exists(self):
        """The 'not_exists' operator on security fields."""
        dag = self._make_security_dag()
        assert dag.evaluate_condition(
            "${security_scan.undefined} not_exists",
            {"security_scan": {"vulnerabilities": 5}},
        ) is True
        assert dag.evaluate_condition(
            "${security_scan.vulnerabilities} not_exists",
            {"security_scan": {"vulnerabilities": 5}},
        ) is False

    # ── Edge condition gating ──

    def test_edge_condition_gates_downstream_task(self):
        """WorkflowDAG.get_effective_dependents filters downstream tasks
        based on edge conditions with security-related checks."""
        dag = WorkflowDAG(WorkflowSpec(
            name="security_workflow",
            version="1.0.0",
            tasks=[
                WorkflowTask(id="security_scan", capability="scan@1"),
                WorkflowTask(id="deploy", capability="deploy@1"),
                WorkflowTask(id="notify", capability="notify@1"),
            ],
            edges=[
                WorkflowEdge(
                    from_task="security_scan",
                    to_task="deploy",
                    data={},
                    condition="${security_scan.vulnerabilities} == 0",
                ),
                WorkflowEdge(
                    from_task="security_scan",
                    to_task="notify",
                    data={},
                    # No condition — always traversed
                ),
            ],
        ))

        # When vulnerabilities == 0, both deploy and notify are enabled
        enabled = dag.get_effective_dependents(
            "security_scan",
            {"security_scan": {"vulnerabilities": 0}},
        )
        enabled_ids = {t.id for t in enabled}
        assert "deploy" in enabled_ids
        assert "notify" in enabled_ids

        # When vulnerabilities > 0, only notify is enabled (deploy blocked)
        enabled = dag.get_effective_dependents(
            "security_scan",
            {"security_scan": {"vulnerabilities": 5}},
        )
        enabled_ids = {t.id for t in enabled}
        assert "deploy" not in enabled_ids
        assert "notify" in enabled_ids

    def test_has_satisfied_inbound_path_with_security_conditions(self):
        """WorkflowDAG.has_satisfied_inbound_path checks if at least one
        inbound edge's security condition is satisfied."""
        dag = WorkflowDAG(WorkflowSpec(
            name="secure_deploy",
            version="1.0.0",
            tasks=[
                WorkflowTask(id="auto_scan", capability="scan@1"),
                WorkflowTask(id="manual_review", capability="review@1"),
                WorkflowTask(id="deploy", capability="deploy@1"),
            ],
            edges=[
                WorkflowEdge(
                    from_task="auto_scan",
                    to_task="deploy",
                    condition="${auto_scan.risk_level} == 'low'",
                ),
                WorkflowEdge(
                    from_task="manual_review",
                    to_task="deploy",
                    condition="${manual_review.status} == 'approved'",
                ),
            ],
        ))

        # Neither path satisfied
        assert dag.has_satisfied_inbound_path(
            "deploy",
            {
                "auto_scan": {"risk_level": "high"},
                "manual_review": {"status": "pending"},
            },
        ) is False

        # Auto-scan path satisfied
        assert dag.has_satisfied_inbound_path(
            "deploy",
            {
                "auto_scan": {"risk_level": "low"},
                "manual_review": {"status": "pending"},
            },
        ) is True

        # Manual review path satisfied
        assert dag.has_satisfied_inbound_path(
            "deploy",
            {
                "auto_scan": {"risk_level": "high"},
                "manual_review": {"status": "approved"},
            },
        ) is True

        # Both paths satisfied
        assert dag.has_satisfied_inbound_path(
            "deploy",
            {
                "auto_scan": {"risk_level": "low"},
                "manual_review": {"status": "approved"},
            },
        ) is True

    # ── skip_if conditions ──

    def test_skip_if_on_security_condition(self):
        """WorkflowDAG.should_skip_task with security-based conditions."""
        dag = WorkflowDAG(WorkflowSpec(
            name="conditional_skip",
            version="1.0.0",
            tasks=[
                WorkflowTask(id="pre_check", capability="check@1"),
                WorkflowTask(
                    id="detailed_scan",
                    capability="deep_scan@1",
                    skip_if="${pre_check.risk_level} == 'low'",
                ),
            ],
            edges=[
                WorkflowEdge(from_task="pre_check", to_task="detailed_scan"),
            ],
        ))

        # Low risk → skip detailed scan
        assert dag.should_skip_task(
            "detailed_scan",
            {"pre_check": {"risk_level": "low"}},
        ) is True

        # High risk → do not skip
        assert dag.should_skip_task(
            "detailed_scan",
            {"pre_check": {"risk_level": "high"}},
        ) is False

        # No task output → do not skip (safe default)
        assert dag.should_skip_task("detailed_scan", {}) is False

    # ── Edge conditions with multiple security checks ──

    def test_compound_security_condition(self):
        """Edge condition combining security checks via 'in' operator."""
        dag = WorkflowDAG(WorkflowSpec(
            name="compound_check",
            version="1.0.0",
            tasks=[
                WorkflowTask(id="scan", capability="scan@1"),
                WorkflowTask(id="deploy", capability="deploy@1"),
            ],
            edges=[
                WorkflowEdge(
                    from_task="scan",
                    to_task="deploy",
                    condition="${scan.risk_level} in 'low,medium'",
                ),
            ],
        ))

        assert dag.evaluate_condition(
            "${scan.risk_level} in 'low,medium'",
            {"scan": {"risk_level": "low"}},
        ) is True
        assert dag.evaluate_condition(
            "${scan.risk_level} in 'low,medium'",
            {"scan": {"risk_level": "medium"}},
        ) is True
        assert dag.evaluate_condition(
            "${scan.risk_level} in 'low,medium'",
            {"scan": {"risk_level": "high"}},
        ) is False

    # ── Missing task data ──

    def test_missing_security_task_output(self):
        """Condition referencing missing task output returns False."""
        dag = self._make_security_dag()
        # Task 'security_scan' has no output yet
        result = dag.evaluate_condition(
            "${security_scan.vulnerabilities} == 0",
            {},
        )
        assert result is False

    # ── Helper ──

    @staticmethod
    def _make_security_dag() -> WorkflowDAG:
        """Create a minimal DAG with security-related tasks for condition
        testing. Edges are empty because individual tests set up their own
        edge structures."""
        return WorkflowDAG(WorkflowSpec(
            name="security_workflow",
            version="1.0.0",
            tasks=[
                WorkflowTask(
                    id="security_scan",
                    capability="security.scan@1.0",
                ),
                WorkflowTask(
                    id="risk_assessment",
                    capability="risk.assess@1.0",
                ),
                WorkflowTask(
                    id="approval",
                    capability="approval.check@1.0",
                ),
                WorkflowTask(
                    id="compliance",
                    capability="compliance.check@1.0",
                ),
                WorkflowTask(
                    id="deploy",
                    capability="deploy.app@1.0",
                ),
            ],
            edges=[],
        ))
