"""
Intent OS — CLI Command: event

Queries execution events from the Event Store.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from commands.helpers import get_event_store

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def cmd_event(args: Any) -> None:
    """Query execution events from the Event Store."""
    store = get_event_store()

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
