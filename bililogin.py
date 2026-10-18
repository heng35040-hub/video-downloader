# -*- coding: utf-8 -*-
"""B站扫码登录 —— 把浏览器里的登录态导出成 yt-dlp 能吃的 cookies.txt。

为什么不用「手动导入 cookies 文件」：
B站的高清（1080P 起）要登录才给。让用户去装浏览器扩展、导出 cookies.txt、
再找文件路径，对普通用户是四步劝退流程。这里直接开一个浏览器窗口让用户
扫码，成功后自己把 cookie 写成 Netscape 格式 —— 一步搞定。

登录态同时留在 `config.PROFILE_BILI` 里，下次再点按钮不用重新扫码。
"""
import os
import time

import config


def has_login(cookies):
    """cookie 列表里是否已有 B站登录态。

    SESSDATA 是登录后才下发的，游客没有。比看页面上的头像元素稳。
    """
    for c in cookies or ():
        if c.get("name") == "SESSDATA" and c.get("value"):
            return True
    return False


def to_netscape(cookies):
    """把 Playwright 的 cookie 列表转成 Netscape cookies.txt 文本。

    yt-dlp / curl 都认这个格式。几个容易踩的点：
    - 字段用 **制表符** 分隔，空格不行
    - 域以 `.` 开头表示包含子域，第二列要写 TRUE
    - HttpOnly 的 cookie 要在域前面加 `#HttpOnly_`，否则会被当成注释跳过
    - 会话 cookie 的过期时间写 0
    """
    lines = ["# Netscape HTTP Cookie File",
             "# 由 VideoDownloader 自动生成，请勿手动编辑", ""]
    for c in cookies or ():
        domain = (c.get("domain") or "").strip()
        name = c.get("name") or ""
        if not domain or not name:
            continue
        try:
            expires = int(c.get("expires") or 0)
        except (TypeError, ValueError):
            expires = 0
        if expires < 0:          # Playwright 用 -1 表示会话 cookie
            expires = 0
        lines.append("\t".join([
            ("#HttpOnly_" if c.get("httpOnly") else "") + domain,
            "TRUE" if domain.startswith(".") else "FALSE",
            c.get("path") or "/",
            "TRUE" if c.get("secure") else "FALSE",
            str(expires),
            name,
            c.get("value") or "",
        ]))
    return "\n".join(lines) + "\n"


def save_cookies(cookies, path=None):
    """写 cookies.txt，返回路径。目录不存在会自动建。"""
    path = path or config.COOKIES_BILI
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = to_netscape(cookies)
    # 先写临时文件再替换 —— 写到一半被打断不会留下半个 cookies 文件
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return path


def _launch(p, headless):
    """起持久化上下文，浏览器依次回退 msedge → chrome → chromium → 自带。"""
    kwargs = {
        "headless": headless,
        "args": ["--no-proxy-server",       # B站国内站，绝不能走代理
                 "--disable-blink-features=AutomationControlled"],
        "user_agent": config.BROWSER_UA,
        "locale": "zh-CN",
        "viewport": {"width": 1100, "height": 760},
    }
    last = None
    for channel in ("msedge", "chrome", "chromium", None):
        try:
            kw = dict(kwargs)
            if channel:
                kw["channel"] = channel
            return p.chromium.launch_persistent_context(config.PROFILE_BILI, **kw)
        except Exception as exc:
            last = exc
    raise RuntimeError(f"启动浏览器失败：{last}")


def login_and_save(emit=None, timeout=240):
    """开浏览器让用户扫码，成功后把 cookie 写成 cookies.txt。

    返回 (成功?, cookies 路径 或 错误文本)。
    """
    from playwright.sync_api import sync_playwright

    def say(text):
        if emit:
            emit("status", text=text)

    say("正在打开 B站登录页…")
    with sync_playwright() as p:
        ctx = _launch(p, headless=False)
        try:
            page = ctx.new_page()
            page.goto("https://passport.bilibili.com/login",
                      wait_until="domcontentloaded", timeout=60000)
            say("请在弹出的浏览器窗口里扫码登录 B站（登录成功后窗口会自动关闭）…")

            deadline = time.time() + timeout
            while time.time() < deadline:
                cookies = ctx.cookies()
                if has_login(cookies):
                    path = save_cookies(cookies)
                    return True, path
                page.wait_for_timeout(1200)
            return False, ("登录超时。请在弹出的窗口里完成扫码后重试；"
                           "若窗口没出现，检查是否装了 Edge 或 Chrome。")
        finally:
            try:
                ctx.close()
            except Exception:
                pass
