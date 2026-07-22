"""
Intent OS — Adapter Base Interface (Adapter Layer)

Defines the abstract contract that all Runtime Adapters must implement.
This is the hardware-driver equivalent in the Intent OS architecture:
the Adapter layer is what allows different AI runtimes to execute the same
Capability Manifest with consistent behavior.

Each Adapter:
  1. Receives a CapabilityManifest and input data
  2. Maps the Intent OS schema to the runtime's native format
     (e.g., OpenAI Function Calling, Anthropic Tool Use)
  3. Executes the capability on the runtime
  4. Maps the runtime's response back to the Intent OS schema
  5. Returns structured results with metadata
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.models import CapabilityManifest


class AdapterBase(ABC):
    """
    Abstract base class for all Runtime Adapters.

    Every adapter must implement:
      - name: Adapter identifier (e.g., "openai", "anthropic")
      - version: Adapter implementation version
      - default_model: Default model identifier
      - execute(): Main execution method

    Design principle: Adapters do NOT interpret the semantic content.
    They translate schema → runtime format → execute → translate back.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Adapter identifier used for routing."""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Adapter implementation version."""
        pass

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Default model identifier for this runtime."""
        pass

    @abstractmethod
    def execute(
        self,
        manifest: CapabilityManifest,
        input_data: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute a capability on this runtime.

        Args:
            manifest: Parsed CapabilityManifest to execute.
            input_data: Input parameters matching manifest.input_schema.
            **kwargs: Additional runtime-specific parameters (e.g., model override).

        Returns:
            Execution results as a dict matching manifest.output_schema.
            May include internal metadata keys prefixed with '_' (e.g., _token_usage, _cost).

        Raises:
            RuntimeError: If execution fails on the runtime.
        """
        pass

    def can_execute(self, manifest: CapabilityManifest) -> bool:
        """
        Check whether this adapter can execute the given manifest.

        Override to implement capability-specific compatibility checks.

        Args:
            manifest: The capability manifest to check.

        Returns:
            True if this adapter can execute the capability.
        """
        return True
