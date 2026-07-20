"""Event envelope — RFC-0500 §4."""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class Event:
    """Canonical Event envelope per SPEC-0000 §3.9 / RFC-0500 §4."""
    event_id: str
    event_type: str
    version: int = 1

    source: dict = field(default_factory=lambda: {"module": "unknown", "instance_id": ""})
    payload: dict = field(default_factory=dict)

    metadata: dict = field(default_factory=lambda: {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sequence_id": 0,
        "content_type": "application/json",
        "size_bytes": 0,
    })
    context: dict = field(default_factory=dict)

    @classmethod
    def new(cls, event_type: str, payload: dict, *,
            source: dict | None = None,
            context: dict | None = None,
            sequence_id: int = 0) -> "Event":
        raw = json.dumps(payload, default=str).encode()
        return cls(
            event_id=f"event://ref/{uuid4()}",
            event_type=event_type,
            source=source or {"module": "unknown", "instance_id": ""},
            payload=payload,
            metadata={
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sequence_id": sequence_id,
                "content_type": "application/json",
                "size_bytes": len(raw),
            },
            context=context or {},
        )

    def to_json(self) -> str:
        return json.dumps({
            "event_id": self.event_id,
            "event_type": self.event_type,
            "version": self.version,
            "source": self.source,
            "payload": self.payload,
            "metadata": self.metadata,
            "context": self.context,
        }, default=str, indent=2)

    def __repr__(self) -> str:
        return f"Event({self.event_type}, id={self.event_id[:24]}…)"
