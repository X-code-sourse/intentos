"""Capability manifest + fn signature validation (RFC-0400 §7)."""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..registry import CapabilityManifest

_TASK_TYPE_RE = re.compile(r"^[a-z][a-z0-9-]{1,63}$")


def validate_capability(manifest: CapabilityManifest) -> dict[str, Any]:
    """Full validation of a capability.

    Checks:
        1. Manifest metadata (task_type, entry_point, etc.)
        2. Fn signature (exactly 2 positional args: task, context)
        3. Input/output JSON Schemas (if present)

    Args:
        manifest: A ``CapabilityManifest`` with ``fn`` populated.

    Returns:
        dict with keys:
            - valid: bool
            - errors: list[str]
            - warnings: list[str]
    """
    errors: list[str] = []
    warnings: list[str] = []

    errors.extend(validate_manifest(manifest))
    errors.extend(validate_fn_signature(manifest.fn))

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def validate_manifest(manifest: CapabilityManifest) -> list[str]:
    """Validate manifest metadata fields.

    Returns a list of error messages (empty means valid).
    """
    errors: list[str] = []

    # ── task_type ───────────────────────────────────────────────────
    if not manifest.task_type:
        errors.append("task_type is required")

    elif not _TASK_TYPE_RE.match(manifest.task_type):
        errors.append(
            f"task_type '{manifest.task_type}' is invalid: "
            f"must be lowercase kebab-case (2-64 chars, start with a letter)"
        )

    # ── fn ──────────────────────────────────────────────────────────
    if manifest.fn is None:
        errors.append("fn (handler function) is required")

    # ── entry_point ─────────────────────────────────────────────────
    if manifest.source == "external" and not manifest.entry_point:
        errors.append("entry_point is required for external capabilities")

    if manifest.entry_point:
        parts = manifest.entry_point.rsplit(".", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            errors.append(
                f"entry_point '{manifest.entry_point}' must be in 'module.attr' format"
            )

    # ── version ─────────────────────────────────────────────────────
    if manifest.version:
        # Basic SemVer check: x.y.z
        sv = re.match(r"^\d+\.\d+\.\d+", manifest.version)
        if not sv:
            errors.append(
                f"version '{manifest.version}' should follow SemVer (e.g. '0.1.0')"
            )

    # ── tags ────────────────────────────────────────────────────────
    if not isinstance(manifest.tags, list):
        errors.append("tags must be a list of strings")

    # ── JSON Schemas ────────────────────────────────────────────────
    if manifest.input_schema is not None:
        errors.extend(_validate_schema(manifest.input_schema, "input_schema"))
    if manifest.output_schema is not None:
        errors.extend(_validate_schema(manifest.output_schema, "output_schema"))

    return errors


def validate_fn_signature(fn: Callable | None) -> list[str]:
    """Validate that a handler function has the correct signature.

    Expected: ``fn(task, context) -> Any``

    Returns a list of error messages (empty means valid).
    """
    errors: list[str] = []

    if fn is None:
        return errors  # Handled by validate_manifest

    if not callable(fn):
        errors.append("handler must be a callable")
        return errors

    try:
        sig = inspect.signature(fn)
    except (ValueError, TypeError) as e:
        errors.append(f"cannot inspect handler signature: {e}")
        return errors

    params = list(sig.parameters.values())

    # Count positional parameters
    positional = [
        p
        for p in params
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]

    if len(positional) < 2:
        errors.append(
            f"handler must accept exactly 2 positional arguments "
            f"(task, context), but got {len(positional)}"
        )
    elif len(positional) > 2:
        errors.append(
            f"handler accepts {len(positional)} positional arguments, "
            f"expected exactly 2 (task, context)"
        )

    # ── Var-positional (*args) and var-keyword (**kwargs) are OK ────
    # Allow optional extras but log a warning via the return dict is not
    # possible here (separate function), so we just pass.

    # ── Return annotation ──────────────────────────────────────────
    return_annotation = sig.return_annotation
    if return_annotation is inspect.Parameter.empty:
        pass  # No annotation — acceptable
    elif return_annotation is None:
        pass  # None is acceptable

    return errors


# ── Internal helpers ────────────────────────────────────────────────


def _validate_schema(schema: dict, field_name: str) -> list[str]:
    """Basic validation of a JSON Schema dict."""
    errors: list[str] = []

    if not isinstance(schema, dict):
        errors.append(f"{field_name} must be a dict (JSON Schema)")
        return errors

    if "type" in schema and schema["type"] not in (
        "object", "array", "string", "number", "integer",
        "boolean", "null",
    ):
        errors.append(
            f"{field_name}.type '{schema['type']}' is not a valid JSON Schema type"
        )

    # Check for nested property schemas
    if schema.get("type") == "object" and "properties" in schema:
        if not isinstance(schema["properties"], dict):
            errors.append(f"{field_name}.properties must be a dict")

    return errors


# ── Convenience ─────────────────────────────────────────────────────


def describe_fn(fn: Callable) -> str:
    """Return a human-readable signature string for a handler function."""
    sig = inspect.signature(fn)
    return f"{fn.__name__}{sig}"
