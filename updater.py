# -*- coding: utf-8 -*-
"""版本号比较与「检查更新」。

设计原则：**检查更新失败绝不能影响正常使用**。所以：
- 所有异常一律吞掉，返回 None（静默）
- 超时 1.5 秒，不给用户造成启动卡顿
- 强制直连：用户可能配了代理，而 Gitee 是国内站，走代理反而可能不通
"""
import json


def parse_version(text):
    """把 "v2026.10.18.4" / "2026.10.19" 拆成 (2026, 10, 18, 4)。

    非法、空、含非数字段时返回 None。只做版本号该做的事，不猜语义。
    """
    if not text:
        return None
    s = str(text).strip().lstrip("vV")
    if not s:
        return None
    parts = []
    for chunk in s.split("."):
        chunk = chunk.strip()
        if not chunk or not chunk.isdigit():
            return None
        parts.append(int(chunk))
    return tuple(parts)


def is_newer(remote, local):
    """远端版本是否比本地新。

    长度不同时补零再比：2026.10.19 与 2026.10.18.4 → 补成
    (2026,10,19,0) vs (2026,10,18,4)，逐段比较才对。
    直接按字符串比会把 "2026.10.9" 判成比 "2026.10.10" 大，是经典坑。
    """
    r, l = parse_version(remote), parse_version(local)
    if not r or not l:
        return False
    n = max(len(r), len(l))
    r = r + (0,) * (n - len(r))
    l = l + (0,) * (n - len(l))
    return r > l


def parse_manifest(data, local_version):
    """把版本清单解析成更新信息；没有更新返回 None。

    清单字段：
      version      必填，如 "2026.10.19"
      notes        可选，一句话说明（显示在状态栏）
      url          可选，网盘下载页（普通用户）
      url_github   可选，GitHub Releases（懂 GitHub 的用户，不用忍受网盘限速）

    抽成纯函数是为了能单测 —— check() 里带网络，不好测。
    """
    if not isinstance(data, dict):
        return None
    ver = data.get("version")
    if not is_newer(ver, local_version):
        return None
    return {
        "version": str(ver).strip().lstrip("vV"),
        "notes": str(data.get("notes") or "").strip(),
        "url": str(data.get("url") or "").strip(),
        "url_github": str(data.get("url_github") or "").strip(),
    }


def check(url, local_version, timeout=1.5):
    """请求版本清单，有新版本返回 {version, notes, url, url_github}，否则 None。

    返回 None 的情形包括：网络失败、非 200、JSON 坏、没有 version 字段、
    版本不比本地新。调用方一律按「没有更新」处理。
    """
    if not url:
        return None
    try:
        import requests
        sess = requests.Session()
        sess.trust_env = False                     # 不读系统代理环境变量
        sess.proxies = {"http": None, "https": None}   # 也不走手填代理
        resp = sess.get(url, timeout=timeout,
                        headers={"Cache-Control": "no-cache"})
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception:
        return None

    return parse_manifest(data, local_version)
