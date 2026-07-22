"""
LLM provider abstraction layer for the Ask command.

Provides a unified interface over Ollama, OpenAI, and Anthropic so callers
never deal with SDK differences.  All third-party SDKs are imported lazily.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name (e.g. ``"ollama"``)."""
        ...

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        """Send a chat completion and return the response text.

        Args:
            messages: List of message dicts with ``role`` and ``content``.
            **kwargs: Provider-specific parameters (model, temperature, etc.).

        Returns:
            The text content of the model's response.
        """
        ...

    @abstractmethod
    def chat_json(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a chat completion and return a parsed JSON response.

        Uses ``response_format`` where the provider supports it, otherwise
        falls back to instructing the model via the system prompt.

        Args:
            messages: List of message dicts with ``role`` and ``content``.
            **kwargs: Provider-specific parameters.

        Returns:
            The parsed JSON object from the model's response.
        """
        ...


# ---------------------------------------------------------------------------
# JSON helper shared by providers without native response_format support
# ---------------------------------------------------------------------------

_JSON_SYSTEM_PROMPT = (
    "You must respond with valid JSON only. "
    "Do not wrap the JSON in markdown code fences or include any other text. "
    "Output the raw JSON object directly."
)


def _inject_json_instruction(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Ensure the message list contains a system prompt instructing JSON output."""
    messages = list(messages)
    for i, msg in enumerate(messages):
        if msg.get("role") == "system":
            existing = msg["content"]
            messages[i] = {**msg, "content": existing + "\n\n" + _JSON_SYSTEM_PROMPT}
            return messages
    messages.insert(0, {"role": "system", "content": _JSON_SYSTEM_PROMPT})
    return messages


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------


class OllamaProvider(LLMProvider):
    """LLM provider backed by a local `Ollama <https://ollama.com>`_ instance.

    Communicates via HTTP to ``http://localhost:11434/api/chat``.
    No API key required.
    """

    name = "ollama"

    def __init__(
        self,
        model: str = "llama3.2:1b",
        base_url: str = "http://localhost:11434",
        **kwargs: Any,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")

    @property
    def model(self) -> str:
        return self._model

    # -- public API -------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        import requests

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }
        for param in ("temperature", "max_tokens", "top_p", "top_k"):
            if param in kwargs:
                payload[param] = kwargs[param]
        timeout = kwargs.get("timeout", 120)

        try:
            resp = requests.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                f"Cannot reach Ollama at {self._base_url}. "
                "Make sure Ollama is installed and running (`ollama serve`)."
            )

    def chat_json(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        messages = _inject_json_instruction(messages)
        text = self.chat(messages, **kwargs)
        return self._parse_json(text)

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        text = text.strip()
        # Strip accidental markdown fences
        if text.startswith("```"):
            first_nl = text.find("\n")
            if first_nl != -1:
                text = text[first_nl + 1 :]
            if text.endswith("```"):
                text = text[:-3].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Ollama did not return valid JSON.\nRaw response:\n{text}"
            ) from exc


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


