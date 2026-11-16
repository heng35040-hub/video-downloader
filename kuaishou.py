# -*- coding: utf-8 -*-
"""Kuaishou backend — pure requests & native curl, no browser.

快手页面支持两套渲染：
1. 移动端页面（m.gifshow.com / fw/photo/）：包含 window.INIT_STATE，里面直接提供
   无水印/高清 mainMvUrls 直链数组及标题，对游客无需登录且无需设备 cookie，
   是最稳定、最持久的抓取路径。
2. 网页端（kuaishou.com/short-video/）：window.__APOLLO_STATE__，需 did cookie。

注意：快手服务端对 Python OpenSSL TLS 指纹有频控拦截（容易出现 SSLEOFError），
优先使用 Windows 自带的 curl.exe（基于 Windows SChannel 原生 TLS 栈）抓取 HTML，
若不可用则平滑回退至 requests Session。拿到直链后通过 requests 流式下载到目标目录。
"""
import json
import logging
import re
import subprocess
import time
import uuid

import config
import procutil
from douyin import (_Cancelled, _dest_path, _download, _sanitize, _session)

_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)

_ID_PATTERNS = (
    re.compile(r"/short-video/([0-9A-Za-z_-]{8,})"),   # 网页端标准链接
    re.compile(r"/fw/photo/([0-9A-Za-z_-]{8,})"),      # 分享跳转的中间页
    re.compile(r"[?&]photoId=([0-9A-Za-z_-]{8,})"),    # 分享链接的参数
)


def _fetch_html(url, session):
    """抓取页面 HTML。优先使用系统自带 curl.exe 规避 TLS 指纹拦截，失败回退 requests。"""
    try:
        cmd = ["curl.exe", "-s", "-L", "--max-time", "15", "-A", _MOBILE_UA, url]
        res = subprocess.run(cmd, capture_output=True, text=True,
                             encoding="utf-8", errors="ignore",
                             creationflags=procutil.CREATE_NO_WINDOW)
        if res.returncode == 0 and res.stdout and len(res.stdout) > 200:
            return res.stdout
    except Exception:
        pass

    try:
        headers = {
            "User-Agent": _MOBILE_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh-Hans;q=0.9",
            "Connection": "close",
        }
        r = session.get(url, headers=headers, allow_redirects=True, timeout=15)
        if r.status_code == 200 and r.text:
            return r.text
    except Exception:
        pass
    return ""


def _video_id(url, session):
    """从链接里挖视频 ID，挖不到就先不跟重定向快速查 Location，再不行跟重定向深挖。"""
    for pat in _ID_PATTERNS:
        m = pat.search(url)
        if m:
            return m.group(1)

    try:
        r0 = session.get(url, allow_redirects=False, timeout=8)
        loc = r0.headers.get("Location") or ""
        for pat in _ID_PATTERNS:
            m = pat.search(loc)
            if m:
                return m.group(1)
    except Exception:
        pass

    try:
        resp = session.get(url, allow_redirects=True, timeout=15)
        for pat in _ID_PATTERNS:
            m = pat.search(resp.url) or pat.search(resp.text[:300000])
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


def _fake_device(session):
    """快手靠 did cookie 认设备；游客没有，就造一个。"""
    session.cookies.set("did", "web_" + uuid.uuid4().hex,
                        domain=".kuaishou.com")
    session.cookies.set("didv", str(int(time.time() * 1000)),
                        domain=".kuaishou.com")


