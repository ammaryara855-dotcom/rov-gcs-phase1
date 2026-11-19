from collections import defaultdict
from dataclasses import dataclass, field
import queue
import time
from typing import Any, Callable


@dataclass
class Event:
    """Base event passed between decoupled modules."""

    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.monotonic)


EventCallback = Callable[[Event], None]


class EventBus:
    """Thread-safe publish/subscribe bus backed by a queue."""

    def __init__(self) -> None:
        self._queue: queue.Queue[Event] = queue.Queue()
        self._subscribers: dict[str, list[EventCallback]] = defaultdict(list)

    def subscribe(self, event_name: str, callback: EventCallback) -> None:
        self._subscribers[event_name].append(callback)

    def publish(self, event: Event) -> None:
        """Safe to call from any thread."""
        self._queue.put(event)

    def dispatch_pending(self, max_events: int = 200) -> int:
        """Dispatch queued events on the consumer/main thread."""
        dispatched = 0
        while dispatched < max_events:
            try:
                event = self._queue.get_nowait()
            except queue.Empty:
                break

            for callback in list(self._subscribers.get(event.name, [])):
                callback(event)
            for callback in list(self._subscribers.get("*", [])):
                callback(event)
            dispatched += 1

        return dispatched