"""
Intent OS — Workflow YAML Parser Tests

Tests cover:
  1. Valid workflow YAML parsing
  2. Required field validation
  3. Variable reference validation
  4. Duration string parsing
  5. Semantics parsing defaults
  6. Error message quality
  7. Edge cases
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

# Ensure project root is in path
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.workflow import WorkflowValidationError
from core.workflow_parser import (
    WorkflowParseError,
    _parse_duration,
    _parse_semantics,
    _validate_variable_references,
    parse_workflow_yaml,
)
from core.workflow import ExecutionSemantics, WorkflowTask, WorkflowEdge


# ──────────────────────────────────────────────
# Sample Valid Workflow YAML
# ──────────────────────────────────────────────

VALID_YAML = """
kind: Workflow
metadata:
  name: test_workflow
  version: 1.0.0
  description: "A test workflow"

spec:
  goal: "Test goal"

  tasks:
    - id: search
      capability: web_search@1.0.0
      description: "Search step"
      input:
        query: "${goal.query}"

    - id: analyze
      capability: text_analyze@1.0.0
      description: "Analyze step"
      input:
        text: "${search.results}"

    - id: report
      capability: report_generate@1.0.0
      description: "Report step"
      input:
        content: "${analyze.result}"

  edges:
    - from: search
      to: analyze
    - from: analyze
      to: report

  semantics:
    retry:
      strategy: exponential
      max_attempts: 3
    timeout:
      task: 60s
      workflow: 300s
    failure:
      propagation: deferred
    parallel:
      strategy: sequential
"""


# ──────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────

class TestWorkflowParser:
    """Test valid workflow YAML parsing."""

    def test_parse_valid_yaml(self):
        """Valid workflow YAML should produce a WorkflowSpec."""
        spec = parse_workflow_yaml(VALID_YAML)
        assert spec.name == "test_workflow"
        assert spec.version == "1.0.0"
        assert len(spec.tasks) == 3
        assert len(spec.edges) == 2

    def test_task_ids_parsed(self):
        """Task IDs should be correctly extracted."""
        spec = parse_workflow_yaml(VALID_YAML)
        task_ids = [t.id for t in spec.tasks]
        assert task_ids == ["search", "analyze", "report"]

    def test_capability_references(self):
        """Capability references should be preserved."""
        spec = parse_workflow_yaml(VALID_YAML)
        assert spec.get_task("search").capability == "web_search@1.0.0"
        assert spec.get_task("analyze").capability == "text_analyze@1.0.0"

    def test_input_bindings(self):
        """Task input bindings should be preserved."""
        spec = parse_workflow_yaml(VALID_YAML)
        assert spec.get_task("search").input["query"] == "${goal.query}"
        assert spec.get_task("analyze").input["text"] == "${search.results}"

    def test_edge_structure(self):
        """Edges should have correct from/to."""
        spec = parse_workflow_yaml(VALID_YAML)
        assert spec.edges[0].from_task == "search"
        assert spec.edges[0].to_task == "analyze"
        assert spec.edges[1].from_task == "analyze"
        assert spec.edges[1].to_task == "report"


class TestWorkflowParserValidation:
    """Test validation error handling."""

    def test_missing_kind(self):
        """Missing 'kind' field should raise."""
        yaml_str = """
metadata:
  name: test
  version: 1.0.0
spec:
  tasks: []
  edges: []
"""
        import pytest
        with pytest.raises(WorkflowParseError) as exc:
            parse_workflow_yaml(yaml_str)
        assert "kind" in str(exc.value).lower()

    def test_wrong_kind(self):
        """Wrong 'kind' value should raise."""
        yaml_str = """
kind: NotWorkflow
metadata:
  name: test
  version: 1.0.0
spec:
  tasks: []
  edges: []
"""
        import pytest
        with pytest.raises(WorkflowParseError) as exc:
            parse_workflow_yaml(yaml_str)
        assert "kind" in str(exc.value).lower()

    def test_missing_name(self):
        """Missing metadata.name should raise."""
        yaml_str = """
kind: Workflow
metadata:
  version: 1.0.0
spec:
  tasks: []
  edges: []
"""
        import pytest
        with pytest.raises(WorkflowParseError):
            parse_workflow_yaml(yaml_str)

    def test_missing_version(self):
        """Missing metadata.version should raise."""
        yaml_str = """
kind: Workflow
metadata:
  name: test
spec:
  tasks: []
  edges: []
"""
        import pytest
        with pytest.raises(WorkflowParseError):
            parse_workflow_yaml(yaml_str)

    def test_empty_tasks(self):
        """Empty tasks list should raise."""
        yaml_str = """
kind: Workflow
metadata:
  name: test
  version: 1.0.0
spec:
  tasks: []
  edges: []
"""
        import pytest
        with pytest.raises(WorkflowParseError):
            parse_workflow_yaml(yaml_str)

    def test_task_missing_id(self):
        """Task missing 'id' should raise."""
        yaml_str = """
kind: Workflow
metadata:
  name: test
  version: 1.0.0
spec:
  tasks:
    - capability: test@1.0
      input: {}
  edges: []
