"""Intent OS CLI — context command: manage execution contexts.

Create, list, inspect, and manage execution contexts that define
the task-level environment for agent execution boundaries.

    intent-os context create --name "US Stock Analysis" --goal "Find undervalued"
    intent-os context list
    intent-os context get <context_id>
    intent-os context assign <context_id> --agent <agent_id>
    intent-os context agents <context_id>
    intent-os context delete <context_id>
"""
from __future__ import annotations

import sys
from typing import Any

from core.context_store import ContextStore, ContextStoreError


def cmd_context(args: Any) -> None:
    """Manage execution contexts."""
    action = args.context_action

    if action == "create":
        _cmd_create(args)
    elif action == "list":
        _cmd_list(args)
    elif action in ("get", "inspect"):
        _cmd_get(args)
    elif action == "history":
        _cmd_history(args)
    elif action == "assign":
        _cmd_assign(args)
    elif action == "agents":
        _cmd_agents(args)
    elif action == "delete":
        _cmd_delete(args)
    elif action == "diff":
        _cmd_diff(args)
    elif action == "resume":
        _cmd_resume(args)
    elif action == "search":
        _cmd_search(args)
    else:
        print(f"Unknown context action: {action}", file=sys.stderr)
        sys.exit(1)


def _cmd_create(args: Any) -> None:
    """Create a new execution context."""
    name = getattr(args, "name", None)
    if not name:
        print("Error: --name is required for context create", file=sys.stderr)
        sys.exit(1)

    goal = getattr(args, "goal", "") or ""
    constraints = getattr(args, "constraint", None) or []
    scope = getattr(args, "scope", "") or ""
    parent = getattr(args, "parent", None)
    created_by = getattr(args, "created_by", "") or ""

    store = ContextStore()
    ctx = store.create(
        name=name,
        goal=goal,
        constraints=constraints,
        task_scope=scope,
        parent_context_id=parent,
        created_by=created_by,
    )

    print()
    print("  ================================================")
    print("    Execution Context Created")
    print("  ================================================")
    print()
    print(f"  Context ID:     {ctx['context_id']}")
    print(f"  Name:           {ctx['name']}")
    if ctx["goal"]:
        print(f"  Goal:           {ctx['goal']}")
    if ctx["constraints"]:
        print(f"  Constraints:    {', '.join(ctx['constraints'])}")
    if ctx["task_scope"]:
        print(f"  Scope:          {ctx['task_scope']}")
    if ctx["parent_context_id"]:
        print(f"  Parent:         {ctx['parent_context_id']}")
    if ctx["created_by"]:
        print(f"  Created by:     {ctx['created_by']}")
    print(f"  Created:        {ctx['created_at'][:19]}")
    print()
    print("  Assign an agent to this context:")
    print(f"    intent-os context assign {ctx['context_id']} --agent <agent_id>")
    print()


def _cmd_list(args: Any) -> None:
    """List execution contexts, optionally filtered by creator or assigned agent."""
    created_by = getattr(args, "created_by", None)
    agent_id = getattr(args, "agent", None)
    store = ContextStore()

    if agent_id:
        contexts = store.get_contexts_for_agent(agent_id)
        filter_label = f"agent: {agent_id}"
    elif created_by:
        contexts = store.list(created_by=created_by)
        filter_label = f"created by: {created_by}"
    else:
        contexts = store.list()
        filter_label = None

    if not contexts:
        print("  No execution contexts found.")
        print()
        print("  Create your first context:")
        print('    intent-os context create --name "My Task" --goal "Analyze ..."')
        print()
        return

    print()
    if filter_label:
        print(f"  Execution Contexts ({filter_label}):")
    else:
        print("  Execution Contexts:")
    print(f"  {'Context ID':<22} {'Name':<25} {'Scope':<14} {'Created'}")
    print(f"  {'-'*73}")
    for ctx in contexts:
        cid = ctx["context_id"]
        name = ctx["name"][:24]
        scope = (ctx["task_scope"] or "-")[:13]
        created = ctx["created_at"][:19] if ctx["created_at"] else "?"
        print(f"  {cid:<22} {name:<25} {scope:<14} {created}")
    print()


