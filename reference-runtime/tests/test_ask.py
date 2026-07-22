"""
Intent OS — Ask Session Tests

Tests cover:
  1. Intent and AskResult dataclass construction
  2. PreferencesStore get/set/get_all
  3. ConversationHistoryStore add/get/clear
  4. AskSession._classify_intent() with mocked LLM returning an Intent
  5. AskSession._resolve_manifest() finding an existing manifest
  6. AskSession._resolve_manifest() generating a new manifest
  7. AskSession process() happy path with mocked everything
  8. AskSession process() error path
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pytest

from core.ask import AskSession, AskResult, Intent
from core.ask_preferences import PreferencesStore, ConversationHistoryStore
from core.models import (
    CapabilityManifest,
    ExecutionRecord,
    ExecutionStatus,
    FieldSchema,
    MetadataSpec,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_manifest(**overrides: Any) -> CapabilityManifest:
    """Build a minimal CapabilityManifest for testing."""
    metadata = MetadataSpec(
        name=overrides.get("name", "test-capability"),
        version=overrides.get("version", "1.0.0"),
        publisher="intent-os",
        description="A test capability",
        tags=["test"],
    )
    input_schema = {
        "query": FieldSchema(type="string", description="The query input"),
    }
    output_schema = {
        "result": FieldSchema(type="string", description="The output result"),
    }
    return CapabilityManifest(
        metadata=metadata,
        input_schema=input_schema,
        output_schema=output_schema,
    )


@pytest.fixture
def mock_llm():
    return MagicMock()


@pytest.fixture
def mock_registry():
    return MagicMock()


@pytest.fixture
def mock_executor():
    return MagicMock()


def _make_session(
    registry: MagicMock,
    executor: MagicMock,
    llm: MagicMock,
    tmp_dir: Path,
    name: str = "test.db",
) -> AskSession:
    return AskSession(
        registry=registry,
        executor=executor,
        llm_provider=llm,
        preferences=PreferencesStore(db_path=str(tmp_dir / name)),
    )


# ====================================================================
# 1. Intent and AskResult dataclass construction
# ====================================================================


class TestDataclassConstruction:
    """Intent and AskResult can be constructed with various field combinations."""

    def test_intent_defaults(self):
        intent = Intent(action="test action")
        assert intent.action == "test action"
        assert intent.capability_name is None
        assert intent.confidence == 0.0
        assert intent.input_fields == {}
        assert intent.preferred_adapter is None
        assert intent.missing_info == []

    def test_intent_full(self):
        intent = Intent(
            action="send email",
            capability_name="email-sender",
            confidence=0.95,
            input_fields={"to": "user@example.com", "subject": "Hello"},
            preferred_adapter="anthropic",
            missing_info=["body"],
        )
        assert intent.action == "send email"
        assert intent.capability_name == "email-sender"
        assert intent.confidence == 0.95
        assert intent.input_fields == {"to": "user@example.com", "subject": "Hello"}
        assert intent.preferred_adapter == "anthropic"
        assert intent.missing_info == ["body"]

    def test_ask_result_defaults(self):
        result = AskResult(success=True, summary="Done", record={"id": 1})
        assert result.success is True
        assert result.summary == "Done"
        assert result.record == {"id": 1}
        assert result.manifest_created is False
        assert result.error is None

    def test_ask_result_full(self):
        result = AskResult(
            success=False,
            summary="Failed",
            record={},
            manifest_created=True,
            error="Something went wrong",
        )
        assert result.success is False
        assert result.summary == "Failed"
        assert result.manifest_created is True
        assert result.error == "Something went wrong"


# ====================================================================
# 2. PreferencesStore get/set/get_all
# ====================================================================


class TestPreferencesStore:
    """Key-value preference store backed by SQLite."""

    def test_set_and_get(self, tmp_path):
        store = PreferencesStore(db_path=str(tmp_path / "prefs.db"))
        store.set("theme", "dark")
        assert store.get("theme") == "dark"

    def test_get_returns_default_when_missing(self, tmp_path):
        store = PreferencesStore(db_path=str(tmp_path / "prefs_default.db"))
        assert store.get("nonexistent", "fallback") == "fallback"

    def test_get_returns_none_when_missing_no_default(self, tmp_path):
        store = PreferencesStore(db_path=str(tmp_path / "prefs_nodefault.db"))
        assert store.get("nonexistent") is None

    def test_overwrite_existing_value(self, tmp_path):
        store = PreferencesStore(db_path=str(tmp_path / "prefs_overwrite.db"))
        store.set("key", "first")
        store.set("key", "second")
        assert store.get("key") == "second"

    def test_round_trips_non_string_types(self, tmp_path):
        store = PreferencesStore(db_path=str(tmp_path / "prefs_types.db"))
        store.set("int_val", 42)
        store.set("float_val", 3.14)
        store.set("list_val", [1, 2, 3])
        store.set("dict_val", {"a": 1})
        store.set("bool_val", True)
        store.set("none_val", None)
        assert store.get("int_val") == 42
        assert store.get("float_val") == 3.14
        assert store.get("list_val") == [1, 2, 3]
        assert store.get("dict_val") == {"a": 1}
        assert store.get("bool_val") is True
        assert store.get("none_val") is None

    def test_get_all_empty(self, tmp_path):
        store = PreferencesStore(db_path=str(tmp_path / "prefs_empty.db"))
        assert store.get_all() == {}

    def test_get_all_returns_all_entries(self, tmp_path):
        store = PreferencesStore(db_path=str(tmp_path / "prefs_all.db"))
        store.set("a", 1)
        store.set("b", "hello")
        store.set("c", [True])
        assert store.get_all() == {"a": 1, "b": "hello", "c": [True]}

    def test_multiple_stores_are_isolated(self, tmp_path):
        store_a = PreferencesStore(db_path=str(tmp_path / "prefs_a.db"))
        store_b = PreferencesStore(db_path=str(tmp_path / "prefs_b.db"))
        store_a.set("key", "value_a")
        store_b.set("key", "value_b")
        assert store_a.get("key") == "value_a"
        assert store_b.get("key") == "value_b"


# ====================================================================
# 3. ConversationHistoryStore add/get/clear
# ====================================================================


class TestConversationHistoryStore:
    """Conversation history persistence with add, get, and clear operations."""

    def test_add_entry_returns_positive_id(self, tmp_path):
        store = ConversationHistoryStore(db_path=str(tmp_path / "hist_add.db"))
        entry_id = store.add_entry("session-1", "user", content="Hello")
        assert isinstance(entry_id, int)
        assert entry_id > 0

    def test_get_history_single_entry(self, tmp_path):
        store = ConversationHistoryStore(db_path=str(tmp_path / "hist_single.db"))
        store.add_entry("session-1", "user", content="Hello")
        history = store.get_history("session-1")
        assert len(history) == 1
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello"
        assert history[0]["session_id"] == "session-1"

    def test_get_history_multiple_entries_oldest_first(self, tmp_path):
        store = ConversationHistoryStore(db_path=str(tmp_path / "hist_multi.db"))
        store.add_entry("session-1", "user", content="First")
        store.add_entry("session-1", "assistant", content="Middle")
        store.add_entry("session-1", "user", content="Last")
        history = store.get_history("session-1")
        assert len(history) == 3
        assert [e["content"] for e in history] == ["First", "Middle", "Last"]

    def test_get_history_respects_limit(self, tmp_path):
        store = ConversationHistoryStore(db_path=str(tmp_path / "hist_limit.db"))
        for i in range(5):
            store.add_entry("session-1", "user", content=f"msg {i}")
        history = store.get_history("session-1", limit=3)
        assert len(history) == 3

    def test_get_history_returns_empty_list_for_unknown_session(self, tmp_path):
        store = ConversationHistoryStore(db_path=str(tmp_path / "hist_unknown.db"))
        store.add_entry("other", "user", content="Hello")
        assert store.get_history("nonexistent") == []

    def test_clear_session_removes_only_target_session(self, tmp_path):
        store = ConversationHistoryStore(db_path=str(tmp_path / "hist_clear.db"))
        store.add_entry("session-1", "user", content="A")
        store.add_entry("session-1", "assistant", content="B")
        store.add_entry("session-2", "user", content="C")
        deleted = store.clear_session("session-1")
        assert deleted == 2
        assert store.get_history("session-1") == []
        assert len(store.get_history("session-2")) == 1

    def test_add_entry_with_metadata(self, tmp_path):
        store = ConversationHistoryStore(db_path=str(tmp_path / "hist_meta.db"))
        store.add_entry(
            "session-1",
            "user",
            content="Hello",
            metadata={"source": "web", "priority": 1},
        )
        history = store.get_history("session-1")
        assert history[0]["metadata"] == {"source": "web", "priority": 1}


# ====================================================================
# 4. AskSession._classify_intent() with mocked LLM returning an Intent
# ====================================================================


class TestClassifyIntent:
    """LLM-based intent classification returns a structured Intent."""

    def test_returns_structured_intent(self, mock_llm, mock_registry, mock_executor, tmp_path):
        mock_llm.chat_json.return_value = {
            "action": "send email",
            "capability_name": "email-sender",
            "confidence": 0.95,
            "input_fields": {"to": "user@example.com"},
            "preferred_adapter": None,
            "missing_info": ["body"],
        }
        mock_registry.list_capabilities.return_value = [
            {"name": "email-sender", "description": "Sends emails", "tags": []},
        ]

        session = _make_session(mock_registry, mock_executor, mock_llm, tmp_path)
        intent = session._classify_intent("send an email to user@example.com")

        assert isinstance(intent, Intent)
        assert intent.action == "send email"
        assert intent.capability_name == "email-sender"
        assert intent.confidence == 0.95
        assert intent.input_fields == {"to": "user@example.com"}
        assert intent.preferred_adapter is None
        assert intent.missing_info == ["body"]

    def test_handles_llm_failure_gracefully(self, mock_llm, mock_registry, mock_executor, tmp_path):
        mock_llm.chat_json.side_effect = RuntimeError("LLM unavailable")
        mock_registry.list_capabilities.return_value = []

        session = _make_session(mock_registry, mock_executor, mock_llm, tmp_path)
        intent = session._classify_intent("do something")

        assert isinstance(intent, Intent)
        assert intent.action == "do something"
        assert intent.capability_name is None
        assert intent.confidence == 0.0
        assert intent.input_fields == {}

    def test_includes_capability_list_in_prompt(self, mock_llm, mock_registry, mock_executor, tmp_path):
        mock_llm.chat_json.return_value = {
            "action": "search",
            "capability_name": None,
            "confidence": 0.0,
        }
        caps = [
            {"name": "web-search", "description": "Search the web", "tags": ["search"]},
            {"name": "calculator", "description": "Do math", "tags": ["math"]},
        ]
        mock_registry.list_capabilities.return_value = caps

        session = _make_session(mock_registry, mock_executor, mock_llm, tmp_path)
        session._classify_intent("search something")

        call_args = mock_llm.chat_json.call_args[0][0]
        system_msg = next(m for m in call_args if m["role"] == "system")
        assert "web-search" in system_msg["content"]
        assert "calculator" in system_msg["content"]

    def test_empty_capability_list_generates_prompt(self, mock_llm, mock_registry, mock_executor, tmp_path):
        mock_llm.chat_json.return_value = {
            "action": "do something",
            "capability_name": None,
            "confidence": 0.0,
        }
        mock_registry.list_capabilities.return_value = []

        session = _make_session(mock_registry, mock_executor, mock_llm, tmp_path)
        session._classify_intent("do something")

        call_args = mock_llm.chat_json.call_args[0][0]
        system_msg = next(m for m in call_args if m["role"] == "system")
        assert "no capabilities are currently registered" in system_msg["content"]


# ====================================================================
# 5. AskSession._resolve_manifest() — finding an existing manifest
# ====================================================================


class TestResolveManifestExisting:
    """Resolution finds an existing manifest via registry search."""

    def test_high_confidence_finds_existing(self, mock_llm, mock_registry, mock_executor, tmp_path):
        manifest = _make_manifest(name="email-sender")
        mock_registry.find_by_text.return_value = [
            {"capability": {"name": "email-sender", "version": "1.0.0"}, "score": 0.95},
        ]
        mock_registry.get.return_value = manifest

        session = _make_session(mock_registry, mock_executor, mock_llm, tmp_path)
        intent = Intent(
            action="send email",
            capability_name="email-sender",
            confidence=0.95,
        )
        resolved, created = session._resolve_manifest(intent)

        assert resolved is manifest
        assert created is False
        mock_registry.find_by_text.assert_called_once_with("email-sender")
        mock_registry.get.assert_called_once_with("email-sender")

    def test_barely_above_threshold_still_finds(self, mock_llm, mock_registry, mock_executor, tmp_path):
        manifest = _make_manifest(name="barely-match")
        mock_registry.find_by_text.return_value = [
            {"capability": {"name": "barely-match", "version": "1.0.0"}, "score": 0.61},
        ]
        mock_registry.get.return_value = manifest

        session = _make_session(mock_registry, mock_executor, mock_llm, tmp_path)
        intent = Intent(action="do it", capability_name="barely-match", confidence=0.6001)
        resolved, created = session._resolve_manifest(intent)

        assert resolved is manifest
        assert created is False

    def test_no_match_triggers_generation(self, mock_llm, mock_registry, mock_executor, tmp_path):
        mock_registry.find_by_text.return_value = []
        mock_llm.chat.return_value = (
            "kind: Capability\n"
            "metadata:\n"
            "  name: generated-cap\n"
            "  version: 1.0.0\n"
            "  publisher: intent-os\n"
            "  description: Generated on the fly\n"
            "  tags: []\n"
            "spec:\n"
            "  input:\n"
            "    query:\n"
            "      type: string\n"
            "      description: The search query\n"
            "  output:\n"
            "    result:\n"
            "      type: string\n"
            "      description: The result\n"
            "  security:\n"
            "    risk: low\n"
            "    require_approval: false\n"
        )

        session = _make_session(mock_registry, mock_executor, mock_llm, tmp_path)
        intent = Intent(
            action="search",
            capability_name="nonexistent",
            confidence=0.95,
        )
        resolved, created = session._resolve_manifest(intent)

        assert resolved is not None
        assert created is True
        assert resolved.name == "generated-cap"


# ====================================================================
# 6. AskSession._resolve_manifest() — generating a new manifest
# ====================================================================


class TestResolveManifestGenerate:
    """Resolution generates a new manifest via LLM (NOT auto-registered)."""

    def test_low_confidence_generates_new_manifest(self, mock_llm, mock_registry, mock_executor, tmp_path):
        mock_llm.chat.return_value = (
            "kind: Capability\n"
            "metadata:\n"
            "  name: auto-cap\n"
            "  version: 1.0.0\n"
            "  publisher: intent-os\n"
            "  description: Auto-generated capability\n"
            "  tags: [auto]\n"
            "spec:\n"
            "  input:\n"
            "    query:\n"
            "      type: string\n"
            "      description: Input query\n"
            "  output:\n"
            "    result:\n"
            "      type: string\n"
            "      description: Output result\n"
            "  security:\n"
            "    risk: low\n"
            "    require_approval: false\n"
        )

        session = _make_session(mock_registry, mock_executor, mock_llm, tmp_path)
        intent = Intent(action="do custom thing", capability_name="auto-cap", confidence=0.3)
        resolved, created = session._resolve_manifest(intent)

        assert created is True
        assert resolved is not None
        assert resolved.name == "auto-cap"
        assert resolved.metadata.version == "1.0.0"
        mock_llm.chat.assert_called_once()
        # Manifest is parsed but NOT auto-registered — user must confirm
        mock_registry.register.assert_not_called()
        assert session.pending_manifest_yaml is not None

    def test_no_capability_name_triggers_generation(self, mock_llm, mock_registry, mock_executor, tmp_path):
        mock_llm.chat.return_value = (
            "kind: Capability\n"
            "metadata:\n"
            "  name: fallback-cap\n"
            "  version: 1.0.0\n"
            "  publisher: intent-os\n"
            "  description: Fallback\n"
            "  tags: []\n"
            "spec:\n"
            "  input:\n"
            "    query:\n"
            "      type: string\n"
            "      description: Input\n"
            "  output:\n"
            "    result:\n"
            "      type: string\n"
            "      description: Output\n"
            "  security:\n"
            "    risk: low\n"
            "    require_approval: false\n"
        )

        session = _make_session(mock_registry, mock_executor, mock_llm, tmp_path)
        intent = Intent(action="do something", capability_name=None, confidence=0.0)
        resolved, created = session._resolve_manifest(intent)

        assert resolved is not None
        assert created is True
        assert resolved.name == "fallback-cap"

    def test_llm_generation_failure_returns_none(self, mock_llm, mock_registry, mock_executor, tmp_path):
        mock_llm.chat.side_effect = RuntimeError("LLM generation failed")

        session = _make_session(mock_registry, mock_executor, mock_llm, tmp_path)
        intent = Intent(action="do something", capability_name="unknown", confidence=0.5)
        resolved, created = session._resolve_manifest(intent)

        assert resolved is None
        assert created is False

    def test_invalid_yaml_from_llm_returns_none(self, mock_llm, mock_registry, mock_executor, tmp_path):
        mock_llm.chat.return_value = "not: valid: yaml: [[broken"

        session = _make_session(mock_registry, mock_executor, mock_llm, tmp_path)
        intent = Intent(action="do something", capability_name="unknown", confidence=0.5)
        resolved, created = session._resolve_manifest(intent)

        assert resolved is None
        assert created is False

    def test_high_confidence_with_no_capability_name_generates(self, mock_llm, mock_registry, mock_executor, tmp_path):
        mock_llm.chat.return_value = (
            "kind: Capability\n"
            "metadata:\n"
            "  name: high-conf-gen\n"
            "  version: 1.0.0\n"
            "  publisher: intent-os\n"
            "  description: Generated despite high confidence\n"
            "  tags: []\n"
            "spec:\n"
            "  input:\n"
            "    query:\n"
            "      type: string\n"
            "      description: Input\n"
            "  output:\n"
            "    result:\n"
            "      type: string\n"
            "      description: Output\n"
            "  security:\n"
            "    risk: low\n"
            "    require_approval: false\n"
        )

        session = _make_session(mock_registry, mock_executor, mock_llm, tmp_path)
        intent = Intent(action="do something", capability_name=None, confidence=0.99)
        resolved, created = session._resolve_manifest(intent)

        # No capability_name => cannot search => falls to generation
        assert resolved is not None
        assert created is True


# ====================================================================
# 7. AskSession process() — happy path
# ====================================================================


class TestProcessHappyPath:
    """Full process pipeline with all mocked dependencies working."""

    def test_full_pipeline_success_with_existing_manifest(self, mock_llm, mock_registry, mock_executor, tmp_path):
        """All five steps complete; existing manifest is found."""
        mock_llm.chat_json.side_effect = [
            # 1. classify
            {
                "action": "send email",
                "capability_name": "email-sender",
                "confidence": 0.95,
                "input_fields": {"to": "user@example.com"},
                "preferred_adapter": None,
                "missing_info": ["body"],
            },
            # 3. extract params
            {"to": "user@example.com", "body": "Hello world"},
            # 5. summarise
            {"summary": "Email sent successfully to user@example.com."},
        ]
        mock_registry.list_capabilities.return_value = [
            {"name": "email-sender", "description": "Sends emails", "tags": []},
        ]

        # 2. resolve manifest — existing
        manifest = _make_manifest(name="email-sender")
        mock_registry.find_by_text.return_value = [
            {"capability": {"name": "email-sender", "version": "1.0.0"}, "score": 0.95},
        ]
        mock_registry.get.return_value = manifest

        # 4. execute
        record = ExecutionRecord(
            manifest_name="email-sender",
            manifest_version="1.0.0",
            status=ExecutionStatus.SUCCESS,
        )
        mock_executor.execute.return_value = record

        session = _make_session(mock_registry, mock_executor, mock_llm, tmp_path)
        result = session.process("send an email to user@example.com")

        assert result.success is True
        assert result.summary == "Email sent successfully to user@example.com."
        assert result.manifest_created is False
        assert result.error is None

    def test_full_pipeline_generates_new_manifest(self, mock_llm, mock_registry, mock_executor, tmp_path):
        """All five steps complete; manifest is auto-generated."""
        mock_llm.chat_json.side_effect = [
            # 1. classify — low confidence
            {
                "action": "search the web",
                "capability_name": None,
                "confidence": 0.2,
                "input_fields": {},
                "preferred_adapter": None,
                "missing_info": ["query"],
            },
            # 3. extract params
            {"query": "intent os"},
            # 5. summarise
            {"summary": "Search completed for 'intent os'."},
        ]
        mock_registry.list_capabilities.return_value = []
        mock_registry.find_by_text.return_value = []

        # 2. generate manifest via LLM
        mock_llm.chat.return_value = (
            "kind: Capability\n"
            "metadata:\n"
            "  name: web-search\n"
            "  version: 1.0.0\n"
            "  publisher: intent-os\n"
            "  description: Search the web\n"
            "  tags: []\n"
            "spec:\n"
            "  input:\n"
            "    query:\n"
            "      type: string\n"
            "      description: Search query\n"
            "  output:\n"
            "    result:\n"
            "      type: string\n"
            "      description: Search results\n"
            "  security:\n"
            "    risk: low\n"
            "    require_approval: false\n"
        )

        # 4. execute
        record = ExecutionRecord(
            manifest_name="web-search",
            manifest_version="1.0.0",
            status=ExecutionStatus.SUCCESS,
        )
        mock_executor.execute.return_value = record

        session = _make_session(mock_registry, mock_executor, mock_llm, tmp_path)
        result = session.process("search for intent os")

        assert result.success is True
        assert result.manifest_created is True
        assert result.summary == "Search completed for 'intent os'."
        # Manifest was generated but NOT auto-registered
        mock_registry.register.assert_not_called()
        assert session.pending_manifest_yaml is not None


# ====================================================================
# 8. confirm_and_register
# ====================================================================

class TestConfirmAndRegister:
    """User confirmation flow for saving generated manifests."""

    def test_confirm_registers_pending(self, mock_llm, mock_registry, mock_executor, tmp_path):
        """Confirming registers the pending manifest."""
        mock_llm.chat.return_value = (
            "kind: Capability\nmetadata:\n  name: test-cap\n  version: 1.0.0\n"
            "spec:\n  input:\n    x:\n      type: string\n"
            "  output:\n    y:\n      type: string\n"
        )
        session = _make_session(mock_registry, mock_executor, mock_llm, tmp_path)
        intent = Intent(action="test", capability_name="test-cap", confidence=0.3)
        session._resolve_manifest(intent)
        assert session.pending_manifest_yaml is not None

        assert session.confirm_and_register() is True
        mock_registry.register.assert_called_once()
        assert session.pending_manifest_yaml is None

    def test_confirm_without_pending_returns_false(self, mock_registry, mock_executor, mock_llm, tmp_path):
        """Confirming with no pending manifest returns False."""
        session = _make_session(mock_registry, mock_executor, mock_llm, tmp_path)
        assert session.confirm_and_register() is False
        mock_registry.register.assert_not_called()


# ====================================================================
# 9. AskSession process() — error path
# ====================================================================


class TestProcessErrorPath:
    """Error handling in the process pipeline."""

    def test_unable_to_resolve_manifest_returns_error(self, mock_llm, mock_registry, mock_executor, tmp_path):
        """When no manifest can be resolved or generated, a graceful error is returned."""
        mock_llm.chat_json.return_value = {
            "action": "do something",
            "capability_name": "unknown",
            "confidence": 0.5,
            "input_fields": {},
            "preferred_adapter": None,
            "missing_info": [],
        }
        mock_registry.list_capabilities.return_value = []
        mock_registry.find_by_text.return_value = []
        mock_llm.chat.side_effect = RuntimeError("LLM generation failed")

        session = _make_session(mock_registry, mock_executor, mock_llm, tmp_path)
        result = session.process("do something")

        assert result.success is False
        assert "Could not resolve or generate" in result.summary
        assert result.error == "No matching capability and unable to generate one."
        assert result.manifest_created is False

    def test_executor_failure_returns_error(self, mock_llm, mock_registry, mock_executor, tmp_path):
        """When the executor raises, process returns a failure AskResult."""
        mock_llm.chat_json.side_effect = [
            # 1. classify
            {
                "action": "crash test",
                "capability_name": "crashy-cap",
                "confidence": 0.95,
                "input_fields": {"query": "test"},
                "preferred_adapter": None,
                "missing_info": [],
            },
            # 3. extract params (succeeds)
            {"query": "test"},
        ]
        mock_registry.list_capabilities.return_value = [
            {"name": "crashy-cap", "description": "A crashing capability", "tags": []},
        ]

        # 2. resolve manifest — existing
        manifest = _make_manifest(name="crashy-cap")
        mock_registry.find_by_text.return_value = [
            {"capability": {"name": "crashy-cap", "version": "1.0.0"}, "score": 0.95},
        ]
        mock_registry.get.return_value = manifest

        # 4. execute — fails
        mock_executor.execute.side_effect = RuntimeError("Execution crashed")

        session = _make_session(mock_registry, mock_executor, mock_llm, tmp_path)
        result = session.process("run the crash test")

        assert result.success is False
        assert "Execution crashed" in result.error
        assert result.manifest_created is False

    def test_classify_failure_falls_through_to_generation(self, mock_llm, mock_registry, mock_executor, tmp_path):
        """When classify raises, a fallback Intent is used and generation is attempted."""
        mock_llm.chat_json.side_effect = [
            RuntimeError("LLM classify crashed"),
            # 3. extract params (succeeds on second call)
            {"query": "test"},
            # 5. summarise
            {"summary": "Completed via fallback path."},
        ]
        mock_registry.list_capabilities.return_value = []

        # 2. generate manifest (classify failure => confidence=0 => generation path)
        mock_llm.chat.return_value = (
            "kind: Capability\n"
            "metadata:\n"
            "  name: fallback-cap\n"
            "  version: 1.0.0\n"
            "  publisher: intent-os\n"
            "  description: Fallback after classify failure\n"
            "  tags: []\n"
            "spec:\n"
            "  input:\n"
            "    query:\n"
            "      type: string\n"
            "      description: The query input\n"
            "  output:\n"
            "    result:\n"
            "      type: string\n"
            "      description: The output result\n"
            "  security:\n"
            "    risk: low\n"
            "    require_approval: false\n"
        )

        # 4. execute
        record = ExecutionRecord(
            manifest_name="fallback-cap",
            manifest_version="1.0.0",
            status=ExecutionStatus.SUCCESS,
        )
        mock_executor.execute.return_value = record

        session = _make_session(mock_registry, mock_executor, mock_llm, tmp_path)
        result = session.process("do something recoverable")

        assert result.success is True
        assert result.summary == "Completed via fallback path."
        assert result.manifest_created is True

    def test_extract_params_failure_falls_back_to_intent_fields(self, mock_llm, mock_registry, mock_executor, tmp_path):
        """When _extract_params's LLM call fails, it falls back to intent.input_fields."""
        mock_llm.chat_json.side_effect = [
            # 1. classify
            {
                "action": "search",
                "capability_name": "search-cap",
                "confidence": 0.95,
                "input_fields": {"query": "fallback value"},
                "preferred_adapter": None,
                "missing_info": [],
            },
            # 3. extract params — fails
            RuntimeError("Extraction failed"),
            # 5. summarise
            {"summary": "Search completed."},
        ]
        mock_registry.list_capabilities.return_value = [
            {"name": "search-cap", "description": "Search", "tags": []},
        ]

        manifest = _make_manifest(name="search-cap")
        mock_registry.find_by_text.return_value = [
            {"capability": {"name": "search-cap", "version": "1.0.0"}, "score": 0.95},
        ]
        mock_registry.get.return_value = manifest

        record = ExecutionRecord(
            manifest_name="search-cap",
            manifest_version="1.0.0",
            status=ExecutionStatus.SUCCESS,
        )
        mock_executor.execute.return_value = record

        session = _make_session(mock_registry, mock_executor, mock_llm, tmp_path)
        result = session.process("search for something")

        assert result.success is True
        assert result.summary == "Search completed."
        # Verify executor was called with the fallback input_fields
        call_kwargs = mock_executor.execute.call_args[1]
        assert call_kwargs["input_data"] == {"query": "fallback value"}
