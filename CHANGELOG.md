# 更新日志

所有重要变更记录在此。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)（采用日期格式 YYYY.MM.DD）。

## [未发布]

### 安全/卫生
- `.gitignore` 补 `*.exe` 通配：防止构建产物被误拷贝进仓库根目录时被
  `git add .` 跟踪（`tools/` 只兜得住运行时下载目录）
- build.spec 注释去掉构建环境产品名，只保留通用表述

## [2026.10.18.4] - 2026-10-18

### 新增
- **界面加了「代理」一栏和「测试」按钮**：留空 = 自动探测（原有逻辑不变），
  也可以手填 `http://` / `socks5h://`（支持 `user:pass@`）。自建 VPS 上跑的
  v2ray / xray / ss-local 大多是 SOCKS、端口也不标准，探测不出来，只能让用户
  自己写。填的值记进 settings.json，重启仍在
- 「测试」不只做 TCP 连通，还会真发一次请求到 x.com 验证能不能翻墙 ——
  端口可能被别的服务占着（比如 8080 上跑的本地网页服务器），TCP 通但代理
  用不了，只探端口会误判

### 修复
- **完全不支持 SOCKS5**：requests 的 SOCKS 支持依赖 PySocks，而它既没在
  requirements.txt 里声明、也没被打包，填 `socks5://` 只会得到
  `Missing dependencies for SOCKS support`。现在加进了两端，并在
  build.spec 的 hiddenimports 里显式列出（requests 是函数内延迟导入
  `socks`，PyInstaller 的静态分析不跟）
- 系统代理只解析 `http=`，`socks=` 被丢掉（`ProxyServer` 形如
  `http=127.0.0.1:7890;https=…;socks=…`）。现在两种都认，http 优先
- `socks5://` 统一改写为 `socks5h://` —— 被墙域名必须让代理解析 DNS，
  本地解析不了
- 端口 1080 原来被当 HTTP 端口探测。1080 业内默认是 SOCKS，硬当 HTTP 会把
  SOCKS 端口当 HTTP 用、报错还难查。现在 SOCKS 常见端口靠**握手**认协议
- 代理相关的错误提示还写着「端口不同可在 config.py 里改」—— 用户装的是
  exe，改不了源码。现在指向界面
- 「连不上代理」提示现在显示**实际使用的代理地址**（用户手填时显示手填的，
  不再显示启动时探测到的那个）；预检提示也不再写死「请先启动 Clash」
- 新增 `tests/test_proxy.py`：23 项守住代理解析、ProxyServer 拆分，以及
  「用户填的代理真的传给了 yt-dlp」（下载和探测两条路径），总测试 111 → 136

## [2026.10.18.3] - 2026-10-18

### 修复
- **画质下拉框里的「（需登录）」标注是错的，已移除**：上一版按「B站 1080P 起
  要登录」的常识给 1080P 加了后缀，实测不成立 —— 未登录直接用
  `bv*[height<=1080]+ba` 能把 1080P 完整下完（yt-dlp 会把 1080P 直链给游客，
  实测 15.3 MB 视频轨 + 5.2 MB 音轨合并成功）。标错了比不标更误导，现在只列
  **实测可用**的画质，不猜
- **探测失败时静默回退成固定档位，看起来像真实画质**：某条视频 yt-dlp 报
  「可能已删除或地区限制」，界面却照样显示 1080p/720p/480p，用户自然以为能下。
  现在把失败原因翻译成中文显示在状态栏（如「读不到画质列表：视频可能已删除，
  或仅限特定地区观看。」），固定档位只作兜底、不再冒充真实数据
- `backends.probe_heights` 改为 `probe_formats`，返回 `(heights, error)`，
  错误经 `errors.friendly()` 翻译；新增 `_short_err` 把 yt-dlp 的 stderr
  压成一句能放进状态栏的话
- `_short_err` 的边界 bug：空 stderr 时 `b"" or ""` 会得到 `str`，再调
  `.decode()` 抛 AttributeError
- `errors.friendly()` 补 B站「已删除 / 地区限制」的中文翻译
- `tests/test_quality.py` 改为守住「不出现需登录后缀」+ `_short_err` 行为，
  总测试 108 → 111

## [2026.10.18.2] - 2026-10-18

### 新增
- **「登录 B站」按钮**：点一下弹出浏览器，扫码后自动把登录态写成
  `cookies/bilibili.txt` —— 不用再装浏览器扩展、导出文件、找路径。登录态同时
  留在 `profile_bili`，下次免登录；成功后自动勾上「B站使用登录信息」
- **画质下拉框改为按视频实际支持的画质动态生成**：链接输入后（防抖 800ms）
  在后台跑 `yt-dlp -J` 读出这条视频的格式列表，去重后按高度从高到低填充。
  探测失败、或抖音/快手这类没有格式列表的平台，回退到原来的固定列表