def _cmd_get(args: Any) -> None:
    """Show details for a specific execution context."""
    ctx_id = args.context_id
    store = ContextStore()
    ctx = store.get(ctx_id)

    if ctx is None:
        print(f"  Context not found: {ctx_id}")
        print()
        print("  List all contexts:")
        print("    intent-os context list")
        print()
        return

    agents = store.get_assigned_agents(ctx_id)
    history = store.get_history(ctx_id)
    last_version = history[0] if history else None
    version_count = len(history)

    print()
    print(f"  Context ID:     {ctx['context_id']}")
    print(f"  Name:           {ctx['name']}")
    if ctx["goal"]:
        print(f"  Goal:           {ctx['goal']}")
    print(f"  Scope:          {ctx['task_scope'] or '-'}")
    if ctx["constraints"]:
        print(f"  Constraints:")
        for c in ctx["constraints"]:
            print(f"    - {c}")
    if ctx["variables"]:
        print(f"  Variables:")
        for k, v in ctx["variables"].items():
            print(f"    {k}: {v}")
    if ctx["parent_context_id"]:
        parent = store.get(ctx["parent_context_id"])
        if parent:
            print(f"  Inherits from:  {parent['name']} ({ctx['parent_context_id']})")
        else:
            print(f"  Parent:         {ctx['parent_context_id']} (not found)")
    if ctx["created_by"]:
        print(f"  Created by:     {ctx['created_by']}")
    print(f"  Created:        {ctx['created_at'][:19] if ctx['created_at'] else '?'}")
    if ctx["expires_at"]:
        print(f"  Expires:        {ctx['expires_at'][:19]}")
    if version_count > 1:
        print(f"  Version:        v{ctx['version']}")
        print(f"  Versions:       {version_count}")
        if last_version:
            print(f"  Last modified:  {last_version['created_at'][:19]}")
            if last_version.get("reason"):
                print(f"  Last reason:    {last_version['reason']}")
    if agents:
        print(f"  Assigned Agents ({len(agents)}):")
        for agent_id in agents:
            print(f"    - {agent_id}")
    else:
        print(f"  Assigned Agents: (none)")

    # ── Show linked experiences ──
    try:
        from pathlib import Path as _Path
        from core.event_store import EventStore
        from core.experience_store import ExperienceStore as ExpStore

        event_store = EventStore(
            str(_Path.home() / ".intent-os" / "intent_os_store.db")
        )
        exp_store = ExpStore()
        linked = exp_store.get_by_context(ctx_id, event_store=event_store, limit=50)

        if linked:
            print(f"  Related Experiences: {len(linked)}")
            for exp in linked[:5]:
                exp_type = exp.get("type", "?")
                obs = (exp.get("observation") or "")[:90]
                print(f"    - [{exp_type}] {obs}")
            if len(linked) > 5:
                print(f"    ... and {len(linked) - 5} more")
        else:
            print(f"  Related Experiences: (none)")
    except Exception:
        pass  # Gracefully handle missing stores or DB not yet initialised

    print()


def _cmd_history(args: Any) -> None:
    """Show version history for an execution context."""
    ctx_id = args.context_id
    store = ContextStore()

    ctx = store.get(ctx_id)
    if ctx is None:
        print(f"  Context not found: {ctx_id}")
        print()
        print("  List all contexts:")
        print("    intent-os context list")
        print()
        return

    history = store.get_history(ctx_id)

    print()
    print(f"  Version History for '{ctx['name']}' ({ctx_id})")
    print(f"  Current version: v{ctx.get('version', 1)}")
    print()

    if not history:
        print("  (no version history)")
        print()
        return

    print(f"  {'Version':<10} {'Reason':<30} {'Timestamp'}")
    print(f"  {'-'*70}")
    for entry in history:
        ver = f"v{entry['version']}"
        reason = entry["reason"][:29] if entry["reason"] else "-"
        ts = entry["created_at"][:19] if entry["created_at"] else "?"
        indicator = " <-- current" if entry["version"] == ctx.get("version", 1) else ""
        print(f"  {ver:<10} {reason:<30} {ts}{indicator}")
    print()


