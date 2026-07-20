"""Shared test fixtures for Agent OS reference implementation."""

import sys
from pathlib import Path

# Ensure src/ is on the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from agentos.backbone.bus import EventBus
from agentos.backbone.event import Event
from agentos.execution_engine import ExecutionEngine
from agentos.workflow_loader import load_from_path
from agentos.planner import plan as do_plan
from agentos.reviewer import review as do_review
from agentos.reporter import format_report


@pytest.fixture
def bus():
    """Fresh EventBus instance per test."""
    return EventBus()


@pytest.fixture
def engine(bus):
    """ExecutionEngine with bus and minimal mock executors."""
    eng = ExecutionEngine(bus=bus)
    eng.pool.register("search", lambda t, c: t.params.get("query", ""))
    eng.pool.register("llm", lambda t, c: "llm output")
    eng.pool.register("gather", lambda t, c: {"outputs": {}, "status": "ok"})
    eng.pool.register("review", lambda t, c: {"status": "passed"})
    eng.pool.register("report", lambda t, c: "# Test Report")
    return eng


@pytest.fixture
def stock_plan():
    """Load and compile stock_research workflow."""
    wf = load_from_path(
        Path(__file__).parent.parent.parent
        / "examples"
        / "workflows"
        / "stock_research.yaml"
    )
    return do_plan(wf, extra_params={"query": "test"})
