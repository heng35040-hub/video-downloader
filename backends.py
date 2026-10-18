# -*- coding: utf-8 -*-
"""YouTube / Bilibili backend — both driven by yt-dlp, differing only in proxy and cookies."""
import json
import os
import pathlib
import re
import subprocess
import threading
import time

import config
import procutil
from errors import friendly

# 被墙平台，必须走本机代理；其余（国内站）一律直连
_PROXY_SOURCES = ("youtube", "x", "instagram", "tiktok")

# 西瓜视频的访客 cookie 文件（常量路径，见 _ixigua_cookie_file）
_IXIGUA_COOKIES = pathlib.Path(config.COOKIES_DIR) / "ixigua.txt"
_IXIGUA_COOKIE_TTL = 7 * 86400


class Job:
    """一次下载任务。

    持有子进程句柄，取消时能杀掉整棵进程树。注意 cancel_now 有竞态：
    可能在子进程起来之前就被调用，所以 _set_proc 里要补一次检查。
    """

    def __init__(self):
        self.cancel = threading.Event()
        self._proc = None
        self._lock = threading.Lock()

    def _set_proc(self, proc):
        with self._lock:
            self._proc = proc
            already = self.cancel.is_set()
        if already:
            procutil.kill_tree(proc)

    def cancel_now(self):
        self.cancel.set()
        with self._lock:
            proc = self._proc
        procutil.kill_tree(proc)


def _base_args(source, outdir, use_cookies, max_height=None):
    args = [
        *config.YTDLP_CMD,
        "--no-playlist",        # 贴了带 &list= 的链接时，别默默下一整个播放列表
        "--no-simulate",        # --print 默认会打开 simulate，必须显式关掉
        "--quiet",              # 只保留进度和错误，输出干净好解析
        "--progress",           # 但 --quiet 会连进度一起吞掉，得显式要回来
        "--newline",            # 不加则进度只用 \r，逐行读会读到一大坨
        "--no-colors",
        "--progress-delta", "0.5",
        "--progress-template", procutil.PROGRESS_TEMPLATE,
        "--ffmpeg-location", config.FFMPEG_DIR,   # GUI 进程的 PATH 未必找得到 ffmpeg
        "--trim-filenames", "120",  # 中文长标题加 .f137.mp4 后缀容易撞 MAX_PATH
        "-P", outdir,
        "-o", "%(title)s.%(ext)s",
        # 画质选择：带高度上限时逐级降级，平台上没有达标清晰度就取最优，
        # 不报告错。不选（最高）就是原始的 bv*+ba/b。
        "-f", (f"bv*[height<={max_height}]+ba/b[height<={max_height}]"
               f"/bv*+ba/b" if max_height else "bv*+ba/b"),
        "--merge-output-format", "mp4",
        # 用 %(...)j 让 yt-dlp 输出 JSON 转义后的纯 ASCII（中文变 \uXXXX）。
        # 原因：内置 yt-dlp 走的是「exe 自调用」子进程，输出编码取决于
        # PYTHONUTF8/PYTHONIOENCODING（procutil.build_env 已设成 UTF-8）；
        # 但外置的 yt-dlp.exe 是打包过的、无视这两个变量，一律按控制台代码页
        # (本机 cp936) 写 stdout。转成 JSON 就两种情况都不会出现非 ASCII 字节。
        "--print", "after_move:%(filepath)j",
        "--print", "video:TITLE %(title)j",
    ]
    if source in _PROXY_SOURCES:
        args += ["--proxy", config.PROXY]   # 被墙站，必须走本机代理
    else:
        # 国内站必须直连。显式传空串关掉代理，同时 build_env 会清掉代理环境变量
        args += ["--proxy", ""]
        # cookies 只有 B站 有；以前这里只判 use_cookies，别的国内站也会被塞进
        # B站的 cookies 文件，属于逻辑错误
        if use_cookies and source == "bilibili":
            args += ["--cookies", config.COOKIES_BILI]
    return args