def _cmd_assign(args: Any) -> None:
    """Assign an agent to an execution context."""
    ctx_id = args.context_id
    agent_id = getattr(args, "agent", None)

    if not agent_id:
        print("Error: --agent is required for context assign", file=sys.stderr)
        sys.exit(1)

    store = ContextStore()

    # Verify the context exists
    ctx = store.get(ctx_id)
    if ctx is None:
        print(f"  Context not found: {ctx_id}", file=sys.stderr)
        print()
        print("  List all contexts:")
        print("    intent-os context list")
        print()
        sys.exit(1)

    ok = store.assign_agent(ctx_id, agent_id)
    if ok:
        print()
        print(f"  Agent '{agent_id}' assigned to context '{ctx_id}'")
        print()
        print(f"  View context details:")
        print(f"    intent-os context get {ctx_id}")
        print()
    else:
        print(f"  Failed to assign agent '{agent_id}' to context '{ctx_id}'", file=sys.stderr)
        sys.exit(1)


def _cmd_agents(args: Any) -> None:
    """List agents assigned to an execution context."""
    ctx_id = args.context_id
    store = ContextStore()

    ctx = store.get(ctx_id)
    if ctx is None:
        print(f"  Context not found: {ctx_id}", file=sys.stderr)
        sys.exit(1)

    agents = store.get_assigned_agents(ctx_id)

    print()
    if not agents:
        print(f"  No agents assigned to context '{ctx_id}'")
        print()
        print("  Assign an agent:")
        print(f"    intent-os context assign {ctx_id} --agent <agent_id>")
        print()
        return

    print(f"  Agents assigned to '{ctx['name']}' ({ctx_id}):")
    print(f"  {'Agent ID':<24}")
    print(f"  {'-'*24}")
    for agent_id in agents:
        print(f"  {agent_id}")
    print()


def _cmd_delete(args: Any) -> None:
    """Delete an execution context."""
    ctx_id = args.context_id
    store = ContextStore()

    if store.delete(ctx_id):
        print(f"  Context deleted: {ctx_id}")
    else:
        print(f"  Context not found: {ctx_id}", file=sys.stderr)
        sys.exit(1)


def _cmd_diff(args: Any) -> None:
    """Show a diff between two contexts or two versions of the same context.

    Usage:
        intent-os context diff <context_id>              # current vs previous
        intent-os context diff <context_id_a> <context_id_b>  # two contexts
    """
    ctx_id_a = args.context_id
    ctx_id_b: str | None = getattr(args, "context_id_b", None)

    store = ContextStore()

    try:
        result = store.diff(ctx_id_a, ctx_id_b)
    except ContextStoreError as exc:
        print(f"  Error: {exc}", file=sys.stderr)
        sys.exit(1)

    _print_diff(result)


