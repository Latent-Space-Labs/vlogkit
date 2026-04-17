"""Per-project pub/sub broker for analyze + other event streams."""
from __future__ import annotations

import asyncio
from collections import defaultdict

from vlogkit.server.schemas import AnalyzeEvent


class _Subscriber:
    """Bundle of (queue, loop) so publish can cross event loops safely.

    In production under uvicorn every request shares one loop, so this is a
    no-op. Under Starlette's TestClient each request runs in its own portal
    with its own loop, and ``asyncio.Queue`` objects are loop-bound — so
    publishing from loop A into a queue awaited on loop B silently stalls
    after the first event. Capturing the subscriber's loop at subscribe
    time and using ``call_soon_threadsafe`` from publish makes this safe.
    """

    __slots__ = ("queue", "loop")

    def __init__(self, queue: asyncio.Queue[AnalyzeEvent], loop: asyncio.AbstractEventLoop):
        self.queue = queue
        self.loop = loop


class WsBroker:
    """In-memory fan-out. One queue per connected WebSocket."""

    def __init__(self) -> None:
        self._subs: dict[str, list[_Subscriber]] = defaultdict(list)

    def subscribe(self, project_id: str) -> asyncio.Queue[AnalyzeEvent]:
        q: asyncio.Queue[AnalyzeEvent] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        self._subs[project_id].append(_Subscriber(q, loop))
        return q

    def unsubscribe(self, project_id: str, q: asyncio.Queue[AnalyzeEvent]) -> None:
        lst = self._subs.get(project_id)
        if not lst:
            return
        for sub in list(lst):
            if sub.queue is q:
                lst.remove(sub)
                return

    async def publish(self, project_id: str, evt: AnalyzeEvent) -> None:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        for sub in list(self._subs.get(project_id, [])):
            if sub.loop is current_loop:
                await sub.queue.put(evt)
            else:
                sub.loop.call_soon_threadsafe(sub.queue.put_nowait, evt)
