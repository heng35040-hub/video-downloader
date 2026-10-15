# 架构设计与踩坑记录

> 从代码注释中迁移而来的设计决策、替代方案对比、反爬应对历史。供维护者参考。

---

## 1. 线程模型（main.py）

**约定**：所有耗时工作在 worker 线程；worker 只往队列塞事件，**绝不碰任何 widget / StringVar**。

**原因**：Tkinter 不是线程安全的。违规表现不是报错，而是随机死锁或界面半死不活，极难复现排查。

**实现**：
- `App.q = queue.Queue()` 事件队列
- `App._pump()` 每 100ms 抽干队列刷新界面
- `App._run_tasks()` 在 `threading.Thread` 中跑，通过 `emit(kind, **kw)` 往队列塞事件

---

## 2. 代理策略（config.py `_detect_proxy`）

**探测顺序**：
1. **Windows 系统代理设置**（注册表 `HKEY_CURRENT_USER\...\Internet Settings`） —— 最可靠，反映用户浏览器实际在用的代理
2. **常见端口探测**（7897, 7890, 10809, 1080, 8118, 2080, 8889） —— Clash Verge / Clash / v2rayN / 通用 socks / privoxy
3. **兜底** `127.0.0.1:7897` —— Clash 默认端口

**分流规则**：
- 被墙平台：YouTube, X, Instagram, TikTok → **必须走代理**
- 国内平台：B站, 抖音, 快手, 小红书, 微博, 西瓜 → **强制直连**（显式 `--proxy ""` + 清理环境变量 `HTTP_PROXY` 等）

**原因**：国内站走代理极大概率被风控/限速/连不上；被墙站不走代理根本连不上。

---

## 3. yt-dlp 输出编码处理（backends.py）

**问题**：`yt-dlp.exe` 是打包可执行文件，无视 `PYTHONIOENCODING`，一律按控制台代码页（中文 Windows 通常是 cp936/GBK）写 stdout。直接读中文路径拿到的是 GBK 字节，按 UTF-8 解码会变 `U+FFFD` 乱码。

**解决**：用 `--print "after_move:%(filepath)j"` —— `%(...)j` 输出 JSON 转义后的纯 ASCII（中文变 `\uXXXX`）。管道里全是 ASCII，无编码烦恼。

**同理**：`--print "video:TITLE %(title)j"` 取标题。

---

## 4. 进程树级取消（procutil.py `kill_tree`）

**问题**：只 `terminate()` 父进程，yt-dlp 合并音视频时 fork 出的 ffmpeg 会成为孤儿进程继续写盘，产出半个损坏的 mp4。

**解决**：Windows 用 `taskkill /F /T /PID <pid>` 杀整棵进程树；Unix 用 `proc.terminate()` + `proc.kill()` 兜底。

---

## 5. 文件名安全（douyin.py `_dest_path` / kuaishou.py 复用）

**风险**：视频标题来自外部输入，可能包含路径穿越序列（`../`）、非法字符、超长路径。

**防御**：
1. `_sanitize()` 过滤 `\ / : * ? " < > |` 及控制字符
2. `tempfile.mkstemp(dir=directory, prefix="dl_", suffix=".part")` —— 临时文件路径由 OS 随机生成，完全不经手外部数据
3. 下载完成 `os.replace(part, dest)` 原子改名
4. 最终兜底：`os.path.dirname(os.path.abspath(dest)) == os.path.abspath(outdir)` 校验，异常时退回纯 ID 命名

---

## 6. 抖音登录态持久化（douyin.py `_open_context` / `config.PROFILE_DOUYIN`）

**现状**：抖音对游客上登录墙，未登录无法获取视频/音乐直链。

**方案**：用 Playwright **持久化 profile**（`launch_persistent_context`）而非一次性上下文：
- 首次有头模式弹窗扫码登录
- 登录态（cookies、localStorage 等）长期保存在 `profile_douyin/` 目录
- 后续无头模式复用该 profile，**免登录**

**关键参数**：
- `channel="chromium"` 选完整版浏览器（headless shell UA 带 `HeadlessChrome` 会被秒识别）
- `--disable-blink-features=AutomationControlled` 隐藏自动化特征
- 手动注入 `Object.defineProperty(navigator,'webdriver',{get:()=>undefined})` 抹掉 `navigator.webdriver`

---

## 7. 抖音音乐/收藏批量下载

**音乐页（/music/<id>）**：
- 游客会被登录墙挡住，但页面加载时会请求 `music/aweme`（使用该音乐的视频列表），其 JSON 内嵌音乐对象的 mp3 直链 —— **免登录主路径**
- `music/detail` 接口和 `audio/*` 媒体响应做兜底

**收藏→音乐列表**：
- 整页批量抓取入口：`/user/self?showSubTab=music&showTab=favorite_collection`
- 滚动加载时逐页捕获列表接口 JSON 内嵌的 mp3 直链
- 万一接口不带，用户手动点播放的 `audio/*` 响应也能兜住
- 下载前弹窗让用户勾选（默认全选），已存在同名文件自动跳过 = **断点续传**

---

## 8. 快手设备伪造（kuaishou.py `_fake_device`）

**核心**：快手靠 `did` cookie 认设备；游客没有，就造一个：
```python
session.cookies.set("did", "web_" + uuid.uuid4().hex, domain=".kuaishou.com")
session.cookies.set("didv", str(int(time.time() * 1000)), domain=".kuaishou.com")
```
**关键参数**：`kpn=KUAISHOU` —— 不带这个参数，服务端只给站点壳数据，视频节点整个不渲染（实测唯一稳定开关）。

