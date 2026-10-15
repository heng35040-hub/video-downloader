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

# Data files to include: (source, destination_in_package)
datas = [
    (os.path.join(PROJECT_ROOT, "cookies"), "cookies"),
    (os.path.join(PROJECT_ROOT, "docs"), "docs"),
    (os.path.join(PROJECT_ROOT, "README.md"), "."),
    (os.path.join(PROJECT_ROOT, "LICENSE"), "."),
    (os.path.join(PROJECT_ROOT, "SECURITY.md"), "."),
]

# Binary files: (source, destination)
binaries = []

# Exclude unnecessary modules to reduce size
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
    "test",
    "unittest",
    "pydoc",
    "doctest",
    "argparse",
    "html",
    "http",
    "email",
    "xml",
    "sqlite3",
    "csv",
    "configparser",
    "fractions",
    "decimal",
    "numbers",
    # "typing",  # Required by inspect
    "dataclasses",
    # "enum",  # Required by re/ast/inspect
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
                        versioninfo.StringStruct("CompanyName", "heng35040-hub"),
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

# Onedir build (faster startup, better AV compatibility) - for distribution
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