- B站未登录时，1080P 及以上的选项标「（需登录）」；登录后自动去掉标注

### 修复
- **提示「请先点【导入 B站登录】」，但界面上从来没有那个按钮**：这条文案在
  `errors.py` 里挂了很久，等于把用户指向空气。现在真的有这个入口了
- `backends._base_args` 里 `--cookies` 只判了 `use_cookies`、没判平台 ——
  勾选后会给微博/小红书/西瓜等国内站也塞 B站 的 cookies 文件。现在限定
  `source == "bilibili"` 才传
- 新增 `bililogin.py` 与 21 项测试（Netscape 格式、登录判定、画质标签规则），
  总测试 87 → 108

### 变更
- B站 cookies 勾选文案改为「B站使用登录信息（可解锁 1080P 及以上）」

## [2026.10.18.1] - 2026-10-18

### 修复
界面状态字段的一轮清理（下载完成后状态栏显示错乱）。

- **下载完成后状态栏仍停在「拿到直链，开始下载…」**：旧实现只在 `ok` 事件里
  更新进度条下方那行详情，状态栏不动；收尾时又靠
  `status_var.get().startswith("[")` 猜「任务是不是还没开始」，只要后端中途
  改过状态（抖音会发「拿到直链，开始下载…」）这个判断就失效，于是那句话一直
  留在界面上。现在改成按本轮**成败计数**算收尾文案（新增纯函数
  `_summary_status`），并在成功/失败时立即更新状态栏
- **成功后进度条掉回 0%**：原来 `finished` 里无条件 `_set_progress(0.0)`，
  下载成功也显示 0%，看着像没下成。现在全成功时停在 100%
- **失败后状态栏也不更新**：只弹了错误框，状态栏还挂着「正在获取直链…」，
  关掉框后看着像还在跑。现在立即改成「下载失败」
- **取消被当成失败**：`failed("已取消")` 会计入失败数、详情写成「失败：已取消」。
  现在取消单独处理 —— 不计失败、详情写「已取消」、格子恢复原色、状态栏显示
  「已取消（本轮完成 N 个）」
- **新任务开始不清残留**：上一轮的「完成：xxx.mp4」和 100% 进度条会留到新任务，
  现在 `_start` 里统一重置状态栏、详情、进度与成败计数
- **下载中点「清空」会清掉界面但后台任务照跑**：现在提示「先点取消再清空」
  并忽略这次点击
- 格子事件里传了 `text="下载中…"` 但 `_apply` 从未使用（死参数），已移除；
  格子状态统一由底色表达（新增 `PANE_DONE` / `PANE_FAIL` 常量）
- `tests/test_status.py`：14 项测试守住收尾文案，总测试 73 → 87

## [2026.10.18] - 2026-10-18

### 修复
- **抖音全部下载失败（提示「没能从页面里抓到视频流」）**：抖音的 CDN 已改为
  对视频/音频走 HTTP Range 分段请求，返回 **206 Partial Content**；而抓流的
  回调只认 200，把所有流都过滤掉了 —— 页面明明在正常播放，程序却一个流都
  抓不到，还把它误报成「登录墙」。现在同时接受 200 与 206
  （视频、音乐、收藏音乐三处抓流回调都改）
- 分段响应的 `content-length` 只是本次分段的长度（可能只有几十 KB），拿它
  排序会选错流；改为读 `Content-Range` 末尾的**文件总长**
- **扫码登录成功后界面提示不变、看起来像卡死**：抖音是 SPA，扫码登录后页面
  不会自己重载，原逻辑只是干等视频流，所以那句「请扫码登录」会一直挂到超时
  （180 秒）才结束。现在：
  - 有头窗口里每 1.5 秒检查一次登录态，一旦登录立刻改提示并**重载页面**
  - 增加定期刷新兜底（每 15 秒）：Edge 新版对登录 cookie 做了 App-Bound
    加密，外部进程可能读不到，靠刷新也能在登录后自动接上
  - 无头那一轮的等待从 30 秒缩短到 15 秒（页面能播时 4 秒内就出流），
    新用户不用干等
- `tests/test_douyin.py`：12 项回归测试守住 206 判定与体积解析，总测试 61 → 73

## [2026.10.16] - 2026-10-16

> 首个正式发布版本。此前的 2026.10.04 / 10.12 / 10.15 均为未发布的开发版本。

### 新增
- **首次启动的「使用须知」勾选**：首次运行（以及须知正文改版后）弹出免责
  声明窗口，必须勾选「我已阅读并同意上述全部条款」才能进入主界面；关窗视为
  不同意，程序直接退出。同意状态连同**版本号**一起记在 `settings.json`
  （`config.DISCLAIMER_VERSION`），正文一改版本号跟着变，老用户会重新看到
  并重新确认 —— 这是「已尽告知义务」最直接的证据，也是 README 免责声明的
  界面化落地
