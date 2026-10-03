# -*- coding: utf-8 -*-
"""把后端吐出来的原始报错翻成人话。

用户不需要看 yt-dlp 的 traceback，需要知道「该怎么办」。
"""
import re

from config import PROXY

_TAIL_LIMIT = 180


def _last_meaningful(raw):
    """取最后一行非空的输出，去掉 yt-dlp 的 ERROR: 前缀。"""
    for line in reversed((raw or "").strip().splitlines()):
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^ERROR:\s*", "", line)
        return line[:_TAIL_LIMIT]
    return ""


def friendly(raw, source):
    """raw: 后端收集到的全部输出；source: youtube / bilibili / douyin / x。"""
    s = (raw or "").lower()

    if source == "youtube":
        if any(k in s for k in ("sign in", "not a bot", "confirm you're not a bot",
                                "cookies", "login required")):
            return ("YouTube 要求登录验证。稍后重试一般能恢复；"
                    "若一直失败，需要提供 cookies 文件。")
        if any(k in s for k in ("connection refused", "failed to resolve",
                                "timed out", "proxy")):
            return (f"连不上代理（{PROXY}）。请确认代理软件已经启动；"
                    "端口不同可在 config.py 里改。")
        if "video unavailable" in s or "private video" in s:
            return "视频不可用或已设为私享。"
        if "requested format" in s:
            return "找不到合适的清晰度，请把链接换成完整视频页地址再试。"

    if source == "bilibili":
        if any(k in s for k in ("403", "sessdata", "premium", "大会员")):
            return "登录信息已失效，请重新导出 cookies。"
        if any(k in s for k in ("connection", "refused", "resolve", "timed out")):
            return "连不上 B站。请检查网络，或确认代理没有拦截国内站点。"
        if "requested format" in s:
            return "当前画质不可用。勾选「使用登录信息」可获得 1080p。"

    if source == "douyin":
        return ("抖音解析失败 —— 抖音的反爬策略经常变，这条路可能已经失效。\n"
                "可以先用浏览器打开视频页，把地址栏的完整链接复制过来再试。")

    if source == "x":
        if any(k in s for k in ("sign in", "authentication", "log in", "login",
                                "cookies", "age-restricted", "sensitive")):
            return ("这条帖子需要登录 X 才能查看（未登录能看的帖子越来越少）。\n"
                    "可在浏览器登录 X 后，把 cookies 导出到 "
                    "cookies\\x.txt 再试。")
        if any(k in s for k in ("connection refused", "failed to resolve",
                                "timed out", "proxy")):
            return (f"连不上代理（{PROXY}）。请确认代理软件已经启动；"
                    "端口不同可在 config.py 里改。")
        if any(k in s for k in ("404", "not found", "no longer exists",
                                "has been deleted", "suspended")):
            return "帖子不存在、已删除，或发帖账号被封禁。"
        if any(k in s for k in ("no video", "no media", "could not find")):
            return "这条帖子里没有视频（可能只有图片或纯文字）。"

    if source == "instagram":
        if any(k in s for k in ("login", "authentication", "checkpoint",
                                "rate limit", "429")):
            return ("Instagram 对未登录访问限制很严：公开内容一般能直接下，"
                    "需要登录的内容目前不支持。")
        if any(k in s for k in ("connection refused", "failed to resolve",
                                "timed out", "proxy")):
            return (f"连不上代理（{PROXY}）。请确认代理软件已经启动；"
                    "端口不同可在 config.py 里改。")
        if any(k in s for k in ("not found", "404", "private")):
            return "帖子不存在、已删除，或是私密账号。"

    if source == "xiaohongshu":
        if any(k in s for k in ("login", "登录", "authenticate", "461", "403")):
            return ("小红书网页版对未登录访问限制很严，这条笔记需要登录"
                    "才能看。目前暂不支持携带登录信息，可换一条公开笔记试。")
        if any(k in s for k in ("not found", "404")):
            return "笔记不存在、已删除，或里面没有视频（纯图片笔记下不了）。"

    if source == "weibo":
        if any(k in s for k in ("login", "登录", "visitor", "passport")):
            return "这条微博需要登录才能看，目前暂不支持携带登录信息。"
        if any(k in s for k in ("not found", "404")):
            return "微博不存在或已删除。"

    if source == "ixigua":
        if any(k in s for k in ("not found", "404")):
            return "视频不存在或已删除。"

    if source == "tiktok":
        if any(k in s for k in ("login", "captcha", "not available", "region")):
            return ("TikTok 对未登录访问和代理 IP 限制很严，可重试几次；"
                    "仍失败多半是这条视频需要登录或地区受限。")
        if any(k in s for k in ("connection refused", "failed to resolve",
                                "timed out", "proxy")):
            return (f"连不上代理（{PROXY}）。请确认代理软件已经启动；"
                    "端口不同可在 config.py 里改。")

    tail = _last_meaningful(raw)
    return "下载失败：" + (tail or "未知错误")


def check_prereqs(source, outdir, cookies_path=None, use_cookies=False,
                  proxy_host=None, proxy_port=None):
    """动手前的预检。返回中文错误信息，没问题则返回 None。

    宁可在这里一句话说清楚，也不要跑 20 秒才失败。
    """
    import os
    import shutil

    from config import YTDLP

    if not os.path.isdir(outdir):
        return f"保存目录不存在：{outdir}"

    free = shutil.disk_usage(outdir).free
    if free < 200 * 1024 * 1024:
        return f"磁盘剩余空间不足 200MB（当前 {free // 1024 // 1024}MB）。"

    if source not in ("douyin", "kuaishou"):
        import shutil
        if not os.path.isfile(YTDLP) and not shutil.which("yt-dlp"):
            return ("没有找到 yt-dlp（下载核心工具）。\n"
                    "安装方法：命令行运行  pip install yt-dlp\n"
                    "或从 github.com/yt-dlp/yt-dlp/releases 下载可执行"
                    "文件加入 PATH，并在 config.py 里指定位置。")
        # 合并音视频必须有 ffmpeg，缺了 yt-dlp 会在最后一步莫名失败
        from config import FFMPEG_DIR
        has_ffmpeg = any(os.path.isfile(os.path.join(FFMPEG_DIR, n))
                         for n in ("ffmpeg.exe", "ffmpeg"))
        if not has_ffmpeg and not shutil.which("ffmpeg"):
            return ("没有找到 ffmpeg（合并音视频必需）。\n"
                    "安装方法：winget install Gyan.FFmpeg，"
                    "或从 ffmpeg.org 下载后加入 PATH；"
                    "也可以修改 config.py 里的 FFMPEG_DIR 指向它。")

    if source in ("youtube", "x", "instagram", "tiktok") and proxy_host:
        import socket
        try:
            socket.create_connection((proxy_host, proxy_port), timeout=1).close()
        except OSError:
            return (f"代理没开（{proxy_host}:{proxy_port}）。"
                    "YouTube 必须走代理，请先启动 Clash。")

    if source == "bilibili" and use_cookies:
        if not cookies_path or not os.path.isfile(cookies_path):
            return f"没有找到 cookies 文件：{cookies_path}\n请先点「导入 B站登录」。"
        try:
            with open(cookies_path, "r", encoding="utf-8", errors="replace") as f:
                body = f.read()
        except OSError as exc:
            return f"读不了 cookies 文件：{exc}"
        if "SESSDATA" not in body:
            return "cookies 文件里没有 SESSDATA，可能不是 B站的登录信息。"

    return None