class OpenAIProvider(LLMProvider):
    """LLM provider backed by the OpenAI Chat Completions API.

    Requires ``OPENAI_API_KEY`` environment variable (or passing ``api_key``).
    """

    name = "openai"

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self._api_key:
            raise ValueError(
                "OPENAI_API_KEY is required for OpenAIProvider. "
                "Set the environment variable or pass the api_key argument."
            )

    @property
    def model(self) -> str:
        return self._model

    # -- public API -------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        client = self._client()
        params = self._build_params(messages, kwargs)
        try:
            resp = client.chat.completions.create(**params)
            return resp.choices[0].message.content or ""
        except Exception as exc:
            self._reraise(exc)

    def chat_json(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        client = self._client()
        params = self._build_params(messages, kwargs)
        params["response_format"] = {"type": "json_object"}
        try:
            resp = client.chat.completions.create(**params)
            text = resp.choices[0].message.content or ""
            return json.loads(text)
        except Exception as exc:
            self._reraise(exc)

    # -- internals --------------------------------------------------------

    def _client(self):
        import openai  # lazy
        return openai.OpenAI(api_key=self._api_key)

    @staticmethod
    def _build_params(
        messages: list[dict[str, Any]],
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": kwargs.get("model", None),  # allow overriding per-call
            "messages": messages,
        }
        # Remove None-valued model so the instance default applies
        if params["model"] is None:
            del params["model"]
        for param in ("temperature", "max_tokens", "top_p", "frequency_penalty", "presence_penalty"):
            if param in kwargs:
                params[param] = kwargs[param]
        return params

    @staticmethod
    def _reraise(exc: Exception) -> None:
        msg = str(exc).lower()
        if "authentication" in msg or "invalid api key" in msg or "incorrect api key" in msg:
            raise RuntimeError(
                "OpenAI authentication failed. Check that your OPENAI_API_KEY is correct."
            ) from exc
        raise RuntimeError(f"OpenAI API error: {exc}") from exc


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


class AnthropicProvider(LLMProvider):
    """LLM provider backed by the Anthropic Messages API.

    Requires ``ANTHROPIC_API_KEY`` environment variable (or passing ``api_key``).
    """

    name = "anthropic"

    def __init__(
        self,
        model: str = "claude-sonnet-4",
        api_key: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self._api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required for AnthropicProvider. "
                "Set the environment variable or pass the api_key argument."
            )

    @property
    def model(self) -> str:
        return self._model

    # -- public API -------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        system, converted = self._convert_messages(messages)
        client = self._client()

        params: dict[str, Any] = {
            "model": self._model,
            "messages": converted,
            "max_tokens": kwargs.get("max_tokens", 4096),
        }
        if system:
            params["system"] = system
        if "temperature" in kwargs:
            params["temperature"] = kwargs["temperature"]
        if "top_p" in kwargs:
            params["top_p"] = kwargs["top_p"]
        if "top_k" in kwargs:
            params["top_k"] = kwargs["top_k"]

        try:
            resp = client.messages.create(**params)
            return resp.content[0].text
        except Exception as exc:
            self._reraise(exc)

    def chat_json(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        # Anthropic does not have a native response_format parameter;
        # use prompt instruction instead.
        messages = _inject_json_instruction(messages)
        text = self.chat(messages, **kwargs)
        return self._parse_json(text)

    # -- internals --------------------------------------------------------

    def _client(self):
        import anthropic  # lazy
        return anthropic.Anthropic(api_key=self._api_key)

    @staticmethod
    def _convert_messages(
        messages: list[dict[str, Any]],
    ) -> tuple[Optional[str], list[dict[str, Any]]]:
        """Split system message out and convert to Anthropic message format."""
        system: Optional[str] = None
        converted: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                system = content
            elif role in ("user", "assistant"):
                converted.append({"role": role, "content": content})
            # Drop tool / function messages silently - Anthropic handles them
            # differently and the basic Ask command does not use them.
        return system, converted

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            first_nl = text.find("\n")
            if first_nl != -1:
                text = text[first_nl + 1 :]
            if text.endswith("```"):
                text = text[:-3].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Anthropic did not return valid JSON.\nRaw response:\n{text}"
            ) from exc

    @staticmethod
    def _reraise(exc: Exception) -> None:
        msg = str(exc).lower()
        if "authentication" in msg or "invalid" in msg and "key" in msg:
            raise RuntimeError(
                "Anthropic authentication failed. "
                "Check that your ANTHROPIC_API_KEY is correct."
            ) from exc
        raise RuntimeError(f"Anthropic API error: {exc}") from exc


# ---------------------------------------------------------------------------
# Auto
# ---------------------------------------------------------------------------


class AutoProvider(LLMProvider):
    """Auto-selects a provider based on what is available on the current machine.

    Priority:
        1. **Ollama** — if a local Ollama instance is reachable (no key needed).
        2. **OpenAI** — if ``OPENAI_API_KEY`` is set.
        3. **Anthropic** — if ``ANTHROPIC_API_KEY`` is set.
    """

    name = "auto"

    def __init__(self, **kwargs: Any) -> None:
        self._delegate = self._select(**kwargs)

    @property
    def model(self) -> str:
        return self._delegate.model  # type: ignore[union-attr]

    # -- public API -------------------------------------------------------

    def chat(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        return self._delegate.chat(messages, **kwargs)

    def chat_json(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        return self._delegate.chat_json(messages, **kwargs)

    # -- selection --------------------------------------------------------

    @staticmethod
    def _select(**kwargs: Any) -> LLMProvider:
        if _ollama_is_available():
            return OllamaProvider(**kwargs)

        if os.environ.get("OPENAI_API_KEY"):
            return OpenAIProvider(**kwargs)

        if os.environ.get("ANTHROPIC_API_KEY"):
            return AnthropicProvider(**kwargs)

        raise RuntimeError(
            "No LLM provider available.\n"
            "  - Install and start Ollama (no API key needed), or\n"
            "  - Set the OPENAI_API_KEY environment variable, or\n"
            "  - Set the ANTHROPIC_API_KEY environment variable."
        )


def _ollama_is_available() -> bool:
    """Quick check whether a local Ollama instance is reachable."""
    import requests

    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=2)
        return resp.status_code < 500
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class ProviderFactory:
    """Creates LLM providers from short configuration strings.

    Usage::

        provider = ProviderFactory.create("ollama", model="llama3.2:1b")
        provider = ProviderFactory.create("openai")
        provider = ProviderFactory.create("anthropic", model="claude-opus-4-20250514")
        provider = ProviderFactory.create("auto")
    """

    _REGISTRY: dict[str, type[LLMProvider]] = {
        "ollama": OllamaProvider,
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "auto": AutoProvider,
    }

    def __init__(self) -> None:
        raise TypeError("ProviderFactory is a static factory; do not instantiate.")

    @classmethod
    def create(cls, config: str, **kwargs: Any) -> LLMProvider:
        """Create a provider instance.

        Args:
            config: One of ``"ollama"``, ``"openai"``, ``"anthropic"``, or ``"auto"``.
            **kwargs: Forwarded to the provider constructor.

        Returns:
            An initialized :class:`LLMProvider` instance.
        """
        key = config.strip().lower()
        provider_cls = cls._REGISTRY.get(key)
        if provider_cls is None:
            raise ValueError(
                f"Unknown provider {config!r}. "
                f"Choose from: {', '.join(cls._REGISTRY)}"
            )
        return provider_cls(**kwargs)
