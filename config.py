# -*- coding: utf-8 -*-
"""Global configuration.

Paths prefer local machine state, then PATH lookup, so other users' machines
work out of the box. yt-dlp / ffmpeg resolve via hardcoded paths first,
then PATH — not pure PATH dependency (Explorer-launched processes inherit
user PATH which may differ from terminal).

When frozen (PyInstaller), BASE points to the executable directory.
Writable directories (logs, cookies, profiles, tools) are redirected to
user data directory (LOCALAPPDATA) to avoid permission issues.
"""
import os
import re
import shutil
import sys

# ---- PyInstaller frozen detection ----
def _get_base_dir():
    """Get base directory: script dir in dev, executable dir when frozen."""
    if getattr(sys, "frozen", False):
        # PyInstaller --onedir: sys.executable is the .exe
        # PyInstaller --onefile: sys._MEIPASS is the temp extract dir
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE = _get_base_dir()

# ---- User data directory (writable) ----
def _get_user_data_dir():
    """Get writable user data directory for logs, cookies, profiles, tools."""
    if getattr(sys, "frozen", False):
        # Frozen: use LOCALAPPDATA\AppName
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "VideoDownloader")
    # Dev: use project directory
    return BASE

USER_DATA_DIR = _get_user_data_dir()
os.makedirs(USER_DATA_DIR, exist_ok=True)

# 一键安装的工具落到用户数据目录 tools\ 下；解析顺序始终是
# 本机现状 → tools\ → PATH，装完即用
TOOLS_DIR = os.path.join(USER_DATA_DIR, "tools")

# ---- 外部工具 ----
_WIN = sys.platform == "win32"


def _tool(name, *candidates):
    """按候选顺序找第一个真实存在的路径；都没有就退回 PATH 查找。"""
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return shutil.which(name) or (candidates[-1] if candidates else name)


def _ytdlp_candidates():
    return (r"yt-dlp.exe",
            os.path.join(TOOLS_DIR, "yt-dlp.exe"))


YTDLP = _tool("yt-dlp.exe" if _WIN else "yt-dlp", *_ytdlp_candidates())


def _ffmpeg_dir():
    for cand in (r"Scripts", TOOLS_DIR, os.path.dirname(YTDLP)):
        if cand and os.path.isfile(
                os.path.join(cand, "ffmpeg.exe" if _WIN else "ffmpeg")):
            return cand
    return TOOLS_DIR if os.path.isdir(TOOLS_DIR) else BASE


FFMPEG_DIR = _ffmpeg_dir()


def refresh_tool_paths():
    """工具装好后重新解析路径，本次运行内立即可用（不用重启）。"""
    global YTDLP, FFMPEG_DIR
    YTDLP = _tool("yt-dlp.exe" if _WIN else "yt-dlp", *_ytdlp_candidates())
    FFMPEG_DIR = _ffmpeg_dir()

# ---- 目录 ----
# 本机有 Downloads 就用现状；别人的机器落到「下载」文件夹
_OUTDIR_CANDIDATES = (
    r"Downloads",
    os.path.join(os.path.expanduser("~"), "Downloads"),
)
OUTDIR_DEFAULT = next((p for p in _OUTDIR_CANDIDATES if os.path.isdir(p)),
                      _OUTDIR_CANDIDATES[-1])