- **创建桌面快捷方式**：界面左下角按钮 + 使用须知页勾选（默认勾选，与市面
  安装向导一致）两个入口，一键在桌面生成 `视频下载器.lnk`
  - 打包后指向 exe 自己；源码运行时指向 `pythonw.exe` + `main.py`
  - 已存在同名快捷方式时**先询问**是否覆盖，不擅自改动用户的图标与命名
  - 从须知页勾选则同意后后台静默创建，失败只记日志、不弹框（首次启动就报错
    很吓人），主界面左下角的同名按钮可随时重试
  - 实现走 PowerShell 的 `WScript.Shell`（Windows 上建 `.lnk` 唯一的免依赖
    方式），参数经 `VD_LNK_*` 环境变量传入，结果写 UTF-8 临时文件再读回
- **yt-dlp 改为内置**：不再依赖首次启动从 GitHub 下载。国内直连 GitHub 的
  可达性不稳定，而只用 B站/抖音等国内平台、不开代理的用户一旦下载失败，
  B站 这类主平台也直接用不了。现在 yt-dlp 作为普通依赖打包进程序，
  开箱即用、首次启动**不需要联网下载**（包体积 51.2 → 57.8 MB）；
  首次启动现在只需要下载 ffmpeg
- **抖音原声下载**：音乐页链接直接存 mp3；支持批量下载「收藏 → 音乐」，
  下载前可勾选
- **抖音/快手免扫码**：登录一次长期有效（登录态保存在本地，不上传任何地方）
- **画质选择**：最高 / 1080p / 720p / 480p，对 yt-dlp 系平台生效；
  平台上没有达标清晰度时自动取最优，不报错
- **代理智能分流**：被墙平台（YouTube / X / Instagram / TikTok）自动走
  本机代理，国内平台强制直连
- **实时进度与取消**：进度条 + 已下载体积，随时取消不留半个损坏文件
- **拖拽 / 剪贴板自动识别**：复制链接后切回窗口即自动填入对应平台格子
- `main.py --selftest`：冻结产物无界面自检（Playwright 驱动、tkinterdnd2
  原生库、requests、**内置 yt-dlp 可执行**——真实跑一次
  `--ytdlp-cli --version`，并给出「引导程序解压 / 模块导入 / 自检内部」
  分段耗时），CI 在构建后执行，防止「构建成功但运行缺文件」；
  用户反馈启动慢时也靠它定位
- `requirements.txt` / `requirements-dev.txt` 依赖声明文件
- `tests/` 单元测试 61 项（URL 抠取、平台识别、报错翻译、内置 yt-dlp 的
  命令行解析、使用须知状态读写、快捷方式目标解析），纯逻辑、不联网
- `.github/workflows/tests.yml`：push / PR 自动跑 pytest（Python 3.10 / 3.12）
- `.github/ISSUE_TEMPLATE/`：Bug 报告表单与联系入口

### 变更
- `config.YTDLP_CMD` 改为**命令行列表**，优先级：
  `tools\yt-dlp.exe` → 内置 `yt_dlp` 模块 → PATH；冻结时内置那份的调用方式是
  `[本 exe, "--ytdlp-cli", ...]`，由 `main.py` 顶部提前分发 —— 复用原有的
  「子进程 + 逐行读 stdout + 杀进程树取消」机制，`backends.py` 一行逻辑没改
- 移除代码中的机器特定路径（本机 Python 安装目录、素材盘等），统一改为
  `tools/` 目录 → PATH → `~/Downloads` 的解析顺序，任何机器开箱即用
- 移除仓库内的收款二维码图片；打赏入口改为接入爱发电主页
  （`config.py` 的 `DONATE_URL = https://afdian.com/a/anodev`），
  README 的「支持作者」段落同步给出链接
- **保持单文件发布形态（onefile）**：`dist/VideoDownloader.exe` 双击即用、
  无需解压。全新构建后连跑实测启动稳定在 3–5 秒（引导程序解压 1.2–1.8 秒、
  模块导入 0.03 秒）。期间曾观测到每次启动约 35 秒，复测确认是**环境性的**
  （那段时间网络不稳，Defender 云查杀卡住每次启动），并非 onefile 的固有代价，
  因此不做形态改动
- **抖音改用系统自带的 Edge / Chrome**（`douyin.py` 的 `_BROWSER_CHANNELS`，
  依次回退 msedge → chrome → chromium → 默认）：不再要求用户下载约 150MB
  的 chromium，包体积更小；浏览器启动失败时给出普通用户可执行的中文提示
- `build.spec` 的 `CompanyName` 改为中性的 "Video Downloader"
- CI 统一改用 `requirements.txt` 安装依赖
- `.gitignore` 补 `settings.json` / `settings.json.tmp`：源码运行时
  `USER_DATA_DIR` 就是仓库根目录，同意状态会落在那里，不能进仓库

