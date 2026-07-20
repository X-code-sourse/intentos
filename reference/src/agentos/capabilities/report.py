"""Report capability — compiles final Markdown output."""
from ..models import PlannedTask
from typing import Any
import re

def report(task: PlannedTask, context: dict[str, Any]) -> str:
    sections = task.params.get("sections", [])
    lines = []
    for sec in sections:
        title = sec.get("title", "")
        content = sec.get("content", "")
        resolved = _resolve_template(content, context)
        if title:
            lines.append(f"## {title}")
        lines.append(resolved)
    return "\n\n".join(lines)


def _resolve_template(template: str, context: dict[str, Any]) -> str:
    """Simple {{variable}} replacement from context."""
    def _replacer(m):
        key = m.group(1).strip()
        val = context.get(key, m.group(0))
        val = context.get(key, "")
        return str(val) if val is not None else m.group(0)
    return re.sub(r"\{\{(.+?)\}\}", _replacer, template)
