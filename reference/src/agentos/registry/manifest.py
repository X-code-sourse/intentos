"""CapabilityManifest dataclass + YAML loader (RFC-0300)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class CapabilityManifest:
    """Structured metadata for a registered Capability."""
    task_type: str = ""
    fn: Callable | None = None
    display_name: str = ""
    description: str = ""
    version: str = "0.1.0"
    tags: list[str] = field(default_factory=list)
    source: str = "builtin"
    enabled: bool = True
    entry_point: str = ""
    input_schema: dict | None = None
    output_schema: dict | None = None


def load_manifest_from_yaml(path: str | Path) -> CapabilityManifest:
    """Load a CapabilityManifest from a YAML file."""
    import yaml
    with open(path) as f:
        raw = yaml.safe_load(f)
    return CapabilityManifest(
        task_type=raw.get("task_type", ""),
        display_name=raw.get("display_name", ""),
        description=raw.get("description", ""),
        version=raw.get("version", "0.1.0"),
        tags=raw.get("tags", []),
        source=raw.get("source", "external"),
        enabled=raw.get("enabled", True),
        entry_point=raw.get("entry_point", ""),
        input_schema=raw.get("input_schema"),
        output_schema=raw.get("output_schema"),
    )
