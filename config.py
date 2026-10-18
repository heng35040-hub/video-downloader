# -*- coding: utf-8 -*-
"""Global configuration.

Paths prefer the app's own tools/ directory, then PATH lookup, so the app
works out of the box on any machine. yt-dlp / ffmpeg resolve via the managed
tools/ directory first, then PATH (Explorer-launched processes inherit user
PATH which may differ from terminal).

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


# ---- yt-dlp ----
# yt-dlp 直接内置（打包进 exe / 装在依赖里），首次启动不再需要联网下载。
# 命令行用**列表**表示，好让内置模块和外置 exe 互换，优先级：
#
#   1) tools\yt-dlp.exe —— 用户自己装的，或自动更新下来的（能保持最新）
#   2) 内置 yt_dlp 模块 —— 冻结时是「exe 自己再调用自己」，
#      见 main.py 顶部的 --ytdlp-cli 分发
#   3) PATH 里的 yt-dlp —— 兜底
YTDLP_CLI_FLAG = "--ytdlp-cli"
_YTDLP_EXE_NAME = "yt-dlp.exe" if _WIN else "yt-dlp"


def _bundled_ytdlp_available():
    """内置 yt_dlp 是否可用。

    刻意用 find_spec 而不是直接 import：yt_dlp 有 1000+ 个 extractor 子模块，
    真导入要花约 1.2 秒，而 config 是在**每次启动**时被导入的 ——
    为了「看一眼在不在」付这个代价太亏（实测启动会从 4.5 秒变 5.7 秒）。
    真正需要它是在跑下载时，那时候由 main.py 的 --ytdlp-cli 分发去导入。

    find_spec 万一在冻结环境里失灵（返回 None），退回真导入兜底，
    宁可慢也不能误判成「不可用」。
    """
    import importlib.util
    try:
        if importlib.util.find_spec("yt_dlp") is not None:
            return True
    except Exception:
        pass
    try:
        import yt_dlp  # noqa: F401
        return True
    except Exception:
        return False


def _bundled_ytdlp_cmd():
    """内置 yt_dlp 模块的调用方式；模块不可用则返回 None。"""
    if not _bundled_ytdlp_available():
        return None
    if getattr(sys, "frozen", False):
        # 冻结后没有独立的 python 解释器可用，只能让 exe 带旗标再跑一遍自己
        return [sys.executable, YTDLP_CLI_FLAG]
    return [sys.executable, "-m", "yt_dlp"]


def _resolve_ytdlp_cmd():
    exe = os.path.join(TOOLS_DIR, _YTDLP_EXE_NAME)
    if os.path.isfile(exe):
        return [exe]
    bundled = _bundled_ytdlp_cmd()
    if bundled:
        return bundled
    found = shutil.which(_YTDLP_EXE_NAME)
    return [found] if found else None


YTDLP_CMD = _resolve_ytdlp_cmd()


def ytdlp_available():
    """yt-dlp 是否可用。内置之后几乎恒为 True，留作预检与自检用。"""
    return bool(YTDLP_CMD)


def _ffmpeg_dir():
    """找 ffmpeg 所在目录，顺序：tools\\ → yt-dlp 同目录 → PATH → 兜底。

    这个目录会作为 --ffmpeg-location 传给 yt-dlp：GUI 进程继承的 PATH
    未必和终端一致，显式给路径最稳，所以这里也主动把 PATH 里的 ffmpeg
    解析成具体目录。
    """
    exe_name = "ffmpeg.exe" if _WIN else "ffmpeg"
    cands = [TOOLS_DIR]
    if YTDLP_CMD:
        cands.append(os.path.dirname(YTDLP_CMD[0]))
    found = shutil.which(exe_name)
    if found:
        cands.append(os.path.dirname(found))
    for cand in cands:
        if cand and os.path.isfile(os.path.join(cand, exe_name)):
            return cand
    return TOOLS_DIR if os.path.isdir(TOOLS_DIR) else BASE


FFMPEG_DIR = _ffmpeg_dir()


def refresh_tool_paths():
    """工具装好后重新解析路径，本次运行内立即可用（不用重启）。"""
    global YTDLP_CMD, FFMPEG_DIR
    YTDLP_CMD = _resolve_ytdlp_cmd()
    FFMPEG_DIR = _ffmpeg_dir()

# ---- 目录 ----
# 默认落到系统「下载」文件夹；用户可在界面上自选保存位置
OUTDIR_DEFAULT = os.path.join(os.path.expanduser("~"), "Downloads")
LOG_DIR = os.path.join(USER_DATA_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")
COOKIES_DIR = os.path.join(USER_DATA_DIR, "cookies")
COOKIES_BILI = os.path.join(COOKIES_DIR, "bilibili.txt")
# 抖音专用浏览器配置目录：扫码登录一次，登录态长期保存在这里
PROFILE_DOUYIN = os.path.join(USER_DATA_DIR, "profile_douyin")
# B站扫码登录专用浏览器配置目录（和抖音分开，互不干扰）
PROFILE_BILI = os.path.join(USER_DATA_DIR, "profile_bili")
# 界面偏好 +「使用须知已同意」标记都存这里（JSON）
SETTINGS_FILE = os.path.join(USER_DATA_DIR, "settings.json")

# ---- 代理（自动探测，开源用户端口各不相同）----
def _handshake_proxy(host, port):
    """握手判断这个端口跑的是 SOCKS5 还是 HTTP 代理。

    返回 "socks5h" / "http" / None（端口没开或两个都不认）。
    自建 v2ray / xray / ss-local 默认开在 1080、10808，跑的什么协议只有握手
    才知道 —— 硬编码成 http 会把 SOCKS 端口当 HTTP 用，报错还很难查。
    """
    import socket
    # 先试 SOCKS5：发 \x05\x01\x00（版本5，1种方法，无需认证），期待 \x05\x00
    try:
        with socket.create_connection((host, port), timeout=0.6) as s:
            s.settimeout(0.6)
            s.sendall(b"\x05\x01\x00")
            resp = s.recv(2)
            if len(resp) == 2 and resp[0] == 5 and resp[1] == 0:
                return "socks5h"
    except OSError:
        pass
    # 再试 HTTP CONNECT：期待 "HTTP/1.x ... 200"
    try:
        with socket.create_connection((host, port), timeout=0.6) as s:
            s.settimeout(0.6)
            s.sendall(b"CONNECT example.com:443 HTTP/1.0\r\n\r\n")
            resp = s.recv(32)
            if b"HTTP/1." in resp and b" 200 " in resp:
                return "http"
    except OSError:
        pass
    return None


def _split_server(server):
    """把注册表的 ProxyServer 拆成 [(协议, 地址), ...]，保持原顺序。

    可能是 `127.0.0.1:7890`，也可能是
    `http=127.0.0.1:7890;https=127.0.0.1:7890;socks=127.0.0.1:7891`。
    """
    out = []
    for part in (server or "").split(";"):
        part = part.strip()
        if not part:
            continue
        scheme, addr = "http", part
        if "=" in part:
            k, _, v = part.partition("=")
            v = v.strip()
            if not v:
                continue
            addr = v
            if k.strip().lower() in ("socks", "socks5", "socks4"):
                scheme = "socks5h"
        out.append((scheme, addr.replace("http://", "").replace("socks5://", "")
                    .strip("/")))
    return out


def _detect_proxy():
    """探测本机代理，返回 (proxy, host, port)。

    顺序：Windows 系统代理设置（用户浏览器在用的那个，最可靠）→
    并发试常见 HTTP 端口 → SOCKS 常见端口握手认协议 → 兜底 7897。
    连不上时预检会给出提示，用户可在界面的代理设置里手动填。

    端口探测**必须并发**：串行时「一个代理都没开」要等满所有 timeout，
    而「干净机器、没装代理」恰恰是新用户最常见的状态，每次启动白等很亏。
    """
    host = "127.0.0.1"
    # 1) 系统代理设置：优先 http=，没有就退回第一项（可能是 socks=）
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
        enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
        if enable:
            server, _ = winreg.QueryValueEx(key, "ProxyServer")
            parts = _split_server(server)
            # http 优先 —— Clash 的混合端口两种协议都通，http 兼容性最好；
            # 只有 socks= 时也认
            picked = (next((p for p in parts if p[0] == "http"), None)
                      or (parts[0] if parts else None))
            if picked:
                scheme, addr = picked
                ph, _, pp = addr.rpartition(":")
                if ph and pp.isdigit():
                    return f"{scheme}://{ph}:{pp}", ph, int(pp)
    except Exception:
        pass

    # 2) 常见 HTTP 端口，按约定直接用（本地这些端口被非代理服务占用极少）
    #    Clash/Clash Verge/ClashX 7897 · Clash for Windows 7890 ·
    #    v2rayN 10809 · Privoxy 8118
    import socket
    from concurrent.futures import ThreadPoolExecutor

    http_ports = (7897, 7890, 10809, 8118, 2080, 8889)

    def _open(port):
        try:
            socket.create_connection((host, port), timeout=0.3).close()
            return port
        except OSError:
            return None

    with ThreadPoolExecutor(max_workers=len(http_ports)) as pool:
        for port in pool.map(_open, http_ports):
            if port:
                return f"http://{host}:{port}", host, port

    # 3) SOCKS 常见端口：握手认出协议才算。
    #    这些端口也可能被别的服务占着，不能盲信
    for port in (1080, 1081, 10808, 9050, 9150):
        scheme = _handshake_proxy(host, port)
        if scheme:
            return f"{scheme}://{host}:{port}", host, port

    # 4) 兜底
    return "http://127.0.0.1:7897", "127.0.0.1", 7897


PROXY_SCHEMES = ("http", "https", "socks5", "socks5h", "socks4")
# 没写协议时按端口猜：这些端口业内默认是 SOCKS
_SOCKS_LIKE_PORTS = (1080, 1081, 10808, 10809, 9050, 9150)


def resolve_proxy(text=""):
    """把用户填的代理地址解析成 (proxy, host, port, 错误提示)。

    text 为空 → 自动探测。否则接受：
      http://127.0.0.1:7890        HTTP 代理（Clash for Windows）
      socks5h://127.0.0.1:10808    SOCKS5，域名交给代理解析（推荐）
      socks5://user:pass@ip:port   带认证的透传，yt-dlp / requests 都认
      127.0.0.1:10808              没写协议时按端口猜，其余按 http
    解析失败返回 (None, None, None, 原因)，调用方提示用户改格式。
    """
    import urllib.parse as up

    text = (text or "").strip()
    if not text:
        proxy, h, p = _detect_proxy()
        return proxy, h, p, ""

    raw = text
    if "://" not in raw:
        # 用户只写了 host:port —— 按端口猜协议，别逼人家记协议名
        addr = raw.split("/", 1)[0]
        h, _, pp = addr.rpartition(":")
        guess = ("socks5h" if pp.isdigit() and int(pp) in _SOCKS_LIKE_PORTS
                 else "http")
        raw = f"{guess}://{raw}"

    try:
        u = up.urlsplit(raw)
    except ValueError as exc:
        return None, None, None, f"地址解析不了：{exc}"

    scheme = (u.scheme or "").lower()
    if scheme not in PROXY_SCHEMES:
        return None, None, None, (
            "协议不认识：%s（支持 %s）" % (u.scheme or "空", " / ".join(PROXY_SCHEMES)))
    try:
        h, pp = u.hostname, u.port
    except ValueError as exc:
        return None, None, None, f"地址格式不对：{exc}"
    if not h or not pp:
        return None, None, None, "要写全主机和端口，例如 socks5h://127.0.0.1:10808"

    # socks5 → socks5h：被墙域名必须让代理解析 DNS，否则本地解析不了
    norm = "socks5h" if scheme == "socks5" else scheme
    if u.username or u.password:
        user, pw = up.unquote(u.username), up.unquote(u.password)
        return f"{norm}://{user}:{pw}@{h}:{pp}", h, pp, ""
    return f"{norm}://{h}:{pp}", h, pp, ""


PROXY, PROXY_HOST, PROXY_PORT = _detect_proxy()

# ---- 浏览器 UA ----
# 取真实 headed Chrome 的值。绝对不能留 headless 默认值 —— 那里面带
# "HeadlessChrome"，反爬一行代码就能认出来。
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

# ---- 支持作者（自愿）----
# Your donation page URL (e.g. Afdian, PayPal); a "Support" button appears
# in the bottom-right of the UI. Leave it empty to hide the button entirely.
# No nagging, no tracking, fully optional.
DONATE_URL = "https://afdian.com/a/anodev"

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


# ---- 使用须知（首次启动必须勾选同意）----
# 版本号与正文绑定：改动正文时把版本号一起改掉，老用户下次启动会重新看到
# 并重新确认，避免「须知变了但用户没看过」的空档。
DISCLAIMER_VERSION = "2026.10.16"

DISCLAIMER_TITLE = "使用须知与免责声明"

DISCLAIMER_TEXT = """本工具是一个本地运行的通用视频下载工具。在开始使用前，请你仔细阅读并确认以下全部内容。

一、用途限制
本工具仅供个人学习、研究使用，用于备份你自己有权访问的内容。
请勿将本工具用于商业用途，请勿批量抓取，请勿以任何形式分发受版权保护的内容。

二、版权归属
通过本工具下载的内容，其版权归原作者及相关权利人所有。
你是否可以对下载内容进行二次使用（转载、剪辑、商用等），请你自行确认并承担相应责任。

三、合规义务
请遵守目标平台的服务条款以及你所在地的法律法规。
本工具不破解任何 DRM、付费墙或会员加密；需要登录才能访问的内容，请先自行登录。
首次使用抖音等功能时，需要你在弹出的浏览器窗口中自行扫码登录。

四、技术说明
本工具完全本地运行：零遥测、零上报、无账号体系，不会把你的任何数据上传到
作者或第三方服务器。抖音登录态、B站 cookies 等敏感数据仅保存在本机，
你可以随时删除。

五、责任承担
使用本工具产生的一切后果由你自行承担。
作者不对因使用本工具而导致的任何直接或间接损失承担责任。

勾选下方选项，即表示你已阅读、理解并同意上述全部条款。"""


def settings_path():
    """设置文件路径（供测试与外部调用，避免直接依赖模块常量）。"""
    return SETTINGS_FILE
