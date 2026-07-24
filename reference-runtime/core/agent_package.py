"""
Intent OS — Agent Package (Portable .agent format)

Export and import agents as portable JSON files that can be
transferred across machines, shared, or archived.

The ``.agent`` format is a single JSON file containing:
- Identity (name, persona, traits, avatar, capabilities)
- Reputation summary (execution stats — no raw data)
- Experiences (top learned patterns)

Usage::

    from core.agent_package import export_agent, import_agent

    # Export an agent to a portable dict
    pkg = export_agent("agent_a82f91c3")

    # Import an agent from a dict
    new_id = import_agent(pkg)
"""
from __future__ import annotations

import json
import uuid
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ════════════════════════════════════════════════════════════════
# Package format version
# ════════════════════════════════════════════════════════════════

_SPEC_VERSION = "1.0"
_FORMAT = "intent-os-agent-v1"

# Valid spec versions this code can import
_SUPPORTED_VERSIONS = {"1.0"}

# Maximum experiences to include in a package
_MAX_EXPERIENCES = 50


# ════════════════════════════════════════════════════════════════
# Data models
# ════════════════════════════════════════════════════════════════

@dataclass
class AgentPackageIdentity:
    """Identity section of the .agent package."""
    agent_id: str
    name: str
    persona: str = ""
    traits: list[str] = field(default_factory=list)
    avatar: str = ""
    owner: str = ""
    capabilities: list[str] = field(default_factory=list)
    created_at: str = ""
    last_seen_at: str = ""


@dataclass
class AgentPackageReputation:
    """Computed reputation summary — no raw execution data."""
    total_executions: int = 0
    success_rate: float = 0.0
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    avg_cost_per_run: float = 0.0
    preferred_models: list[str] = field(default_factory=list)


@dataclass
class AgentPackageExperience:
    """Single experience entry in the package."""
    type: str = ""
    observation: str = ""
    recommendation: str = ""
    confidence: float = 0.0


@dataclass
class AgentPackage:
    """Portable agent representation — the .agent format."""
    spec_version: str = _SPEC_VERSION
    format: str = _FORMAT
    exported_at: str = ""
    identity: AgentPackageIdentity = field(default_factory=AgentPackageIdentity)
    reputation: AgentPackageReputation = field(default_factory=AgentPackageReputation)
    experiences: list[AgentPackageExperience] = field(default_factory=list)


# ════════════════════════════════════════════════════════════════
# Export
# ════════════════════════════════════════════════════════════════


