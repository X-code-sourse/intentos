"""
Intent OS — CLI Command: import

Imports a capability from an external format (openai-function, mcp-server).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from commands.helpers import get_registry_store

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def cmd_import(args: Any) -> None:
    """Import a capability from an external format."""
    from tools.importer import Importer

    _, registry = get_registry_store()
    importer = Importer(registry=registry, auto_register=True)

    source = args.source
    output_dir = args.output_dir

    if args.format == "openai-function":
        if source == "-":
            content = sys.stdin.read()
        else:
            path = Path(source)
            if not path.exists():
                print(f"Error: File not found: {path}", file=sys.stderr)
                sys.exit(1)
            content = path.read_text(encoding="utf-8")

        try:
            result = importer.import_openai_function(
                content,
                output_dir=output_dir,
                publisher=args.publisher,
                tags=args.tags.split(",") if args.tags else ["imported", "openai"],
            )
        except Exception as exc:
            print(f"Import failed: {exc}", file=sys.stderr)
            sys.exit(1)

        print(f"[OK] Imported '{result.manifest.name}@{result.manifest.version}'")
        print(f"  Source: openai-function")
        if result.output_path:
            print(f"  Manifest: {result.output_path}")
        if result.registered:
            print(f"  Registry: registered")

    elif args.format == "mcp-server":
        try:
            results = importer.import_mcp_server(
                source,
                output_dir=output_dir,
                publisher=args.publisher,
                tags=args.tags.split(",") if args.tags else ["imported", "mcp"],
                timeout=args.timeout,
            )
        except Exception as exc:
            print(f"MCP import failed: {exc}", file=sys.stderr)
            sys.exit(1)

        print(f"[OK] Imported {len(results)} capabilities from MCP server:")
        for r in results:
            status = "registered" if r.registered else "converted"
            print(f"  - {r.manifest.name} ({status})")
            if r.output_path:
                print(f"    Manifest: {r.output_path}")

    else:
        print(f"Error: Unknown import format '{args.format}'. Supported: openai-function, mcp-server",
              file=sys.stderr)
        sys.exit(1)