### 修复
- **ffmpeg 一键下载加入多源自动切换**：原先只用 gyan.dev 一个源，实测
  （2026-10）它直连只有 **34–49 KB/s**，而包有 109 MB —— 用户要干等约
  50 分钟；而且它是「慢而不失败」，原来的「直连失败才走代理」回退永远不会
  触发。现在按顺序试多个源，并加了**慢源探测**（20 秒内平均速度低于
  200 KB/s 就换源），gyan.dev 慢时自动切到 GitHub 上的 BtbN/FFmpeg-Builds。
  实测同一台机器：**50 分钟 → 38.5 秒**
- **启动提速两处**（内置 yt-dlp 之后顺手清理的）：
  - `config` 不再为了「看一眼内置模块在不在」就 `import yt_dlp`
    （1000+ 个 extractor 子模块，约 350 ms），改用 `importlib.util.find_spec`
    探测，并保留真导入兜底
  - 代理端口探测由**串行改并发**：一个代理都没开时原先要等 7 × 150 ms，
    新用户（干净机器、没装代理）每次启动都白等；并发后最坏约等于单个超时
- `build.spec` 的 `excludes` 不再排除 `email` / `http` / `xml` / `html` /
  `dataclasses` / `configparser` 等标准库 —— 它们是 `requests` 的运行时依赖
  （`email.utils`、`email.parser`、`http.client`、`http.cookiejar`），排除后
  打包版下载功能会在运行时 `ImportError`
- `config.FFMPEG_DIR` 改为独立解析：原先靠「yt-dlp 所在目录」顺带找到 ffmpeg，
  yt-dlp 换成内置模块后这条链断了（会指向解释器目录），现在按
  `tools\` → yt-dlp 同目录 → PATH 依次找，并把 PATH 里的 ffmpeg 解析成具体目录
- `build.spec` 移除多余的 `collect_all("playwright")`：Playwright **自带**
  官方 PyInstaller hook（entry point `pyinstaller40`，内容即
  `collect_data_files("playwright")`），已会自动收集 node 驱动；
  重复收集只让归档多出 77 个冗余条目
- 移除 CI 中无效的 `playwright install chromium`（浏览器不会被打进包，
  只落在 runner 本机）
- README / Release 文案修正：onefile 的启动延迟是**每次**启动，而非仅首次

### 安全
- **`build.spec` 的 `excludes` 增加 `sitecustomize` / `usercustomize`**：
  这两个是「谁的环境谁注入」的钩子模块，打包机 `PYTHONPATH` 里若恰好有一个，
  PyInstaller 的模块图会顺着它把**外部代码**一起打进 exe。
  本地打包时实测踩中过一次：exe 里混进了某桌面客户端的「安全删除 shim」
  （会 monkey-patch `os.remove` / `shutil.rmtree`），并带出内部会话标识
  与沙箱 IPC 地址。GitHub Actions 的干净 runner 不受影响，仅本地打包会中招，
  现已从打包配置层面根除（同时本地打包需清空 `PYTHONPATH`）
- **桌面快捷方式改用环境变量传参**，去掉 `-EncodedCommand`（UTF-16LE + base64）：
  脚本本体保持纯 ASCII，参数经 `VD_LNK_*` 环境变量传入（Windows 环境变量是
  Unicode，中文没问题）。base64 命令行是恶意软件的常见混淆手法，容易拉高杀软
  的启发式评分 —— 本程序未签名，经不起再加一层可疑特征。另加了一道保险丝：
  脚本若混入非 ASCII 字符直接抛错
- **`tests.yml` 补装 `yt-dlp`**：`TestBundledYtdlp` 断言 `import yt_dlp` 可用，
  而该工作流原先只装 pytest，干净 runner 上 4 项必红（已用干净环境模拟 runner
  复现：`4 failed, 57 passed`）。yt-dlp 仅约 3 MB，不违背「不装
  requests/playwright」的初衷
- 重写 git 历史，彻底清除历史提交中残留的本机路径文件与收款二维码图片

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
- 初始开发版本：支持 10 平台（YouTube、B站、抖音、X、Instagram、快手、小红书、微博、西瓜、TikTok）
- Tkinter GUI：拖拽/剪贴板自动识别、多平台并发下载、画质选择、实时进度、取消不留损坏文件
- 代理智能分流：被墙平台自动走代理，国内平台强制直连
- 抖音原声下载 + 收藏音乐批量下载（勾选 + 断点续传）
- 抖音/快手免扫码登录（登录态本地持久化）
- 一键安装 yt-dlp/ffmpeg（官方源 + 安全闸）
- yt-dlp 每两周自动更新

---

*模板参考：https://keepachangelog.com/zh-CN/1.0.0/*
