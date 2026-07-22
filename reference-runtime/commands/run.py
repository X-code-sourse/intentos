"""Intent OS CLI — run command."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any
from core.recorder import save_execution_record
from commands.helpers import load_manifest, setup_executor, save_to_event_store, display_record

def cmd_run(args: argparse.Namespace) -> None:
    manifest, _ = load_manifest(args.manifest)
    input_data = {}
    if args.input:
        try: input_data = json.loads(args.input)
        except json.JSONDecodeError: input_data = {"text": args.input}
    elif args.input_file:
        try: input_data = json.loads(Path(args.input_file).read_text())
        except (json.JSONDecodeError, FileNotFoundError) as exc:
            print(f"Error reading input file: {exc}", file=sys.stderr); sys.exit(1)
    executor = setup_executor()
    adapters = executor.get_available_adapters()
    if not adapters:
        print("Error: No runtime adapters available.", file=sys.stderr)
        print("Install at least one: pip install openai  or  pip install anthropic", file=sys.stderr)
        sys.exit(1)
    adapter_name = args.adapter or adapters[0]
    if adapter_name not in executor._adapters:
        print(f"Error: Adapter '{adapter_name}' not loaded.", file=sys.stderr)
        print(f"Available: {', '.join(adapters)}", file=sys.stderr)
        sys.exit(1)
    print(f"\nExecuting '{manifest.id}' via '{adapter_name}'...")
    try:
        record = executor.execute(manifest=manifest, input_data=input_data, adapter_name=adapter_name)
    except Exception as exc:
        print(f"\nExecution failed: {exc}", file=sys.stderr); sys.exit(1)
    display_record(record, args.output)
    try: save_to_event_store(record)
    except Exception: pass
    if args.save:
        save_path = save_execution_record(record, args.save)
        print(f"\nExecution record saved to: {save_path}")