def _short_err(stderr, limit=120):
    """把 yt-dlp 的 stderr 压成一句能放进状态栏的话。"""
    if not stderr:                       # 注意：b"" 是 falsy，不能写成
        return "未知原因"                 # `(stderr or "").decode()` —— 那会得到
    if isinstance(stderr, bytes):        # str 再调 .decode() 直接 AttributeError
        text = stderr.decode("utf-8", "replace")
    else:
        text = str(stderr)
    text = text.strip()
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        if line.startswith("ERROR:"):
            line = line[len("ERROR:"):].strip()
        # 去掉 "[BiliBili] 1VEJQ6DEHk: " 这种前缀
        m = re.match(r"^\[[^\]]+\]\s*[^:]{0,40}:\s*", line)
        if m:
            line = line[m.end():]
        return line[:limit]
    return "未知原因"


def probe_formats(url, source, use_cookies=False, timeout=45):
    """探测这条链接**实际能拿到**的画质。返回 (heights, error)。

    heights 是从高到低、去重的高度列表；探不到时为 None，error 给出原因。
    用 `yt-dlp -J` 只取元数据、不下载。

    为什么不猜「哪些画质需要登录」：实测 B站未登录也能下 1080P（yt-dlp 会把
    1080P 的直链给游客，真能下完）。所以这里只报**实测可用**的，不在界面上
    瞎标「需登录」—— 标错了比不标更误导。
    """
    cmd = [
        *config.YTDLP_CMD,
        "-J", "--no-playlist", "--no-warnings",
        "--skip-download", "--no-progress", "--no-colors",
    ]
    blocked = source in _PROXY_SOURCES
    if blocked:
        cmd += ["--proxy", config.PROXY]
    else:
        cmd += ["--proxy", ""]
        if use_cookies and source == "bilibili":
            cmd += ["--cookies", config.COOKIES_BILI]
    cmd.append(url)

    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout,
                              env=procutil.build_env(no_proxy=not blocked))
    except subprocess.TimeoutExpired:
        return None, "解析超时"
    except Exception as exc:
        return None, f"{type(exc).__name__}"
    if proc.returncode != 0:
        return None, _short_err(proc.stderr)
    try:
        data = json.loads(proc.stdout.decode("utf-8", "replace"))
    except ValueError:
        return None, "返回内容无法解析"

    heights = set()
    for f in (data.get("formats") or ()):
        if (f.get("vcodec") or "none") == "none":     # 纯音频轨，跳过
            continue
        try:
            heights.add(int(f.get("height")))
        except (TypeError, ValueError):
            continue
    return (sorted(heights, reverse=True) or None), None


def _json_str(text):
    """解析 yt-dlp 用 %(...)j 输出的 JSON 字符串，失败返回 None。"""
    try:
        val = json.loads(text.strip())
    except (ValueError, TypeError):
        return None
    return val if isinstance(val, str) else None


def _newest_file(outdir, since):
    """目录里 since 之后最新的文件 —— filepath 行丢失时的兜底。

    同时只有一个下载任务，所以这个兜底是可靠的。
    """
    best, best_m = None, since
    try:
        for name in os.listdir(outdir):
            if name.endswith((".part", ".ytdl", ".f137.mp4")):
                continue
            p = os.path.join(outdir, name)
            try:
                m = os.path.getmtime(p)
            except OSError:
                continue
            if m > best_m and os.path.isfile(p):
                best, best_m = p, m
    except OSError:
        pass
    return best