def _print_diff(result: dict[str, Any]) -> None:
    """Pretty-print a context diff result."""
    ctx_a = result["context_a"]

    # ── Single version (no diff possible) ──
    if result.get("single_version"):
        print()
        print(f"  Context \"{ctx_a['name']}\" ({ctx_a['id']}) has only")
        print(f"  one version (v{ctx_a['version']}) — no diff possible.")
        print()
        print(f"  Update the context to create a new version:")
        print(f"    intent-os context update {ctx_a['id']} --goal \"...\"")
        print()
        return

    ctx_b = result["context_b"]

    # ── Identical ──
    if result["identical"]:
        print()
        a_label = f"{ctx_a['name']} (v{ctx_a['version']})"
        b_label = f"{ctx_b['name']} (v{ctx_b['version']})"
        print(f"  No differences between {a_label} and {b_label}.")
        print()
        return

    # ── Header ──
    a_label = f"\"{ctx_a['name']}\" (v{ctx_a['version']})"
    b_label = f"\"{ctx_b['name']}\" (v{ctx_b['version']})"
    print()
    print(f"  Context diff: {a_label} vs {b_label}")
    print()

    constraints_added: list[str] = result["constraints_added"]
    constraints_removed: list[str] = result["constraints_removed"]
    variables_added: list[str] = result["variables_added"]
    variables_removed: list[str] = result["variables_removed"]
    variables_changed: list[str] = result["variables_changed"]
    goal_changed: bool = result["goal_changed"]
    scope_changed: bool = result["scope_changed"]

    # ── Constraints ──
    if constraints_added or constraints_removed:
        added_tag = f"+{len(constraints_added)} added" if constraints_added else ""
        removed_tag = f"-{len(constraints_removed)} removed" if constraints_removed else ""
        parts = [p for p in [added_tag, removed_tag] if p]
        header = f"  Constraints ({', '.join(parts)}):"
        print(header)
        for c in constraints_added:
            print(f"    + {c}")
        for c in constraints_removed:
            print(f"    - {c}")
        print()

    # ── Variables ──
    var_parts: list[str] = []
    if variables_added:
        var_parts.append(f"+{len(variables_added)}")
    if variables_removed:
        var_parts.append(f"-{len(variables_removed)}")
    if variables_changed:
        var_parts.append(f"~{len(variables_changed)}")

    if var_parts:
        print(f"  Variables ({', '.join(var_parts)}):")
        # We need the variable values from the resolved contexts.
        # Re-fetch from the store to get the values for the diff display.
        store = ContextStore()

        # Resolve actual var dicts for display
        vars_a: dict[str, Any] = {}
        vars_b: dict[str, Any] = {}

        # For context_a
        if ctx_a["version"] == "current":
            ctx_live = store.get(ctx_a["id"])
            vars_a = dict(ctx_live["variables"]) if ctx_live else {}
        else:
            snap = store.get_version(ctx_a["id"], int(ctx_a["version"]))
            vars_a = dict(snap["variables"]) if snap else {}

        # For context_b
        if ctx_b["version"] == "current":
            ctx_live = store.get(ctx_b["id"])
            vars_b = dict(ctx_live["variables"]) if ctx_live else {}
        else:
            snap = store.get_version(ctx_b["id"], int(ctx_b["version"]))
            vars_b = dict(snap["variables"]) if snap else {}

        for k in variables_added:
            print(f"    + {k}: {_fmt_val(vars_a.get(k))}")
        for k in variables_removed:
            print(f"    - {k}")
        for k in variables_changed:
            old_v = _fmt_val(vars_b.get(k))
            new_v = _fmt_val(vars_a.get(k))
            print(f"    ~ {k}: {old_v} → {new_v}")
        print()

    # ── Goal / Scope ──
    if goal_changed:
        print("  Goal: changed")
    if scope_changed:
        print("  Scope: changed")

    print()


def _cmd_search(args: Any) -> None:
    """Search an agent's context for relevant capabilities and experiences."""
    from core.agent_store import AgentStore
    from core.context_retrieval import retrieve_context

    agent_id = args.agent_id
    query = getattr(args, "query", "") or ""
    limit = getattr(args, "limit", 10)

    store = AgentStore()
    agent = store.get(agent_id)
    if agent is None:
        print(f"  Agent not found: {agent_id}", file=sys.stderr)
        sys.exit(1)

    results = retrieve_context(agent_id, query, max_results=limit)

    avatar_line = f" {agent.avatar}" if agent.avatar else ""
    print()
    print("  ================================================")
    print("    Context Search Results")
    print("  ================================================")
    print()
    print(f"  Query: \"{query[:80]}\"")
    print(f"  Agent: {agent.name}{avatar_line} ({agent_id})")
    print()

    if not results:
        print("  No relevant context found.")
        print()
        return

    for r in results:
        source_tag = "CAPABILITY" if r.source == "capability" else "EXPERIENCE"
        print(f"  [{r.relevance_score:.2f}] {source_tag}  {r.source_id}")
        content = r.content[:100]
        print(f"         {content}")
        confidence_str = f"{r.confidence:.0%} confidence" if r.confidence > 0 else ""
        if confidence_str:
            print(f"         ({confidence_str})")
        print()
    print(f"  Search completed. {len(results)} result(s).")
    print()


