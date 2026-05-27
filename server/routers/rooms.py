from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..models import RoomCreate

router = APIRouter(prefix="/api/rooms", tags=["rooms"])


def _mgr(request: Request):
    return request.app.state.room_manager


@router.get("")
async def list_rooms(request: Request):
    mgr = _mgr(request)
    return [s.model_dump() for s in mgr.get_all_statuses()]


@router.post("")
async def add_room(data: RoomCreate, request: Request):
    mgr = _mgr(request)
    room = await mgr.add_room(data)
    return room.model_dump()


@router.delete("/{room_id}")
async def remove_room(room_id: str, request: Request):
    mgr = _mgr(request)
    result = mgr.get_room(room_id)
    if not result:
        raise HTTPException(status_code=404, detail="Room not found")
    await mgr.remove_room(room_id)
    return {"ok": True}


@router.post("/{room_id}/start")
async def start_room(room_id: str, request: Request):
    mgr = _mgr(request)
    result = mgr.get_room(room_id)
    if not result:
        raise HTTPException(status_code=404, detail="Room not found")
    await mgr.start_room(room_id)
    _, status = mgr.get_room(room_id)
    return status.model_dump()


@router.post("/{room_id}/stop")
async def stop_room(room_id: str, request: Request):
    mgr = _mgr(request)
    result = mgr.get_room(room_id)
    if not result:
        raise HTTPException(status_code=404, detail="Room not found")
    await mgr.stop_room(room_id)
    _, status = mgr.get_room(room_id)
    return status.model_dump()