LOG_DIR = os.path.join(USER_DATA_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")
COOKIES_DIR = os.path.join(USER_DATA_DIR, "cookies")
COOKIES_BILI = os.path.join(COOKIES_DIR, "bilibili.txt")
# 抖音专用浏览器配置目录：扫码登录一次，登录态长期保存在这里
PROFILE_DOUYIN = os.path.join(USER_DATA_DIR, "profile_douyin")

# ---- 代理（自动探测，开源用户端口各不相同）----
def _detect_proxy():
    """探测本机代理，返回 (proxy, host, port)。

    顺序：Windows 系统代理设置（用户浏览器在用的那个，最可靠）→
    逐个试常见代理端口 → 兜底 Clash 默认 7897（连不上时预检会给出
    明确提示，用户可改 config.py）。只做 TCP 探测，不做真实请求，
    启动耗时可忽略。
    """
    host = "127.0.0.1"
    # 1) 系统代理设置
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
        enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
        if enable:
            server, _ = winreg.QueryValueEx(key, "ProxyServer")
            if server:
                if "=" in server:          # 形如 http=127.0.0.1:7890;https=...
                    for part in server.split(";"):
                        if part.startswith(("http=", "https=")):
                            server = part.split("=", 1)[1]
                            break
                server = server.replace("http://", "").strip("/")
                if ":" in server:
                    ph, pp = server.rsplit(":", 1)
                    if pp.isdigit():
                        return f"http://{ph}:{pp}", ph, int(pp)
    except Exception:
        pass
    # 2) 常见端口探测（Clash Verge / Clash / v2rayN / 通用 socks / privoxy）
    import socket
    for port in (7897, 7890, 10809, 1080, 8118, 2080, 8889):
        try:
            socket.create_connection((host, port), timeout=0.15).close()
            return f"http://{host}:{port}", host, port
        except OSError:
            continue
    # 3) 兜底
    return "http://127.0.0.1:7897", "127.0.0.1", 7897


PROXY, PROXY_HOST, PROXY_PORT = _detect_proxy()

# ---- 浏览器 UA ----
# 取真实 headed Chrome 的值。绝对不能留 headless 默认值 —— 那里面带
# "HeadlessChrome"，反爬一行代码就能认出来。
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

# ---- 支持作者（自愿）----
# Fill in your donation page URL (e.g. Afdian, PayPal); a "Support" button
# appears in the bottom-right of the UI. Empty = completely hidden.
# Default empty: no nagging, no tracking, fully optional.
DONATE_URL = ""

# ---- 画质 ----
# 对 yt-dlp 平台生效；抖音/快手取页面默认（免登录本来就只有一路/默认一路）
QUALITY_OPTIONS = ("最高", "1080p", "720p", "480p")
QUALITY_HEIGHT = {"最高": None, "1080p": 1080, "720p": 720, "480p": 480}

# ---- 平台 ----
SOURCES = ("youtube", "bilibili", "douyin", "x",
           "instagram", "kuaishou", "xiaohongshu",
           "weibo", "ixigua", "tiktok")
SOURCE_LABEL = {"youtube": "YouTube", "bilibili": "B站", "douyin": "抖音",
                "x": "X (Twitter)", "instagram": "Instagram",
                "kuaishou": "快手", "xiaohongshu": "小红书",
                "weibo": "微博", "ixigua": "西瓜视频", "tiktok": "TikTok"}

_DOMAIN_RULES = (
    ("youtube", ("youtube.com", "youtu.be")),
    ("bilibili", ("bilibili.com", "b23.tv")),
    ("douyin", ("douyin.com", "iesdouyin.com")),
    # twitter.com 是 X 改名前的域名，t.co 是分享短链，都得认
    ("x", ("x.com", "twitter.com", "t.co")),
    ("instagram", ("instagram.com", "instagr.am")),
    ("kuaishou", ("kuaishou.com", "chenzhongtech.com")),
    ("xiaohongshu", ("xiaohongshu.com", "xhslink.com")),
    ("weibo", ("weibo.com", "weibo.cn", "t.cn")),
    ("ixigua", ("ixigua.com",)),
    ("tiktok", ("tiktok.com",)),
)


def detect_source(text):
    """从一段文本里认出平台，认不出返回 None。"""
    if not text:
        return None
    t = text.strip().lower()
    for src, domains in _DOMAIN_RULES:
        for d in domains:
            if d in t:
                return src
    return None


# 按 RFC 3986 的字符集匹配，天然会在中文和空格处停下
# （抖音分享文案形如「7.36 复制打开抖音… https://v.douyin.com/xxx/ 看看」）
_URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")


def extract_url(text):
    """从剪贴板 / 拖拽内容里抠出第一个 http(s) 链接。"""
    if not text:
        return None
    m = _URL_RE.search(text)
    if not m:
        return None
    # 尾部可能是中文标点或英文句末符号，不属于 URL
    return m.group(0).rstrip(".,;:!?)]}\"'")


def display_url(url, limit=72):
    """界面上显示用的短链接。"""
    if not url:
        return ""
    return url if len(url) <= limit else url[: limit - 1] + "…"
