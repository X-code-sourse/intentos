"""Intent OS CLI — validate command."""
from __future__ import annotations
import argparse
from commands.helpers import load_manifest

def cmd_validate(args: argparse.Namespace) -> None:
    manifest, validation = load_manifest(args.manifest)
    print(f"\nManifest: {manifest.metadata.name}@{manifest.metadata.version}")
    print(f"Publisher: {manifest.metadata.publisher or '(none)'}")
    print(f"Input fields: {list(manifest.input_schema.keys())}")
    print(f"Output fields: {list(manifest.output_schema.keys())}")
    print(f"Requirements: {manifest.requirements}")
    print(f"Security risk: {manifest.security.risk.value if manifest.security else 'default (low)'}")
    print(f"\n[OK] Manifest is valid")
