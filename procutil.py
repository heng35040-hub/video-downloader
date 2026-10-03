# -*- coding: utf-8 -*-
"""子进程封装 —— 编码、进度解析、进程树取消。

两个 yt-dlp 后端都靠它，而且这里是全项目最容易出错的地方：
本机 stdout 编码是 gbk、文件系统编码是 utf-8，两者混用就是乱码的来源。
"""
import os
import re
import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# yt-dlp 的 --progress-template 输出。刻意只输出纯 ASCII 数字：
# 人类可读那行混着 ANSI 转义和中文标题，解析它等于自找乱码。
PROGRESS_TEMPLATE = (
    "download:PROG %(progress.downloaded_bytes)s %(progress.total_bytes)s "
    "%(progress.total_bytes_estimate)s %(progress.speed)s %(progress.eta)s"
)
_PROG_RE = re.compile(r"^PROG\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$")

_MERGE_HINTS = ("[Merger]", "[ffmpeg]", "[FixupM3u8]", "[VideoRemuxer]")


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def parse_progress(line):
    """解析一行进度输出。

    返回 (比例, 进度文本)；不是进度行则返回 None。
    比例可能是 None —— 总大小未知，调用方据此切成不确定进度条。
    """
    m = _PROG_RE.match(line.strip())
    if not m:
        return None
    done, total, est, speed, _eta = m.groups()
    if done == "NA":
        return 0.0, ""
    done_n = _num(done)
    total_n = _num(total) or _num(est)
    if done_n is None:
        return None
    frac = None
    if total_n:
        frac = max(0.0, min(1.0, done_n / total_n))
    text = human_size(done_n)
    if total_n:
        text += " / " + human_size(total_n)
    spd = _num(speed)
    if spd:
        text += f"   {human_size(spd)}/s"
    return frac, text


def is_merge_line(line):
    """判断是否是「正在合并音视频」阶段。

    合并阶段没有任何进度事件，不让界面知道的话，看起来就像卡死在 100%。
    """
    return any(h in line for h in _MERGE_HINTS)


def human_size(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{int(n)} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def build_env(no_proxy=False):
    """准备子进程环境变量：强制 UTF-8 输出；必要时剔掉代理变量。

    本机 locale 是 cp936 而 yt-dlp 输出 UTF-8，不强制的话中文标题必乱码。
    国内站（B站/抖音）必须直连，若环境里有 HTTP_PROXY 会污染，一并清掉。
    """
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if no_proxy:
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                  "http_proxy", "https_proxy", "all_proxy"):
            env.pop(k, None)
    else:
        # 走代理的场合也统一成同一个值，避免外部变量覆盖
        for k in ("HTTP_PROXY", "http_proxy"):
            env.pop(k, None)
    return env


def popen(cmd, no_proxy=False, cwd=None):
    """起一个子进程，供逐行读取。

    几个刻意的选择：
    - 显式 encoding="utf-8" 覆盖 locale；errors="replace" 而非 strict，
      否则一个坏字节就会打死读取循环
    - 不用 text=True（它按 locale 解码，正是乱码来源）
    - 不用 shell=True（argv 形式才能正确传 Unicode，且不经过 cmd.exe）
    - CREATE_NO_WINDOW：pythonw 自己没有控制台，不加这个每个子进程都弹黑框
    """
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        cwd=cwd,
        env=build_env(no_proxy=no_proxy),
        creationflags=CREATE_NO_WINDOW,
    )


def kill_tree(proc):
    """杀掉整棵进程树。

    不能只 terminate：yt-dlp 合并音视频时会 fork 出 ffmpeg，
    只终止父进程会留下孤儿 ffmpeg 继续写盘，产出半个损坏的 mp4。
    """
    if proc is None:
        return
    try:
        if proc.poll() is not None:
            return
    except Exception:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    else:
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass
