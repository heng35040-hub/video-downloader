# 更新日志

所有重要变更记录在此。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)（采用日期格式 YYYY.MM.DD）。

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