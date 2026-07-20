"""Capability scaffolding — ``agentos capability scaffold`` (RFC-0400 §5)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# ── Template constants ──────────────────────────────────────────────

TEMPLATE__INIT_PY = '''"""{{name}} capability — Agent OS SDK."""
from .handler import handler

__all__ = ["handler"]
'''

TEMPLATE_MANIFEST = """task_type: {{task_type}}
display_name: {{display_name}}
description: {{description}}
version: {{version}}
tags: [{{tags}}]
source: external
enabled: true
entry_point: handler.handler
{% if with_schema %}
input_schema:
  type: object
  properties:
    query:
      type: string
      description: Input query for this capability
output_schema:
  type: object
  properties:
    result:
      type: string
{% endif %}
"""

TEMPLATE_HANDLER = '''"""{{name}} capability — Agent OS SDK scaffold."""
from __future__ import annotations
from typing import Any


def handler(task, context) -> Any:
    """Execute the {{task_type}} capability.

    Args:
        task: PlannedTask — current task metadata (id, type, params).
        context: dict — outputs from completed tasks, keyed by task_id.

    Returns:
        Any — result injected into downstream task contexts.
    """
    _ = context  # available for cross-task data access

    # ── TODO: implement your capability logic here ──────────────────
    query = task.params.get("query", "")
    result = query + " processed by {{task_type}}"

    return {"result": result}
'''

TEMPLATE_TEST = '''"""Tests for the {{task_type}} capability."""
from {{package_name}}.handler import handler
from unittest.mock import MagicMock


def test_handler_returns_result():
    task = MagicMock()
    task.id = "t1"
    task.type = "{{task_type}}"
    task.params = {"query": "test"}
    context = {}

    result = handler(task, context)
    assert result is not None
    assert "result" in result


def test_handler_receives_params():
    task = MagicMock()
    task.id = "t1"
    task.type = "{{task_type}}"
    task.params = {"query": "hello world"}
    context = {}

    result = handler(task, context)
    assert "hello world" in result["result"]
'''

TEMPLATE_REQUIREMENTS = """# {{name}} capability dependencies
# agentos>=0.1.0
"""

TEMPLATE_WORKFLOW = """id: {{task_type}}-demo
name: {{display_name}} Demo
description: A demo workflow using the {{task_type}} capability
tasks:
  - id: step1
    type: {{task_type}}
    params:
      query: "Agent OS"
    enabled: true
"""


def scaffold(
    name: str,
    output_dir: str | Path = ".",
    *,
    display_name: str | None = None,
    description: str = "",
    version: str = "0.1.0",
    tags: str = "demo",
    with_schema: bool = False,
) -> Path:
    """Generate a new external capability scaffold.

    Creates a directory with all necessary files to start developing
    an Agent OS Capability.

    Args:
        name: Capability name (used as task_type and directory name).
            Must be lowercase kebab-case.
        output_dir: Parent directory for the new capability.
        display_name: Human-readable name (defaults to capitalized ``name``).
        description: Short description of the capability.
        version: SemVer version string.
        tags: Comma-separated tag string.
        with_schema: If True, include input_schema/output_schema in manifest.

    Returns:
        Path to the created capability directory.

    Raises:
        ValueError: If ``name`` is not valid kebab-case.
        FileExistsError: If the output directory already exists.
    """
    import re

    if not re.match(r"^[a-z][a-z0-9-]{1,63}$", name):
        raise ValueError(
            f"name '{name}' is invalid: must be lowercase kebab-case "
            f"(start with a letter, 2-64 chars, lowercase letters/digits/hyphens)"
        )

    dest = Path(output_dir).resolve() / name
    if dest.exists():
        raise FileExistsError(f"Directory already exists: {dest}")

    if display_name is None:
        display_name = name.replace("-", " ").title()

    # Package name: replace hyphens with underscores for valid Python identifier
    package_name = name.replace("-", "_")

    context: dict[str, Any] = {
        "name": name,
        "task_type": name,
        "package_name": package_name,
        "display_name": display_name,
        "description": description or f"{display_name} capability",
        "version": version,
        "tags": tags,
        "with_schema": with_schema,
    }

    # ── Create directory structure ──────────────────────────────────
    dirs = [
        dest,
        dest / "tests",
        dest / "examples",
    ]
    for d in dirs:
        d.mkdir(parents=True)

    # ── Write files ─────────────────────────────────────────────────
    files = {
        dest / "__init__.py": _render(TEMPLATE__INIT_PY, context),
        dest / "manifest.yaml": _render(TEMPLATE_MANIFEST, context),
        dest / "handler.py": _render(TEMPLATE_HANDLER, context),
        dest / "requirements.txt": _render(TEMPLATE_REQUIREMENTS, context),
        dest / "tests" / "__init__.py": "",
        dest / "tests" / "test_handler.py": _render(TEMPLATE_TEST, context),
        dest / "examples" / f"{name}-workflow.yaml": _render(TEMPLATE_WORKFLOW, context),
    }

    for filepath, content in files.items():
        filepath.write_text(content, encoding="utf-8")

    return dest


# ── Template rendering (simple Jinja2-free string substitution) ─────


def _render(template: str, context: dict[str, Any]) -> str:
    """Render a template with simple ``{{var}}`` substitution.

    Supports ``{% if var %}...{% endif %}`` blocks (no else/elif).
    This is intentionally minimal — no Jinja2 dependency required.
    """
    result = template
    # Process {% if with_schema %}...{% endif %} blocks
    import re as _re

    def _if_block(m):
        var_name = m.group(1).strip()
        inner = m.group(2)
        return inner if context.get(var_name) else ""

    result = _re.sub(
        r"\{%\s*if\s+(\w+)\s*%\}(.*?)\{%\s*endif\s*%\}",
        _if_block,
        result,
        flags=_re.DOTALL,
    )

    # Replace {{var}} placeholders
    def _var(m):
        var_name = m.group(1).strip()
        return str(context.get(var_name, m.group(0)))

    result = _re.sub(r"\{\{(\w+)\}\}", _var, result)

    return result
