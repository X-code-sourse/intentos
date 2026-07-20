"""Agent OS Capability SDK — RFC-0400.

Third-party Capability development toolkit.

Public API:
    load_capability(path, registry=None)       -> CapabilityManifest
    discover_capabilities(path, registry=None)  -> list[CapabilityManifest]
    discover_installed(registry=None)           -> list[CapabilityManifest]

    validate_capability(manifest)               -> dict
    validate_manifest(manifest)                 -> list[str]
    validate_fn_signature(fn)                   -> list[str]

    scaffold(name, output_dir=".", **options)   -> Path
"""

from .loader import load_capability, discover_capabilities, discover_installed
from .validator import validate_capability, validate_manifest, validate_fn_signature
from .scaffold import scaffold

__all__ = [
    "load_capability",
    "discover_capabilities",
    "discover_installed",
    "validate_capability",
    "validate_manifest",
    "validate_fn_signature",
    "scaffold",
]
