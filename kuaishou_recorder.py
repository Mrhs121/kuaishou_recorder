#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快手直播间录制工具

用法:
    uv run kuaishou_recorder.py <直播间URL>
    uv run kuaishou_recorder.py https://live.kuaishou.com/u/yall1102
    uv run kuaishou_recorder.py https://live.kuaishou.com/u/yall1102 --quality HD --output ./recordings
"""

import argparse
import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from typing import Optional

import httpx

from browser_cookies import extract_cookies_for_domain, SUPPORTED_BROWSERS


# ── HTTP 请求 ──────────────────────────────────────────────────────────────────

async def resolve_short_url(client: httpx.AsyncClient, url: str) -> str:
    """解析短链接，返回标准直播间 URL。长链接直接返回。"""
    if "live.kuaishou.com/u/" in url:
        return url

    response = await client.get(url, headers={
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
    })
    final_url = str(response.url)

    # 短链接重定向到移动端页面 (v.m.chenzhongtech.com/fw/live/{userId})
    # 用户ID在 URL 路径中，如 /fw/live/FF168168CC
    if "live.kuaishou.com/u/" not in final_url:
        # 优先从路径中提取 (/fw/live/FF168168CC)
        m = re.search(r'/fw/live/([^?&/]+)', final_url)
        if m:
            return f"https://live.kuaishou.com/u/{m.group(1)}"
        # 备选：从 shareObjectId 参数提取
        m = re.search(r'[?&]shareObjectId=([^&]+)', final_url)
        if m:
            return f"https://live.kuaishou.com/u/{m.group(1)}"
        raise ValueError(f"无法从短链接中提取用户ID: {final_url}")

    return final_url


async def async_req(
    url: str,
    proxy_addr: Optional[str] = None,
    headers: Optional[dict] = None,
    data: Optional[dict] = None,
    timeout: int = 20,
) -> str:
    async with httpx.AsyncClient(proxy=proxy_addr, timeout=timeout, verify=False, http2=True) as client:
        if data:
            response = await client.post(url, data=data, headers=headers)
        else:
            response = await client.get(url, headers=headers, follow_redirects=True)
        return response.text


# ── 获取直播流数据 ─────────────────────────────────────────────────────────────

def _parse_initial_state(html_str: str) -> Optional[dict]:
    """从 HTML 中解析 window.__INITIAL_STATE__ JSON"""
    m = re.search(r"<script>window.__INITIAL_STATE__=(.*?);\(function\(\)\{var s;", html_str)
    if not m:
        return None
    raw = m.group(1)
    # 替换 JavaScript 的 undefined 为 null，使其成为合法 JSON
    raw = re.sub(r'(?<=[:,\[{])\s*undefined\s*(?=[,\]}])', 'null', raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _extract_stream_from_play_list(state: dict) -> dict:
    """从 liveroom.playList 结构中提取直播流信息 (新版页面结构)"""
    play_list = state.get("liveroom", {}).get("playList", [])
    if not play_list:
        return {"is_live": False}

    item = play_list[0]

    # 检查是否被限流
    error_type = item.get("errorType")
    if error_type and error_type.get("title"):
        title = error_type["title"]
        content = error_type.get("content", "")
        print(f"[错误] {title} {content}")
        if "过快" in title or "稍后" in title:
            return {"is_live": False, "rate_limited": True}
        return {"is_live": False}

    if not item.get("isLiving"):
        author = item.get("author", {})
        return {"is_live": False, "anchor_name": author.get("name", "")}

    live_stream = item.get("liveStream", {})
    if not live_stream:
        return {"is_live": False}

    author = item.get("author", {})
    result = {"anchor_name": author.get("name", ""), "is_live": False}

    play_urls = live_stream.get("playUrls")
    if play_urls:
        if isinstance(play_urls, dict) and "h264" in play_urls:
            adaptation = play_urls["h264"].get("adaptationSet")
            if adaptation:
                result["flv_url_list"] = adaptation["representation"]
                result["is_live"] = True
        elif isinstance(play_urls, list) and play_urls:
            adaptation = play_urls[0].get("adaptationSet")
            if adaptation:
                result["flv_url_list"] = adaptation["representation"]
                result["is_live"] = True

    return result


def _extract_stream_legacy(state: dict) -> dict:
    """从旧版页面结构中提取直播流信息 (正则匹配 liveStream...gameInfo)"""
    try:
        json_str = json.dumps(state, ensure_ascii=False)
        match = re.findall(r'(\{"liveStream".*?),"gameInfo', json_str)
        if not match:
            return {"is_live": False}
        play_list = json.loads(match[0] + "}")
    except (json.JSONDecodeError, IndexError):
        return {"is_live": False}

    if "errorType" in play_list or "liveStream" not in play_list:
        return {"is_live": False}

    if not play_list.get("liveStream"):
        return {"is_live": False, "rate_limited": True}

    anchor_name = play_list.get("author", {}).get("name", "")
    result = {"anchor_name": anchor_name, "is_live": False}

    live_stream = play_list["liveStream"]
    play_urls = live_stream.get("playUrls")
    if play_urls:
        if isinstance(play_urls, dict) and "h264" in play_urls:
            adaptation = play_urls["h264"].get("adaptationSet")
            if adaptation:
                result["flv_url_list"] = adaptation["representation"]
                result["is_live"] = True
        elif isinstance(play_urls, list) and play_urls:
            adaptation = play_urls[0].get("adaptationSet")
            if adaptation:
                result["flv_url_list"] = adaptation["representation"]
                result["is_live"] = True

    return result


async def get_kuaishou_stream_data(url: str, proxy_addr: Optional[str] = None, cookies: Optional[str] = None) -> dict:
    """从快手直播间页面解析直播流地址，支持短链接"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
        "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    }
    if cookies:
        # 清理换行符和多余空白，确保 cookie 是单行
        headers["Cookie"] = "; ".join(
            part.strip() for part in cookies.replace("\n", ";").split(";") if part.strip()
        )

    # 使用同一个 client 完成短链接解析和页面请求，共享 cookies 和连接池
    async with httpx.AsyncClient(proxy=proxy_addr, timeout=20, verify=False, http2=True, follow_redirects=True) as client:
        # 解析短链接 (如 https://v.kuaishou.com/Kx0sn17z)
        try:
            url = await resolve_short_url(client, url)
        except Exception as e:
            print(f"[错误] 解析短链接失败: {e}")
            return {"is_live": False}

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await client.get(url, headers=headers)
                html_str = response.text
            except Exception as e:
                print(f"[错误] 请求页面失败: {e}")
                return {"is_live": False}

            state = _parse_initial_state(html_str)
            if not state:
                print("[错误] 页面中未找到直播数据")
                return {"is_live": False}

            # 优先用新版 playList 结构
            result = _extract_stream_from_play_list(state)
            if result.get("rate_limited"):
                if attempt < max_retries - 1:
                    wait = (attempt + 1) * 30
                    print(f"[信息] 被限流, {wait}秒后重试 ({attempt + 1}/{max_retries})...")
                    await asyncio.sleep(wait)
                    continue
                else:
                    print("[错误] 多次重试仍被限流, 请配置代理或更换 IP")
                    return {"is_live": False}

            # 如果 playList 没数据，尝试旧版解析
            if not result.get("is_live") and not result.get("anchor_name"):
                legacy = _extract_stream_legacy(state)
                if legacy.get("is_live") or legacy.get("anchor_name"):
                    result = legacy

            return result

    return {"is_live": False}


