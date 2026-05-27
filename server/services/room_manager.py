from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from .event_bus import EventBus
from .record_manager import RecordManager
from ..models import Room, RoomCreate, RoomStatus, RoomStatusOut, RoomsConfig, Settings

# Import from the existing CLI module
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from kuaishou_recorder import (
    get_kuaishou_stream_data,
    select_stream_url,
)
from browser_cookies import extract_cookies_for_domain


CONFIG_DIR = Path.home() / ".kuaishou_recorder"
ROOMS_FILE = CONFIG_DIR / "rooms.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"


class RoomManager:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._record_manager = RecordManager()
        self._rooms: dict[str, Room] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._statuses: dict[str, RoomStatusOut] = {}
        self._settings = Settings()
        self._load_settings()
        self._load_rooms()

    # ── Persistence ─────────────────────────────────────────────────────────

    def _load_rooms(self):
        if ROOMS_FILE.exists():
            data = json.loads(ROOMS_FILE.read_text())
            config = RoomsConfig(**data)
            for room in config.rooms:
                self._rooms[room.id] = room
                self._statuses[room.id] = RoomStatusOut(
                    id=room.id,
                    url=room.url,
                    anchor_name=room.anchor_name,
                    quality=room.quality,
                    status=RoomStatus.DISABLED if not room.enabled else RoomStatus.IDLE,
                )

    def _save_rooms(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        config = RoomsConfig(rooms=list(self._rooms.values()))
        ROOMS_FILE.write_text(config.model_dump_json(indent=2))

    def _load_settings(self):
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text())
            self._settings = Settings(**data)

    def _save_settings(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(self._settings.model_dump_json(indent=2))

    # ── Settings ────────────────────────────────────────────────────────────

    def get_settings(self) -> Settings:
        return self._settings

    def update_settings(self, settings: Settings) -> Settings:
        self._settings = settings
        self._save_settings()
        return self._settings

    # ── Room CRUD ───────────────────────────────────────────────────────────

    def get_all_statuses(self) -> list[RoomStatusOut]:
        return list(self._statuses.values())

    def get_room(self, room_id: str) -> tuple[Room, RoomStatusOut] | None:
        room = self._rooms.get(room_id)
        status = self._statuses.get(room_id)
        if room and status:
            return room, status
        return None

    async def add_room(self, data: RoomCreate) -> Room:
        room = Room(
            id=uuid.uuid4().hex[:8],
            url=data.url,
            quality=data.quality or self._settings.default_quality,
            browser=data.browser or self._settings.browser_for_cookies,
        )
        self._rooms[room.id] = room
        self._statuses[room.id] = RoomStatusOut(
            id=room.id,
            url=room.url,
            anchor_name=room.anchor_name,
            quality=room.quality,
            status=RoomStatus.IDLE,
        )
        self._save_rooms()
        await self._broadcast_status(room.id)
        return room

    async def remove_room(self, room_id: str):
        await self.stop_room(room_id)
        self._rooms.pop(room_id, None)
        self._statuses.pop(room_id, None)
        self._save_rooms()
        await self._event_bus.publish("room_list", [s.model_dump() for s in self._statuses.values()])

    # ── Start / Stop ────────────────────────────────────────────────────────

    async def start_room(self, room_id: str):
        room = self._rooms.get(room_id)
        if not room:
            return
        if room_id in self._tasks and not self._tasks[room_id].done():
            return

        room.enabled = True
        self._save_rooms()
        self._tasks[room_id] = asyncio.create_task(self._poll_room(room_id))
        await self._broadcast_status(room_id)

    async def stop_room(self, room_id: str):
        task = self._tasks.pop(room_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await self._record_manager.stop_recording(room_id)
        room = self._rooms.get(room_id)
        if room:
            room.enabled = False
            self._save_rooms()

        status = self._statuses.get(room_id)
        if status:
            status.is_recording = False
            status.status = RoomStatus.DISABLED
            status.file_path = None
            await self._broadcast_status(room_id)

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def start_all(self):
        for room_id, room in self._rooms.items():
            if room.enabled:
                self._tasks[room_id] = asyncio.create_task(self._poll_room(room_id))

    async def stop_all(self):
        for room_id in list(self._tasks.keys()):
            task = self._tasks.pop(room_id)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self._record_manager.stop_all()

    # ── Polling Loop ────────────────────────────────────────────────────────

    async def _poll_room(self, room_id: str):
        room = self._rooms[room_id]
        status = self._statuses[room_id]

        while True:
            try:
                # 每轮重新读取设置，使配置变更实时生效
                settings = self._settings
                poll_interval = settings.poll_interval

                # 手动配置的 cookies 优先，其次从浏览器提取
                cookies = settings.cookies.strip() or None
                if not cookies and room.browser:
                    try:
                        cookies = extract_cookies_for_domain(room.browser, ".kuaishou.com")
                    except Exception:
                        pass

                stream_data = await get_kuaishou_stream_data(
                    room.url,
                    proxy_addr=settings.proxy or None,
                    cookies=cookies,
                )

                anchor_name = stream_data.get("anchor_name", "")
                if anchor_name and anchor_name != status.anchor_name:
                    status.anchor_name = anchor_name
                    if room.anchor_name != anchor_name:
                        room.anchor_name = anchor_name
                        self._save_rooms()

                if not stream_data.get("is_live"):
                    if status.is_recording:
                        await self._record_manager.stop_recording(room_id)
                        status.is_recording = False
                        status.file_path = None
                    status.is_live = False
                    status.status = RoomStatus.IDLE
                    status.error_message = None
                    await self._broadcast_status(room_id)
                else:
                    status.is_live = True
                    stream_url = select_stream_url(stream_data, room.quality)
                    if not stream_url:
                        status.status = RoomStatus.ERROR
                        status.error_message = "未找到可用的直播流地址"
                        await self._broadcast_status(room_id)
                    elif not status.is_recording:
                        status.status = RoomStatus.LIVE
                        await self._broadcast_status(room_id)

                        filepath = await self._record_manager.start_recording(
                            room_id,
                            stream_url,
                            status.anchor_name or "未知",
                            settings.save_path,
                            settings.save_format,
                        )
                        status.is_recording = True
                        status.status = RoomStatus.RECORDING
                        status.file_path = filepath
                        status.record_started_at = datetime.now().isoformat()
                        status.error_message = None
                        await self._broadcast_status(room_id)

                        # Wait for ffmpeg to exit (stream ended)
                        proc = self._record_manager._processes.get(room_id)
                        if proc:
                            await proc.wait()
                        status.is_recording = False
                        status.file_path = None
                        status.status = RoomStatus.IDLE
                        await self._broadcast_status(room_id)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                status.status = RoomStatus.ERROR
                status.error_message = str(e)
                await self._broadcast_status(room_id)

            await asyncio.sleep(poll_interval)

    # ── SSE Broadcast ───────────────────────────────────────────────────────

    async def _broadcast_status(self, room_id: str):
        status = self._statuses.get(room_id)
        if status:
            await self._event_bus.publish("room_update", status.model_dump())
