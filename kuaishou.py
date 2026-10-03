# -*- coding: utf-8 -*-
"""快手后端 —— 纯 requests，不用浏览器。

快手网页端把视频数据直接渲染在页面的 window.__APOLLO_STATE__ 里，
但游客没有设备 cookie 会被反爬拦截（弹「浏览器版本过低」假页面，
连有头真 Chrome 都拦 —— 别再往浏览器指纹方向折腾了）。可行的路径是：
自己造一个 did=web_<随机> 设备 cookie，服务端就会正常吐数据。
从 JSON 里挖 VisionVideoDetailPhoto 节点拿直链，立刻下载
（直链有时效，抓到必须马上用）。

yt-dlp 没有快手提取器，这条路是实测可行的最短路径。
复用 douyin.py 里的通用件（流式下载、会话、文件名清洗）。
"""
import json
import re
import time
import uuid

import config
from douyin import (_Cancelled, _dest_path, _download, _sanitize, _session)

_ID_PATTERNS = (
    re.compile(r"/short-video/([0-9A-Za-z]{8,})"),   # 网页端标准链接
    re.compile(r"/fw/photo/([0-9A-Za-z]{8,})"),      # 分享跳转的中间页
    re.compile(r"[?&]photoId=([0-9A-Za-z]{8,})"),    # 分享链接的参数
)


def _video_id(url, session):
    """从链接里挖视频 ID，挖不到就跟一次重定向再挖。"""
    for pat in _ID_PATTERNS:
        m = pat.search(url)
        if m:
            return m.group(1)

    try:
        resp = session.get(url, allow_redirects=True, timeout=15)
    except Exception:
        return None

    for pat in _ID_PATTERNS:
        m = pat.search(resp.url) or pat.search(resp.text[:300000])
        if m:
            return m.group(1)
    return None


def _fake_device(session):
    """快手靠 did cookie 认设备；游客没有，就造一个。"""
    session.cookies.set("did", "web_" + uuid.uuid4().hex,
                        domain=".kuaishou.com")
    session.cookies.set("didv", str(int(time.time() * 1000)),
                        domain=".kuaishou.com")


def _parse_detail(html):
    """从页面里的 __APOLLO_STATE__ JSON 挖视频节点。

    赋值语句后面还粘着别的脚本，用 raw_decode 只取第一个 JSON 值。
    """
    i = html.find("window.__APOLLO_STATE__")
    if i < 0:
        return None
    raw = html[i + len("window.__APOLLO_STATE__="):].lstrip()
    try:
        data, _ = json.JSONDecoder().raw_decode(raw)
    except ValueError:
        return None
    for key, node in data.get("defaultClient", {}).items():
        if key.startswith("VisionVideoDetailPhoto:"):
            return node
    return None


def download_kuaishou(url, outdir, emit, job):
    """下载一个快手视频。返回 (成功?, 文件路径 或 错误文本)。"""
    try:
        import requests  # noqa: F401
    except ImportError:
        return False, "缺少 requests 库，请先运行：pip install requests"

    try:
        session = _session()
        emit("status", text="正在解析链接…")
        vid = _video_id(url, session)
        if not vid:
            return False, ("认不出这个链接里的视频 ID。\n"
                           "请用浏览器打开快手视频页，复制地址栏里的完整链接"
                           "（含 /short-video/）再试。")
        emit("log", text=f"视频 ID: {vid}")

        _fake_device(session)
        # kpn=KUAISHOU 是关键：不带这个参数，服务端只给站点壳数据，
        # 视频节点整个不渲染（实测唯一稳定的开关）
        page_url = (f"https://www.kuaishou.com/short-video/{vid}"
                    "?kpn=KUAISHOU")
        r = session.get(page_url, timeout=20)
        photo = _parse_detail(r.text)
        if not photo or not photo.get("photoUrl"):
            return False, ("快手页面里没解析到视频数据 —— 快手的反爬策略"
                           "经常变，这条路可能已经失效。\n"
                           "可以先用浏览器打开视频页确认视频能正常播放。")

        title = photo.get("caption") or photo.get("name") or ""
        emit("title", text=_sanitize(title))
        dest = _dest_path(outdir, title, vid)
        emit("status", text="拿到直链，开始下载…")
        try:
            _download(photo["photoUrl"], dest, session, emit, job,
                      referer="https://www.kuaishou.com/")
        except _Cancelled:
            return False, "已取消"
        return True, dest
    except Exception as exc:
        return False, (f"快手模块出错：{type(exc).__name__}: {exc}")