def _cmd_resume(args: Any) -> None:
    """Resume an agent's last context — show where it left off."""
    from commands.helpers import get_event_store
    from core.agent_store import AgentStore
    from core.experience_store import ExperienceStore

    agent_id = args.agent_id

    store = ContextStore()
    agent_store = AgentStore()
    agent = agent_store.get(agent_id)

    if agent is None:
        print(f"  Agent not found: {agent_id}", file=sys.stderr)
        sys.exit(1)

    # Find latest context
    latest_ctx = store.get_latest_for_agent(agent_id)

    # Find recent executions
    try:
        event_store = get_event_store()
        records = event_store.query_records(limit=1000)
        agent_records = [r for r in records
                         if r.get("agent_id") == agent_id
                         or (isinstance(r.get("agent_name"), str) and r["agent_name"] == agent.name)]
        total = len(agent_records)
        recent = sorted(agent_records,
                        key=lambda r: r.get("created_at", "") or "",
                        reverse=True)[:5]
    except Exception:
        total = 0
        recent = []

    # Count experiences
    try:
        exp_store = ExperienceStore()
        exps = exp_store.list(agent_id=agent_id, limit=200)
        exp_by_type: dict[str, int] = {}
        for e in exps:
            t = e.get("type", "unknown")
            exp_by_type[t] = exp_by_type.get(t, 0) + 1
        total_exps = len(exps)
    except Exception:
        exp_by_type = {}
        total_exps = 0

    avatar_line = f" {agent.avatar}" if agent.avatar else ""
    persona_line = f" — {agent.persona}" if agent.persona else ""
    status_icon = ">" if agent.status == "active" else "o"

    print()
    print(f"  ================================================")
    print(f"    Context Resume")
    print(f"  ================================================")
    print()
    print(f"  Agent:       {agent.name}{avatar_line}{persona_line}")
    print(f"  ID:          {agent.agent_id}")
    print(f"  {status_icon}  Status:      {agent.status}")
    if agent.traits:
        print(f"  Traits:      {', '.join(agent.traits)}")
    print()

    # Last context section
    if latest_ctx:
        history = store.get_history(latest_ctx["context_id"])
        exec_count = 0
        try:
            event_store = get_event_store()
            exec_count = len(event_store.get_executions_by_context(latest_ctx["context_id"]))
        except Exception:
            pass

        print(f"  Last Context: {latest_ctx['context_id']}")
        print(f"    Goal:      {latest_ctx.get('goal', '') or '(no goal set)'}")
        print(f"    Scope:     {latest_ctx.get('task_scope', '') or '-'}")
        print(f"    Version:   v{latest_ctx.get('version', 1)} ({len(history)} version(s))")
        print(f"    Executions: {exec_count} record(s) linked")
        if latest_ctx.get("constraints"):
            print(f"    Constraints ({len(latest_ctx['constraints'])}):")
            for c in latest_ctx["constraints"]:
                print(f"      - {c}")
        print()
    else:
        print(f"  Last Context: (none — this agent has no assigned contexts)")
        print()

    # Recent executions
    if recent:
        print(f"  Recent Executions ({total} total):")
        print(f"  {'Date':<22} {'Task':<30} {'Result':<8} {'Cost':<8}")
        print(f"  {'-'*68}")
        for r in recent:
            created = (r.get("created_at") or "?")[:19]
            task = r.get("manifest_name") or r.get("capability") or "-"
            status_r = r.get("status", "?")
            status_sym = "OK" if status_r == "success" else "FAIL"
            cost = f"${r.get('total_cost_usd', 0) or 0:.2f}"
            print(f"  {created:<22} {task:<30} {status_sym:<8} {cost:<8}")
        print()

    # Experience summary
    if total_exps > 0:
        print(f"  Experience ({total_exps}):")
        for etype, count in sorted(exp_by_type.items()):
            print(f"    {etype:<22} {count}")
        print()

    # Next steps
    if latest_ctx:
        print(f"  Continue with this context:")
        print(f"    intent-os context create --parent {latest_ctx['context_id']} \\")
        print(f"      --name \"{latest_ctx['name']} (continued)\" \\")
        print(f"      --goal \"Continue {latest_ctx.get('goal', 'work')[:60]}\"")
        print()
    print(f"  View agent profile:")
    print(f"    intent-os agent get {agent_id}")
    print()
    print(f"  File system sync:")
    print(f"    intent-os agent sync {agent_id}")
    print()


def _fmt_val(val: Any) -> str:
    """Format a value for diff display."""
    if isinstance(val, list):
        return "[" + ", ".join(str(v) for v in val) + "]"
    if isinstance(val, dict):
        return "{" + ", ".join(f"{k}: {v}" for k, v in val.items()) + "}"
    return str(val)