def _ixigua_cookie_file(emit):
    """西瓜视频连游客都要 ttwid cookie；没有就向字节官方接口注册一个。

    cookies\\ixigua.txt 缓存 7 天，过期重注册。失败返回 None，
    让 yt-dlp 自己去撞报错，不在预检环节卡死流程。
    """
    if (_IXIGUA_COOKIES.is_file()
            and time.time() - _IXIGUA_COOKIES.stat().st_mtime
            < _IXIGUA_COOKIE_TTL):
        return str(_IXIGUA_COOKIES)

    import requests

    try:
        s = requests.Session()
        s.trust_env = False            # 字节接口国内直连
        s.headers["User-Agent"] = config.BROWSER_UA
        s.headers["Content-Type"] = "application/json"
        r = s.post(
            "https://ttwid.bytedance.com/ttwid/union/register/",
            data=json.dumps({
                "region": "cn", "aid": 1768, "needFid": False,
                "service": "www.ixigua.com",
                "migrate_info": {"ticket": "", "source": "node"},
                "cbUrlProtocol": "https", "union": True,
            }), timeout=20)
        ttwid = r.cookies.get("ttwid")
        if not ttwid:
            return None
        # Netscape 格式，yt-dlp 直接可读；过期时间给一年
        _IXIGUA_COOKIES.parent.mkdir(parents=True, exist_ok=True)
        _IXIGUA_COOKIES.write_text(
            "# Netscape HTTP Cookie File\n"
            f".ixigua.com\tTRUE\t/\tTRUE\t"
            f"{int(time.time()) + 31536000}\tttwid\t{ttwid}\n",
            encoding="utf-8")
        emit("log", text="已注册西瓜访客 ttwid")
        return str(_IXIGUA_COOKIES)
    except Exception:
        return None


def download_ytdlp(url, source, outdir, use_cookies, emit, job,
                   max_height=None):
    """跑 yt-dlp。返回 (成功?, 文件路径 或 错误文本)。

    emit(kind, **kw) 会在工作线程里被调用；它只往队列里塞事件，
    绝不碰任何界面对象（Tkinter 不是线程安全的）。
    """
    started = time.time()
    if not config.YTDLP_CMD:
        return False, ("内置的 yt-dlp 没能加载（打包或依赖不完整）。\n"
                       "请重新下载最新版程序；从源码运行请先执行："
                       "pip install -r requirements.txt")
    cmd = _base_args(source, outdir, use_cookies, max_height) + [url]
    if source == "ixigua":
        cookie_file = _ixigua_cookie_file(emit)
        if cookie_file:
            cmd += ["--cookies", cookie_file]
    emit("log", text=" ".join(cmd))

    proc = procutil.popen(
        cmd, no_proxy=(source not in ("youtube", "x", "instagram", "tiktok")))
    job._set_proc(proc)

    lines = []
    filepath = None
    last_frac = 0.0

    try:
        for raw in proc.stdout:
            if job.cancel.is_set():
                break
            line = raw.rstrip("\r\n")
            if not line:
                continue
            lines.append(line)

            if line.startswith("TITLE "):
                emit("title", text=_json_str(line[6:]) or "")
                continue

            parsed = procutil.parse_progress(line)
            if parsed is not None:
                frac, text = parsed
                if frac is None:
                    emit("progress", frac=-1.0, text=text)
                else:
                    # 分段下载时估算总量会抖，只许前进不许后退，否则进度条来回跳
                    last_frac = max(last_frac, frac)
                    emit("progress", frac=last_frac, text=text)
                continue

            if procutil.is_merge_line(line):
                emit("merge", text="正在合并音视频…")
                continue

            if filepath is None and line.startswith('"'):
                cand = _json_str(line)
                if cand and os.path.isabs(cand):
                    filepath = cand
    except Exception as exc:      # stdout 被取消操作关掉时会抛
        lines.append(f"[读取输出异常] {exc}")
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
        try:
            rc = proc.wait(timeout=10)
        except Exception:
            procutil.kill_tree(proc)
            rc = -1

    if job.cancel.is_set():
        return False, "已取消"

    if rc == 0:
        # 拿到的路径也可能是坏的（模板变动、编码问题等），一律以文件系统为准
        if not filepath or not os.path.isfile(filepath):
            found = _newest_file(outdir, started)
            if found:
                filepath = found
        if filepath and os.path.isfile(filepath):
            return True, filepath
        return False, (f"yt-dlp 报告成功，但没找到输出文件。\n"
                       f"捕获到的路径: {filepath!r}\n"
                       f"目录: {outdir!r}\n"
                       f"末几行: {lines[-5:]}")

    # 失败：把最后几十行交给 errors 翻译
    return False, friendly("\n".join(lines[-40:]), source)