def export_agent(agent_id: str, db_path: str | None = None) -> dict[str, Any]:
    """Load an agent from SQLite and build a portable .agent dict.

    Args:
        agent_id: The agent to export.
        db_path: Optional custom database path (for testing).

    Returns:
        A JSON-serialisable dict conforming to the .agent format.

    Raises:
        RuntimeError: If the agent is not found.
    """
    from core.agent_store import AgentStore
    from core.experience_store import ExperienceStore
    from core.event_store import EventStore

    # ── Load agent identity ──
    store = AgentStore(db_path)
    agent = store.get(agent_id)
    if agent is None:
        raise RuntimeError(f"Agent not found: {agent_id}")

    identity = AgentPackageIdentity(
        agent_id=agent.agent_id,
        name=agent.name,
        persona=agent.persona or "",
        traits=list(agent.traits or []),
        avatar=agent.avatar or "",
        owner=agent.owner or "",
        capabilities=list(agent.capabilities or []),
        created_at=agent.created_at or "",
        last_seen_at=agent.last_seen_at or "",
    )

    # ── Load experiences ──
    exp_store = ExperienceStore(db_path)
    raw_exps = exp_store.list(agent_id=agent_id, limit=_MAX_EXPERIENCES)
    experiences = [
        AgentPackageExperience(
            type=e.get("type", ""),
            observation=(e.get("observation") or "").strip(),
            recommendation=(e.get("recommendation") or "").strip(),
            confidence=float(e.get("confidence", 0.0)),
        )
        for e in raw_exps
    ]

    # ── Compute reputation from execution records ──
    reputation = AgentPackageReputation()
    try:
        event_store = EventStore(db_path)
        # query_records doesn't have agent_id filter, use connection directly
        conn = event_store.get_connection()
        rows = conn.execute(
            """SELECT total_cost_usd, total_tokens, status, manifest_name
               FROM execution_records
               WHERE agent_id = ?""",
            (agent_id,),
        ).fetchall()
        conn.close()

        total = len(rows)
        successes = sum(1 for r in rows if r["status"] == "success")
        total_cost = sum(r["total_cost_usd"] or 0 for r in rows)
        total_tokens = sum(r["total_tokens"] or 0 for r in rows)

        # Preferred models: query from events linked to this agent's traces
        model_counts: Counter = Counter()
        trace_ids = [r["manifest_name"] for r in rows if r["manifest_name"]]
        # Simpler approach: get model info from execution_records manifest_name
        for r in rows:
            mn = r["manifest_name"]
            if mn:
                model_counts[mn] += 1

        reputation = AgentPackageReputation(
            total_executions=total,
            success_rate=successes / max(total, 1),
            total_cost_usd=total_cost,
            total_tokens=total_tokens,
            avg_cost_per_run=total_cost / max(total, 1),
            preferred_models=[m for m, _ in model_counts.most_common(5)],
        )
    except Exception:
        pass  # Reputation is best-effort during export

    # ── Assemble package ──
    pkg = AgentPackage(
        exported_at=datetime.now(timezone.utc).isoformat(),
        identity=identity,
        reputation=reputation,
        experiences=experiences,
    )

    return _package_to_dict(pkg)


def _package_to_dict(pkg: AgentPackage) -> dict[str, Any]:
    """Convert an AgentPackage dataclass tree to a plain dict."""
    result: dict[str, Any] = {
        "spec_version": pkg.spec_version,
        "format": pkg.format,
        "exported_at": pkg.exported_at,
        "identity": asdict(pkg.identity),
        "reputation": asdict(pkg.reputation),
        "experiences": [asdict(e) for e in pkg.experiences],
    }
    return result


# ════════════════════════════════════════════════════════════════
# Import
# ════════════════════════════════════════════════════════════════


