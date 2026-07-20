"""In-memory Event Bus — RFC-0500 §5.

At-least-once delivery, push subscriptions, dead-letter queue.
"""

import enum
import threading
import time
from collections import defaultdict
from typing import Callable

from .event import Event


class DeliveryStatus(enum.Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    DEAD_LETTER = "dead_letter"


class DeadLetterEntry:
    """An event that exhausted delivery retries."""
    def __init__(self, event: Event, subscriber_id: str, attempts: list[dict]):
        self.event = event
        self.subscriber_id = subscriber_id
        self.attempts = attempts
        self.moved_at: str = ""


_SubCallback = Callable[[Event], bool | None]  # return False to nack


class EventBus:
    """In-memory pub/sub with at-least-once delivery."""

    def __init__(self):
        self._lock = threading.Lock()
        self._subscriptions: dict[str, list[_SubCallback]] = defaultdict(list)
        self._dead_letter: list[DeadLetterEntry] = []
        self._sequence = 0

    # ── subscription ────────────────────────────────────────────────

    def subscribe(self, event_type_prefix: str, callback: _SubCallback):
        """Register a callback for events whose type starts with *prefix*."""
        with self._lock:
            self._subscriptions[event_type_prefix].append(callback)

    def unsubscribe(self, event_type_prefix: str, callback: _SubCallback):
        with self._lock:
            try:
                self._subscriptions[event_type_prefix].remove(callback)
            except ValueError:
                pass

    # ── publish ─────────────────────────────────────────────────────

    def publish(self, event: Event) -> list[DeadLetterEntry]:
        """Deliver *event* to all matching subscribers.

        Returns any dead-letter entries created during delivery.
        """
        with self._lock:
            self._sequence += 1
            event.metadata["sequence_id"] = self._sequence

        dead = []
        for prefix, callbacks in self._matching(event.event_type):
            for cb in callbacks:
                attempts: list[dict] = []
                ok = False
                for attempt in range(1, 4):  # max_retries=3
                    try:
                        result = cb(event)
                        if result is False:
                            raise ValueError("subscriber nack")
                        ok = True
                        break
                    except Exception as exc:
                        attempts.append({
                            "attempt": attempt,
                            "error": str(exc),
                            "at": time.time(),
                        })
                        time.sleep(0.1 * attempt)  # simple backoff

                if not ok:
                    entry = DeadLetterEntry(event, prefix, attempts)
                    entry.moved_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    self._dead_letter.append(entry)
                    dead.append(entry)
        return dead

    def _matching(self, event_type: str) -> list[tuple[str, list]]:
        with self._lock:
            return [(p, list(cbs)) for p, cbs in self._subscriptions.items()
                    if event_type.startswith(p)]

    # ── dead-letter ─────────────────────────────────────────────────

    @property
    def dead_letter_queue(self) -> list[DeadLetterEntry]:
        return list(self._dead_letter)

    def replay_dead_letter(self) -> list[DeadLetterEntry]:
        """Re-attempt delivery of all dead-letter events."""
        pending = list(self._dead_letter)
        self._dead_letter.clear()
        still_dead = []
        for entry in pending:
            event = entry.event
            dead = self.publish(event)
            still_dead.extend(dead)
        return still_dead
