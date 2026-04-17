"""Per-project pub/sub broker for analyze + other event streams."""
from __future__ import annotations

import asyncio
from collections import defaultdict

from vlogkit.server.schemas import AnalyzeEvent


class WsBroker:
    """In-memory fan-out. One queue per connected WebSocket."""

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[AnalyzeEvent]]] = defaultdict(list)

    def subscribe(self, project_id: str) -> asyncio.Queue[AnalyzeEvent]:
        q: asyncio.Queue[AnalyzeEvent] = asyncio.Queue()
        self._queues[project_id].append(q)
        return q

    def unsubscribe(self, project_id: str, q: asyncio.Queue[AnalyzeEvent]) -> None:
        lst = self._queues.get(project_id)
        if lst and q in lst:
            lst.remove(q)

    async def publish(self, project_id: str, evt: AnalyzeEvent) -> None:
        for q in list(self._queues.get(project_id, [])):
            await q.put(evt)
