"""
浏览器 Cookie 提取模块

支持从 Chrome/Firefox/Safari 浏览器中提取 cookies。
移植自 yt-dlp (https://github.com/yt-dlp/yt-dlp) 的 cookies.py。

用法:
    from browser_cookies import extract_cookies_for_domain

    cookie_str = extract_cookies_for_domain("chrome", ".kuaishou.com")
"""

import base64
import glob
import hashlib
import http.cookiejar
import json
import os
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile

from Crypto.Cipher import AES


CHROMIUM_BASED_BROWSERS = {"brave", "chrome", "chromium", "edge", "opera", "vivaldi", "whale"}
SUPPORTED_BROWSERS = CHROMIUM_BASED_BROWSERS | {"firefox", "safari"}


# ── AES 解密 ──────────────────────────────────────────────────────────────────

def _unpad_pkcs7(data: bytes) -> bytes:
    pad_len = data[-1]
    if pad_len < 1 or pad_len > 16:
        raise ValueError("invalid PKCS7 padding")
    if data[-pad_len:] != bytes([pad_len] * pad_len):
        raise ValueError("invalid PKCS7 padding")
    return data[:-pad_len]


def _aes_cbc_decrypt(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    return AES.new(key, AES.MODE_CBC, iv).decrypt(ciphertext)


def _aes_gcm_decrypt(ciphertext: bytes, key: bytes, nonce: bytes, tag: bytes) -> bytes:
    return AES.new(key, AES.MODE_GCM, nonce).decrypt_and_verify(ciphertext, tag)


def _pbkdf2_sha1(password: bytes, salt: bytes, iterations: int, key_length: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha1", password, salt, iterations, key_length)


def _decrypt_aes_cbc(ciphertext: bytes, key: bytes, *, hash_prefix: bool = False) -> str | None:
    iv = b" " * 16
    plaintext = _unpad_pkcs7(_aes_cbc_decrypt(ciphertext, key, iv))
    if hash_prefix:
        plaintext = plaintext[32:]
    return plaintext.decode("utf-8")


# ── macOS Keychain ────────────────────────────────────────────────────────────

def _get_mac_keyring_password(browser_keyring_name: str) -> bytes | None:
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-w", "-a", browser_keyring_name, "-s", f"{browser_keyring_name} Safe Storage"],
            capture_output=True,
        )
        if result.returncode == 0:
            return result.stdout.rstrip(b"\n")
    except Exception:
        pass
    return None


# ── 浏览器路径 ─────────────────────────────────────────────────────────────────

def _get_chromium_browser_dir(browser_name: str) -> str:
    if sys.platform == "darwin":
        appdata = os.path.expanduser("~/Library/Application Support")
        dirs = {
            "brave": os.path.join(appdata, "BraveSoftware/Brave-Browser"),
            "chrome": os.path.join(appdata, "Google/Chrome"),
            "chromium": os.path.join(appdata, "Chromium"),
            "edge": os.path.join(appdata, "Microsoft Edge"),
            "opera": os.path.join(appdata, "com.operasoftware.Opera"),
            "vivaldi": os.path.join(appdata, "Vivaldi"),
            "whale": os.path.join(appdata, "Naver/Whale"),
        }
    elif sys.platform in ("win32", "cygwin"):
        appdata_local = os.path.expandvars("%LOCALAPPDATA%")
        appdata_roaming = os.path.expandvars("%APPDATA%")
        dirs = {
            "brave": os.path.join(appdata_local, R"BraveSoftware\Brave-Browser\User Data"),
            "chrome": os.path.join(appdata_local, R"Google\Chrome\User Data"),
            "chromium": os.path.join(appdata_local, R"Chromium\User Data"),
            "edge": os.path.join(appdata_local, R"Microsoft\Edge\User Data"),
            "opera": os.path.join(appdata_roaming, R"Opera Software\Opera Stable"),
            "vivaldi": os.path.join(appdata_local, R"Vivaldi\User Data"),
            "whale": os.path.join(appdata_local, R"Naver\Naver Whale\User Data"),
        }
    else:
        config = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        dirs = {
            "brave": os.path.join(config, "BraveSoftware/Brave-Browser"),
            "chrome": os.path.join(config, "google-chrome"),
            "chromium": os.path.join(config, "chromium"),
            "edge": os.path.join(config, "microsoft-edge"),
            "opera": os.path.join(config, "opera"),
            "vivaldi": os.path.join(config, "vivaldi"),
            "whale": os.path.join(config, "naver-whale"),
        }
    return dirs[browser_name]


def _get_chromium_keyring_name(browser_name: str) -> str:
    names = {
        "brave": "Brave",
        "chrome": "Chrome",
        "chromium": "Chromium",
        "edge": "Microsoft Edge" if sys.platform == "darwin" else "Chromium",
        "opera": "Opera" if sys.platform == "darwin" else "Chromium",
        "vivaldi": "Vivaldi" if sys.platform == "darwin" else "Chrome",
        "whale": "Whale",
    }
    return names[browser_name]


def _firefox_browser_dirs() -> list[str]:
    if sys.platform in ("cygwin", "win32"):
        return list(filter(os.path.isdir, map(os.path.expandvars, [
            R"%APPDATA%\Mozilla\Firefox\Profiles",
            R"%LOCALAPPDATA%\Packages\Mozilla.Firefox_n80bbvh6b1yt2\LocalCache\Roaming\Mozilla\Firefox\Profiles",
        ])))
    elif sys.platform == "darwin":
        return [os.path.expanduser("~/Library/Application Support/Firefox/Profiles")]
    else:
        paths = [
            os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "mozilla/firefox"),
            os.path.expanduser("~/.mozilla/firefox"),
            os.path.expanduser("~/.var/app/org.mozilla.firefox/config/mozilla/firefox"),
            os.path.expanduser("~/snap/firefox/common/.mozilla/firefox"),
        ]
        return [p for p in paths if os.path.isdir(p)]


