"""
Intent OS — CLI Command: list

Lists available adapters and registered capabilities.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from commands.helpers import setup_executor, get_registry_store

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def cmd_list(args: Any) -> None:
    """List available adapters and registered capabilities."""
    executor = setup_executor()
    adapters = executor.get_available_adapters()
    print(f"Available adapters: {', '.join(adapters) if adapters else '(none)'}")
    _, registry = get_registry_store()
    caps = registry.list_capabilities()
    if caps:
        print(f"\nRegistered capabilities ({len(caps)}):")
        for cap in caps:
            print(f"  {cap['name']}@{cap['version']}")
    else:
        print("\nNo capabilities registered")
