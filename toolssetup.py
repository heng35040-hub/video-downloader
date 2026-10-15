# -*- coding: utf-8 -*-
"""Missing tool detection and one-click installer.

Downloads only from official sources; validates targets before requesting:
HTTPS only, domain must resolve to public IP (rejects private/loopback/reserved
addresses to prevent SSRF-style internal content download).

- yt-dlp: GitHub official releases (github.com/yt-dlp/yt-dlp)
- ffmpeg: gyan.dev builds — ffmpeg.org's recommended Windows build source

Security design:
- Files written via pathlib write_bytes to constant dir + literal filenames;
  no dynamic path construction.
- Zip extracted in memory; entry names (untrusted) used only for matching,
  never in path construction.
- Tool sizes manageable (~80MB zip, ~200MB extracted), in-memory handling OK.
"""
import contextlib
import io
import ipaddress
import os
import pathlib
import re
import shutil
import socket
import zipfile
from urllib.parse import urlparse

import config

_YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
_FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

# 落盘位置：程序目录 tools\，目录是常量、文件名全是字面量
_TOOLS = pathlib.Path(config.TOOLS_DIR)
_YTDLP_NAME = "yt-dlp.exe" if os.name == "nt" else "yt-dlp"
_YTDLP_EXE = _TOOLS / _YTDLP_NAME
_FFMPEG_EXE = _TOOLS / "ffmpeg.exe"
_FFPROBE_EXE = _TOOLS / "ffprobe.exe"

# zip 包内只认 bin\ 下的这两个文件（官方包结构），匹配的是原始条目名
_ZIP_MEMBER_RE = re.compile(r"(^|[\\/])bin[\\/](ffmpeg|ffprobe)\.exe$", re.I)

_TOOLS_INFO = {
    "ytdlp": {
        "name": "yt-dlp",
        "desc": "视频解析与下载核心（开源命令行工具，GitHub 最流行的下载器之一）",
        "source": "github.com/yt-dlp/yt-dlp 官方发布",
    },
    "ffmpeg": {
        "name": "ffmpeg",
        "desc": "音视频合并处理（开源多媒体框架，几乎所有播放器的底层）",
        "source": "gyan.dev —— ffmpeg.org 官方推荐的 Windows 构建源",
    },
}


class _Cancelled(Exception):
    pass


