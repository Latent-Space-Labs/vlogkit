"""Tests for the per-project WebSocket broker."""
from __future__ import annotations

import asyncio

import pytest

from vlogkit.server.schemas import AnalyzeStarted
from vlogkit.server.ws import WsBroker


@pytest.mark.asyncio
async def test_broker_fans_out_to_subscribers() -> None:
    broker = WsBroker()
    q1 = broker.subscribe("p1")
    q2 = broker.subscribe("p1")

    evt = AnalyzeStarted(job_id="j1", clip_count=3)
    await broker.publish("p1", evt)

    got1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    got2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert got1 == evt
    assert got2 == evt


@pytest.mark.asyncio
async def test_broker_isolates_projects() -> None:
    broker = WsBroker()
    q_a = broker.subscribe("proj-a")
    q_b = broker.subscribe("proj-b")

    evt = AnalyzeStarted(job_id="j1", clip_count=1)
    await broker.publish("proj-a", evt)

    assert not q_b.qsize()
    assert (await asyncio.wait_for(q_a.get(), timeout=1.0)) == evt


@pytest.mark.asyncio
async def test_unsubscribe_removes_queue() -> None:
    broker = WsBroker()
    q = broker.subscribe("p1")
    broker.unsubscribe("p1", q)
    await broker.publish("p1", AnalyzeStarted(job_id="j", clip_count=0))
    assert q.qsize() == 0
