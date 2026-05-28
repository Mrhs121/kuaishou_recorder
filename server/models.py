from __future__ import annotations

import os
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

_DEFAULT_SAVE_PATH = os.environ.get("RECORDER_SAVE_PATH", os.path.join(os.path.expanduser("~"), "kuaishou_live"))


class RoomStatus(str, Enum):
    IDLE = "idle"
    LIVE = "live"
    RECORDING = "recording"
    ERROR = "error"
    DISABLED = "disabled"


class RoomCreate(BaseModel):
    url: str
    quality: str = "OD"
    browser: Optional[str] = "chrome"


class Room(BaseModel):
    id: str
    url: str
    anchor_name: str = ""
    quality: str = "OD"
    enabled: bool = True
    browser: Optional[str] = "chrome"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class RoomStatusOut(BaseModel):
    id: str
    url: str
    anchor_name: str = ""
    quality: str = "OD"
    is_live: bool = False
    is_recording: bool = False
    status: RoomStatus = RoomStatus.IDLE
    file_path: Optional[str] = None
    error_message: Optional[str] = None
    record_started_at: Optional[str] = None


class Settings(BaseModel):
    save_path: str = Field(default_factory=lambda: _DEFAULT_SAVE_PATH)
    save_format: str = "ts"
    default_quality: str = "OD"
    browser_for_cookies: str = "chrome"
    cookies: str = ""
    proxy: str = ""
    poll_interval: int = 120


class RoomsConfig(BaseModel):
    rooms: list[Room] = []