def human(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{int(n)} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def missing_tools():
    """返回缺失工具的信息列表，全齐返回 []。"""
    out = []
    if not os.path.isfile(config.YTDLP) and not shutil.which("yt-dlp"):
        out.append({**_TOOLS_INFO["ytdlp"], "key": "ytdlp"})
    has_ffmpeg = any(
        os.path.isfile(os.path.join(config.FFMPEG_DIR, n))
        for n in ("ffmpeg.exe", "ffmpeg"))
    if not has_ffmpeg and not shutil.which("ffmpeg"):
        out.append({**_TOOLS_INFO["ffmpeg"], "key": "ffmpeg"})
    return out


def _assert_public_host(url):
    """下载前的安全闸：仅 https，且域名必须解析到公网地址。"""
    u = urlparse(url)
    if u.scheme != "https":
        raise ValueError(f"仅允许 https 下载：{url}")
    host = u.hostname or ""
    for _f, _t, _p, _c, sa in socket.getaddrinfo(host, 443):
        ip = ipaddress.ip_address(sa[0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise ValueError(f"下载地址解析到了非公网地址：{host}")


def _session():
    import requests

    s = requests.Session()
    s.trust_env = False          # 工具下载直连官方源，不走用户代理
    s.headers["User-Agent"] = config.BROWSER_UA
    return s


def _download_bytes(url, progress_cb, should_cancel):
    """拉取官方源到内存，返回 bytes。只碰网络，不碰文件系统。

    直连优先；连接失败时自动改走探测到的本机代理重试一次 ——
    GitHub 直连在国内时好时坏，而很多人的 Clash 一直开着。
    """
    import requests

    _assert_public_host(url)
    session = _session()
    try:
        return _stream_to_bytes(session, url, progress_cb, should_cancel)
    except _Cancelled:
        raise
    except (requests.exceptions.ConnectionError,
            requests.exceptions.Timeout) as exc:
        if not config.PROXY:
            raise
        progress_cb(-1.0, "直连失败，改走本机代理重试…")
        session.proxies = {"http": config.PROXY, "https": config.PROXY}
        try:
            return _stream_to_bytes(session, url, progress_cb, should_cancel)
        except _Cancelled:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"直连和代理（{config.PROXY}）都连不上官方源。\n"
                "请检查网络；若代理软件没开，开启后重试一般即可。") from exc


def _stream_to_bytes(session, url, progress_cb, should_cancel):
    _assert_public_host(url)
    buf = bytearray()
    with session.get(url, stream=True, timeout=(15, 60),
                     allow_redirects=True) as resp:
        resp.raise_for_status()
        _assert_public_host(resp.url)      # 重定向后的最终地址也要过闸
        total = int(resp.headers.get("Content-Length") or 0)
        for chunk in resp.iter_content(256 * 1024):
            if should_cancel():
                raise _Cancelled()
            if not chunk:
                continue
            buf.extend(chunk)
            done = len(buf)
            if total:
                progress_cb(done / total, f"{human(done)} / {human(total)}")
            else:
                progress_cb(-1.0, f"已下载 {human(done)}")
    return bytes(buf)


def _install_ytdlp(progress_cb, should_cancel):
    """下载 yt-dlp 官方单文件可执行程序到 tools\\ 目录。"""
    data = _download_bytes(_YTDLP_URL, progress_cb, should_cancel)
    _TOOLS.mkdir(parents=True, exist_ok=True)
    _YTDLP_EXE.write_bytes(data)
    if os.name != "nt":
        _YTDLP_EXE.chmod(0o755)
    return str(_YTDLP_EXE)


def _install_ffmpeg(progress_cb, should_cancel):
    """下载官方 zip，在内存中解包，只抽出 ffmpeg.exe / ffprobe.exe。"""
    zip_data = _download_bytes(_FFMPEG_URL, progress_cb, should_cancel)
    _TOOLS.mkdir(parents=True, exist_ok=True)
    got_ffmpeg = False
    with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
        for info in z.infolist():
            if not _ZIP_MEMBER_RE.search(info.filename):
                continue
            base = os.path.basename(info.filename).lower()
            # 条目名只用来决定写哪个字面量目标，绝不参与路径构造
            if base == "ffmpeg.exe":
                _FFMPEG_EXE.write_bytes(z.read(info))
                got_ffmpeg = True
            elif base == "ffprobe.exe":
                _FFPROBE_EXE.write_bytes(z.read(info))
    if not got_ffmpeg:
        raise RuntimeError("zip 里没找到 ffmpeg.exe，官方包结构可能变了")
    return str(_FFMPEG_EXE)


def install_tool(key, progress_cb, should_cancel=lambda: False):
    """安装单个工具。progress_cb(frac, text)，should_cancel() 为真则中止。"""
    try:
        if key == "ytdlp":
            return _install_ytdlp(progress_cb, should_cancel)
        if key == "ffmpeg":
            return _install_ffmpeg(progress_cb, should_cancel)
        raise ValueError(f"未知工具：{key}")
    except Exception:
        # 只清理正在安装的这个工具的半成品，别误删已装好的兄弟工具
        for target in {"ytdlp": [_YTDLP_EXE],
                       "ffmpeg": [_FFMPEG_EXE, _FFPROBE_EXE]}.get(key, []):
            with contextlib.suppress(OSError):
                target.unlink()
        raise
    finally:
        config.refresh_tool_paths()


# ---- 后续更新 ----
# yt-dlp 是更新最勤的一环（YouTube 一改版就得跟），官方 exe 自带 -U
# 自更新能力。ffmpeg 几年才一动，不做自动更新。

_SELFUPDATE_INTERVAL = 14 * 24 * 3600      # 每两周尝试一次


def _run_selfupdate(use_proxy):
    """跑一次 yt-dlp -U。返回 (是否成功, 输出文本)。

    代理用 --proxy 旗标显式给：yt-dlp 会自己读 Windows 系统代理，
    实测会拿到过期端口连环境变量里都没有的幽灵代理 —— 空串旗标
    才是真正的直连，显式地址才是真正的代理。
    """
    import subprocess

    import procutil

    args = [str(_YTDLP_EXE), "-U",
            "--proxy", (config.PROXY if use_proxy else "")]
    r = subprocess.run(
        args, capture_output=True, text=True,
        timeout=300, creationflags=procutil.CREATE_NO_WINDOW)
    text = ((r.stdout or "") + (r.stderr or "")).strip()
    return r.returncode == 0, text


def maybe_self_update_ytdlp():
    """静默自更新 tools\\ 里的 yt-dlp（失败不吭声，下次启动再试）。

    只管自装副本：用户 PATH/pip 里自己装的 yt-dlp 不越权代管。
    """
    import logging
    import time

    if not _YTDLP_EXE.is_file():
        return
    if time.time() - _YTDLP_EXE.stat().st_mtime < _SELFUPDATE_INTERVAL:
        return
    if os.path.realpath(config.YTDLP) != os.path.realpath(str(_YTDLP_EXE)):
        return                      # 当前生效的不是自装副本
    try:
        ok, text = _run_selfupdate(False)
        if not ok and config.PROXY:
            ok, text = _run_selfupdate(True)
        logging.info("yt-dlp 自更新: %s", text[:200] if text else "无输出")
    except Exception:
        logging.exception("yt-dlp 自更新失败（忽略，两周后再试）")
    finally:
        # 无论成败都摸一下 mtime —— 已是最新时 exe 不会重写，
        # 不摸的话每次启动都会白跑一遍 -U
        with contextlib.suppress(OSError):
            _YTDLP_EXE.touch()
