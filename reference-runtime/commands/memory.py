"""Intent OS CLI — memory command: manage agent memory.

View memory health and prune low-value experiences.

    intent-os memory stats <agent_id>
    intent-os memory prune <agent_id> [--keep 50] [--dry-run]
"""
from __future__ import annotations

import sys
from typing import Any


def cmd_memory(args: Any) -> None:
    """Manage agent memory (experience lifecycle)."""
    from core.agent_store import AgentStore
    from core.experience_store import ExperienceStore

    action = getattr(args, "memory_action", None)

    if action == "stats":
        _cmd_stats(args)
    elif action == "prune":
        _cmd_prune(args)
    else:
        print(f"  Unknown memory action: {action}", file=sys.stderr)
        print()
        print("  Available actions:")
        print("    intent-os memory stats <agent_id>")
        print("    intent-os memory prune <agent_id> [--keep N] [--dry-run]")
        print()
        sys.exit(1)


def _cmd_stats(args: Any) -> None:
    """Show memory health for an agent."""
    from core.agent_store import AgentStore
    from core.experience_store import ExperienceStore

    agent_id = args.agent_id
    store = AgentStore()
    agent = store.get(agent_id)
    if agent is None:
        print(f"  Agent not found: {agent_id}", file=sys.stderr)
        sys.exit(1)

    exp_store = ExperienceStore()
    stats = exp_store.memory_stats(agent_id)

    avatar_line = f" {agent.avatar}" if agent.avatar else ""
    print()
    print("  ================================================")
    print("    Agent Memory Health")
    print("  ================================================")
    print()
    print(f"  Agent: {agent.name}{avatar_line} ({agent_id})")
    print()

    if stats["total"] == 0:
        print("  No experiences stored yet.")
        print()
        return

    print(f"  Total experiences: {stats['total']}")
    print()
    print("  By type:")
    for etype, count in sorted(stats["by_type"].items()):
        print(f"    {etype:<30} {count}")
    print()

    print("  Health metrics:")
    print(f"    Avg confidence:       {stats['avg_confidence']:.2f}")
    print(f"    Avg usage:            {stats['avg_usage_count']:.1f}x")
    print(f"    Avg memory score:     {stats['avg_memory_score']:.2f}")
    print(f"    Oldest experience:    {stats['oldest_days']} days ago")
    print(f"    Prune candidates:     {stats['prune_candidates']}")
    print()
    if stats['prune_candidates'] > 0:
        print("  Run prune to clean up:")
        print(f"    intent-os memory prune {agent_id} --keep 50")
        print()


def _cmd_prune(args: Any) -> None:
    """Prune low-value experiences for an agent."""
    from core.agent_store import AgentStore
    from core.experience_store import ExperienceStore

    agent_id = args.agent_id
    keep = getattr(args, "keep", 50)
    dry_run = getattr(args, "dry_run", False)

    store = AgentStore()
    agent = store.get(agent_id)
    if agent is None:
        print(f"  Agent not found: {agent_id}", file=sys.stderr)
        sys.exit(1)

    exp_store = ExperienceStore()
    result = exp_store.prune(agent_id, keep=keep, dry_run=dry_run)

    print()
    if dry_run:
        print("  ================================================")
        print("    Memory Prune — Dry Run")
        print("  ================================================")
    else:
        print("  ================================================")
        print("    Memory Prune")
        print("  ================================================")
    print()
    print(f"  Agent:  {agent.name} ({agent_id})")
    print(f"  Total:  {result['total']} experiences")
    print(f"  Kept:   {result['kept']}")
    print(f"  Would delete:" if dry_run else f"  Deleted:  {result['deleted']}")
    print()

    if dry_run and result['deleted'] > 0:
        print(f"  Run without --dry-run to execute:")
        print(f"    intent-os memory prune {agent_id} --keep {keep}")
        print()
