# -*- coding: utf-8 -*-
"""Douyin (TikTok CN) backend — does not use yt-dlp.

Douyin has anti-scraping; yt-dlp only gets HTML from share pages.
Viable path: open video page in browser → capture CDN direct URLs from
network responses → download immediately. URLs carry short-lived signatures
(l= / dy_q=), expiring in minutes.

Playwright is lazy-imported (inside functions): importing it takes 1-2s and
requires a browser; top-level import would break other platforms if it fails.
"""
import os
import re
import tempfile
import time

import config
import procutil

_ID_PATTERNS = (
    re.compile(r"/video/(\d{6,})"),           # 标准视频页
    re.compile(r"/share/video/(\d{6,})"),     # 分享页
    re.compile(r"[?&]modal_id=(\d{6,})"),     # 弹窗形式
    re.compile(r'"(?:aweme_id|item_id|itemId)"\s*:\s*"(\d{6,})"'),  # 页面内 JSON
)

_MUSIC_RE = re.compile(r"/music/(\d{6,})")    # 音乐/原声详情页

# 收藏-音乐列表页：整页批量抓取的入口。没有单条链接可复制，
# 只能认这个地址。
_FAV_MUSIC_MARK = ("/user/self", "showSubTab=music")

_MEDIA_HINT = ("douyinvod.com", "/video/tos/")   # 子域名一直在换，别写死 v26-web

# 抖音的 CDN 对视频/音频走 HTTP Range 分段请求，返回 **206 Partial Content**
# 而不是 200。早先只认 200，导致页面明明在正常播放、一个流都抓不到 ——
# 症状是「没能从页面里抓到视频流」，很容易误判成登录墙。
_OK_STATUS = (200, 206)


def _media_size(headers):
    """取这条响应对应的**文件总大小**。

    206 的 content-length 只是本次分段的长度（可能只有几十 KB），拿它排序会
    选错流；真正的总长在 Content-Range 的 "bytes 0-123/45678" 末尾。
    """
    headers = headers or {}
    m = re.search(r"/(\d+)\s*$", headers.get("content-range") or "")
    if m:
        return int(m.group(1))
    try:
        return int(headers.get("content-length") or 0)
    except ValueError:
        return 0


def _logged_in(ctx):
    """当前浏览器上下文里是否已有抖音登录态。

    sessionid / sid_tt 是登录后才下发的，游客没有 —— 比去看页面上的头像
    元素稳（那些 class 名一直在变）。
    """
    try:
        for c in ctx.cookies():
            if c.get("name") in ("sessionid", "sessionid_ss", "sid_tt") \
                    and c.get("value"):
                return True
    except Exception:
        pass
    return False


_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


class _Cancelled(Exception):
    pass


# 浏览器选择顺序：系统自带 Edge → 系统 Chrome → Playwright 自带 chromium
# → Playwright 默认浏览器。Windows 10/11 默认自带 Edge，所以绝大多数用户
# 开箱即用，不必额外下载约 150MB 的 chromium；只有极精简的系统才会落到
# 后面两步（那两步需要事先 playwright install chromium）。
_BROWSER_CHANNELS = ("msedge", "chrome", "chromium")

_NO_BROWSER_HINT = (
    "没能启动浏览器。程序会依次尝试系统自带的 Microsoft Edge、Google Chrome，"
    "再回退到 Playwright 自带浏览器，但都没找到。\n"
    "请安装 Microsoft Edge（Windows 10/11 通常自带）或 Google Chrome 后重试。"
)

_DRIVER_HINT = (
    "Playwright 驱动没能启动（打包时可能漏收了 playwright/driver）。\n"
    "请到项目 Releases 页重新下载最新版 exe；从源码运行则执行："
    "pip install -r requirements.txt"
)


def _browser_hint(exc):
    """按异常内容给出对新手有用的中文提示；认不出就返回空串。"""
    text = str(exc)
    if "Driver not found" in text or "playwright/driver" in text:
        return _DRIVER_HINT
    if ("Executable doesn't exist" in text
            or "browserType.launch" in text
            or "channel" in text.lower()):
        return _NO_BROWSER_HINT
    return ""