---

## 9. 西瓜视频访客 cookie 自动注册（backends.py `_ixigua_cookie_file`）

**现状**：西瓜连游客都要 `ttwid` cookie。

**方案**：向字节官方接口 `https://ttwid.bytedance.com/ttwid/union/register/` 注册一个 `ttwid`，缓存 7 天（`cookies/ixigua.txt`，Netscape 格式）。过期重注册。失败返回 `None` 让 yt-dlp 自己撞报错，不在预检环节卡死流程。

---

## 10. 工具下载安全闸（toolssetup.py `_assert_public_host`）

**下载前校验**：
1. 仅允许 HTTPS
2. 域名解析必须得到**公网 IP**（拒绝私有/环回/链路本地/保留/组播/未指定地址）

**防范**：供应链劫持、DNS 重绑定、被诱导下载内网服务内容。

**重定向后再校验一次** `_assert_public_host(resp.url)`。

---

## 11. yt-dlp 自更新（toolssetup.py `maybe_self_update_ytdlp`）

- 每两周尝试一次（`_SELFUPDATE_INTERVAL = 14 * 24 * 3600`）
- 只管自装副本：用户 PATH/pip 里自己装的 yt-dlp **不越权代管**
- 显式 `--proxy ""`（直连）或 `--proxy <addr>`（代理）：yt-dlp 会自己读 Windows 系统代理，实测会拿到过期端口连环境变量里都没有的幽灵代理 —— 空串旗标才是真正的直连
- 无论成败都 `touch()` mtime，避免每次启动白跑 `-U`

---

## 12. 冒烟测试设计（smoke_test.py + .github/workflows/smoke.yml）

**目的**：反爬机制悄悄失效的自动哨兵。每周一自动跑，哪个平台解析路线失效一周内发现。

**结果三档**：
- **PASS** 下载成功
- **SKIP** 链接失效/内容被删/环境不具备（如 CI 无代理） —— 非程序锅
- **FAIL** 解析或下载失败 —— 很可能反爬变了，需修

**注意**：固定测试链接迟早被作者删。SKIP 常驻前先浏览器确认链接活着；死链换新并更新 `CASES`。

**不要做的事**：接验证码打码平台、多线程批量爬取 —— 法律风险和封禁风险同时陡增，个人工具不需要。

---

## 13. 编码硬化（procutil.py `build_env` / `popen`）

- 子进程环境强制 `PYTHONUTF8=1` + `PYTHONIOENCODING=utf-8`
- `encoding="utf-8", errors="replace"` 覆盖 locale；`replace` 而非 `strict`，否则一个坏字节打死读取循环
- 不用 `text=True`（它按 locale 解码，正是乱码来源）
- 不用 `shell=True`（argv 形式才能正确传 Unicode，且不经过 cmd.exe）
- `CREATE_NO_WINDOW`：pythonw 自己没有控制台，不加这个每个子进程都弹黑框

---

## 14. 进度解析（procutil.py `parse_progress`）

**模板**：`--progress-template "download:PROG %(progress.downloaded_bytes)s %(progress.total_bytes)s %(progress.total_bytes_estimate)s %(progress.speed)s %(progress.eta)s"`

**刻意只输出纯 ASCII 数字** —— 人类可读那行混着 ANSI 转义和中文标题，解析它等于自找乱码。

**分段下载时估算总量会抖** —— 只许前进不许后退（`last_frac = max(last_frac, frac)`），否则进度条来回跳。

---

## 15. 错误翻译策略（errors.py `friendly`）

**原则**：用户不需要 traceback，需要知道「该怎么办」。

**按平台分类匹配关键词**，给出可执行建议：
- YouTube: 登录验证、代理连不上、视频不可用、格式不可用
- B站: cookies 失效、连不上、画质需登录
- X: 需登录、代理、404、无视频
- Instagram: 登录限制、代理、404
- 小红书/微博: 需登录、404
- TikTok: 登录/验证码/地区限制、代理
- 兜底：取最后一行有意义输出，去掉 `ERROR:` 前缀

**预检**（`check_prereqs`）：动手前把能查的都查了（目录存在、磁盘空间、yt-dlp/ffmpeg 可用、代理端口通、B站 cookies 有 SESSDATA），宁可这里一句话说清楚，也不要跑 20 秒才失败。

---

## 16. 抖音/快手反爬维护指南

| 平台 | 解析方式 | 易碎点（改这里） |
|------|----------|-----------------|
| 抖音 | Playwright 捞 CDN 直链 / 音乐接口 JSON | `douyin.py` 的响应过滤条件与 `_extract_play_urls` |
| 快手 | 纯 requests 解析 `__APOLLO_STATE__` | `kuaishou.py` 的 `_parse_detail` 与 `kpn` 参数 |
| 其余 | yt-dlp | 基本只需保持 yt-dlp 最新（tools\ 里的副本每两周自动 `-U`） |

---

## 17. 依赖版本策略

- **Python 3.10+**（含 tkinter）
- **yt-dlp**：自动更新，锁定在 `tools/yt-dlp.exe`
- **ffmpeg**：gyan.dev essentials 构建，锁定在 `tools/ffmpeg.exe`
- **Playwright**：仅抖音/快手用，`playwright install chromium`
- **requests / tkinterdnd2**：标准库级依赖，版本宽松

---

*最后更新：2026-10（随代码迁移同步）*