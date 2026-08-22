"""Synchronous publish/subscribe event bus.

Stands in for the "Event Bus" in the orchestration architecture: agents
publish what happened, other agents subscribe to what they care about,
and none of them import each other directly.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

Handler = Callable[[dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)
        self.log: list[tuple[str, dict[str, Any]]] = []

    def subscribe(self, event_type: str, handler: Handler) -> None:
        self._subscribers[event_type].append(handler)

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        self.log.append((event_type, payload))
        for handler in self._subscribers.get(event_type, []):
            handler(payload)
