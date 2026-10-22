"""
In-Process Event Bus & SignalSource Abstraction.
Implements topic pattern: bwssb/{zone}/{site}/{asset}/{signal}
Allows seamless swapping between SimulatedSource and real MQTT/OPC-UA drivers.
"""

from typing import Protocol, AsyncIterator, Dict, Set, Optional, Callable
import asyncio
import logging
from .models import MessageEnvelope

logger = logging.getLogger("bwssb_iot.bus")

class SignalSource(Protocol):
    """Protocol for telemetry ingestion drivers (Simulated, MQTT Sparkplug B, OPC-UA)."""
    async def subscribe(self, topic_filter: str) -> AsyncIterator[MessageEnvelope]:
        ...
    async def publish(self, topic: str, envelope: MessageEnvelope) -> None:
        ...

class InProcessEventBus:
    """Lightweight asynchronous pub/sub event bus with topic wildcard matching."""

    def __init__(self):
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, topic: str, envelope: MessageEnvelope) -> None:
        async with self._lock:
            # Deliver to exact topic subscribers and wildcard '#' or '+'
            for sub_filter, queues in self._subscribers.items():
                if self._matches(sub_filter, topic):
                    for q in list(queues):
                        try:
                            q.put_nowait(envelope)
                        except asyncio.QueueFull:
                            # Drop oldest if congested
                            try:
                                q.get_nowait()
                                q.put_nowait(envelope)
                            except Exception:
                                pass

    async def subscribe(self, topic_filter: str) -> AsyncIterator[MessageEnvelope]:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        async with self._lock:
            if topic_filter not in self._subscribers:
                self._subscribers[topic_filter] = set()
            self._subscribers[topic_filter].add(q)

        try:
            while True:
                envelope = await q.get()
                yield envelope
        finally:
            async with self._lock:
                if topic_filter in self._subscribers and q in self._subscribers[topic_filter]:
                    self._subscribers[topic_filter].remove(q)
                    if not self._subscribers[topic_filter]:
                        del self._subscribers[topic_filter]

    def _matches(self, pattern: str, topic: str) -> bool:
        if pattern == "#" or pattern == "*":
            return True
        p_parts = pattern.split("/")
        t_parts = topic.split("/")
        if len(p_parts) != len(t_parts) and pattern != "#":
            return False
        for p, t in zip(p_parts, t_parts):
            if p == "+":
                continue
            if p == "#":
                return True
            if p != t:
                return False
        return True

class SimulatedSource(SignalSource):
    """Simulated telemetry publisher and subscriber."""

    def __init__(self, bus: InProcessEventBus):
        self.bus = bus

    async def subscribe(self, topic_filter: str = "#") -> AsyncIterator[MessageEnvelope]:
        async for msg in self.bus.subscribe(topic_filter):
            yield msg

    async def publish(self, topic: str, envelope: MessageEnvelope) -> None:
        await self.bus.publish(topic, envelope)

# Global singleton event bus
event_bus = InProcessEventBus()
simulated_source = SimulatedSource(event_bus)