def import_agent(package: dict[str, Any],
                 name_override: str | None = None,
                 owner_override: str | None = None,
                 db_path: str | None = None) -> str:
    """Import an agent from a .agent dict into the local SQLite stores.

    A new ``agent_id`` is generated to avoid conflicts with existing agents.

    Args:
        package: A dict conforming to the .agent format.
        name_override: Optional name to override the package's identity.name.
        owner_override: Optional owner to override the package's identity.owner.

    Returns:
        The new ``agent_id`` of the imported agent.

    Raises:
        ValueError: If the package format is invalid or the spec_version
            is not supported.
    """
    from core.agent_store import AgentStore
    from core.experience_store import ExperienceStore

    # ── Validate format ──
    if not isinstance(package, dict):
        raise ValueError("Invalid .agent package: expected a dict")

    spec_ver = package.get("spec_version", "")
    if spec_ver not in _SUPPORTED_VERSIONS:
        raise ValueError(
            f"Unsupported .agent spec_version '{spec_ver}'. "
            f"Supported: {', '.join(sorted(_SUPPORTED_VERSIONS))}"
        )

    pkg_format = package.get("format", "")
    if pkg_format != _FORMAT:
        raise ValueError(
            f"Unknown .agent format '{pkg_format}'. Expected '{_FORMAT}'."
        )

    identity_data = package.get("identity", {})
    if not isinstance(identity_data, dict):
        raise ValueError("Invalid .agent package: 'identity' must be a dict")

    name = name_override or identity_data.get("name", "imported-agent")
    owner = owner_override or identity_data.get("owner", "imported")
    persona = identity_data.get("persona", "") or ""
    traits_raw = identity_data.get("traits") or []
    avatar = identity_data.get("avatar", "") or ""
    capabilities_raw = identity_data.get("capabilities") or []

    # ── Create the agent ──
    store = AgentStore(db_path)
    agent = store.create(
        name=name,
        description=f"Imported from {identity_data.get('agent_id', 'unknown')}",
        owner=owner,
        persona=persona,
        traits=list(traits_raw) if isinstance(traits_raw, list) else [],
        avatar=avatar,
    )
    new_id = agent.agent_id

    # Grant capabilities
    if capabilities_raw:
        store.update_agent(new_id, capabilities=list(capabilities_raw))

    # ── Import experiences ──
    exp_store = ExperienceStore(db_path)
    raw_exps = package.get("experiences") or []
    seen_obs: set[str] = set()
    for exp in raw_exps:
        if not isinstance(exp, dict):
            continue
        obs = (exp.get("observation") or "").strip()
        if not obs or obs in seen_obs:
            continue
        seen_obs.add(obs)
        try:
            exp_store.create(
                agent_id=new_id,
                type=exp.get("type", "user_feedback"),
                observation=obs,
                recommendation=(exp.get("recommendation") or "").strip(),
                confidence=float(exp.get("confidence", 0.5)),
            )
        except Exception:
            continue  # Skip invalid experiences

    # ── Sync to filesystem ──
    try:
        _sync_imported_agent(new_id, name, persona, traits_raw, avatar, owner, capabilities_raw)
    except Exception:
        pass  # Filesystem sync is best-effort

    return new_id


def _sync_imported_agent(agent_id: str, name: str, persona: str,
                         traits: list[str], avatar: str, owner: str,
                         capabilities: list[str]) -> None:
    """Write a minimal IDENTITY.yaml for an imported agent."""
    import yaml
    agent_dir = Path.home() / ".intent-os" / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)

    identity = {
        "agent_id": agent_id,
        "name": name,
        "persona": persona or "",
        "traits": list(traits) if isinstance(traits, list) else [],
        "avatar": avatar or "",
        "owner": owner or "",
        "capabilities": list(capabilities) if isinstance(capabilities, list) else [],
    }
    with open(agent_dir / "IDENTITY.yaml", "w", encoding="utf-8") as f:
        yaml.dump(identity, f, default_flow_style=False, allow_unicode=True)


# ════════════════════════════════════════════════════════════════
# File I/O convenience
# ════════════════════════════════════════════════════════════════


def export_agent_to_file(agent_id: str, output_path: str | Path | None = None) -> Path:
    """Export an agent to a ``.agent`` JSON file.

    Args:
        agent_id: The agent to export.
        output_path: Destination path.  If ``None``, writes to
            ``~/.intent-os/agents/<id>/<name>.agent``.

    Returns:
        The path the file was written to.
    """
    pkg = export_agent(agent_id)

    if output_path is None:
        from core.agent_store import AgentStore
        store = AgentStore()
        agent = store.get(agent_id)
        name = agent.name.replace(" ", "_") if agent else agent_id
        output_path = Path.home() / ".intent-os" / "agents" / agent_id / f"{name}.agent"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(pkg, f, indent=2, ensure_ascii=False)

    return output_path


def import_agent_from_file(file_path: str | Path,
                           name_override: str | None = None,
                           owner_override: str | None = None) -> str:
    """Import an agent from a ``.agent`` JSON file.

    Args:
        file_path: Path to the ``.agent`` file.
        name_override: Optional name override.
        owner_override: Optional owner override.

    Returns:
        The new ``agent_id``.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file content is not a valid .agent package.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f".agent file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        try:
            package = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid .agent file (not valid JSON): {exc}") from exc

    return import_agent(package, name_override=name_override, owner_override=owner_override)