def _newest(files):
    return max(files, key=lambda p: os.lstat(p).st_mtime, default=None)


def _open_db_copy(database_path: str, tmpdir: str) -> sqlite3.Cursor:
    copy_path = os.path.join(tmpdir, "temporary.sqlite")
    shutil.copy(database_path, copy_path)
    conn = sqlite3.connect(copy_path)
    return conn.cursor()


def _find_files(root: str, filename: str):
    if not os.path.isdir(root):
        return
    for curr_root, _, files in os.walk(root):
        for f in files:
            if f == filename:
                yield os.path.join(curr_root, f)


# ── Chrome Cookie 提取 ─────────────────────────────────────────────────────────

def _extract_chrome_cookies(browser_name: str, domain: str) -> str:
    browser_dir = _get_chromium_browser_dir(browser_name)
    keyring_name = _get_chromium_keyring_name(browser_name)

    cookie_db = _newest(_find_files(browser_dir, "Cookies"))
    if not cookie_db:
        raise FileNotFoundError(f"未找到 {browser_name} 的 Cookies 数据库")

    with tempfile.TemporaryDirectory() as tmpdir:
        cursor = _open_db_copy(cookie_db, tmpdir)
        try:
            meta_rows = cursor.execute("SELECT value FROM meta WHERE key = 'version'").fetchone()
            meta_version = int(meta_rows[0]) if meta_rows else 0

            # 获取解密密钥
            decrypt_key = None
            if sys.platform == "darwin":
                password = _get_mac_keyring_password(keyring_name)
                if password:
                    decrypt_key = _pbkdf2_sha1(password, salt=b"saltysalt", iterations=1003, key_length=16)
            elif sys.platform == "linux":
                # Linux v10 用固定密码
                decrypt_key = _pbkdf2_sha1(b"peanuts", salt=b"saltysalt", iterations=1, key_length=16)

            cursor.connection.text_factory = bytes
            cursor.execute(
                "SELECT host_key, name, value, encrypted_value, path, expires_utc, is_secure FROM cookies"
            )
            # WHERE host_key LIKE ?", (f"%{domain}",)

            cookies = {}
            for host_key, name, value, encrypted_value, path, expires_utc, is_secure in cursor.fetchall():
                host_key = host_key.decode()
                name = name.decode()

                # 只提取匹配域名的 cookies
                if domain and not (host_key == domain or host_key.endswith(domain)):
                    continue

                if value:
                    val = value.decode()
                elif encrypted_value and decrypt_key:
                    version = encrypted_value[:3]
                    ciphertext = encrypted_value[3:]
                    hash_prefix = meta_version >= 24
                    try:
                        if sys.platform == "darwin":
                            val = _decrypt_aes_cbc(ciphertext, decrypt_key, hash_prefix=hash_prefix)
                        elif sys.platform == "linux":
                            val = _decrypt_aes_cbc(ciphertext, decrypt_key, hash_prefix=hash_prefix)
                        elif sys.platform in ("win32", "cygwin"):
                            val = _decrypt_windows_chrome(ciphertext, browser_dir, hash_prefix=hash_prefix)
                        else:
                            continue
                    except Exception:
                        continue
                    if val is None:
                        continue
                else:
                    continue

                cookies[name] = val

            return "; ".join(f"{k}={v}" for k, v in cookies.items())
        finally:
            cursor.connection.close()


