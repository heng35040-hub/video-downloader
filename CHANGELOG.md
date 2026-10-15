# 更新日志

所有重要变更记录在此。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)（采用日期格式 YYYY.MM.DD）。

## [未发布]

### 变更
- 移除代码中的机器特定路径（本机 Python 安装目录、素材盘等），统一改为
  `tools/` 目录 → PATH → `~/Downloads` 的解析顺序，任何机器开箱即用
- 移除仓库内的收款二维码图片；打赏入口改为接入爱发电主页
  （`config.py` 的 `DONATE_URL = https://afdian.com/a/anodev`），
  README 的「支持作者」段落同步给出链接
- **打包改为双形态**：`build.spec` 支持 onefile / onedir，用环境变量
  `VD_BUILD_MODE` 切换。Release 主推 onedir 的 `VideoDownloader-win64.zip`
  （解压后双击，启动 1–3 秒），同时保留单文件 `VideoDownloader.exe` 作备选。
  实测（Win11 + Defender）onefile 每次启动都要解压约 1200 个文件并被杀软
  逐个扫描，约 35 秒，不适合作为主推形态
- **抖音改用系统自带的 Edge / Chrome**（`douyin.py` 的 `_BROWSER_CHANNELS`，
  依次回退 msedge → chrome → chromium → 默认）：不再要求用户下载约 150MB
  的 chromium，包体积更小；浏览器启动失败时给出普通用户可执行的中文提示
- `build.spec` 的 `CompanyName` 改为中性的 "Video Downloader"
- CI 统一改用 `requirements.txt` 安装依赖

### 新增
- `requirements.txt` / `requirements-dev.txt` 依赖声明文件
- `tests/` 单元测试（URL 抠取、平台识别、报错翻译），纯逻辑、不联网
- `.github/workflows/tests.yml`：push / PR 自动跑 pytest（Python 3.10 / 3.12）
- `.github/ISSUE_TEMPLATE/`：Bug 报告表单与联系入口
- `main.py --selftest`：冻结产物无界面自检（Playwright 驱动、tkinterdnd2
  原生库、requests、分段耗时），CI 在两种形态构建后执行，防止
  「构建成功但运行缺文件」
- Release 同时提供 zip 与单文件 exe 两种形态

### 修复
- `build.spec` 的 `excludes` 不再排除 `email` / `http` / `xml` / `html` /
  `dataclasses` / `configparser` 等标准库 —— 它们是 `requests` 的运行时依赖
  （`email.utils`、`email.parser`、`http.client`、`http.cookiejar`），排除后
  打包版「一键下载 yt-dlp/ffmpeg」与抖音/快手下载会在运行时 `ImportError`
- 移除 CI 中无效的 `playwright install chromium`（浏览器不会被打进包，
  只落在 runner 本机）
- README / Release 文案修正：onefile 的启动延迟是**每次**启动，而非仅首次

### 安全
- 重写 git 历史，彻底清除历史提交中残留的本机路径文件

## [2026.10.15] - 2026-10-15

### 新增
- PyInstaller onedir 打包配置 (`build.spec`)
- GitHub Actions 自动构建发布流水线 (`.github/workflows/build.yml`)
- 标准开源文档：`SECURITY.md`、`CONTRIBUTING.md`、`docs/ARCHITECTURE.md`
- 隐私声明（README 新增零遥测/零上报/零账号体系说明）
- 代码 docstring 专业化重写（英文 + 中文摘要）
- 配置文件 `DONATE_URL` 说明明确化（默认空、无强求、无追踪）

### 变更
- `config.py`：支持 PyInstaller frozen 模式，写入目录自动重定向到 `%LOCALAPPDATA%\VideoDownloader\`
- 移除代码中口语化/教程式注释，迁移至 `docs/ARCHITECTURE.md`

### 修复
- 解决打包后 Program Files 无写权限问题（logs、cookies、profile、tools 统一落用户数据目录）

## [2026.10.12] - 2026-10-12

### 新增
- 冒烟测试 CI (`.github/workflows/smoke.yml`)，每周一自动跑 9 平台真实下载
- `smoke_test.py` 固定公开链接测试，PASS/SKIP/FAIL 三档结果

### 变更
- 快手持久化超时归为 SKIP（非程序问题）
- 修复 CI 编码问题（`PYTHONUTF8=1`）

## [2026.10.04] - 2026-10-04

### 新增
- 初始版本：支持 10 平台（YouTube、B站、抖音、X、Instagram、快手、小红书、微博、西瓜、TikTok）
- Tkinter GUI：拖拽/剪贴板自动识别、多平台并发下载、画质选择、实时进度、取消不留损坏文件
- 代理智能分流：被墙平台自动走代理，国内平台强制直连
- 抖音原声下载 + 收藏音乐批量下载（勾选 + 断点续传）
- 抖音/快手免扫码登录（登录态本地持久化）
- 一键安装 yt-dlp/ffmpeg（官方源 + 安全闸）
- yt-dlp 每两周自动更新

---

*模板参考：https://keepachangelog.com/zh-CN/1.0.0/*