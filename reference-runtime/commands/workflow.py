"""
Intent OS — CLI Command: workflow

Plans and runs workflows (plan, run).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from commands.helpers import setup_executor, save_to_event_store, get_registry_store

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def cmd_workflow(args: Any) -> None:
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
            real_executor = setup_executor()
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
                _, registry = get_registry_store()
                scheduler.set_registry(registry)
            except Exception:
                pass

        print(f"  Executing...")
        record = scheduler.execute(input_data=input_data, adapter_name=adapter_name)

        # Auto-save to Event Store
        try:
            save_to_event_store(record)
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
