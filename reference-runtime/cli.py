#!/usr/bin/env python3
"""
Intent OS — Reference Runtime CLI

The main entry point for the Intent OS Reference Runtime.

Usage:
    # Validate and execute capabilities
    intent-os validate manifest.yaml
    intent-os run manifest.yaml --adapter openai --input '{"text": "..."}'
    intent-os compare manifest.yaml --input '{"text": "..."}'

    # Manage the capability registry
    intent-os registry list
    intent-os registry register my_cap.yaml
    intent-os registry get <name>
    intent-os registry unregister <name>
    intent-os registry export snapshot.json

    # Plan and run workflows
    intent-os workflow plan "research NVIDIA stock"
    intent-os workflow run workflow.yaml --input '{"company":"NVIDIA"}'

    # Query execution history
    intent-os event list
    intent-os event trace <trace_id>
    intent-os event query --capability <name>

    # Analyze execution data
    intent-os analytics summary
    intent-os analytics capabilities
    intent-os analytics failures
    intent-os analytics suggestions
    intent-os analytics export cost_model_data.json

    # Start MCP Server
    intent-os mcp-server start --port 8080 --adapter ollama
    intent-os mcp-server status

    # Import/Export capabilities
    intent-os import openai-function ./my_tool.json --publisher "me"
    intent-os import mcp-server http://localhost:8080/mcp
    intent-os export openai manifest.yaml --as-tool
    intent-os export mcp manifest.yaml
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from core.executor import Executor
from core.models import ValidationError
from core.parser import parse_manifest, ManifestParseError
from core.recorder import (
    compare_records,
    save_execution_record,
)

# Ensure the project root is in the path when running locally
_project_root = Path(__file__).parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def _load_manifest(path_str: str) -> tuple[Any, Any]:
    """Load and validate a manifest file."""
    path = Path(path_str)
    if not path.exists():
        print(f"Error: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    if path.suffix not in (".yaml", ".yml"):
        print(f"Warning: Expected .yaml file, got '{path.suffix}'", file=sys.stderr)

    try:
        manifest, validation = parse_manifest(path)
    except ManifestParseError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if validation.errors:
        print("Manifest validation errors:", file=sys.stderr)
        for err in validation.errors:
            print(f"  [{err.severity}] {err.field}: {err.message}", file=sys.stderr)
        sys.exit(1)

    if validation.warnings:
        for warn in validation.warnings:
            print(f"  [{warn.severity}] {warn.field}: {warn.message}", file=sys.stderr)

    print(f"[OK] Manifest '{manifest.id}' loaded successfully")
    return manifest, validation


def _setup_executor(adapters: list[str] | None = None) -> Executor:
    """Create an executor with the requested adapters loaded."""
    executor = Executor()

    # Detect available API keys
    has_api_keys = bool(os.environ.get("OPENAI_API_KEY")) or bool(os.environ.get("OPENROUTER_API_KEY"))
    has_ollama = False

    # Always attempt to load all available adapters
    adapter_classes = []

    try:
        from adapters.openai_adapter import OpenAIAdapter
        adapter_classes.append(OpenAIAdapter)
    except ImportError:
        pass

    try:
        from adapters.anthropic_adapter import AnthropicAdapter
        adapter_classes.append(AnthropicAdapter)
    except ImportError:
        pass

    try:
        from adapters.github_models_adapter import GitHubModelsAdapter
        adapter_classes.append(GitHubModelsAdapter)
    except ImportError:
        pass

    try:
        from adapters.openrouter_adapter import OpenRouterAdapter
        adapter_classes.append(OpenRouterAdapter)
    except ImportError:
        pass

    try:
        from adapters.ollama_adapter import OllamaAdapter
        adapter_classes.append(OllamaAdapter)
    except ImportError:
        pass

    for adapter_cls in adapter_classes:
        try:
            adapter = adapter_cls()
            # Check Ollama availability
            if adapter.name == "ollama":
                try:
                    import urllib.request
                    req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
                    resp = urllib.request.urlopen(req, timeout=1)
                    if resp.status == 200:
                        executor.register_adapter(adapter.name, adapter)
                        has_ollama = True
                except Exception:
                    pass
            else:
                executor.register_adapter(adapter.name, adapter)
        except Exception as exc:
            print(f"  Warning: Failed to load {adapter_cls.__name__}: {exc}",
                  file=sys.stderr)

    if executor.get_available_adapters():
        print(f"  Adapters loaded: {', '.join(executor.get_available_adapters())}")
        if has_ollama and not has_api_keys:
            print(f"  Using local Ollama (free, no API key needed)")
            print(f"  Tip: Set OPENAI_API_KEY or OPENROUTER_API_KEY for cloud models")
    else:
        print("  Warning: No adapters loaded.")
        print("  Tip: Install Ollama (https://ollama.com) and run: ollama pull llama3.2:1b")
        print("  Or set OPENAI_API_KEY for cloud models.")

    return executor


def _get_registry_store() -> tuple[Path, Any]:
    """Get or create the default persistent registry store."""
    store_dir = Path.home() / ".intent-os"
    store_dir.mkdir(parents=True, exist_ok=True)
    db_path = store_dir / "store.db"
    from core.registry import CapabilityRegistry
    registry = CapabilityRegistry(db_path=str(db_path))
    return db_path, registry


def _get_event_store() -> Any:
    """Get or create the default persistent Event Store."""
    store_dir = Path.home() / ".intent-os"
    store_dir.mkdir(parents=True, exist_ok=True)
    db_path = store_dir / "events.db"
    from core.event_store import EventStore
    return EventStore(db_path=str(db_path))


def _save_to_event_store(record: Any) -> None:
    """Save an ExecutionRecord to the default Event Store."""
    store = _get_event_store()
    store.save_events_batch(record.events)
    store.save_execution_record(record)


# ──────────────────────────
# Command handlers
# ──────────────────────────

def cmd_validate(args: argparse.Namespace) -> None:
    """Validate a manifest without executing."""
    manifest, validation = _load_manifest(args.manifest)
    print(f"\nManifest: {manifest.metadata.name}@{manifest.metadata.version}")
    print(f"Publisher: {manifest.metadata.publisher or '(none)'}")
    print(f"Input fields: {list(manifest.input_schema.keys())}")
    print(f"Output fields: {list(manifest.output_schema.keys())}")
    print(f"Requirements: {manifest.requirements}")
    print(f"Security risk: {manifest.security.risk.value if manifest.security else 'default (low)'}")
    print(f"\n[OK] Manifest is valid")


def cmd_run(args: argparse.Namespace) -> None:
    """Execute a capability on a specific runtime adapter."""
    manifest, _ = _load_manifest(args.manifest)

    # Parse input data
    input_data: dict[str, Any] = {}
    if args.input:
        try:
            input_data = json.loads(args.input)
        except json.JSONDecodeError:
            input_data = {"text": args.input}
    elif args.input_file:
        try:
            input_data = json.loads(Path(args.input_file).read_text())
        except (json.JSONDecodeError, FileNotFoundError) as exc:
            print(f"Error reading input file: {exc}", file=sys.stderr)
            sys.exit(1)

    # Build executor with requested adapter
    executor = _setup_executor()
    adapters = executor.get_available_adapters()

    if not adapters:
        print("Error: No runtime adapters available.", file=sys.stderr)
        print("Install at least one: pip install openai  or  pip install anthropic",
              file=sys.stderr)
        sys.exit(1)

    adapter_name = args.adapter or adapters[0]

    if adapter_name not in executor._adapters:
        print(f"Error: Adapter '{adapter_name}' not loaded.", file=sys.stderr)
        print(f"Available: {', '.join(adapters)}", file=sys.stderr)
        sys.exit(1)

    # Execute
    print(f"\nExecuting '{manifest.id}' via '{adapter_name}'...")
    try:
        record = executor.execute(
            manifest=manifest,
            input_data=input_data,
            adapter_name=adapter_name,
        )
    except Exception as exc:
        print(f"\nExecution failed: {exc}", file=sys.stderr)
        sys.exit(1)

    # Display results
    _display_record(record, args.output)

    # Auto-save to Event Store
    try:
        _save_to_event_store(record)
    except Exception:
        pass

    # Save record if requested
    if args.save:
        save_path = save_execution_record(record, args.save)
        print(f"\nExecution record saved to: {save_path}")


def cmd_compare(args: argparse.Namespace) -> None:
    """
    Execute the same capability on two adapters and compare results.
    """
    manifest, _ = _load_manifest(args.manifest)

    # Parse input
    input_data: dict[str, Any] = {}
    if args.input:
        try:
            input_data = json.loads(args.input)
        except json.JSONDecodeError:
            input_data = {"text": args.input}

    # Build executor
    executor = _setup_executor()
    adapters = executor.get_available_adapters()

    if len(adapters) < 2:
        print(
            "Warning: Comparison is most useful with at least 2 adapters loaded "
            "(openai + anthropic)",
            file=sys.stderr,
        )

    records = []
    for adapter_name in adapters:
        print(f"\n{'='*60}")
        print(f"Executing on '{adapter_name}'...")
        try:
            record = executor.execute(
                manifest=manifest,
                input_data=input_data,
                adapter_name=adapter_name,
            )
            records.append((adapter_name, record))
            print(f"  Status: {record.status.value}")
            print(f"  Latency: {record.total_latency_ms:.0f}ms")
            print(f"  Cost: ${record.total_cost_usd:.4f}")
            print(f"  Tokens: {record.total_tokens}")
        except Exception as exc:
            print(f"  FAILED: {exc}")

    # Compare if we have at least 2 records
    if len(records) >= 2:
        print(f"\n{'='*60}")
        print("COMPARISON RESULTS")
        print(f"{'='*60}")

        for i in range(len(records)):
            for j in range(i + 1, len(records)):
                name_a, rec_a = records[i]
                name_b, rec_b = records[j]
                result = compare_records(rec_a, rec_b)

                print(f"\n{name_a} vs {name_b}:")
                print(f"  Schema compatible: "
                      f"[{'OK' if result['checks']['schema_compatibility']['passed'] else 'FAIL'}]")
                print(f"  Event structure match: "
                      f"[{'OK' if result['checks']['event_structure_match']['passed'] else 'FAIL'}]")
                print(f"  Metric dimensions match: "
                      f"[{'OK' if result['checks']['metric_dimensions_match']['passed'] else 'FAIL'}]")

                detail = result['checks']['metric_dimensions_match']['details']
                if detail.get('missing_in_b') or detail.get('missing_in_a'):
                    print(f"   - Missing in {name_b}: {detail['missing_in_b']}")
                    print(f"   - Missing in {name_a}: {detail['missing_in_a']}")

                verdict = "COMPATIBLE" if result['compatible'] else "NOT COMPATIBLE"
                print(f"\n  >>> Overall: {verdict}")

        # Also show side-by-side metrics
        print(f"\n{'='*60}")
        print("METRICS COMPARISON")
        print(f"{'='*60}")
        headers = ["Metric"] + [r[0] for r in records]
        rows = [
            ("Status", [r[1].status.value for r in records]),
            ("Latency (ms)", [f"{r[1].total_latency_ms:.0f}" for r in records]),
            ("Cost ($)", [f"{r[1].total_cost_usd:.4f}" for r in records]),
            ("Tokens", [str(r[1].total_tokens) for r in records]),
        ]
        _print_table(headers, rows)

    # Auto-save all records to Event Store
    for _, record in records:
        try:
            _save_to_event_store(record)
        except Exception:
            pass

    # Save records
    if args.save:
        for adapter_name, record in records:
            save_path = Path(args.save) / f"{adapter_name}_record.json"
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_execution_record(record, save_path)
            print(f"  Record saved: {save_path}")


def cmd_list(args: argparse.Namespace) -> None:
    """List available adapters and registered capabilities."""
    executor = _setup_executor()
    adapters = executor.get_available_adapters()
    print(f"Available adapters: {', '.join(adapters) if adapters else '(none)'}")
    _, registry = _get_registry_store()
    caps = registry.list_capabilities()
    if caps:
        print(f"\nRegistered capabilities ({len(caps)}):")
        for cap in caps:
            print(f"  {cap['name']}@{cap['version']}")
    else:
        print("\nNo capabilities registered")


def cmd_registry(args: argparse.Namespace) -> None:
    """Manage the capability registry."""
    from core.parser import parse_manifest, ManifestParseError
    _, registry = _get_registry_store()

    if args.action == "list":
        caps = registry.list_capabilities()
        if not caps:
            print("No capabilities registered.")
            return
        print(f"Registered capabilities ({len(caps)}):")
        for cap in caps:
            pub = f" ({cap['publisher'] or 'unknown'})" if cap.get('publisher') else ""
            desc = f" - {cap['description'][:60]}" if cap.get('description') else ""
            print(f"  {cap['name']}@{cap['version']}{pub}{desc}")

    elif args.action == "get":
        cap = registry.get(args.name, args.version)
        if cap is None:
            print(f"Capability '{args.name}' not found.")
            sys.exit(1)
        print(f"Name: {cap.name}@{cap.version}")
        print(f"Publisher: {cap.metadata.publisher or '(none)'}")
        print(f"Description: {cap.metadata.description or '(none)'}")
        print(f"Tags: {cap.metadata.tags or '(none)'}")
        print(f"Input fields: {list(cap.input_schema.keys())}")
        print(f"Output fields: {list(cap.output_schema.keys())}")

    elif args.action == "register":
        path = Path(args.manifest_path)
        if not path.exists():
            print(f"Error: File not found: {path}", file=sys.stderr)
            sys.exit(1)
        try:
            manifest, _ = parse_manifest(path)
        except ManifestParseError as exc:
            print(f"Error parsing manifest: {exc}", file=sys.stderr)
            sys.exit(1)
        try:
            registry.register(manifest)
            print(f"[OK] Registered '{manifest.id}'")
        except Exception as exc:
            print(f"Registration failed: {exc}", file=sys.stderr)
            sys.exit(1)

    elif args.action == "unregister":
        try:
            registry.unregister(args.name, args.version)
            ver_str = f"@{args.version}" if args.version else " (all versions)"
            print(f"[OK] Unregistered '{args.name}{ver_str}'")
        except Exception as exc:
            print(f"Unregister failed: {exc}", file=sys.stderr)
            sys.exit(1)

    elif args.action == "export":
        output = Path(args.output_path)
        try:
            result = registry.save_snapshot(str(output))
            print(f"[OK] Snapshot exported to {result}")
        except Exception as exc:
            print(f"Export failed: {exc}", file=sys.stderr)
            sys.exit(1)


def cmd_event(args: argparse.Namespace) -> None:
    """Query execution events from the Event Store."""
    store = _get_event_store()

    if args.action == "list":
        event_count = store.get_event_count()
        record_count = store.get_record_count()
        print(f"Event Store: ~/.intent-os/events.db")
        print(f"  Events: {event_count}")
        print(f"  Execution records: {record_count}")
        if record_count > 0:
            traces = store.get_all_trace_ids()
            print(f"  Traces: {len(traces)}")
            print(f"\nRecent traces:")
            for t in traces[:20]:
                rec = store.get_record(t)
                if rec:
                    print(f"  {t}: {rec.get('manifest_name','?')}@{rec.get('manifest_version','?')} - {rec.get('status','?')}")

    elif args.action == "trace":
        events = store.get_events_by_trace(args.trace_id)
        if not events:
            print(f"No events found for trace '{args.trace_id}'")
            return
        print(f"Trace: {args.trace_id}")
        print(f"Events: {len(events)}")
        for evt in events:
            ts = evt.get("timestamp", "")[11:19]
            print(f"  [{ts}] {evt.get('event_type','')} ({evt.get('source','')})")
        record = store.get_record(args.trace_id)
        if record:
            print(f"\nRecord: {record.get('manifest_name','?')}@{record.get('manifest_version','?')}")
            print(f"  Status: {record.get('status','?')}")
            print(f"  Latency: {record.get('total_latency_ms',0):.0f}ms")
            print(f"  Cost: ${record.get('total_cost_usd',0):.4f}")

    elif args.action == "query":
        events = store.query_events(
            trace_id=args.trace_id,
            event_type=args.event_type,
            capability=args.capability,
            runtime=args.runtime,
            limit=args.limit or 20,
        )
        if not events:
            print("No matching events found.")
            return
        print(f"Found {len(events)} events:")
        for evt in events[:args.limit or 20]:
            ts = evt.get("timestamp", "")[11:19]
            print(f"  [{ts}] {evt.get('event_type','')} | {evt.get('capability','') or ''} | {evt.get('runtime','') or ''}")


def cmd_analytics(args: argparse.Namespace) -> None:
    """Analyze execution history from the Event Store."""
    from core.analytics import AnalyticsEngine
    store = _get_event_store()
    analytics = AnalyticsEngine(store)

    if args.action == "summary":
        summary = analytics.get_trend_summary(days=30)
        print(f"Execution Summary (last 30 days)")
        print(f"  Total executions: {summary['total_executions']}")
        print(f"  Top capabilities:")
        for cap in summary['top_capabilities'][:5]:
            print(f"    {cap['capability']}: score={cap['performance_score']}, success={cap['success_rate']:.0%}")
        print(f"  Failure patterns:")
        for pat in summary['failure_patterns'][:5]:
            print(f"    {pat.get('manifest_name','?')} on {pat.get('runtime_id','?')}: {pat.get('failure_count',0)} failures")

    elif args.action == "capabilities":
        rankings = analytics.get_capability_rankings()
        if not rankings:
            print("No execution data available.")
            return
        print(f"Capability Rankings ({len(rankings)}):")
        print(f"  {'Name':<30} {'Score':<8} {'Success':<10} {'Latency':<12} {'Cost':<10}")
        print(f"  {'-'*70}")
        for cap in rankings:
            print(f"  {cap['capability']:<30} {cap['performance_score']:<8.1f} {cap['success_rate']:<10.0%} {cap['avg_latency_ms']:<12.0f}ms ${cap['avg_cost_usd']:<8.4f}")

    elif args.action == "runtimes":
        comparison = analytics.get_runtime_comparison()
        if not comparison:
            print("No execution data available.")
            return
        print(f"Runtime Comparison:")
        print(f"  {'Runtime':<20} {'Runs':<8} {'Success':<10} {'Latency':<12} {'Cost':<10}")
        print(f"  {'-'*60}")
        for r in comparison:
            sr = r.get('success_rate', 0) or 0
            print(f"  {r['runtime_id']:<20} {r['total_runs']:<8} {sr:<10.0%} {r.get('avg_latency_ms',0):<12.0f}ms ${r.get('avg_cost_usd',0):<8.4f}")

    elif args.action == "failures":
        report = analytics.get_failure_report()
        print(f"Failure Analysis")
        print(f"  Total records: {report['total_records']}")
        print(f"  Total failures: {report['total_failures']}")
        print(f"  Overall failure rate: {report['overall_failure_rate']:.2%}")
        print(f"\n  Most error-prone capabilities:")
        for cap in report['most_error_prone'][:10]:
            print(f"    {cap['capability']}: {cap['failure_count']}/{cap['total_runs']} ({cap['failure_rate']:.1%})")

    elif args.action == "trends":
        trend = analytics.get_cost_trend(days=30)
        print(f"Cost Trends (last 30 days)")
        print(f"  Total executions: {trend['total_executions']}")
        print(f"  Total cost: ${trend['total_cost_usd']:.4f}")
        print(f"  Avg cost/execution: ${trend['avg_cost_per_execution']:.4f}")
        print(f"\n  Cost by runtime:")
        for r in trend['cost_by_runtime']:
            print(f"    {r['runtime']:<20} {r['total_runs']:<8} runs avg ${r['avg_cost']:<8.4f}")

    elif args.action == "suggestions":
        suggestions = analytics.get_optimization_suggestions()
        if not suggestions:
            print("No optimization suggestions at this time.")
            return
        print(f"Optimization Suggestions ({len(suggestions)}):")
        for s in suggestions:
            print(f"\n  [{s['type']}]")
            print(f"  Suggestion: {s['suggestion']}")
            print(f"  Expected: {s['expected_impact']}")

    elif args.action == "export":
        data = analytics.export_cost_model_data(
            limit=args.limit or 1000,
            output_path=args.output_path,
        )
        print(f"[OK] Exported {len(data)} records")
        if args.output_path:
            print(f"  Saved to: {args.output_path}")


def cmd_workflow(args: argparse.Namespace) -> None:
    """Workflow management commands."""
    from core.workflow import WorkflowDAG, TaskStatus
    from core.workflow_runner import SimulatedExecutor, register_mock_capabilities
    from core.recorder import ExecutionRecorder
    from core.scheduler import Scheduler
    from core.planner import WorkflowPlanner
    from core.registry import CapabilityRegistry

    if args.action == "run":
        # Load workflow YAML using the formal parser
        from core.workflow_parser import parse_workflow_yaml, WorkflowParseError
        path = Path(args.query)
        if not path.exists():
            print(f"Error: File not found: {path}", file=sys.stderr)
            sys.exit(1)
        try:
            spec = parse_workflow_yaml(path)
        except WorkflowParseError as exc:
            print(f"Workflow parse error: {exc}", file=sys.stderr)
            sys.exit(1)
        spec_obj = spec
        dag = WorkflowDAG(spec_obj)

        print(f"[OK] Loaded workflow '{spec.id}'")
        print(f"  Tasks: {len(spec.tasks)}, Edges: {len(spec.edges)}")
        print(f"  Topological order: {dag.topological_order}")

        # Parse input
        input_data: dict[str, Any] = {}
        if args.input:
            try:
                input_data = json.loads(args.input)
            except json.JSONDecodeError:
                input_data = {"input": args.input}

        # Select executor: real adapters if available, simulated fallback
        try:
            real_executor = _setup_executor()
            has_real = len(real_executor.get_available_adapters()) > 0
        except Exception:
            real_executor = None
            has_real = False

        adapter_name = getattr(args, 'adapter', None)
        use_simulated = getattr(args, 'simulate', False) or not has_real

        if use_simulated:
            executor = SimulatedExecutor()
            print(f"  Using simulated executor (--adapter for real runtimes)")
        else:
            executor = real_executor
            print(f"  Using real executor: {', '.join(executor.get_available_adapters())}")

        recorder = ExecutionRecorder(trace_id=f"wf-{spec.name}")
        scheduler = Scheduler(executor, recorder, dag)
        if not use_simulated:
            try:
                _, registry = _get_registry_store()
                scheduler.set_registry(registry)
            except Exception:
                pass

        print(f"  Executing...")
        record = scheduler.execute(input_data=input_data, adapter_name=adapter_name)

        # Auto-save to Event Store
        try:
            _save_to_event_store(record)
        except Exception:
            pass

        print(f"\n  Status: {record.status.value}")
        print(f"  Latency: {record.total_latency_ms:.0f}ms")
        print(f"  Cost: ${record.total_cost_usd:.4f}")
        print(f"  Events: {len(record.events)}")

        print(f"\n  Task Results:")
        for task in dag.spec.tasks:
            status_mark = {
                TaskStatus.SUCCEEDED: "OK",
                TaskStatus.FAILED_FATAL: "!!",
                TaskStatus.SKIPPED: "--",
                TaskStatus.BLOCKED: "##",
            }.get(task.status, "??")
            latency = f"{task.latency_ms}ms" if task.latency_ms else "-"
            print(f"    {status_mark} {task.id}: {task.status.value} ({latency})")

    elif args.action == "plan":
        # Plan from goal
        executor = SimulatedExecutor()
        manifests = register_mock_capabilities(executor)
        registry = CapabilityRegistry()
        for m in manifests.values():
            registry.register(m)

        planner = WorkflowPlanner(registry=registry)
        goal_text = args.query or "default research task"
        try:
            result = planner.plan(goal_text)
        except Exception as exc:
            print(f"Planning failed: {exc}", file=sys.stderr)
            sys.exit(1)

        dag = result.workflow_dag
        print(f"[OK] Plan generated for: {goal_text}")
        print(f"  Template: {result.template_name}")
        print(f"  Tasks: {len(dag.spec.tasks)}")

        for i, tid in enumerate(dag.topological_order):
            task = dag.get_task(tid)
            level = dag.get_level(tid)
            prefix = "  " * level + "-> " if level > 0 else "  "
            print(f"{prefix}{task.id} ({task.capability})")

        print(f"\n  Run with: intent-os workflow run <file.yaml>")


def cmd_mcp_server(args: argparse.Namespace) -> None:
    """Start or manage the Intent OS MCP Server."""
    from mcp_server import MCPServer

    if args.mcp_action == "start":
        server = MCPServer(
            host=args.host,
            port=args.port,
            adapter=args.adapter,
        )
        print(f"[OK] Starting Intent OS MCP Server on {args.host}:{args.port}")
        print(f"  SSE: http://{args.host}:{args.port}/sse")
        print(f"  Messages: POST http://{args.host}:{args.port}/messages")
        print(f"  Adapter: {args.adapter}")
        print("  Press Ctrl+C to stop.")
        try:
            server.run()
        except KeyboardInterrupt:
            print("\nStopped.")
    elif args.mcp_action == "status":
        server = MCPServer(
            host=getattr(args, 'host', '127.0.0.1'),
            port=args.port,
            adapter=args.adapter,
        )
        info = server.status()
        print(f"Intent OS MCP Server")
        print(f"  Host: {info['host']}")
        print(f"  Port: {info['port']}")
        print(f"  Transport: {info['transport']}")
        print(f"  SSE endpoint: http://{info['host']}:{info['port']}{info['sse_path']}")
        print(f"  Default adapter: {info['default_adapter']}")
        print(f"  Capabilities registered: {info['capability_count']}")
        for cap in info['capabilities']:
            print(f"    - {cap['name']}: {cap['description']}")


def cmd_import(args: argparse.Namespace) -> None:
    """Import a capability from an external format."""
    from tools.importer import Importer

    _, registry = _get_registry_store()
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


def cmd_export(args: argparse.Namespace) -> None:
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


# ──────────────────────────
# Display helpers
# ──────────────────────────

def _display_record(record: Any, output_file: str | None = None) -> None:
    """Display execution record results."""
    print(f"\n{'='*60}")
    print(f"EXECUTION RESULT")
    print(f"{'='*60}")
    print(f"  Status: {record.status.value}")
    if record.error:
        print(f"  Error: {record.error}")
    print(f"  Runtime: {record.runtime_id} via {record.adapter}")
    print(f"  Latency: {record.total_latency_ms:.0f}ms")
    print(f"  Cost: ${record.total_cost_usd:.4f}")
    print(f"  Tokens: {record.total_tokens}")
    print(f"  Events: {len(record.events)}")

    if record.output:
        print(f"\n  Output:")
        output_str = json.dumps(
            {k: v for k, v in record.output.items() if not k.startswith("_")},
            indent=4,
            default=str,
        )
        for line in output_str.split("\n"):
            print(f"    {line}")

    if record.events:
        print(f"\n  Event Sequence:")
        for evt in record.events:
            marker = {
                "TaskStarted": ">>",
                "CapabilityInvoked": "->",
                "TaskCompleted": "OK",
                "TaskFailed": "!!",
            }.get(evt.event_type.value, "..")
            extra = ""
            if evt.metrics and "latency_ms" in evt.metrics:
                extra = f" ({evt.metrics['latency_ms']}ms)"
            print(f"    {marker} {evt.event_type.value}{extra}")

    if output_file:
        with open(output_file, "w") as f:
            f.write(json.dumps(record.to_dict(), indent=2, default=str))
        print(f"\n  Full record written to: {output_file}")


def _print_table(headers: list[str], rows: list[tuple[str, list[str]]]) -> None:
    """Print a simple ASCII table."""
    col_width = max(len(h) for h in headers)
    for label, values in rows:
        col_width = max(col_width, len(label))
        for v in values:
            col_width = max(col_width, len(v))
    col_width = max(col_width + 2, 12)

    header_line = "  " + "".join(h.ljust(col_width) for h in headers)
    print(header_line)
    print("  " + "-" * len(header_line))
    for label, values in rows:
        print(f"  {label.ljust(col_width)}" + "".join(v.ljust(col_width) for v in values))


# ──────────────────────────
# Parser
# ──────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="intent-os",
        description="Intent OS Reference Runtime - Open AI Capability Interoperability",
        epilog="Phase 0 - Prove that one Manifest can run on multiple runtimes.",
    )
    parser.add_argument("--version", action="version", version="intent-os 0.2.0")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # validate
    validate_parser = subparsers.add_parser("validate", help="Validate a Capability Manifest")
    validate_parser.add_argument("manifest", help="Path to Capability Manifest YAML file")
    validate_parser.set_defaults(func=cmd_validate)

    # run
    run_parser = subparsers.add_parser("run", help="Execute a capability on a runtime")
    run_parser.add_argument("manifest", help="Path to Capability Manifest YAML file")
    run_parser.add_argument("--adapter", "-a", default=None, help="Runtime adapter (openai, anthropic, ollama)")
    run_parser.add_argument("--input", "-i", default=None, help="Input JSON string")
    run_parser.add_argument("--input-file", "-f", default=None, help="Input JSON file")
    run_parser.add_argument("--output", "-o", default=None, help="Save execution record to file")
    run_parser.add_argument("--save", "-s", default=None, help="Save execution record path")
    run_parser.set_defaults(func=cmd_run)

    # compare
    compare_parser = subparsers.add_parser("compare", help="Execute on all runtimes and compare results")
    compare_parser.add_argument("manifest", help="Path to Capability Manifest YAML file")
    compare_parser.add_argument("--input", "-i", default=None, help="Input JSON string")
    compare_parser.add_argument("--save", "-s", default=None, help="Directory to save records")
    compare_parser.set_defaults(func=cmd_compare)

    # list
    list_parser = subparsers.add_parser("list", help="List available adapters and capabilities")
    list_parser.set_defaults(func=cmd_list)

    # registry
    registry_parser = subparsers.add_parser("registry", help="Manage the capability registry")
    registry_sub = registry_parser.add_subparsers(dest="action", help="Registry actions")
    reg_list = registry_sub.add_parser("list", help="List all registered capabilities")
    reg_list.set_defaults(action="list", func=cmd_registry)
    reg_get = registry_sub.add_parser("get", help="Get capability details")
    reg_get.add_argument("name", help="Capability name")
    reg_get.add_argument("--version", "-v", default=None, help="Version (default: latest)")
    reg_get.set_defaults(func=cmd_registry)
    reg_register = registry_sub.add_parser("register", help="Register a capability from a Manifest")
    reg_register.add_argument("manifest_path", help="Path to Capability Manifest YAML file")
    reg_register.set_defaults(func=cmd_registry)
    reg_unregister = registry_sub.add_parser("unregister", help="Unregister a capability")
    reg_unregister.add_argument("name", help="Capability name")
    reg_unregister.add_argument("--version", "-v", default=None, help="Version (omit for all)")
    reg_unregister.set_defaults(func=cmd_registry)
    reg_export = registry_sub.add_parser("export", help="Export registry snapshot to JSON")
    reg_export.add_argument("output_path", help="Output JSON file path")
    reg_export.set_defaults(func=cmd_registry)

    # event
    event_parser = subparsers.add_parser("event", help="Query execution events from the Event Store")
    event_sub = event_parser.add_subparsers(dest="action", help="Event actions")
    ev_list = event_sub.add_parser("list", help="List Event Store statistics")
    ev_list.set_defaults(func=cmd_event)
    ev_trace = event_sub.add_parser("trace", help="View events for a specific trace ID")
    ev_trace.add_argument("trace_id", help="Trace ID to inspect")
    ev_trace.set_defaults(func=cmd_event)
    ev_query = event_sub.add_parser("query", help="Query events with filters")
    ev_query.add_argument("--trace-id", dest="trace_id", default=None)
    ev_query.add_argument("--event-type", default=None)
    ev_query.add_argument("--capability", default=None)
    ev_query.add_argument("--runtime", default=None)
    ev_query.add_argument("--limit", type=int, default=20)
    ev_query.set_defaults(func=cmd_event)

    # analytics
    analytics_parser = subparsers.add_parser("analytics", help="Analyze execution history")
    analytics_sub = analytics_parser.add_subparsers(dest="action", help="Analytics actions")
    for name, help_text in [
        ("summary", "Overall execution summary"),
        ("capabilities", "Capability performance rankings"),
        ("runtimes", "Runtime comparison"),
        ("failures", "Failure analysis report"),
        ("trends", "Cost trends over time"),
        ("suggestions", "Optimization suggestions"),
    ]:
        p = analytics_sub.add_parser(name, help=help_text)
        p.set_defaults(func=cmd_analytics)
    an_export = analytics_sub.add_parser("export", help="Export cost model training data")
    an_export.add_argument("output_path", nargs="?", default=None)
    an_export.add_argument("--limit", type=int, default=1000)
    an_export.set_defaults(func=cmd_analytics)

    # workflow
    workflow_parser = subparsers.add_parser("workflow", help="Plan and run workflows")
    workflow_parser.add_argument("action", choices=["run", "plan"])
    workflow_parser.add_argument("query", nargs="?", default=None,
                                 help="Workflow YAML path (for run) or goal text (for plan)")
    workflow_parser.add_argument("--input", "-i", default=None, help="Input JSON (for run)")
    workflow_parser.add_argument("--adapter", "-a", default=None, help="Runtime adapter (for run)")
    workflow_parser.add_argument("--simulate", action="store_true",
                                 help="Force simulated execution (for run)")
    workflow_parser.set_defaults(func=cmd_workflow)

    # mcp-server
    mcp_parser = subparsers.add_parser("mcp-server", help="Start or manage the Intent OS MCP Server")
    mcp_sub = mcp_parser.add_subparsers(dest="mcp_action", help="MCP Server actions")
    mcp_start = mcp_sub.add_parser("start", help="Start the MCP Server (SSE transport)")
    mcp_start.add_argument("--port", type=int, default=8080)
    mcp_start.add_argument("--host", default="127.0.0.1")
    mcp_start.add_argument("--adapter", default="ollama")
    mcp_start.set_defaults(func=cmd_mcp_server)
    mcp_status = mcp_sub.add_parser("status", help="Show MCP Server status")
    mcp_status.add_argument("--port", type=int, default=8080)
    mcp_status.add_argument("--adapter", default="ollama")
    mcp_status.set_defaults(func=cmd_mcp_server)

    # import
    import_parser = subparsers.add_parser("import", help="Import a capability from an external format")
    import_parser.add_argument("format", choices=["openai-function", "mcp-server"])
    import_parser.add_argument("source", help="Source file path or URL")
    import_parser.add_argument("--output-dir", "-o", default="./manifests")
    import_parser.add_argument("--publisher", default=None)
    import_parser.add_argument("--tags", default=None, help="Comma-separated tags")
    import_parser.add_argument("--timeout", type=int, default=30)
    import_parser.set_defaults(func=cmd_import)

    # export
    export_parser = subparsers.add_parser("export", help="Export a capability to an external format")
    export_parser.add_argument("format", choices=["openai", "mcp"])
    export_parser.add_argument("source", help="Manifest YAML file path or capability name")
    export_parser.add_argument("--output", "-o", default=None, help="Output file path")
    export_parser.add_argument("--as-tool", action="store_true", help="Wrap in OpenAI tool format")
    export_parser.set_defaults(func=cmd_export)

    return parser


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        args.func(args)
    except Exception as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        if args.command == "compare":
            pass
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