def _parse_detail(html):
    """从页面里的 INIT_STATE、APOLLO_STATE 或页面源码中提取视频直链与标题。"""
    if not html:
        return None

    # 1. 优先解析移动端 window.INIT_STATE（最稳定，含 mainMvUrls 直链）
    m_init = re.search(r"window\.INIT_STATE\s*=\s*(.*?);?</script>", html, re.DOTALL)
    if m_init:
        try:
            data = json.loads(m_init.group(1).rstrip(";"))
            found = []

            def _search(obj):
                if isinstance(obj, dict):
                    if obj.get("mainMvUrls"):
                        found.append(obj)
                    elif obj.get("photoUrl"):
                        found.append(obj)
                    for v in obj.values():
                        _search(v)
                elif isinstance(obj, list):
                    for item in obj:
                        _search(item)

            _search(data)
            if found:
                item = found[0]
                urls = []
                if isinstance(item.get("mainMvUrls"), list):
                    urls = [u["url"] for u in item["mainMvUrls"]
                            if isinstance(u, dict) and u.get("url")]
                purl = urls[0] if urls else item.get("photoUrl")
                title = item.get("caption") or item.get("name") or item.get("title") or ""
                if purl:
                    return {"photoUrl": purl, "caption": title}
        except Exception:
            pass

    # 2. 从 __APOLLO_STATE__ 提取
    i = html.find("window.__APOLLO_STATE__")
    if i >= 0:
        raw = html[i + len("window.__APOLLO_STATE__="):].lstrip()
        try:
            data, _ = json.JSONDecoder().raw_decode(raw)
            dc = data.get("defaultClient", {})
            for key, node in dc.items():
                if isinstance(node, dict):
                    if node.get("photoUrl"):
                        return node
                    photo = node.get("photo")
                    if isinstance(photo, dict) and photo.get("photoUrl"):
                        return photo
        except ValueError:
            pass

    # 3. 正则提取 mainMvUrls
    m_main = re.search(r'"mainMvUrls"\s*:\s*\[(.*?)(?:\]\s*[,}])', html, re.DOTALL)
    if m_main:
        urls = re.findall(r'"url"\s*:\s*"([^"]+)"', m_main.group(1))
        if urls:
            try:
                purl = urls[0].encode("utf-8").decode("unicode_escape").replace(r"\/", "/")
            except Exception:
                purl = urls[0].replace(r"\/", "/")
            m_cap = re.search(r'"caption"\s*:\s*"([^"]*)"', html)
            cap = ""
            if m_cap:
                try:
                    cap = m_cap.group(1).encode("utf-8").decode("unicode_escape")
                except Exception:
                    cap = m_cap.group(1)
            return {"photoUrl": purl, "caption": cap}

    # 4. 正则提取 photoUrl
    m_url = re.search(r'"photoUrl"\s*:\s*"([^"]+)"', html)
    if m_url:
        try:
            purl = m_url.group(1).encode("utf-8").decode("unicode_escape").replace(r"\/", "/")
        except Exception:
            purl = m_url.group(1).replace(r"\/", "/")
        m_cap = re.search(r'"caption"\s*:\s*"([^"]*)"', html)
        cap = ""
        if m_cap:
            try:
                cap = m_cap.group(1).encode("utf-8").decode("unicode_escape")
            except Exception:
                cap = m_cap.group(1)
        return {"photoUrl": purl, "caption": cap}

    return None


def download_kuaishou(url, outdir, emit, job):
    """下载一个快手视频。返回 (成功?, 文件路径 或 错误文本)。"""
    try:
        import requests  # noqa: F401
    except ImportError:
        return False, "缺少 requests 库，请先运行：pip install requests"

    try:
        session = _session()
        emit("status", text="正在解析快手链接…")

        # 1. 优先直接抓取当前链接（如分享短链 /f/xxx，curl 会跟随重定向到移动端页面直接拿到 HTML）
        html = _fetch_html(url, session)
        photo = _parse_detail(html)

        # 2. 如果直接抓取未拿到，提取 vid 并构造移动端/网页端页面深挖
        vid = None
        if not photo:
            vid = _video_id(url, session)
            if vid:
                emit("log", text=f"视频 ID: {vid}")
                m_url = f"https://m.gifshow.com/fw/photo/{vid}"
                html = _fetch_html(m_url, session)
                photo = _parse_detail(html)

        # 3. 检查是否有明确的删除或验证拦截
        if not photo or not photo.get("photoUrl"):
            if "作品不存在" in html or '"result": 2' in html or '"result":2' in html:
                return False, "视频不存在或已删除。"
            if "captcha" in html.lower():
                return False, "快手触发了人机验证，请稍后重试或在浏览器中打开。"
            if not vid:
                vid = _video_id(url, session)
            if not vid:
                return False, ("认不出这个链接里的视频 ID。\n"
                               "请用浏览器打开快手视频页，复制地址栏里的完整链接"
                               "（含 /short-video/）再试。")
            return False, "快手页面里未找到视频数据（视频可能已删除，或需要验证）。"

        if not vid:
            vid = _video_id(url, session) or "kuaishou"

        title = photo.get("caption") or photo.get("name") or "快手视频"
        emit("title", text=_sanitize(title))
        dest = _dest_path(outdir, title, vid)
        emit("status", text="拿到直链，开始下载…")
        try:
            _download(photo["photoUrl"], dest, session, emit, job,
                      referer="https://m.gifshow.com/")
        except _Cancelled:
            return False, "已取消"
        return True, dest
    except Exception as exc:
        logging.exception("下载快手失败: %s", url)
        return False, (f"快手模块出错：{type(exc).__name__}: {exc}")
