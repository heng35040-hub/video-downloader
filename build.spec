# -*- coding: utf-8 -*-
# PyInstaller spec file for Video Downloader
# Build: pyinstaller --clean build.spec

import os
import sys
from PyInstaller.utils.hooks import collect_all
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
# Playwright 没有官方 PyInstaller hook（pyinstaller-hooks-contrib 里没有它，
# 只有 tkinterdnd2 有），不手动收集的话冻结后 sync_playwright() 会报
# "Driver not found"。collect_all 会把 playwright/driver（node.exe + JS 实现，
# 约 100MB）一并收进来。
#
# 注意：这里只收 Playwright 的「驱动」，不收浏览器本体。抖音默认直接用系统
# 自带的 Edge/Chrome（见 douyin.py 的 _BROWSER_CHANNELS），所以不需要额外
# 下载约 150MB 的 chromium。
_pw_datas, _pw_binaries, _pw_hiddenimports = collect_all("playwright")

# Data files to include: (source, destination_in_package)
# Cookies are user data and must never be bundled; config.py stores them in
# LOCALAPPDATA when frozen. Do not add the ignored local cookies/ directory.
datas = [
    (os.path.join(PROJECT_ROOT, "docs"), "docs"),
    (os.path.join(PROJECT_ROOT, "README.md"), "."),
    (os.path.join(PROJECT_ROOT, "LICENSE"), "."),
    (os.path.join(PROJECT_ROOT, "SECURITY.md"), "."),
] + _pw_datas

# Binary files: (source, destination)
binaries = list(_pw_binaries)

hiddenimports += _pw_hiddenimports

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
]

# Main script
main_script = os.path.join(PROJECT_ROOT, "main.py")

# Icon (optional)
icon_path = None

# Version info for Windows
ver_info = versioninfo.VSVersionInfo(
    ffi=versioninfo.FixedFileInfo(
        filevers=(2026, 10, 15, 0),
        prodvers=(2026, 10, 15, 0),
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
                        versioninfo.StringStruct("FileVersion", "2026.10.15.0"),
                        versioninfo.StringStruct("InternalName", "VideoDownloader"),
                        versioninfo.StringStruct("LegalCopyright", "MIT License"),
                        versioninfo.StringStruct("OriginalFilename", "VideoDownloader.exe"),
                        versioninfo.StringStruct("ProductName", "Video Downloader"),
                        versioninfo.StringStruct("ProductVersion", "2026.10.15.0"),
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
# 打包形态由环境变量 VD_BUILD_MODE 决定（默认 onefile）
#
#   VD_BUILD_MODE=onefile  -> dist/VideoDownloader.exe               单一文件
#   VD_BUILD_MODE=onedir   -> dist/VideoDownloader/VideoDownloader.exe  文件夹
#
# 为什么两种都要有（本机实测，Windows 11 + Defender 实时防护开启）：
#   - onefile 每次启动都要把包内约 1200 个文件解压到临时目录，并被杀软
#     逐个扫描，实测启动约 35 秒（对比极简 onefile 基线 2.3 秒）；
#   - onedir 只需解压一次，启动 1–3 秒。
#   所以 Release 以 onedir 的 zip 为主推，单文件 exe 作为「不想解压」的备选。
#
# 用法：
#   pyinstaller --clean build.spec                      # 单文件
#   set VD_BUILD_MODE=onedir && pyinstaller --clean build.spec
# ---------------------------------------------------------------------------
MODE = os.environ.get("VD_BUILD_MODE", "onefile").strip().lower()
if MODE not in ("onefile", "onedir"):
    raise SystemExit(f"未知的 VD_BUILD_MODE: {MODE!r}（只支持 onefile / onedir）")

_exe_kwargs = dict(
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

if MODE == "onedir":
    # 注意：onedir 必须有 COLLECT；exclude_binaries=True 让依赖交给 COLLECT 收。
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **_exe_kwargs)
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="VideoDownloader",
    )
else:
    # onefile：这里绝不能出现 COLLECT，否则会退回 onedir。
    exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
              **_exe_kwargs)