# ── 画质选择 ───────────────────────────────────────────────────────────────────

QUALITY_BITRATE = {"BD": 4000, "UHD": 2000, "HD": 1000, "SD": 800, "LD": 600}


def select_stream_url(stream_data: dict, quality: str = "OD") -> Optional[str]:
    """根据画质选择直播流 URL"""
    if not stream_data.get("is_live"):
        return None

    flv_list = stream_data.get("flv_url_list")
    if not flv_list:
        return None

    quality = quality.upper()

    if "bitrate" in flv_list[0]:
        sorted_list = sorted(flv_list, key=lambda x: x["bitrate"], reverse=True)
        target_bitrate = QUALITY_BITRATE.get(quality, 99999)
        for item in sorted_list:
            if item["bitrate"] <= target_bitrate:
                return item["url"]
        return sorted_list[-1]["url"]
    else:
        quality_order = ["LD", "SD", "HD", "UHD", "BD"]
        idx = quality_order.index(quality) if quality in quality_order else len(quality_order) - 1
        reversed_list = flv_list[::-1]
        while len(reversed_list) < 5:
            reversed_list.append(reversed_list[-1])
        return reversed_list[idx]["url"]


# ── ffmpeg 录制 ─────────────────────────────────────────────────────────────────

def record_stream(stream_url: str, anchor_name: str, output_dir: str, save_format: str = "ts") -> None:
    """使用 ffmpeg 录制直播流"""
    # 按主播名创建子文件夹
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', anchor_name) if anchor_name else "未知"
    output_dir = os.path.join(output_dir, safe_name)
    os.makedirs(output_dir, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{anchor_name}_{now}.{save_format.lower()}"
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
        "-re", "-i", stream_url,
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

    print(f"[录制] 保存到: {filepath}")
    print(f"[录制] 按 Ctrl+C 停止录制")

    process = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def handle_signal(signum, frame):
        print("\n[录制] 正在停止...")
        if sys.platform == "win32":
            process.stdin.write(b"q\n")
            process.stdin.flush()
        else:
            process.send_signal(signal.SIGINT)

    signal.signal(signal.SIGINT, handle_signal)

    try:
        process.wait()
    except KeyboardInterrupt:
        if sys.platform == "win32":
            process.stdin.write(b"q\n")
            process.stdin.flush()
        else:
            process.send_signal(signal.SIGINT)
        process.wait()

    print(f"[录制] 已停止, 文件: {filepath}")


# ── 主流程 ──────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="快手直播间录制工具")
    parser.add_argument("url", help="快手直播间 URL, 如 https://live.kuaishou.com/u/xxxxx")
    parser.add_argument("--quality", "-q", default="OD", choices=["OD", "BD", "UHD", "HD", "SD", "LD"],
                        help="画质: OD(原画) BD(蓝光) UHD(超清) HD(高清) SD(标清) LD(流畅), 默认 OD")
    default_output = os.path.join(os.path.expanduser("~"), "kuaishou_live")
    parser.add_argument("--output", "-o", default=default_output,
                        help=f"输出目录, 默认 {default_output}")
    parser.add_argument("--format", "-f", default="ts", choices=["ts", "flv", "mp4", "mkv"],
                        help="录制格式, 默认 ts")
    parser.add_argument("--cookie", "-c", default=None, help="快手 cookie 字符串")
    parser.add_argument("--cookies-from-browser", "-b", default=None, metavar="BROWSER",
                        help=f"从浏览器提取 cookies, 可选: {', '.join(sorted(SUPPORTED_BROWSERS))}")
    parser.add_argument("--proxy", "-p", default=None, help="代理地址, 如 http://127.0.0.1:7890")
    parser.add_argument("--check", action="store_true", help="仅检查直播状态, 不录制")
    args = parser.parse_args()

    # 获取 cookies
    cookie = args.cookie
    if args.cookies_from_browser and not cookie:
        print(f"[信息] 正在从 {args.cookies_from_browser} 提取 cookies...")
        try:
            cookie = extract_cookies_for_domain(args.cookies_from_browser, ".kuaishou.com")
            if cookie:
                print(f"[信息] 成功提取 cookies")
            else:
                print(f"[警告] 未找到 kuaishou.com 的 cookies, 请先在浏览器中登录快手")
        except Exception as e:
            print(f"[警告] 提取 cookies 失败: {e}")

    print(f"[信息] 正在获取直播信息: {args.url}")
    stream_data = await get_kuaishou_stream_data(args.url, proxy_addr=args.proxy, cookies=cookie)

    anchor_name = stream_data.get("anchor_name", "未知")
    print(f"[信息] 主播: {anchor_name}")

    if not stream_data.get("is_live"):
        print("[信息] 未在直播")
        return

    print(f"[信息] 正在直播中")

    stream_url = select_stream_url(stream_data, args.quality)
    if not stream_url:
        print("[错误] 未找到可用的直播流地址")
        return

    print(f"[信息] 直播流: {stream_url[:80]}...")

    if args.check:
        return

    record_stream(stream_url, anchor_name, args.output, args.format)


if __name__ == "__main__":
    asyncio.run(main())
