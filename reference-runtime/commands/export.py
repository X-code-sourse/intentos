"""
Intent OS — CLI Command: export

Exports a capability to an external format (openai, mcp).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def cmd_export(args: Any) -> None:
    """Export a capability to an external format."""
    from tools.exporter import Exporter

    exporter = Exporter(registry=None)
    source = args.source
    output_file = args.output

    try:
        if args.format == "openai":
            if output_file:
                exporter.export_openai_to_file(
                    source, output_file,
                    as_tool=args.as_tool,
                )
                print(f"[OK] Exported to '{output_file}'")
            else:
                content = exporter.export_openai(source, as_tool=args.as_tool)
                print(content)

        elif args.format == "mcp":
            if output_file:
                exporter.export_mcp_tool_to_file(source, output_file)
                print(f"[OK] Exported to '{output_file}'")
            else:
                content = exporter.export_mcp_tool(source)
                print(content)

        else:
            print(f"Error: Unknown export format '{args.format}'. Supported: openai, mcp",
                  file=sys.stderr)
            sys.exit(1)

    except Exception as exc:
        print(f"Export failed: {exc}", file=sys.stderr)
        sys.exit(1)
