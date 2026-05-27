from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

router = APIRouter(tags=["events"])


@router.get("/api/events")
async def sse_events(request: Request):
    event_bus = request.app.state.event_bus
    mgr = request.app.state.room_manager
    queue = event_bus.subscribe()

    async def event_generator():
        try:
            # Send initial full state
            yield {
                "event": "room_list",
                "data": [s.model_dump() for s in mgr.get_all_statuses()],
            }
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30)
                    yield msg
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield {"event": "ping", "data": ""}
        finally:
            event_bus.unsubscribe(queue)

    return EventSourceResponse(event_generator())