"""
        import pytest
        with pytest.raises(WorkflowParseError):
            parse_workflow_yaml(yaml_str)

    def test_duplicate_task_ids(self):
        """Duplicate task IDs should raise."""
        yaml_str = """
kind: Workflow
metadata:
  name: test
  version: 1.0.0
spec:
  tasks:
    - id: A
      capability: test@1.0
      input: {}
    - id: A
      capability: test@1.0
      input: {}
  edges: []
"""
        import pytest
        with pytest.raises(WorkflowParseError):
            parse_workflow_yaml(yaml_str)

    def test_edge_unknown_task(self):
        """Edge referencing unknown task should raise."""
        yaml_str = """
kind: Workflow
metadata:
  name: test
  version: 1.0.0
spec:
  tasks:
    - id: A
      capability: test@1.0
      input: {}
  edges:
    - from: A
      to: UNKNOWN
"""
        import pytest
        with pytest.raises(WorkflowParseError):
            parse_workflow_yaml(yaml_str)


class TestWorkflowParserSemantics:
    """Test semantics parsing."""

    def test_default_semantics(self):
        """Empty semantics should produce defaults."""
        yaml_str = """
kind: Workflow
metadata:
  name: test
  version: 1.0.0
spec:
  tasks:
    - id: A
      capability: test@1.0
      input: {}
  edges: []
"""
        spec = parse_workflow_yaml(yaml_str)
        assert spec.semantics.retry.max_attempts == 3
        assert spec.semantics.timeout.task_ms == 30000
        assert spec.semantics.failure.max_failures == 1

    def test_custom_retry(self):
        """Custom retry should be parsed."""
        yaml_str = """
kind: Workflow
metadata:
  name: test
  version: 1.0.0
spec:
  tasks:
    - id: A
      capability: test@1.0
      input: {}
  edges: []
  semantics:
    retry:
      strategy: fixed
      max_attempts: 5
      initial_interval: 2s
"""
        spec = parse_workflow_yaml(yaml_str)
        assert spec.semantics.retry.max_attempts == 5
        assert spec.semantics.retry.initial_interval_ms == 2000

    def test_duration_parsing(self):
        """Duration strings should parse correctly."""
        assert _parse_duration("30s") == 30000
        assert _parse_duration("5m") == 300000
        assert _parse_duration("100ms") == 100
        assert _parse_duration(None) == 30000
        assert _parse_duration("unknown") == 30000
        assert _parse_duration("10") == 10000


class TestWorkflowParserVariableRefs:
    """Test variable reference validation."""

    def test_goal_reference_valid(self):
        """${goal.field} references should be valid."""
        tasks = [WorkflowTask(id="search", capability="t@1", input={"q": "${goal.query}"})]
        _validate_variable_references(tasks, [], "test goal")

    def test_task_reference_valid(self):
        """${task_id.field} referencing an existing task should be valid."""
        tasks = [
            WorkflowTask(id="search", capability="t@1", input={"q": "test"}),
            WorkflowTask(id="analyze", capability="t@1", input={"text": "${search.results}"}),
        ]
        _validate_variable_references(tasks, [], "test goal")

    def test_task_reference_unknown(self):
        """${unknown_task.field} should raise."""
        tasks = [
            WorkflowTask(id="analyze", capability="t@1", input={"text": "${nonexistent.results}"}),
        ]
        import pytest
        with pytest.raises(WorkflowParseError):
            _validate_variable_references(tasks, [], "test goal")

    def test_nested_variable_references(self):
        """Nested variable references in dict values should be checked."""
        tasks = [
            WorkflowTask(id="search", capability="t@1", input={"q": "test"}),
            WorkflowTask(id="analyze", capability="t@1", input={
                "config": {"source": "${search.results}"},
            }),
        ]
        _validate_variable_references(tasks, [], "test goal")

    def test_edge_data_variables(self):
        """Variable references in edge data should be checked."""
        tasks = [
            WorkflowTask(id="A", capability="t@1", input={}),
            WorkflowTask(id="B", capability="t@1", input={}),
        ]
        edges = [WorkflowEdge(from_task="A", to_task="B", data={"key": "${A.output}"})]
        _validate_variable_references(tasks, edges, "test goal")


class TestWorkflowParserFileLoading:
    """Test loading from actual YAML files."""

    def test_load_research_workflow(self):
        """research_workflow.yaml should parse successfully."""
        yaml_path = Path(_project_root) / "examples" / "research_workflow.yaml"
        if yaml_path.exists():
            spec = parse_workflow_yaml(yaml_path)
            assert spec.name == "company_research"
            assert len(spec.tasks) == 4

    def test_error_message_readable(self):
        """Error messages should be human-readable."""
        bad_yaml = """
kind: Workflow
metadata:
  name: ""
  version: ""
spec:
  tasks:
    - id: A
      capability: test@1.0
      input: {}
  edges: []
"""
        import pytest
        with pytest.raises(WorkflowParseError) as exc:
            parse_workflow_yaml(bad_yaml)
        msg = str(exc.value)
        # Should mention the missing field
        assert "name" in msg or "version" in msg
