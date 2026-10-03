# -*- coding: utf-8 -*-
"""各平台冒烟测试 —— 反爬机制悄悄失效的自动哨兵。

用法：
    python smoke_test.py              # 全部启用的平台
    python smoke_test.py kuaishou x   # 只测指定平台

每个平台用一条固定的公开内容链接走真实下载路径，落到临时目录后删除。
配合 GitHub Actions 每周定时跑（.github/workflows/smoke.yml），
哪个平台的解析路线失效了一周内就能发现，不用等用户来报。

结果分三档：
    PASS  下载成功
    SKIP  链接失效/内容被删/环境不具备（如本机没代理）—— 不是程序的锅
    FAIL  解析或下载失败 —— 很可能是反爬变了，需要修

注意：固定的测试链接迟早会被作者删掉。哪条从 SKIP 变成常驻 FAIL 前，
先浏览器里确认链接还活着；死链就换一条并更新本文件。
"""
import os
import shutil
import sys
import tempfile
import time
import traceback

# CI 的 Windows runner 上 stdout 默认 cp1252，中文/emoji 会炸
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

import config
import errors

# 每个平台一条「常驻」公开链接（2026-10 全部实测通过）。
# 小红书的 xsec_token 会过期，过期后该平台会变 SKIP（内容级问题），
# 换一条新鲜分享链接即可。西瓜视频需要完整浏览器 cookie，
# 暂不内置冒烟（应用里仍保留 ttwid 自动注册的尽力支持）。
CASES = {
    "kuaishou": {"url": "https://www.kuaishou.com/short-video/3xwrzgsfd5fyjyg"},
    "douyin": {"url": "https://www.douyin.com/music/7149936801028131598"},
    "youtube": {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    "bilibili": {"url": "https://www.bilibili.com/video/BV1GJ411x7h7"},
    "x": {"url": "https://x.com/captainamerica/status/719944021058060289"},
    "instagram": {"url": "https://www.instagram.com/reel/Chunk8-jurw/"},
    "xiaohongshu": {"url": "https://www.xiaohongshu.com/explore/6411cf99000000001300b6d9"},
    "weibo": {"url": "https://m.weibo.cn/detail/5120561132606436"},
    "tiktok": {"url": "https://www.tiktok.com/@nasa/video/7664638705177150477"},
    # ixigua: yt-dlp 需要页面 SSR 数据，游客 cookie 拿不全，冒烟暂缓：
    # "ixigua":  {"url": "https://www.ixigua.com/视频ID"},
}

# 冒烟下载限 480p —— 哨兵只验证「路线通不通」，没必要拉全高清
SMOKE_MAX_HEIGHT = 480

# 这些词出现在报错里，说明是内容没了/环境不具备，不是解析路线失效
_SKIP_HINTS = ("404", "not found", "已删除", "不存在", "没有视频",
               "私密", "private", "不可用", "unavailable", "代理",
               "proxy", "找不到 yt-dlp", "没有找到", "no video formats",
               "blocked", "ip address", "cookies", "timed out")


def _run_one(source, case, outdir):
    """跑一个平台。返回 (档位, 说明)。"""
    problem = errors.check_prereqs(
        source, outdir, config.COOKIES_BILI, False,
        config.PROXY_HOST, config.PROXY_PORT)
    if problem:
        return "SKIP", problem.splitlines()[0]

    emit = lambda kind, **kw: None
    job = _Job()
    started = time.time()

    if source == "douyin":
        import douyin
        ok, result = douyin.download_douyin(case["url"], outdir, emit, job)
    elif source == "kuaishou":
        import kuaishou
        ok, result = kuaishou.download_kuaishou(case["url"], outdir,
                                                emit, job)
    else:
        import backends
        ok, result = backends.download_ytdlp(case["url"], source, outdir,
                                             False, emit, job,
                                             SMOKE_MAX_HEIGHT)

    secs = time.time() - started
    if ok and os.path.isfile(result):
        size = os.path.getsize(result) // 1024
        return "PASS", f"{secs:.1f}s, {size}KB"
    low = (result or "").lower()
    if any(h.lower() in low for h in _SKIP_HINTS):
        return "SKIP", (result or "").splitlines()[0][:60]
    return "FAIL", (result or "").splitlines()[0][:60]


class _Job:
    """smoke 用的最小取消句柄，接口与 backends.Job 对齐。"""

    def __init__(self):
        import threading
        self.cancel = threading.Event()

    def cancel_now(self):
        self.cancel.set()

    def _set_proc(self, proc):
        pass


def main(argv):
    targets = [s for s in argv if s in CASES] if argv else list(CASES)
    unknown = [s for s in argv if s not in CASES]
    if unknown:
        print(f"未知的平台：{unknown}（可选：{list(CASES)}）")
        return 2

    results = []
    for source in targets:
        outdir = tempfile.mkdtemp(prefix="smoke_")
        print(f"[{source}] 测试中…", flush=True)
        try:
            level, note = _run_one(source, CASES[source], outdir)
        except Exception as exc:
            traceback.print_exc()
            level, note = "FAIL", f"{type(exc).__name__}: {exc}"
        finally:
            shutil.rmtree(outdir, ignore_errors=True)
        mark = {"PASS": "✅", "SKIP": "⏭ ", "FAIL": "❌"}[level]
        print(f"{mark} [{level}] {source:12s} {note}", flush=True)
        results.append((source, level))

    fails = [s for s, lv in results if lv == "FAIL"]
    print(f"\n汇总：{len(results)} 个平台，"
          f"FAIL {len(fails)} 个{('：' + ', '.join(fails)) if fails else ''}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