def _decrypt_windows_chrome(ciphertext: bytes, browser_dir: str, *, hash_prefix: bool = False) -> str | None:
    """Windows Chrome v10: AES-GCM, key from Local State + DPAPI"""
    import ctypes
    import ctypes.wintypes

    # 从 Local State 获取加密 key
    local_state = _newest(_find_files(browser_dir, "Local State"))
    if not local_state:
        return None
    with open(local_state, encoding="utf8") as f:
        data = json.load(f)
    base64_key = data.get("os_crypt", {}).get("encrypted_key")
    if not base64_key:
        return None

    encrypted_key = base64.b64decode(base64_key)
    if not encrypted_key.startswith(b"DPAPI"):
        return None

    # DPAPI 解密
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buffer = ctypes.create_string_buffer(encrypted_key[5:])
    blob_in = DATA_BLOB(ctypes.sizeof(buffer), buffer)
    blob_out = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        return None
    v10_key = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)

    # AES-GCM 解密
    nonce_length = 96 // 8
    tag_length = 16
    nonce = ciphertext[:nonce_length]
    ct = ciphertext[nonce_length:-tag_length]
    tag = ciphertext[-tag_length:]

    try:
        plaintext = _aes_gcm_decrypt(ct, v10_key, nonce, tag)
        if hash_prefix:
            plaintext = plaintext[32:]
        return plaintext.decode("utf-8")
    except Exception:
        return None


# ── Firefox Cookie 提取 ─────────────────────────────────────────────────────────

def _extract_firefox_cookies(domain: str) -> str:
    search_roots = _firefox_browser_dirs()
    if not search_roots:
        raise FileNotFoundError("未找到 Firefox 配置目录")

    cookie_dbs = []
    for root in search_roots:
        for pattern in ("", "*/", "Profiles/*/"):
            cookie_dbs.extend(glob.glob(os.path.join(root, pattern, "cookies.sqlite")))

    cookie_db = _newest(cookie_dbs)
    if not cookie_db:
        raise FileNotFoundError("未找到 Firefox cookies.sqlite")

    with tempfile.TemporaryDirectory() as tmpdir:
        cursor = _open_db_copy(cookie_db, tmpdir)
        try:
            cursor.execute("SELECT host, name, value, path, expiry, isSecure FROM moz_cookies")
            cookies = {}
            for host, name, value, path, expiry, is_secure in cursor.fetchall():
                if domain and not (host == domain or host.endswith(domain)):
                    continue
                cookies[name] = value
            return "; ".join(f"{k}={v}" for k, v in cookies.items())
        finally:
            cursor.connection.close()


# ── Safari Cookie 提取 ─────────────────────────────────────────────────────────

def _extract_safari_cookies(domain: str) -> str:
    if sys.platform != "darwin":
        raise ValueError("Safari 仅支持 macOS")

    cookies_path = os.path.expanduser("~/Library/Cookies/Cookies.binarycookies")
    if not os.path.isfile(cookies_path):
        cookies_path = os.path.expanduser(
            "~/Library/Containers/com.apple.Safari/Data/Library/Cookies/Cookies.binarycookies"
        )
    if not os.path.isfile(cookies_path):
        raise FileNotFoundError("未找到 Safari Cookies 文件")

    with open(cookies_path, "rb") as f:
        data = f.read()

    cookies = _parse_safari_cookies(data, domain)
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def _parse_safari_cookies(data: bytes, domain: str) -> dict:
    cookies = {}
    cursor = 0

    # Header: "cook" + page_count
    if data[0:4] != b"cook":
        raise ValueError("不是有效的 Safari cookies 文件")
    page_count = struct.unpack(">I", data[4:8])[0]
    cursor = 8

    page_sizes = []
    for _ in range(page_count):
        page_sizes.append(struct.unpack(">I", data[cursor:cursor + 4])[0])
        cursor += 4

    for page_size in page_sizes:
        page_data = data[cursor:cursor + page_size]
        cursor += page_size
        _parse_safari_page(page_data, domain, cookies)

    return cookies


def _parse_safari_page(page_data: bytes, domain: str, cookies: dict):
    if page_data[0:4] != b"\x00\x00\x01\x00":
        return
    num_cookies = struct.unpack("<I", page_data[4:8])[0]

    offsets = []
    offset_cursor = 8
    for _ in range(num_cookies):
        offsets.append(struct.unpack("<I", page_data[offset_cursor:offset_cursor + 4])[0])
        offset_cursor += 4

    for offset in offsets:
        try:
            _parse_safari_cookie(page_data, offset, domain, cookies)
        except Exception:
            continue


def _parse_safari_cookie(page_data: bytes, offset: int, domain: str, cookies: dict):
    pos = offset
    # cookie size
    cookie_size = struct.unpack("<I", page_data[pos:pos + 4])[0]
    pos += 4
    # flags
    flags = struct.unpack("<I", page_data[pos:pos + 4])[0]
    is_secure = bool(flags & 0x1)
    pos += 4
    # url offset
    url_offset = struct.unpack("<I", page_data[pos:pos + 4])[0]
    pos += 4
    # name offset
    name_offset = struct.unpack("<I", page_data[pos:pos + 4])[0]
    pos += 4
    # path offset
    path_offset = struct.unpack("<I", page_data[pos:pos + 4])[0]
    pos += 4
    # value offset
    value_offset = struct.unpack("<I", page_data[pos:pos + 4])[0]
    pos += 4
    # comment offset (unused)
    pos += 4
    # expiry (8 bytes double)
    expiry = struct.unpack(">d", page_data[pos:pos + 8])[0]
    pos += 8
    # creation (8 bytes double, unused)
    pos += 8

    def read_cstring(data: bytes, off: int) -> str:
        end = data.index(b"\x00", off)
        return data[off:end].decode("utf-8", errors="replace")

    cookie_domain = read_cstring(page_data, offset + url_offset)
    name = read_cstring(page_data, offset + name_offset)
    value = read_cstring(page_data, offset + value_offset)

    if domain and not (cookie_domain == domain or cookie_domain.endswith(domain)):
        return

    cookies[name] = value


# ── 公开接口 ────────────────────────────────────────────────────────────────────

def extract_cookies_for_domain(browser: str, domain: str) -> str:
    """
    从浏览器提取指定域名的 cookies，返回 "key=value; ..." 格式字符串。

    Args:
        browser: 浏览器名称 (chrome, firefox, safari, edge, brave, chromium, opera, vivaldi, whale)
        domain: 域名，如 ".kuaishou.com"

    Returns:
        cookie header 字符串
    """
    browser = browser.lower().strip()
    if browser not in SUPPORTED_BROWSERS:
        raise ValueError(f"不支持的浏览器: {browser}, 可选: {', '.join(sorted(SUPPORTED_BROWSERS))}")

    if browser == "firefox":
        return _extract_firefox_cookies(domain)
    elif browser == "safari":
        return _extract_safari_cookies(domain)
    elif browser in CHROMIUM_BASED_BROWSERS:
        return _extract_chrome_cookies(browser, domain)
    else:
        raise ValueError(f"不支持的浏览器: {browser}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="从浏览器提取指定域名的 cookies")
    parser.add_argument("browser", help="浏览器名称 (chrome, firefox, safari, edge, ...)")
    parser.add_argument("--domain", "-d", default=".kuaishou.com", help="域名, 默认 .kuaishou.com")
    args = parser.parse_args()

    try:
        cookie_str = extract_cookies_for_domain(args.browser, args.domain)
        if cookie_str:
            print(f"[信息] 提取到的 cookies ({args.browser} @ {args.domain}):")
            print(cookie_str)
        else:
            print(f"[信息] 未找到 {args.domain} 的 cookies")
    except Exception as e:
        print(f"[错误] {e}")
