# 视频下载器

一个 Windows 桌面端的视频下载工具：把链接拖进对应平台的格子就能下载，
自动识别平台、自动走代理/直连、实时进度、报错翻成人话。

支持 10 个平台：YouTube、B站、抖音、X (Twitter)、Instagram、快手、
小红书、微博、西瓜视频、TikTok。

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## 功能特点

- **拖拽 / 剪贴板自动识别**：复制链接后切回窗口即自动填入对应平台格子
- **多平台同时下载**：多个格子可以同时填，点一次下载依次完成
- **画质选择**：最高 / 1080p / 720p / 480p，对 yt-dlp 系平台生效
  （抖音/快手取页面默认清晰度）；平台上没有达标清晰度时自动取最优，不报错
- **代理智能分流**：被墙平台（YouTube / X / Instagram / TikTok）自动走
  本机代理，国内平台强制直连
- **抖音原声下载**：音乐页链接直接存 mp3；支持批量下载「收藏 → 音乐」，
  下载前可勾选
- **抖音/快手免扫码**：登录一次长期有效（登录态保存在本地，不上传任何地方）
- **实时进度与取消**：进度条 + 已下载体积，随时取消不留半个损坏文件

## 环境要求

- Windows 10/11
- 直接使用 Releases 中的 exe：无需安装 Python、yt-dlp 或 ffmpeg；首次运行可在弹窗中一键下载所需组件
- 从源码运行：Python 3.10+（含 tkinter）
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) 和 [ffmpeg](https://ffmpeg.org)（源码运行时需自行安装；打包版首次运行可一键下载）
- **抖音功能**使用系统自带的 Microsoft Edge 或 Google Chrome 驱动浏览器
  （Windows 10/11 一般自带 Edge），**无需额外下载约 150MB 的 chromium**；
  只有在极精简的系统上两者都没有时，才需要自行安装 Edge/Chrome

  **没有装也没关系**：启动时会弹窗提示缺什么，点「一键下载并配置」
  即可从官方源自动下载（yt-dlp 来自 GitHub 官方 releases，ffmpeg 来自
  ffmpeg.org 官方推荐的 gyan.dev 构建源），安装到程序目录 `tools\`
  并立即生效。也可以关闭弹窗自行安装；加入 PATH 后程序能自动找到，
  或在 `config.py` 里手动指定路径
- 下载被墙平台（YouTube / X / Instagram / TikTok）需要本机代理。
  端口**自动探测**：优先读 Windows 系统代理设置，其次尝试常见端口
  （7897 / 7890 / 10809 等）；自动探测不合适时在 `config.py` 里手动指定

## 安装

**方式一：直接下载 exe（推荐，不需要 Python 环境）**

到 [GitHub 最新版下载页](https://github.com/heng35040-hub/video-downloader/releases/latest) 下载 `VideoDownloader.exe`，
**双击即用** —— 不需要装 Python、不需要解压、不需要配环境变量。

> 单文件程序**每次**启动时，引导程序都要先把自身内容解压到临时目录，
> 实测约 3–5 秒（不只是第一次），这是正常现象。

**方式二：从源码运行**

**1. 安装 Python**

到 [python.org/downloads](https://www.python.org/downloads/) 装
Python 3.10 或更新版本，安装时**勾选 "Add python.exe to PATH"**
（tkinter 界面库 Windows 版自带，无需额外安装）。

**2. 拉代码、装依赖**

```bat
git clone https://github.com/heng35040-hub/video-downloader.git
cd video-downloader
pip install -r requirements.txt
```

> 抖音功能不需要 `playwright install chromium`：程序会直接用系统自带的
> Edge / Chrome（`douyin.py` 的 `_BROWSER_CHANNELS`）。

**3. 启动**

```bat
python main.py
```

**4. 首次启动：缺什么补什么**

程序启动时会自检 yt-dlp 和 ffmpeg，缺了会弹窗 —— 点「一键下载并配置」
即自动从官方源下载装好（装进程序目录 `tools\`，立即生效），**不需要
手动装这两个工具**。想手动装也可以：`pip install yt-dlp` +
[winget install Gyan.FFmpeg](https://ffmpeg.org)，加入 PATH 后程序同样能认。

双击启动可参考 `run.bat`（自动找 py/pythonw 静默启动，可自己建个快捷方式）。

**5. 跑单元测试（可选）**

```bat
pip install -r requirements-dev.txt
pytest -q
```

## 平台说明

| 平台 | 连接方式 | 登录要求 |
|---|---|---|
| YouTube | 代理 | 免登录 |
| B站 | 直连 | 免登录（可选 cookies 解锁高画质） |
| 抖音 | 直连 | 首次扫码登录一次（视频）；音乐页/收藏音乐免登录 |
| X (Twitter) | 代理 | 免登录（公开帖子） |
| Instagram | 代理 | 免登录（公开内容） |
| 快手 | 直连 | 免登录 |
| 小红书 | 直连 | 免登录（仅视频笔记；分享链接自带的 xsec_token 过期后需重新分享） |
| 微博 | 直连 | 免登录（公开微博） |
| 西瓜视频 | 直连 | 实验性：游客 cookie 自动注册，部分视频可用 |
| TikTok | 代理 | 免登录（公开视频，对代理 IP 限制较严） |

各平台的反爬策略变化频繁，某个平台失效不代表全部失效；欢迎提 issue。

## 下载抖音收藏的音频

1. 网页版打开 收藏 → 音乐 列表页，复制地址栏链接（含 `showSubTab=music`）
2. 拖进抖音格子，点下载
3. 首次会弹出浏览器窗口，扫码登录抖音（只需一次）
4. 程序自动滚动加载整个列表，弹窗让你勾选要下载的条目，然后逐条存成 mp3

已存在的同名文件自动跳过，中断后再拖一次等于断点续传。

## 项目结构

```
main.py              Tkinter 界面
backends.py          yt-dlp 驱动（YouTube / B站 / X / Instagram / 小红书 / 微博 / 西瓜 / TikTok）
douyin.py            抖音（Playwright 抓取 + requests 下载）
kuaishou.py          快手（纯 requests 解析）
procutil.py          子进程封装（编码、进度、进程树取消）
errors.py            报错翻译 + 下载前预检
config.py            路径与常量
conftest.py          pytest 路径配置
build.spec           PyInstaller 打包配置（单文件 onefile）
tests/               单元测试（URL 解析、平台识别、报错翻译）
requirements.txt     运行时依赖
requirements-dev.txt 开发/测试依赖
```

## 反爬维护（给维护者）

抖音、快手这类平台的反爬确实会频繁调整（实测抖音几个月内就上过一次
登录墙）。这个项目把脆弱点做了收敛，失效时定位和修复都只动一处：

| 平台 | 解析方式 | 易碎点（改这里） |
|---|---|---|
| 抖音 | Playwright 捞 CDN 直链 / 音乐接口 JSON | `douyin.py` 的响应过滤条件、`_extract_play_urls` 与浏览器回退链 `_BROWSER_CHANNELS` |
| 快手 | 纯 requests 解析 `__APOLLO_STATE__` | `kuaishou.py` 的 `_parse_detail` 与 `kpn` 参数 |
| 其余 | yt-dlp | 基本只需保持 yt-dlp 最新（tools\ 里的副本每两周自动 `-U`） |

**冒烟测试**：`python smoke_test.py` 对每个平台用固定公开链接走一遍真实
下载，输出 PASS / SKIP / FAIL。哪个平台悄悄失效一目了然；
`.github/workflows/smoke.yml` 会在 GitHub Actions 里每周一自动跑一次，
变红即提示该修了。测试链接被作者删掉时会显示 SKIP，记得定期换新链接。

**单元测试**：`pytest -q` 跑 `tests/` 下的纯逻辑测试（URL 抠取、平台识别、
报错翻译），不联网、秒级完成；`.github/workflows/tests.yml` 在每次 push /
PR 时自动执行。改完代码先跑这个，再考虑跑冒烟。

**打包**：`pyinstaller --clean build.spec` 产出单文件 `dist\VideoDownloader.exe`。
spec 里不能出现 `COLLECT`，否则会退回 onedir（一整个文件夹）。
Playwright 自带 PyInstaller hook，会把 node 驱动自动收进包，无需手写 `collect_all`；
抖音用的浏览器走系统自带 Edge/Chrome，不打包 chromium。

**打包自检**：`dist\VideoDownloader.exe --selftest` 会无界面跑一遍启动自检，
确认 Playwright 驱动、tkinterdnd2 原生库、requests 都真的打进了包，并给出
「引导程序解压 / 模块导入 / 自检内部」三段耗时；结果写入
`%TEMP%\VideoDownloader-selftest.txt`，退出码 0 表示通过。
`.github/workflows/build.yml` 在构建后会执行这一步 —— PyInstaller 漏收文件时
构建照样「成功」，只有这个自检能暴露问题；用户反馈启动慢时也靠它定位。

**不要做的事**：不要接验证码打码平台、不要做多线程批量爬取——
那是法律风险和封禁风险同时陡增的区域，个人工具不需要。

## 支持作者（自愿）

本项目保持开源免费，下载、更新与全部功能都不受任何影响。

如果它帮到了你，可以请作者喝杯咖啡 —— **完全自愿，不打赏也一样**：

[☕ 在爱发电支持作者](https://afdian.com/a/anodev)

程序界面右下角也有一个同样的按钮。或者，给仓库点个 Star、提 Issue
反馈问题、或把这个工具分享给需要的人，同样是很好的支持。

## 免责声明

- 本工具仅供个人学习与研究使用，用于备份**你自己有权访问**的内容。
- 请遵守目标平台的服务条款与你所在地的法律法规；下载内容的
  **版权归原作者所有**，是否可以二次使用由你自行确认。
- 禁止将本工具用于商业用途、批量抓取，或以任何形式分发受版权保护的内容。
- 本工具不破解任何 DRM/付费加密；需要登录才能看的内容请先自行登录。
- 使用本工具产生的一切后果由使用者自行承担，与作者无关。

## 隐私声明

**本工具零遥测、零上报、零账号体系，完全本地化运行。**

| 项目 | 说明 |
|------|------|
| **网络请求** | 仅连接：目标视频平台（下载内容）、GitHub/gyan.dev（工具下载）、字节跳动 ttwid 接口（西瓜访客 cookie） |
| **本地存储** | `cookies/`（B站 cookies）、`profile_douyin/`（抖音登录态）、`logs/`（运行日志）、`tools/`（yt-dlp/ffmpeg） —— 全在程序目录，用户可控可删 |
| **代理探测** | 仅读 Windows 注册表 + 本地回环 TCP 探测常见端口，**无外网流量** |
| **自动更新** | 仅每两周从 GitHub 官方 releases 更新 `tools/yt-dlp.exe`，可删 `tools/` 禁用 |
| **敏感数据** | B站 `SESSDATA`、抖音登录态 **仅本地使用，不上传任何地方** |

详见 [SECURITY.md](SECURITY.md) 完整安全模型说明。

## License

[MIT](LICENSE)
