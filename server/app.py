from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .services.event_bus import EventBus
from .services.room_manager import RoomManager
from .routers import rooms, settings, events

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@asynccontextmanager
async def lifespan(app: FastAPI):
    event_bus = EventBus()
    room_manager = RoomManager(event_bus)

    app.state.event_bus = event_bus
    app.state.room_manager = room_manager

    await room_manager.start_all()
    yield
    await room_manager.stop_all()


app = FastAPI(title="快手直播录制", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rooms.router)
app.include_router(settings.router)
app.include_router(events.router)

# Serve frontend static files (production build)
static_dir = ROOT / "server" / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")


def main():
    import uvicorn
    uvicorn.run("server.app:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