def _launch(p, headless, channel=None):
    """按给定 channel 起持久化上下文；channel=None 表示用 Playwright 自带浏览器。"""
    kwargs = {
        "headless": headless,
        "args": [
            "--no-proxy-server",   # 否则 Chromium 继承系统代理，抖音走代理必挂
            "--disable-blink-features=AutomationControlled",
        ],
        "user_agent": config.BROWSER_UA,
        "locale": "zh-CN",
        "viewport": {"width": 1280, "height": 800},
    }
    if channel:
        kwargs["channel"] = channel
    return p.chromium.launch_persistent_context(config.PROFILE_DOUYIN, **kwargs)


def _open_context(p, headless):
    """起一个带本地登录态的浏览器上下文。

    用持久化 profile（config.PROFILE_DOUYIN）而不是一次性上下文：
    抖音现在对游客上登录墙，第一次在有头窗口里扫码登录后，
    登录态长期保存在 profile 里，之后免登录。

    浏览器优先用系统自带的 Edge/Chrome（channel 参数），不下载 chromium：
    一是省掉约 150MB 的首次下载，二是完整版浏览器的 UA 里不会带
    HeadlessChrome 这类一眼被反爬认出的标记。
    """
    last = None
    for channel in _BROWSER_CHANNELS:
        try:
            return _launch(p, headless, channel)
        except Exception as exc:        # 这个 channel 没装，试下一个
            last = exc
    try:
        return _launch(p, headless, None)   # 回退：Playwright 自带 chromium
    except Exception as exc:
        last = exc
    raise RuntimeError(
        f"{last}\n\n{_browser_hint(last) or _NO_BROWSER_HINT}") from last


