# -*- coding: utf-8 -*-
# PyInstaller spec file for Video Downloader
# Build: pyinstaller --clean build.spec

import os
import sys
from PyInstaller.utils.win32 import versioninfo

# Get the project root directory (spec file location)
PROJECT_ROOT = os.getcwd()

# Hidden imports for packages that PyInstaller might miss
hiddenimports = [
    "tkinter",
    "tkinter.ttk",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinterdnd2",
    "tkinterdnd2.TkinterDnD",
    "requests",
    "playwright",
    "playwright.sync_api",
    # PySocks —— requests / yt-dlp 的 SOCKS 代理支持靠它。**必须显式列出**：
    # requests 是在函数里 `import socks`（延迟导入），PyInstaller 的静态分析
    # 不跟，漏打包的后果是填 socks5:// 代理时报
    # "Missing dependencies for SOCKS support"。
    "socks",
    "sockshandler",
    # 内置的 yt-dlp。yt_dlp 自带官方 PyInstaller hook
    # （entry point pyinstaller40 → yt_dlp.__pyinstaller），显式列出来
    # 是为了确保 hook 一定触发，把 1000+ 个 extractor 子模块收全。
    "yt_dlp",
    "json",
    "re",
    "os",
    "sys",
    "threading",
    "queue",
    "logging",
    "logging.handlers",
    "traceback",
    "datetime",
    "pathlib",
    "subprocess",
    "tempfile",
    "uuid",
    "ipaddress",
    "socket",
    "zipfile",
    "io",
    "contextlib",
    "urllib.parse",
    "shutil",
    "ctypes",
    "ctypes.wintypes",
]

# ---- Playwright ----
# Playwright **自带** PyInstaller hook（通过 entry point `pyinstaller40` 注册，
# 内容就是 collect_data_files("playwright")）。只要静态分析能扫到
# `playwright.sync_api` 的导入（douyin.py 里是函数内懒导入，照样能扫到），
# playwright/driver（node.exe + JS 实现，约 100MB）就会自动进包，
# 冻结后 sync_playwright() 才能正常拉起驱动。
#
# 所以这里不需要再手写 collect_all —— 重复收集只会让归档多一份无用条目。
# 早期版本误以为没有官方 hook 而手动收集过，已移除。
#
# 注意：进包的只有「驱动」，不含浏览器本体。抖音默认直接用系统自带的
# Edge/Chrome（见 douyin.py 的 _BROWSER_CHANNELS），无需下载约 150MB 的 chromium。

# Data files to include: (source, destination_in_package)
# Cookies are user data and must never be bundled; config.py stores them in
# LOCALAPPDATA when frozen. Do not add the ignored local cookies/ directory.
datas = [
    (os.path.join(PROJECT_ROOT, "docs"), "docs"),
    (os.path.join(PROJECT_ROOT, "README.md"), "."),
    (os.path.join(PROJECT_ROOT, "LICENSE"), "."),
    (os.path.join(PROJECT_ROOT, "SECURITY.md"), "."),
]

# Binary files: (source, destination)
binaries = []

# Exclude unnecessary modules to reduce size
#
# 只排除确定用不到的重型第三方库。**不要**在这里排标准库：
# 早先排掉 email / http / xml / html 会把 requests 一起搞挂（requests 依赖
# email.utils、email.parser、http.client、http.cookiejar），症状是打包后
# 「一键下载 yt-dlp/ffmpeg」与抖音/快手下载在运行时 ImportError。
excludes = [
    "matplotlib",
    "numpy",
    "pandas",
    "scipy",
    "PIL",
    "cv2",
    "torch",
    "tensorflow",
    "jupyter",
    "notebook",
    "IPython",
    "pytest",
    "test",
    "unittest",
    "pydoc",
    "doctest",
    # ⚠️ 必须排除：sitecustomize / usercustomize 是「谁的环境谁注入」的钩子模块。
    # 如果打包机的 PYTHONPATH 里恰好有一个（例如各种 CLI 工具链、IDE、沙箱
    # 会往 PYTHONPATH 塞 sitecustomize.py 来打补丁），PyInstaller 的模块图会
    # 顺着它把那份**外部代码**一起打进 exe —— 实测踩过一次：exe 里混进了
    # 某桌面客户端的「安全删除 shim」（会 monkey-patch os.remove / shutil.rmtree），
    # 还带出了 CODEBUDDY_SESSION_ID、沙箱 IPC 地址等内部标识。
    # 用户机器上不需要任何 site 定制，直接排除最干净。
    "sitecustomize",
    "usercustomize",
]

# Main script
main_script = os.path.join(PROJECT_ROOT, "main.py")

# Icon (optional)
icon_path = None

# Version info for Windows
# ⚠️ 每次发版都要同步更新这里（外加 CHANGELOG 和 tag 名），
#    否则 exe 属性里显示的「文件版本」会和实际发布版本对不上。
#    曾经就因为漏改，v2026.10.16 的 exe 里嵌的还是 2026.10.15.0。
ver_info = versioninfo.VSVersionInfo(
    ffi=versioninfo.FixedFileInfo(
        filevers=(2026, 10, 18, 4),
        prodvers=(2026, 10, 18, 4),
        mask=0x3F,
        flags=0,
        OS=0x40004,
        fileType=0x1,
        subtype=0,
        date=(0, 0),
    ),
    kids=[
        versioninfo.StringFileInfo(
            [
                versioninfo.StringTable(
                    "040904B0",
                    [
                        versioninfo.StringStruct("CompanyName", "Video Downloader"),
                        versioninfo.StringStruct("FileDescription", "Video Downloader"),
                        versioninfo.StringStruct("FileVersion", "2026.10.18.4"),
                        versioninfo.StringStruct("InternalName", "VideoDownloader"),
                        versioninfo.StringStruct("LegalCopyright", "MIT License"),
                        versioninfo.StringStruct("OriginalFilename", "VideoDownloader.exe"),
                        versioninfo.StringStruct("ProductName", "Video Downloader"),
                        versioninfo.StringStruct("ProductVersion", "2026.10.18.4"),
                    ],
                ),
            ],
        ),
        versioninfo.VarFileInfo([versioninfo.VarStruct("Translation", [1033, 1200])]),
    ],
)

block_cipher = None

a = Analysis(
    [main_script],
    pathex=[PROJECT_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Filter out unnecessary files
a.datas = [x for x in a.datas if not x[0].endswith(".pyc")]
a.binaries = [x for x in a.binaries if not x[0].endswith(".pdb")]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ---------------------------------------------------------------------------
# 单文件模式（onefile）：产物是 dist/VideoDownloader.exe 一个文件，双击即用，
# 不需要解压、不需要找文件夹 —— 这是面向用户的唯一发布形态。
#
# 关键点：spec 里**不能**出现 COLLECT。PyInstaller 见到 COLLECT 就会切到
# onedir（产出一整个文件夹），新手下载后还得自己找 exe。
#
# 代价：引导程序每次启动都要把包内约 1200 个文件解压到临时目录。本机实测
# （Win11 + Defender）全新构建后连跑 5 次，启动稳定在 4.0–4.6 秒，其中
# 解压约 1.8 秒、模块导入约 0.03 秒；对照 onedir 约 1.2 秒。
#
# 注意：曾经观测到每次启动约 35 秒，事后确认是**环境性的**（那段时间网络
# 不稳，Defender 云查杀卡住每次启动），并非 onefile 的固有代价，已复测排除。
# 如果将来有用户反馈启动异常慢，多半也是杀软/网络，而不是包本身。
# ---------------------------------------------------------------------------
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="VideoDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
    version=ver_info,
)

