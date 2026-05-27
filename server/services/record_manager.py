from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime


class RecordManager:
    def __init__(self):
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    async def start_recording(
        self,
        room_id: str,
        record_url: str,
        anchor_name: str,
        save_path: str,
        save_format: str = "ts",
    ) -> str:
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', anchor_name) if anchor_name else "未知"
        output_dir = os.path.join(save_path, safe_name)
        os.makedirs(output_dir, exist_ok=True)

        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{safe_name}_{now}.{save_format}"
        filepath = os.path.join(output_dir, filename)

        user_agent = (
            "Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 "
            "(KHTML, like Gecko) SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile Safari/537.36"
        )

        cmd = [
            "ffmpeg", "-y",
            "-rw_timeout", "15000000",
            "-loglevel", "error",
            "-hide_banner",
            "-user_agent", user_agent,
            "-protocol_whitelist", "rtmp,crypto,file,http,https,tcp,tls,udp,rtp,httpproxy",
            "-thread_queue_size", "1024",
            "-analyzeduration", "20000000",
            "-probesize", "10000000",
            "-fflags", "+discardcorrupt",
            "-re", "-i", record_url,
            "-bufsize", "8000k",
            "-sn", "-dn",
            "-reconnect_delay_max", "60",
            "-reconnect_streamed",
            "-reconnect_at_eof",
            "-max_muxing_queue_size", "1024",
            "-correct_ts_overflow", "1",
            "-avoid_negative_ts", "1",
        ]

        fmt = save_format.lower()
        if fmt == "ts":
            cmd.extend(["-c:v", "copy", "-c:a", "copy", "-f", "mpegts", filepath])
        elif fmt == "flv":
            cmd.extend(["-c:v", "copy", "-c:a", "copy", "-bsf:a", "aac_adtstoasc", "-f", "flv", filepath])
        elif fmt == "mp4":
            cmd.extend(["-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", "-f", "mp4", filepath])
        elif fmt == "mkv":
            cmd.extend(["-flags", "global_header", "-c:v", "copy", "-c:a", "copy", "-f", "matroska", filepath])
        else:
            cmd.extend(["-c:v", "copy", "-c:a", "copy", "-f", "mpegts", filepath])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        self._processes[room_id] = proc
        return filepath

    async def stop_recording(self, room_id: str):
        proc = self._processes.pop(room_id, None)
        if proc and proc.returncode is None:
            try:
                proc.stdin.write(b"q\n")
                await proc.stdin.drain()
                await asyncio.wait_for(proc.wait(), timeout=10)
            except (asyncio.TimeoutError, BrokenPipeError, ProcessLookupError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass

    def is_recording(self, room_id: str) -> bool:
        proc = self._processes.get(room_id)
        return proc is not None and proc.returncode is None

    async def stop_all(self):
        for room_id in list(self._processes.keys()):
            await self.stop_recording(room_id)
