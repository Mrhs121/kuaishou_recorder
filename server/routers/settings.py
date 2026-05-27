from __future__ import annotations

from fastapi import APIRouter, Request

from ..models import Settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_settings(request: Request):
    mgr = request.app.state.room_manager
    return mgr.get_settings().model_dump()


@router.put("")
async def update_settings(data: Settings, request: Request):
    mgr = request.app.state.room_manager
    settings = mgr.update_settings(data)
    return settings.model_dump()
