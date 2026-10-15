# 安全模型

本项目采用**零信任、最小权限、本地优先**的安全设计。以下是核心安全属性的说明。

---

## 🔒 无遥测、无上报、无账号体系

- **零网络请求到作者服务器**：代码中不存在任何 `requests.post/get` 指向项目维护者的域名。
- **零 Analytics / Crash Report / 唯一 ID 生成**：不收集使用统计、不上报崩溃、不生成设备指纹。
- **零账号系统**：无注册、无登录、无云同步。所有配置、缓存、日志均存储在本地程序目录。

---

## 📁 本地数据存储

| 数据类型 | 存储位置 | 说明 |
|----------|----------|------|
| 下载文件 | 用户自选目录（默认 `~/Downloads` 或 `Downloads`） | 完全用户可控 |
| B站 cookies | `cookies/bilibili.txt` (Netscape 格式) | 仅在用户勾选"使用登录信息"且手动导入时产生 |
| 抖音登录态 | `profile_douyin/` (Chromium 持久化 profile) | 首次扫码登录后自动生成，后续免登录复用 |
| 西瓜访客 cookie | `cookies/ixigua.txt` | 自动注册 `ttwid`，7 天过期自动刷新 |
| 应用日志 | `logs/app.log` (滚动 512KB × 2) | 仅记录程序运行信息，不含敏感数据 |
| 工具缓存 | `tools/` (yt-dlp.exe, ffmpeg.exe) | 一键安装/自更新产生，用户可随时删除 |

> **建议**：如需迁移/备份/清理，直接复制/删除上述目录即可。无隐藏注册表项、无系统级安装痕迹。

---

## 🌐 网络连接行为

### 1. 视频下载（核心功能）
- **目标**：用户提供的视频平台域名（YouTube, B站, 抖音, X, Instagram, 快手, 小红书, 微博, 西瓜, TikTok）
- **必然暴露**：你的公网 IP 给目标平台 CDN/服务器
- **缓解**：内置**代理智能分流**（见下），建议搭配代理软件使用

### 2. 代理自动探测（启动时）
- 读取 Windows 系统代理注册表设置
- TCP 探测常见本地代理端口（7897, 7890, 10809...）
- **纯本地回环连接**，无外网流量

### 3. 工具下载/更新（toolssetup.py）
| 来源 | 用途 | 频率 |
|------|------|------|
| `github.com/yt-dlp/yt-dlp/releases` | yt-dlp 单文件可执行程序 | 首次缺失 + 每两周自更新 |
| `www.gyan.dev/ffmpeg/builds/` | ffmpeg/ffprobe (zip) | 首次缺失 |

**安全闸**：
- 仅允许 HTTPS
- 域名解析必须得到**公网 IP**（拒绝私有/环回/链路本地/保留/组播/未指定地址）
- 重定向后再校验一次最终 URL
- 直连失败时**可选**走用户代理重试（不强制）

### 4. 西瓜视频访客 cookie 注册
- 目标：`ttwid.bytedance.com` (字节跳动官方接口)
- 仅获取游客标识 `ttwid`，**不关联真实身份**
- 缓存 7 天，失败静默降级

### 5. Playwright 浏览器下载（首次运行）
- `playwright install chromium` 从 Microsoft/CDN 下载 Chromium
- 仅抖音/快手模块懒加载触发

---

## 🛡️ 代理智能分流（防泄露核心）

| 平台类别 | 连接方式 | 实现 |
|----------|----------|------|
| 被墙平台 | **强制走代理** | yt-dlp `--proxy <detected>` |
| 国内平台 | **强制直连** | yt-dlp `--proxy ""` + 子进程环境变量清理 `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY` |

**防污染**：国内站若误走代理极大概率被风控/限速/连不上；被墙站不走代理根本连不上。分流在 `config.py` 探测阶段决定，`backends.py` 执行时强制生效。

---

## 📦 供应链安全（工具下载）

### 落盘安全
- 目标路径：**常量目录 + 字面量文件名**（`tools/yt-dlp.exe`, `tools/ffmpeg.exe`）
- 无动态路径拼接，无用户输入参与路径构造
- `pathlib.Path.write_bytes()` 原子写入

### Zip 解包安全
- 在内存中解包（`io.BytesIO` + `zipfile.ZipFile`）
- Zip 内条目名（不可信输入）**仅用于匹配**，绝不参与路径构造
- 只提取 `bin/ffmpeg.exe` 和 `bin/ffprobe.exe`（官方包固定结构）

### 完整性
- yt-dlp：GitHub Releases 官方单文件，无签名验证（GitHub TLS 传输信任链）
- ffmpeg：gyan.dev 官方推荐源，zip 内文件名固定匹配

---

## ⚙️ 进程隔离与取消

- **子进程编码硬化**：`PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`, `errors="replace"` 防止编码注入类异常
- **进程树级取消**：`taskkill /F /T` 杀掉 yt-dlp + ffmpeg 全树，取消不留半个损坏文件
- **无 shell 注入**：`subprocess.Popen(argv, shell=False)`，参数列表形式传递

---

## 🧪 冒烟测试（CI 安全）

- GitHub Actions `windows-latest` runner（微软托管，临时环境）
- 每周一自动跑 9 平台真实下载
- **无 secrets**，无敏感环境变量
- 测试链接为公开内容，下载后立即删除临时目录

---

## ✅ 合规清单

- [x] 无用户数据收集
- [x] 无第三方追踪器
- [x] 无自动更新可执行代码（仅 yt-dlp 官方单文件，可禁用）
- [x] 无远程代码执行向量
- [x] 无路径穿越风险
- [x] 无 SSRF 风险（公网 IP 校验）
- [x] 无 shell 注入
- [x] 敏感本地数据（cookies/profile）用户可控、可删、可迁移

---

## 📢 给用户的建议

1. **使用代理**：下载被墙平台内容时，确保代理软件（Clash/V2Ray 等）已启动并正确分流。
2. **保护 cookies**：`cookies/bilibili.txt` 包含 `SESSDATA` 等敏感字段，**请勿分享/上传**。
3. **物理隔离**：`profile_douyin/` 存储抖音登录态，如电脑共用，建议使用独立用户账号或定期清理。
4. **验证下载**：工具从官方源下载 yt-dlp/ffmpeg，若极度在意供应链，可手动安装并加入 PATH，程序会优先使用系统版本。

---

## 📧 安全问题报告

如发现安全问题，请通过 GitHub Issues（标记 `security`）或私信维护者报告。不提供赏金，但会致谢并尽快修复。

---

*本文档随代码版本同步更新。最后更新：2026-10*