def _session():
    """一个绕过系统代理的 requests 会话。

    抖音是国内站必须直连。别指望 Clash 的分流规则一定对，
    这里直接 trust_env=False 并显式把 proxies 置空。
    """
    import requests

    s = requests.Session()
    s.trust_env = False
    s.proxies = {"http": None, "https": None}
    s.headers.update({
        "User-Agent": config.BROWSER_UA,
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    return s


def _video_id(url, session):
    """从链接里挖视频 ID，挖不到就跟一次重定向再挖。"""
    for pat in _ID_PATTERNS:
        m = pat.search(url)
        if m:
            return m.group(1)

    try:
        # 用 GET 而不是 HEAD：有些短链返回 200 + HTML 跳转壳，HEAD 什么也拿不到
        resp = session.get(url, allow_redirects=True, timeout=15)
    except Exception:
        return None

    for pat in _ID_PATTERNS:
        m = pat.search(resp.url) or pat.search(resp.text[:300000])
        if m:
            return m.group(1)
    return None


def _capture(page_url, job, headless=True, timeout=30, emit=None):
    """用浏览器打开视频页，捞 CDN 直链。返回 (直链, 标题)。

    emit 传入时，会在有头窗口里实时汇报登录状态：用户扫码成功后立刻把
    「请扫码登录」换成「已登录」，而不是一直挂着那句提示让人以为卡死了。
    """
    from playwright.sync_api import sync_playwright

    found = []          # [(url, 文件总大小)]

    with sync_playwright() as p:
        ctx = _open_context(p, headless)
        try:
            # Playwright 在所有模式下 navigator.webdriver 都是 true，手动抹掉
            ctx.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            )

            def on_response(resp):
                # 用 response 而不是 request：request 阶段每个预加载都会触发，
                # 且拿不到状态码，无法判断链接是否真的可用
                try:
                    if resp.status not in _OK_STATUS:
                        return
                    headers = resp.headers or {}
                    if not headers.get("content-type", "").startswith("video/"):
                        return
                    if not any(h in resp.url for h in _MEDIA_HINT):
                        return
                    found.append((resp.url, _media_size(headers)))
                except Exception:
                    pass

            ctx.on("response", on_response)
            page = ctx.new_page()
            page.goto(page_url, wait_until="domcontentloaded", timeout=45000)

            deadline = time.time() + timeout
            click_at = time.time() + 8
            clicked = False
            login = None            # None=还没查过
            next_login_check = 0.0
            reload_at = time.time() + 15

            def do_reload():
                """重载页面并重置点击/重载计时（抖音是 SPA，重载后要重新触发播放）。"""
                nonlocal clicked, click_at, reload_at
                try:
                    page.reload(wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass
                clicked = False
                click_at = time.time() + 3
                reload_at = time.time() + 15

            while time.time() < deadline and not found:
                if job and job.cancel.is_set():
                    return None, None
                now = time.time()

                # 有头窗口里实时播报登录状态：扫码成功后立刻改提示，
                # 而不是一直挂着「请扫码登录」让人以为卡死了
                if emit and not headless and now >= next_login_check:
                    next_login_check = now + 1.5
                    cur = _logged_in(ctx)
                    if cur != login:
                        login = cur
                        emit("status", text=(
                            "登录成功，正在获取直链…" if cur else
                            "弹出了浏览器窗口 —— 请在里面扫码登录抖音"
                            "（只需一次），登录成功后会自动继续…"))
                        if cur:
                            # 扫码登录后页面不会自己重载，不刷新就一直停在
                            # 游客态、拿不到流
                            do_reload()

                # 兜底：Edge 新版把登录 cookie 做了 App-Bound 加密，外部进程
                # 可能读不到，_logged_in 会一直判 False。这时靠定期刷新，
                # 用户登录后最多等 15 秒就能自动接上
                if now >= reload_at and not found:
                    do_reload()

                if not clicked and time.time() >= click_at:
                    clicked = True
                    try:
                        page.click("video", timeout=2000)   # 有的页面不自动播放
                    except Exception:
                        pass
                page.wait_for_timeout(250)

            title = None
            try:
                title = page.title()
            except Exception:
                pass
        finally:
            try:
                ctx.close()
            except Exception:
                pass

    if not found:
        return None, title
    found.sort(key=lambda t: t[1], reverse=True)   # 取体积最大的那路
    return found[0][0], title


def _sanitize(title):
    if not title:
        return ""
    t = re.sub(r"\s*[-–—]\s*抖音\s*$", "", title.strip())
    t = _BAD_CHARS.sub("_", t).strip(" .")
    return t[:100]


def _dest_path(outdir, title, vid, ext=".mp4"):
    name = _sanitize(title) or f"douyin_{vid}"
    dest = os.path.join(outdir, name + ext)
    n = 1
    # 自己下的话不会像 yt-dlp 那样自动避让重名，直接覆盖会丢文件
    while os.path.exists(dest):
        dest = os.path.join(outdir, f"{name} ({n}){ext}")
        n += 1
    # 标题是外部输入：分隔符已被 _sanitize 剥掉，这里再钉一道 ——
    # 最终路径必须落在保存目录这一层，异常时退回纯 ID 命名
    if os.path.dirname(os.path.abspath(dest)) != os.path.abspath(outdir):
        dest = os.path.join(outdir, f"douyin_{vid}{ext}")
    return dest


def _download(media_url, dest, session, emit, job,
              referer="https://www.douyin.com/"):
    """流式下载。先写临时文件再改名，取消时不会留下看着像完整的半个文件。

    临时文件用 tempfile.mkstemp 在保存目录里生成：路径由操作系统随机
    给出、完全不经手外部数据，页面标题再恶意也构不成路径穿越。
    """
    directory = os.path.dirname(os.path.abspath(dest))
    fd, part = tempfile.mkstemp(dir=directory, prefix="dl_", suffix=".part")
    try:
        with session.get(media_url,
                         headers={"Referer": referer},
                         stream=True, timeout=(15, 60)) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            with os.fdopen(fd, "wb") as f:
                for chunk in resp.iter_content(256 * 1024):
                    if job.cancel.is_set():
                        raise _Cancelled()
                    if not chunk:
                        continue
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        emit("progress", frac=min(1.0, done / total),
                             text=f"{procutil.human_size(done)} / "
                                  f"{procutil.human_size(total)}")
                    else:
                        # CDN 经常用 chunked 传输，没有 Content-Length
                        emit("progress", frac=-1.0,
                             text=f"已下载 {procutil.human_size(done)}")
        os.replace(part, dest)
    except BaseException:
        try:
            os.remove(part)
        except OSError:
            pass
        raise
    return dest


def _extract_play_urls(node):
    """在任意层级的 JSON 里收集 play_url / play_path 的直链，返回 [(url, title)]。

    抖音的 aweme 数据里视频用的是 play_addr，音乐才是 play_url，
    所以这里天然只会命中音频。接口结构改了也不至于全瞎 ——
    递归找这两个键，宁可多拿不能漏拿。
    """
    urls = []
    if isinstance(node, dict):
        for key in ("play_url", "play_path"):
            v = node.get(key)
            if isinstance(v, dict):
                title = node.get("title")
                for u in v.get("url_list") or []:
                    if isinstance(u, str) and u.startswith("http"):
                        urls.append((u, title if isinstance(title, str) else ""))
        for v in node.values():
            urls.extend(_extract_play_urls(v))
    elif isinstance(node, list):
        for v in node:
            urls.extend(_extract_play_urls(v))
    return urls


def _capture_music(page_url, job, headless=True, timeout=30):
    """用浏览器打开音乐页，捞出音频直链。返回 (直链, 标题)。

    游客会被登录墙挡住音乐区，但页面一加载就会请求 music/aweme
    （使用该音乐的视频列表），它的 JSON 里内嵌着音乐对象的 mp3 直链 ——
    这是免登录的主路径。music/detail 接口和 audio/* 媒体响应做兜底。
    """
    from playwright.sync_api import sync_playwright

    play_map = {}       # url -> title，来自接口 JSON
    found = []          # [(url, content_length)]，audio/* 响应

    with sync_playwright() as p:
        ctx = _open_context(p, headless)
        try:
            ctx.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            )

            def on_response(resp):
                try:
                    if resp.status not in _OK_STATUS:
                        return
                    u = resp.url
                    ct = (resp.headers or {}).get("content-type", "")
                    if ("music/detail" in u or "music/aweme" in u) \
                            and "json" in ct:
                        for u2, t2 in _extract_play_urls(resp.json()):
                            if u2 not in play_map:
                                play_map[u2] = t2
                        return
                    if ct.startswith("audio/"):
                        size = _media_size(resp.headers)
                        if (u, size) not in found:
                            found.append((u, size))
                except Exception:
                    pass

            ctx.on("response", on_response)
            page = ctx.new_page()
            page.goto(page_url, wait_until="domcontentloaded", timeout=45000)

            deadline = time.time() + timeout
            while time.time() < deadline and not (play_map or found):
                if job and job.cancel.is_set():
                    return None, None
                page.wait_for_timeout(250)

            title = None
            try:
                title = page.title()
            except Exception:
                pass
        finally:
            try:
                ctx.close()
            except Exception:
                pass

    if play_map:
        url, t = next(iter(play_map.items()))
        return url, (t or title)
    found.sort(key=lambda t: t[1], reverse=True)
    if found:
        return found[0][0], title
    return None, title


def _sniff_audio(path):
    """看文件头认音频格式：mp3 / m4a / 认不出返回 None。"""
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except OSError:
        return None
    if head[:3] == b"ID3":
        return "mp3"
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        return "mp3"                     # 裸 MPEG 帧同步，无 ID3 头的 mp3
    if head[4:8] == b"ftyp":
        return "m4a"
    return None


def _to_mp3(src, dst):
    """ffmpeg 转成 mp3（q2 约等于 190kbps VBR，听感和体积平衡）。"""
    import subprocess
    import sys

    exe = os.path.join(config.FFMPEG_DIR,
                       "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    if not os.path.isfile(exe):
        return False
    try:
        r = subprocess.run(
            [exe, "-v", "error", "-y", "-i", src,
             "-c:a", "libmp3lame", "-q:a", "2", dst],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=procutil.CREATE_NO_WINDOW, timeout=300)
    except Exception:
        return False
    return r.returncode == 0 and os.path.isfile(dst) and os.path.getsize(dst) > 0


def _download_music(url, outdir, emit, job):
    """下载音乐页(/music/<id>)的原声，统一输出 mp3。"""
    session = _session()
    mid = _MUSIC_RE.search(url).group(1)
    page_url = f"https://www.douyin.com/music/{mid}"
    emit("log", text=f"音乐 ID: {mid}")

    last_err = ""
    # 先静默试一次（音乐接口游客也能拿到）；不行才弹有头浏览器扫码
    for attempt, (headless, wait) in enumerate(((True, 30), (False, 180)), 1):
        if job.cancel.is_set():
            return False, "已取消"
        if headless:
            emit("status", text=f"正在解析音乐页…（第 {attempt} 次）")
        else:
            emit("status", text="弹出了浏览器窗口 —— 请在里面扫码登录抖音"
                                "（只需一次），登录后会自动继续下载…")

        media, title = _capture_music(page_url, job,
                                      headless=headless, timeout=wait)
        if not media:
            last_err = "没能从音乐页里抓到音频直链"
            continue

        emit("status", text="拿到音频直链，开始下载…")
        if title:
            emit("title", text=_sanitize(title))
        dest = _dest_path(outdir, title, "music_" + mid, ext=".mp3")
        try:
            _download(media, dest, session, emit, job)
        except _Cancelled:
            return False, "已取消"
        except Exception as exc:
            # 直链过期是最常见的瞬态失败（403），重捕一次即可
            last_err = f"下载直链失败：{exc}"
            continue

        kind = _sniff_audio(dest)
        if kind == "mp3":
            return True, dest
        # m4a 或认不出的格式都转一遍 mp3，保证剪映/抖音上传直接能用
        emit("status", text="正在转成 mp3…")
        tmp = dest[:-4] + ".tmp.mp3"
        if _to_mp3(dest, tmp):
            os.replace(tmp, dest)
            return True, dest
        try:
            os.remove(tmp)
        except OSError:
            pass
        if kind == "m4a":               # 转码失败至少把扩展名改对
            fixed = dest[:-4] + ".m4a"
            os.replace(dest, fixed)
            return True, fixed
        return True, dest

    return False, ("抖音音乐解析失败：" + last_err + "\n\n"
                   "请确认复制的是音乐页地址栏链接"
                   "（形如 douyin.com/music/数字）。\n"
                   "若重试时弹出了浏览器窗口，请在里面扫码登录抖音"
                   "（只需一次，之后免登录）。")


def _looks_like_audio(url):
    """筛掉 JSON 里混进来的视频/图片直链，只留音频资产。"""
    u = url.lower()
    return ("ies-music" in u or ".mp3" in u or "/aweme/v1/play" in u)


def _capture_fav_music(page_url, job, headless=True, timeout=300):
    """打开「收藏 → 音乐」列表页，边滚动边抓音频直链。

    列表接口的 JSON 里内嵌着每条音乐对象的 mp3 直链（和 music/aweme
    同一个结构），滚动加载时逐页捕获；万一接口不带，用户手点播放的
    audio/* 响应也能兜住。返回 [(url, title), ...] 按页面顺序去重。
    """
    from playwright.sync_api import sync_playwright

    play_map = {}       # url -> title（dict 保序）
    audio_urls = []

    with sync_playwright() as p:
        ctx = _open_context(p, headless)
        try:
            ctx.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            )

            def on_response(resp):
                try:
                    if resp.status not in _OK_STATUS:
                        return
                    u = resp.url
                    ct = (resp.headers or {}).get("content-type", "")
                    if "json" in ct:
                        for u2, t2 in _extract_play_urls(resp.json()):
                            if u2 not in play_map and _looks_like_audio(u2):
                                play_map[u2] = t2
                    elif ct.startswith("audio/"):
                        if u not in play_map and u not in audio_urls:
                            audio_urls.append(u)
                except Exception:
                    pass

            ctx.on("response", on_response)
            page = ctx.new_page()
            page.goto(page_url, wait_until="domcontentloaded", timeout=45000)

            # 先等列表数据（未登录时这里永远等不到，靠 timeout 退出）
            deadline = time.time() + timeout
            while time.time() < deadline and not (play_map or audio_urls):
                if job and job.cancel.is_set():
                    return []
                page.wait_for_timeout(500)

            # 滚动加载剩余项；连续 4 滚没有新东西就算到底了
            last_n, stable = 0, 0
            while time.time() < deadline and (play_map or audio_urls):
                if job and job.cancel.is_set():
                    return []
                page.mouse.move(640, 450)
                page.mouse.wheel(0, 2400)
                page.wait_for_timeout(900)
                n = len(play_map) + len(audio_urls)
                stable = stable + 1 if n == last_n else 0
                last_n = n
                if stable >= 4:
                    break
            page.wait_for_timeout(1500)   # 给最后一屏的接口留时间
        finally:
            try:
                ctx.close()
            except Exception:
                pass

    items = list(play_map.items())
    seen = {u for u, _ in items}
    items += [(u, "") for u in audio_urls if u not in seen]
    return items


def _download_fav_music(outdir, emit, job, chooser=None):
    """批量下载「收藏 → 音乐」列表的全部音频，统一输出 mp3。

    chooser(items) -> 索引列表 或 None（用户取消）：提供了它就把抓到的
    音频先弹窗让用户勾选，只下选中的。已存在同名文件的自动跳过，
    所以中断后再拖一次链接等于断点续传。
    """
    session = _session()
    page_url = ("https://www.douyin.com/user/self?from_tab_name=main"
                "&showSubTab=music&showTab=favorite_collection")
    emit("log", text="抖音收藏-音乐 批量模式")

    last_err = ""
    for attempt, (headless, wait) in enumerate(((True, 45), (False, 300)), 1):
        if job.cancel.is_set():
            return False, "已取消"
        if headless:
            emit("status", text="正在打开收藏页…（未登录会失败，然后弹窗）")
        else:
            emit("status", text="弹出了浏览器窗口 —— 请扫码登录抖音（只需一次）。"
                                "登录后不用动页面，程序会自动滚动抓取并下载；"
                                "若迟迟无进度，手动点几条收藏的播放键也行。")

        items = _capture_fav_music(page_url, job,
                                   headless=headless, timeout=wait)
        if job.cancel.is_set():
            return False, "已取消"
        if not items:
            last_err = "收藏页里没抓到音频（多半是还没登录）"
            continue

        total_all = len(items)
        if chooser and total_all > 1:
            emit("status", text=f"抓到 {total_all} 条，请在弹窗里勾选要下载的…")
            picked = chooser(items)
            if picked is None:
                return False, "已取消"
            if not picked:
                return False, "没有勾选任何音频，已停止。"
            items = [items[i] for i in picked]

        total = len(items)
        emit("log", text=f"抓到 {total} 条音频")
        ok_n = skip_n = fail_n = 0
        for i, (u, title) in enumerate(items, 1):
            if job.cancel.is_set():
                return False, "已取消"
            name = _sanitize(title) or f"douyin_music_{i}"
            base = os.path.join(outdir, name + ".mp3")
            if os.path.exists(base):
                skip_n += 1
                continue
            emit("status", text=f"下载收藏音频 {i}/{total}：{name[:40]}")
            emit("progress", frac=-1.0, text="")
            dest = _dest_path(outdir, name, i, ext=".mp3")
            try:
                _download(u, dest, session, emit, job)
            except _Cancelled:
                return False, "已取消"
            except Exception:
                fail_n += 1
                continue

            kind = _sniff_audio(dest)
            if kind != "mp3":
                emit("status", text=f"转码 {name[:30]}…")
                tmp = dest[:-4] + ".tmp.mp3"
                if _to_mp3(dest, tmp):
                    os.replace(tmp, dest)
                else:
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                    if kind == "m4a":
                        fixed = dest[:-4] + ".m4a"
                        os.replace(dest, fixed)
                        dest = fixed
            ok_n += 1

        if ok_n == 0 and fail_n == total:
            last_err = f"{total} 条音频全部下载失败（直链可能已过期，重试一次）"
            continue
        parts = [f"新增 {ok_n} 首"]
        if skip_n:
            parts.append(f"已有 {skip_n} 首")
        if fail_n:
            parts.append(f"失败 {fail_n} 首")
        return True, "收藏音乐批量下载完成：" + "，".join(parts)

    return False, ("抖音收藏批量下载失败：" + last_err + "\n\n"
                   "首次使用请在弹出的浏览器窗口里扫码登录抖音"
                   "（只需一次，之后免登录）。")


def download_douyin(url, outdir, emit, job, chooser=None):
    """下载一个抖音视频或音乐原声。返回 (成功?, 文件路径 或 错误文本)。

    chooser 仅批量模式用：下载前弹窗让用户勾选，见 _download_fav_music。
    """
    try:
        import requests  # noqa: F401
    except ImportError:
        return False, "缺少 requests 库，请先运行：pip install requests"

    try:
        if all(mark in url for mark in _FAV_MUSIC_MARK):
            return _download_fav_music(outdir, emit, job, chooser=chooser)
        if "/user/self" in url:
            return False, ("这是个人主页链接。\n"
                           "想批量下载收藏音频，请先切到「收藏 → 音乐」标签页，"
                           "再复制地址栏链接拖进来。\n"
                           "单条音乐请复制音乐页链接（douyin.com/music/数字）。")

        if _MUSIC_RE.search(url):
            return _download_music(url, outdir, emit, job)

        session = _session()
        emit("status", text="正在解析链接…")
        vid = _video_id(url, session)
        if not vid:
            return False, ("认不出这个链接里的视频 ID。\n"
                           "请用浏览器打开抖音视频页，"
                           "复制地址栏里的完整链接（含 /video/数字）再试。")
        emit("log", text=f"视频 ID: {vid}")
        page_url = f"https://www.douyin.com/video/{vid}"

        last_err = ""
        # 先静默试一次；不行才弹有头浏览器 —— 第一次需要扫码登录抖音，
        # 登录态会存进本地 profile，之后一直免登录。
        # 无头那轮 15 秒足够（页面能播的话 4 秒内就出流），别让新用户干等 30 秒
        for attempt, (headless, wait) in enumerate(((True, 15), (False, 180)), 1):
            if job.cancel.is_set():
                return False, "已取消"
            if headless:
                emit("status", text="正在获取直链…")
            else:
                # 具体提示由 _capture 按实际登录状态播报（已登录 / 待扫码）
                emit("status", text="正在打开浏览器…")

            media, title = _capture(page_url, job,
                                    headless=headless, timeout=wait, emit=emit)
            if not media:
                last_err = "没能从页面里抓到视频流"
                continue

            emit("status", text="拿到直链，开始下载…")
            dest = _dest_path(outdir, title, vid)
            try:
                _download(media, dest, session, emit, job)
                return True, dest
            except _Cancelled:
                return False, "已取消"
            except Exception as exc:
                # 直链过期是最常见的瞬态失败（403），重捕一次即可
                last_err = f"下载直链失败：{exc}"

        return False, (f"抖音解析失败：{last_err}\n\n"
                       "抖音对未登录访问有登录墙 —— 重试一次，在弹出的浏览器"
                       "窗口里扫码登录抖音（只需一次，之后免登录），"
                       "登录后视频和音乐都能下。")
    except Exception as exc:
        msg = f"抖音模块出错：{type(exc).__name__}: {exc}"
        hint = _browser_hint(exc)
        if hint:
            msg += "\n" + hint
        return False, msg
