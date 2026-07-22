"""
Intent OS — CLI Command: ask

Natural-language capability invocation: classify intent, resolve or generate a
manifest, extract parameters, execute, and summarise the result.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from commands.helpers import get_registry_store, setup_executor

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def cmd_ask(args: Any) -> None:
    """Process a natural-language query: classify, execute, and summarise."""
    # -- resolve the query string -------------------------------------------
    query = args.query
    if not query or not query.strip():
        print("Error: No query provided.", file=sys.stderr)
        print("Usage: intent-os ask \"<your natural language request>\"", file=sys.stderr)
        sys.exit(1)

    query = query.strip()

    print("Intent OS — Ask")
    print(f'  Query: "{query}"')
    print()

    # -- lazy imports -------------------------------------------------------
    from core.llm_provider import ProviderFactory
    from core.ask import AskSession

    # -- registry -----------------------------------------------------------
    print("  Loading capability registry ...")
    db_path, registry = get_registry_store()
    capabilities = registry.list_capabilities()
    print(f"  Registry: {db_path}")
    print(f"  Capabilities registered: {len(capabilities)}")

    # -- LLM provider -------------------------------------------------------
    print()
    print("  Initialising LLM provider (auto)...")

    try:
        provider = ProviderFactory.create("auto")
    except RuntimeError as exc:
        print(f"  Error: {exc}", file=sys.stderr)
        print()
        print("  Install Ollama (free, local, no API key):")
        print("    https://ollama.com/download")
        print("    ollama pull llama3.2:1b")
        print("    ollama serve")
        print()
        print("  Or set an API key:")
        print("    export OPENAI_API_KEY=sk-...")
        print("    export ANTHROPIC_API_KEY=sk-ant-...")
        print()
        sys.exit(1)

    print(f"  Using provider: {provider.name} (model: {provider.model})")

    # -- executor -----------------------------------------------------------
    print()
    print("  Loading runtime adapters ...")
    executor = setup_executor()

    available = executor.get_available_adapters()
    if not available:
        print()
        print("  [i] No adapters are available. The Ask session will still")
        print("      classify and generate manifests, but execution will fail.")
        print("      See the adapter setup instructions above.")

    # -- AskSession ---------------------------------------------------------
    print()
    print("  Processing request ...")
    print()

    session = AskSession(
        registry=registry,
        executor=executor,
        llm_provider=provider,
    )

    result = session.process(query)

    # -- output -------------------------------------------------------------
    if result.error:
        print(f"  Error: {result.error}", file=sys.stderr)
        sys.exit(1)

    print(f"  {'[OK]' if result.success else '[!]'} {result.summary}")
    print()

    if result.manifest_created:
        yaml_text = session.pending_manifest_yaml
        print("  I created a new capability to handle your request:")
        print()
        for line in (yaml_text or "").strip().split("\n")[:10]:
            print(f"    {line}")
        if yaml_text and len(yaml_text.split("\n")) > 10:
            print("    ...")
        print()
        print("  Save this capability for future use?")
        try:
            answer = input("  [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer in ("y", "yes"):
            if session.confirm_and_register():
                print("  [OK] Saved! You can reuse it anytime with:")
                print(f'    intent-os ask "{query}"')
            else:
                print("  [!] Failed to save.")
        else:
            print("  [i] Not saved. I'll generate it again next time you ask.")
        print()

    if result.record and isinstance(result.record, dict):
        status = result.record.get("status", "?")
        runtime = result.record.get("runtime_id", "?")
        adapter = result.record.get("adapter", "?")
        latency = result.record.get("total_latency_ms", "?")
        cost = result.record.get("total_cost_usd", "?")
        tokens = result.record.get("total_tokens", "?")

        print("  Execution details:")
        print(f"    Status:  {status}")
        print(f"    Runtime: {runtime}")
        print(f"    Adapter: {adapter}")
        print(f"    Latency: {latency}ms" if isinstance(latency, (int, float)) else f"    Latency: {latency}")
        print(f"    Cost:    ${cost:.4f}" if isinstance(cost, (int, float)) else f"    Cost:    {cost}")
        print(f"    Tokens:  {tokens}")
        print()

    if not result.success:
        sys.exit(1)
