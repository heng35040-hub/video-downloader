# -*- coding: utf-8 -*-
"""视频下载器 —— Tkinter GUI 界面。

Threading contract: all blocking work runs in a worker thread.
Worker only posts events to a queue; it never touches widgets or StringVars
(Tkinter is not thread-safe — violations cause random deadlocks, not crashes).
"""
import os
import sys
import time

# ---------------------------------------------------------------------------
# 启动耗时锚点（仅 --selftest 使用，正常运行时无副作用）。
# _MEIPASS 的创建时刻 ≈ 引导程序解压完成时刻，用它把「引导程序解压」
# 和「模块导入」分开报告，方便定位打包后启动慢到底慢在哪一段。
# ---------------------------------------------------------------------------
_T_BOOT = time.time()
_T_MEIPASS_CTIME = (os.path.getctime(sys._MEIPASS)
                    if getattr(sys, "_MEIPASS", None) else None)


# ---------------------------------------------------------------------------
# 内置 yt-dlp 的入口。
#
# backends.py 不再依赖外部的 yt-dlp.exe，而是执行
#   [sys.executable, "--ytdlp-cli", <原样的 yt-dlp 参数...>]
# 也就是「让本程序把自己当成 yt-dlp 命令行再跑一遍」。这样
# 「子进程 + 逐行读 stdout + 杀进程树取消」这套现成机制可以原样复用，
# 一行都不用改。
#
# 必须放在所有重活之前（tkinter、日志、建目录），否则每次下载都白等一截。
# 注意冻结后 console=False，但父进程用管道拉起时 stdout 依然可写
# （procutil.build_env 已经给子进程设了 PYTHONUTF8=1，输出是 UTF-8）。
# ---------------------------------------------------------------------------
def _run_ytdlp_cli(argv):
    if sys.stdout is None:          # 从资源管理器直接双击时没有控制台
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    from yt_dlp import main as ytdlp_main
    try:
        return ytdlp_main(argv) or 0
    except SystemExit as exc:       # yt-dlp 内部用 sys.exit 表达退出码
        return exc.code if isinstance(exc.code, int) else 0


if "--ytdlp-cli" in sys.argv:
    sys.exit(_run_ytdlp_cli(sys.argv[sys.argv.index("--ytdlp-cli") + 1:]))

import datetime
import logging
import queue
import threading
import traceback
from logging.handlers import RotatingFileHandler

# ---------------------------------------------------------------------------
# pythonw.exe 下 sys.stdout / sys.stderr 是 None（不是空流！），
# 任何 print 或任何往 stdout 写日志的库都会抛 AttributeError 直接猝死。
# 必须放在所有其他 import 之前接住。
# ---------------------------------------------------------------------------
import config

os.makedirs(config.LOG_DIR, exist_ok=True)

_log_handle = open(config.LOG_FILE, "a", encoding="utf-8", buffering=1)


class _StreamToLog:
    def write(self, text):
        if text:
            _log_handle.write(text)

    def flush(self):
        try:
            _log_handle.flush()
        except Exception:
            pass


if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = _StreamToLog()

import tkinter as tk                      # noqa: E402
from tkinter import filedialog, messagebox, ttk   # noqa: E402

try:
    from tkinterdnd2 import DND_FILES, DND_TEXT, TkinterDnD
    DND_AVAILABLE = True
except Exception:                          # 装不上也要能用，退回纯粘贴模式
    DND_AVAILABLE = False

import backends                            # noqa: E402
import errors                              # noqa: E402
import updater                             # noqa: E402

PANE_IDLE = "#f2f2f2"
PANE_ACTIVE = "#d6e9ff"
PANE_DROP = "#bcdcf5"
PANE_FILLED_BORDER = "#2f7fd0"
PANE_DONE = "#d8f5d8"        # 该平台本轮下载成功
PANE_FAIL = "#ffd9d9"        # 该平台本轮下载失败

# 能探测「实际支持哪些画质」的平台：都走 yt-dlp，能列出格式。
# 抖音/快手是自研解析（抖音直接抓 CDN 流、快手纯 requests），没有格式列表，
# 画质下拉框对它们也没意义（下载逻辑压根不看这个值）。
_PROBE_SOURCES = tuple(s for s in config.SOURCES
                       if s not in ("douyin", "kuaishou"))


def _setup_logging():
    handler = RotatingFileHandler(config.LOG_FILE, maxBytes=512 * 1024,
                                  backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def _enable_dpi_awareness():
    """建根窗口之前调用，否则 Windows 会把窗口位图拉伸，字发虚。"""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)  # per-monitor v2
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def _fix_scaling(root):
    """DPI 感知打开之后 Tk 的字号缩放会不对（125%/150% 屏上字变小），补回来。"""
    try:
        root.tk.call("tk", "scaling", root.winfo_fpixels("1i") / 72.0)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 使用须知
#
# 首次启动（以及须知正文改版后）必须勾选同意才能进入主界面 —— 这是「已尽
# 告知义务」最直接的证据，也是 README 免责声明的界面化落地。
# 同意状态记在 settings.json 里，连同版本号一起存：正文一改，版本号跟着变，
# 老用户会重新看到弹窗。
# ---------------------------------------------------------------------------
def _load_settings():
    """读 settings.json；读不了或内容不是 dict 就返回空 dict。"""
    import json
    try:
        with open(config.SETTINGS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _save_settings(data):
    """整体写回 settings.json。先写临时文件再原子替换，避免写一半写坏。"""
    import json
    try:
        os.makedirs(os.path.dirname(config.SETTINGS_FILE), exist_ok=True)
        tmp = config.SETTINGS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, config.SETTINGS_FILE)
    except Exception:
        logging.exception("写入设置文件失败")


def _disclaimer_accepted():
    """当前版本的使用须知是否已被同意过。"""
    return (_load_settings().get("disclaimer_version")
            == config.DISCLAIMER_VERSION)


def _save_disclaimer_accepted():
    """记住「已同意」。"""
    data = _load_settings()
    data["disclaimer_version"] = config.DISCLAIMER_VERSION
    _save_settings(data)


def _load_proxy_setting():
    """用户手填的代理地址；空串 = 自动探测。"""
    return _load_settings().get("proxy") or ""


def _save_proxy_setting(value):
    data = _load_settings()
    data["proxy"] = value
    _save_settings(data)


def _show_disclaimer(root):
    """弹出使用须知，返回 (是否同意, 是否要建桌面快捷方式)。关窗 = 不同意。

    勾选项布局照搬市面安装向导：先「我已阅读并同意」，再「在桌面创建快捷方式」
    （默认勾选）。
    """
    win = tk.Toplevel(root)
    win.title(config.DISCLAIMER_TITLE)
    win.resizable(False, False)

    frm = ttk.Frame(win, padding=16)
    frm.pack(fill="both", expand=True)

    ttk.Label(frm, text=config.DISCLAIMER_TITLE,
              font=("", 13, "bold")).pack(anchor="w")

    body = tk.Text(frm, width=64, height=18, wrap="word", relief="solid",
                   bd=1, padx=10, pady=8, font=("", 10), cursor="arrow",
                   background="#fbfbfb")
    body.pack(fill="both", expand=True, pady=(10, 0))
    body.insert("1.0", config.DISCLAIMER_TEXT)
    body.configure(state="disabled")     # 只读，但仍可滚动、可复制

    agree = tk.BooleanVar(value=False)
    want_shortcut = tk.BooleanVar(value=True)   # 与安装向导一致：默认勾选
    result = {"ok": False, "shortcut": False}

    def _finish(ok):
        result["ok"] = ok
        try:
            result["shortcut"] = bool(want_shortcut.get())
        except Exception:            # 变量读取失败就当作不要，别影响启动
            result["shortcut"] = False
        win.destroy()

    chk = ttk.Checkbutton(frm, variable=agree,
                          text="我已阅读并同意上述全部条款")
    chk_sc = ttk.Checkbutton(frm, variable=want_shortcut,
                             text="在桌面创建快捷方式")
    btns = ttk.Frame(frm)
    btn_ok = ttk.Button(btns, text="同意并继续", state="disabled",
                        command=lambda: _finish(True))
    btn_no = ttk.Button(btns, text="不同意并退出",
                        command=lambda: _finish(False))

    def _on_toggle():
        btn_ok.configure(state="normal" if agree.get() else "disabled")

    chk.configure(command=_on_toggle)

    # pack 顺序 = 显示顺序：正文 → 勾选项 → 按钮行
    chk.pack(anchor="w", pady=(10, 0))
    chk_sc.pack(anchor="w", pady=(4, 0))
    btns.pack(fill="x", pady=(10, 0))
    btn_ok.pack(side="right")
    btn_no.pack(side="right", padx=6)

    win.protocol("WM_DELETE_WINDOW", lambda: _finish(False))
    win.update_idletasks()
    x = root.winfo_screenwidth() // 2 - win.winfo_reqwidth() // 2
    y = root.winfo_screenheight() // 3 - win.winfo_reqheight() // 2
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    try:
        win.grab_set()                   # 模态：不处理完不许动主窗口
    except Exception:
        pass
    win.lift()
    try:
        win.focus_force()
    except Exception:
        pass
    root.wait_window(win)
    return result["ok"], result["shortcut"]


# ---------------------------------------------------------------------------
# 桌面快捷方式
#
# exe 是绿色单文件，没有安装程序、也不会自己往桌面放图标，所以给一个手动入口。
# 建 .lnk 只能用 Windows Shell 的 COM 接口；用 PowerShell 起一个 WScript.Shell
# 是最省依赖的做法（不必引入 pywin32）。
# ---------------------------------------------------------------------------
def _shortcut_target():
    """返回 (目标程序, 启动参数, 工作目录, 图标)。

    打包后直接指向 exe 自己；源码运行时指向 pythonw.exe + main.py，
    让从源码跑的人也能得到一个双击即用的快捷方式。
    """
    if getattr(sys, "frozen", False):
        exe = sys.executable
        return exe, "", os.path.dirname(exe), exe
    py = sys.executable
    pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
    if os.path.isfile(pyw):              # 优先无控制台的 pythonw
        py = pyw
    return py, f'"{os.path.join(config.BASE, "main.py")}"', config.BASE, py


class ShortcutExists(Exception):
    """桌面已存在同名快捷方式，需要用户确认是否覆盖。"""

    def __init__(self, path):
        super().__init__(path)
        self.path = path


def create_desktop_shortcut(name="视频下载器", force=False):
    """在桌面创建快捷方式，返回 (lnk 路径, 是否覆盖了已存在的)。

    force=False 时若同名快捷方式已存在，不擅自覆盖，抛 ShortcutExists
    交给界面去问用户 —— 用户可能自己改过图标或名字。

    参数一律通过**环境变量**传给 PowerShell，脚本本体保持纯 ASCII：

    - 本机 PowerShell 5.1 对命令行里的非 ASCII 参数会按控制台代码页解码，
      直接拼中文会变乱码；环境变量在 Windows 上是 Unicode 的，中文没问题。
    - 也顺带避开了 -EncodedCommand（UTF-16LE + base64）—— 那个形式是恶意
      软件的常见混淆手法，容易拉高杀软的启发式评分。本程序未签名，经不起
      再加一层可疑特征。

    结果同样不走 stdout（管道编码不确定），让脚本写进 UTF-8 临时文件再读回。
    """
    import subprocess
    import tempfile

    target, args, workdir, icon = _shortcut_target()
    out_file = os.path.join(tempfile.gettempdir(),
                            f"vd_shortcut_{os.getpid()}.txt")

    script = (
        "$ProgressPreference = 'SilentlyContinue'\n"
        "$ErrorActionPreference = 'Stop'\n"
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n"
        "$ws = New-Object -ComObject WScript.Shell\n"
        "$desktop = [Environment]::GetFolderPath('Desktop')\n"
        "$path = Join-Path $desktop ($env:VD_LNK_NAME + '.lnk')\n"
        "$existed = Test-Path -LiteralPath $path\n"
        # 默认不覆盖；VD_LNK_FORCE 缺失时也走「不覆盖」这一侧
        "if ($existed -and $env:VD_LNK_FORCE -ne '1') {\n"
        "  Set-Content -LiteralPath $env:VD_LNK_OUT "
        "-Value ('skip|' + $path) -Encoding UTF8\n"
        "  exit 0\n"
        "}\n"
        # 已存在的 .lnk 有时处于被占用/受保护状态，先尽力删一次；
        # 删不掉也不影响 —— Save() 本身就会覆盖。
        "if ($existed) { Remove-Item -LiteralPath $path -Force "
        "-ErrorAction SilentlyContinue | Out-Null }\n"
        "$sc = $ws.CreateShortcut($path)\n"
        "$sc.TargetPath = $env:VD_LNK_TARGET\n"
        "$sc.Arguments = '' + $env:VD_LNK_ARGS\n"
        "$sc.WorkingDirectory = $env:VD_LNK_WORKDIR\n"
        "$sc.IconLocation = $env:VD_LNK_ICON + ',0'\n"
        "$sc.Description = $env:VD_LNK_NAME\n"
        "$sc.Save()\n"
        "if (-not (Test-Path -LiteralPath $path)) "
        "{ throw 'shortcut was not written: ' + $path }\n"
        "Set-Content -LiteralPath $env:VD_LNK_OUT "
        "-Value ($existed.ToString() + '|' + $path) -Encoding UTF8\n"
    )
    if not script.isascii():             # 保险丝：脚本混入中文就失去意义了
        raise RuntimeError("PowerShell 脚本必须是纯 ASCII")

    child_env = {
        **os.environ,
        "VD_LNK_NAME": name,
        "VD_LNK_TARGET": target,
        "VD_LNK_ARGS": args,
        "VD_LNK_WORKDIR": workdir,
        "VD_LNK_ICON": icon,
        "VD_LNK_FORCE": "1" if force else "0",
        "VD_LNK_OUT": out_file,
    }

    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, timeout=30, env=child_env,
        creationflags=0x08000000 if sys.platform == "win32" else 0)

    text = ""
    try:
        with open(out_file, encoding="utf-8-sig") as fh:
            text = fh.read().strip()
    except Exception:
        text = ""
    finally:
        try:
            os.remove(out_file)
        except Exception:          # 某些安全策略会拦截删除，忽略即可
            pass

    if not text:
        err = (proc.stderr or b"").decode("utf-8", "replace").strip()
        raise RuntimeError(err or f"PowerShell 返回码 {proc.returncode}")

    status, _, path = text.partition("|")
    status, path = status.strip(), path.strip()
    if status == "skip":
        raise ShortcutExists(path)
    return path, status.lower() == "true"


def _create_shortcut_quietly():
    """首次启动时按用户勾选**静默**建桌面快捷方式。

    放后台线程跑，不挡主窗口出现；失败只记日志、不弹框 —— 首次启动就报错
    很吓人，而且主界面左下角本来就有同名按钮可以重试。
    """
    def work():
        try:
            path, _existed = create_desktop_shortcut()
            logging.info("首次启动已创建桌面快捷方式: %s", path)
        except ShortcutExists:
            logging.info("桌面已存在同名快捷方式，跳过创建")
        except Exception:
            logging.exception("首次启动创建桌面快捷方式失败")

    threading.Thread(target=work, daemon=True).start()


def parse_time(text):
    """把 "90" / "1:30" / "01:02:03" 解析成秒；空串或非法返回 None。

    支持全角冒号（中文输入法下很容易打出来），分钟/秒必须小于 60。
    纯函数，方便单测 —— 时间解析错了会导致截取出错，不能靠手点验证。
    """
    s = (text or "").strip().replace("：", ":")
    if not s:
        return None
    parts = s.split(":")
    if len(parts) > 3 or any(not p.strip().isdigit() for p in parts):
        return None
    nums = [int(p) for p in parts]
    if len(nums) == 1:
        return nums[0]
    if len(nums) == 2:
        minute, second = nums
        if second >= 60:
            return None
        return minute * 60 + second
    hour, minute, second = nums
    if minute >= 60 or second >= 60:
        return None
    return hour * 3600 + minute * 60 + second


def _quality_labels(source, heights):
    """把探测到的高度列表变成下拉框选项 [(显示文字, 高度上限), ...]。

    heights 为 None/空时回退到固定列表（探测失败、或抖音快手这类没有格式
    列表的平台），保证下拉框永远有东西可选。

    这里**不标「需登录」**。曾经按「B站 1080P 起要登录」的常识加过后缀，
    实测是错的：未登录直接用 `bv*[height<=1080]+ba` 能把 1080P 下完
    （yt-dlp 会把 1080P 直链给游客）。标错了比不标更误导，所以只列实测
    可用的画质，不猜。
    """
    if heights:
        return [("最高", None)] + [(f"{h}p", h) for h in heights]
    return ([("最高", None)]
            + [(label, config.QUALITY_HEIGHT[label])
               for label in config.QUALITY_OPTIONS[1:]])


def _summary_status(done, fail, cancelled):
    """本轮任务结束时的状态栏文案。

    抽成纯函数是为了能单测 —— 旧实现是在 finished 里判断
    `status_var.get().startswith("[")`，只要后端中途改过状态（比如
    「拿到直链，开始下载…」）就判断失效，视频下完了状态栏还挂着那句。
    """
    if cancelled:
        return f"已取消（本轮完成 {done} 个）" if done else "已取消"
    if fail and done:
        return f"完成 {done} 个，失败 {fail} 个"
    if fail:
        return "全部失败"
    if done:
        return "全部完成"
    return ""


class App:
    def __init__(self, root, dnd_ok):
        self.root = root
        self.dnd_ok = dnd_ok
        self.q = queue.Queue()
        self.job = None
        self.worker = None
        self.busy = False
        self.alive = True
        # 本轮任务的成败计数。收尾文案由它算出来，而不是去猜 status_var
        # 里还留着什么字符串（旧实现用 startswith("[") 判断，只要后端中途
        # 改过状态就失效，导致下载完成后还挂着「拿到直链，开始下载…」）
        self._done = 0
        self._fail = 0

        self.urls = {s: "" for s in config.SOURCES}
        self.active = "youtube"
        self.panes = {}
        self._last_clip = ""
        self._downloading_pane = None

        self.entry_var = tk.StringVar()
        self.outdir_var = tk.StringVar(value=config.OUTDIR_DEFAULT)
        self.cookie_var = tk.BooleanVar(value=False)
        self.quality_var = tk.StringVar(value=config.QUALITY_OPTIONS[0])
        # 代理：默认留空 = 自动探测（见 config._detect_proxy）。用户可以手填
        # http:// / socks5h://，也照顾自建 VPS 代理和非标准端口
        self.proxy_var = tk.StringVar(value=_load_proxy_setting())
        self.proxy_hint_var = tk.StringVar()
        self.status_var = tk.StringVar(value="")
        self.detail_var = tk.StringVar(value="")
        self.percent_var = tk.StringVar(value="0%")
        # 画质下拉框：默认用固定列表；探测到这条视频的实际格式后重建。
        # 映射存的是「下拉框显示的文字 -> 高度上限」，因为标签里可能带
        # 「（需登录）」后缀，不能再拿 config.QUALITY_HEIGHT 直接查。
        self._quality_map = dict(config.QUALITY_HEIGHT)
        self._probe_seq = 0        # 链接一换就让上一次探测结果作废
        self._probe_after = None   # 防抖定时器句柄
        # 检查更新：_update_info 有值说明发现了新版，按钮会变成下载入口
        self._update_info = None
        self._checking_update = False

        self._build()
        self._select("youtube")
        self._pump()
        self.root.after(500, self._watch_clipboard)
        self._hint()
        self.root.after(700, self._check_missing_tools)
        self.root.after(2500, self._bg_selfupdate)
        self.root.after(4000, self._auto_check_update)

    # ------------------------------------------------------------------ 界面
    def _build(self):
        self.root.title("视频下载器")
        self.root.minsize(900, 640)
        try:
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)
            self.root.report_callback_exception = self._tk_exception
        except Exception:
            pass

        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        # ---- 平台格子（数量跟随 config.SOURCES，每行 5 个自动换行）----
        grid = ttk.Frame(outer)
        grid.pack(fill="both", expand=True)
        cols = 5
        for c in range(cols):
            grid.columnconfigure(c, weight=1)
        for r in range((len(config.SOURCES) + cols - 1) // cols):
            grid.rowconfigure(r, weight=1)
        for i, source in enumerate(config.SOURCES):
            self.panes[source] = self._make_pane(grid, source)
            self.panes[source].grid(row=i // cols, column=i % cols,
                                    sticky="nsew", padx=5, pady=4)

        status_row = ttk.Frame(outer)
        status_row.pack(fill="x", pady=(6, 0))
        ttk.Label(status_row, textvariable=self.status_var,
                  foreground="#2f7fd0").pack(side="left")
        ttk.Label(status_row, text="确保代理能正常访问网站",
                  foreground="#aaa", font=("", 8)).pack(side="right")

        # ---- 链接输入 ----
        self.entry_row = ttk.Frame(outer)
        self.entry_row.pack(fill="x", pady=(6, 0))
        ttk.Label(self.entry_row, text="链接：").pack(side="left")
        self.entry = ttk.Entry(self.entry_row, textvariable=self.entry_var)
        self.entry.pack(side="left", fill="x", expand=True, padx=4)
        self.entry_var.trace_add("write", self._on_entry_change)
        # 抖音/快手的分享是一大段中文文案，直接粘进输入框下载器只会报错。
        # 拦截粘贴事件，把链接抠出来再填。
        self.entry.bind("<<Paste>>", self._on_paste)

        # B站 登录相关控件不常驻 —— 只在 B站格子激活时出现（见 _update_cookie_cb）。
        # 「登录 B站」按钮必须有：errors.py 早就让用户「点导入 B站登录」，
        # 但界面上从来没有这个入口，等于把人指向空气。
        self.cookie_row = ttk.Frame(outer)
        self.cookie_cb = ttk.Checkbutton(
            self.cookie_row, variable=self.cookie_var,
            text="B站使用登录信息（可解锁 1080P 及以上）")
        self.cookie_cb.pack(side="left")
        self.bili_login_btn = ttk.Button(
            self.cookie_row, text="登录 B站", command=self._bili_login)
        self.bili_login_btn.pack(side="left", padx=(8, 0))

        ttk.Separator(outer).pack(fill="x", pady=10)

        # ---- 保存位置 ----
        out_row = ttk.Frame(outer)
        out_row.pack(fill="x")
        ttk.Label(out_row, text="保存到：").pack(side="left")
        ttk.Entry(out_row, textvariable=self.outdir_var).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Button(out_row, text="浏览…", command=self._browse).pack(side="left")

        # ---- 代理 ----
        # 只影响被墙平台（YouTube / X / Instagram / TikTok），国内平台一律直连。
        # 留空 = 自动探测（系统代理 → 常见端口）。留一个手填入口是必须的：
        # 自建 VPS 的 v2ray / xray / ss-local 大多是 SOCKS，端口也不标准，
        # 探测不出来，只能让用户自己写。
        proxy_row = ttk.Frame(outer)
        proxy_row.pack(fill="x", pady=(6, 0))
        ttk.Label(proxy_row, text="代理：").pack(side="left")
        ttk.Entry(proxy_row, textvariable=self.proxy_var).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Button(proxy_row, text="测试",
                   command=self._test_proxy).pack(side="left")
        ttk.Label(outer, textvariable=self.proxy_hint_var, foreground="#aaa",
                  font=("", 8)).pack(anchor="w", pady=(2, 0))
        self._refresh_proxy_hint()

        btns = ttk.Frame(outer)
        btns.pack(fill="x", pady=10)
        ttk.Label(btns, text="画质：").pack(side="left")
        self.quality_cb = ttk.Combobox(btns, textvariable=self.quality_var,
                                       values=config.QUALITY_OPTIONS,
                                       state="readonly", width=8)
        self.quality_cb.pack(side="left", padx=(0, 10))
        self.go_btn = ttk.Button(btns, text="下  载", command=self._start)
        self.go_btn.pack(side="left")
        self.cancel_btn = ttk.Button(btns, text="取消", command=self._cancel,
                                     state="disabled")
        self.cancel_btn.pack(side="left", padx=6)
        ttk.Button(btns, text="清空", command=self._clear).pack(side="left", padx=6)

        # ---- 片段下载（仅 yt-dlp 系平台）----
        # 长视频只要中间一段时，没必要整条下完再剪 —— yt-dlp 的
        # --download-sections 能只拉取指定区间。抖音/快手走自己的解析器，
        # 拿不到区间信息，所以这两个平台置灰。
        sec_row = ttk.Frame(outer)
        sec_row.pack(fill="x", pady=(0, 4))
        self.section_var = tk.BooleanVar(value=False)
        self.section_chk = ttk.Checkbutton(
            sec_row, text="只下载片段", variable=self.section_var,
            command=self._refresh_section_state)
        self.section_chk.pack(side="left")
        ttk.Label(sec_row, text="从").pack(side="left", padx=(8, 2))
        self.sec_start = ttk.Entry(sec_row, width=9)
        self.sec_start.pack(side="left")
        ttk.Label(sec_row, text="到").pack(side="left", padx=(4, 2))
        self.sec_end = ttk.Entry(sec_row, width=9)
        self.sec_end.pack(side="left")
        self.section_hint = ttk.Label(sec_row, text="", foreground="#aaa",
                                      font=("", 8))
        self.section_hint.pack(side="left", padx=(8, 0))
        self._refresh_section_state()

        ttk.Separator(outer).pack(fill="x")

        # ---- 进度 ----
        bar_row = ttk.Frame(outer)
        bar_row.pack(fill="x", pady=(10, 0))
        self.bar = ttk.Progressbar(bar_row, mode="determinate", maximum=100)
        self.bar.pack(side="left", fill="x", expand=True)
        ttk.Label(bar_row, textvariable=self.percent_var, width=6,
                  anchor="e").pack(side="left", padx=(8, 0))
        ttk.Label(outer, textvariable=self.detail_var,
                  foreground="#666").pack(fill="x", pady=(4, 0))

        # 底部一行：左边「创建桌面快捷方式」「检查更新」，右边打赏
        # （DONATE_URL 留空则不显示）
        bottom = ttk.Frame(outer)
        bottom.pack(fill="x")
        self.shortcut_btn = ttk.Button(bottom, text="创建桌面快捷方式",
                                       command=self._make_shortcut)
        self.shortcut_btn.pack(side="left")
        self.update_btn = ttk.Button(bottom, text="检查更新",
                                     command=lambda: self._check_update(True))
        self.update_btn.pack(side="left", padx=(8, 0))
        # 版本号放在最不起眼的位置，但用户报问题时能一眼对上号
        ttk.Label(bottom, text=f"v{config.VERSION}", foreground="#aaa",
                  font=("", 8)).pack(side="left", padx=(8, 0))
        if config.DONATE_URL:
            import webbrowser
            ttk.Button(bottom, text="☕ 支持作者（自愿）",
                       command=lambda: webbrowser.open(config.DONATE_URL)
                       ).pack(side="right")

    def _make_pane(self, parent, source):
        """一个格子就是单个 tk.Label。

        不能做成 Frame+Label —— 拖拽目标不继承给子控件，拖上去只会落在
        Label 上，Frame 的注册永远不触发，看起来能拖其实静默失败。
        """
        text = config.SOURCE_LABEL[source] + "\n\n" + (
            "把链接拖到这里" if self.dnd_ok else "点这里，然后粘贴链接")
        lbl = tk.Label(parent, text=text, relief="ridge", bd=2,
                       bg=PANE_IDLE, fg="#333", justify="center",
                       cursor="hand2", padx=6, pady=10)
        lbl.bind("<Button-1>", lambda _e, s=source: self._select(s))

        if self.dnd_ok:
            try:
                lbl.drop_target_register(DND_TEXT, DND_FILES)
                lbl.dnd_bind("<<Drop>>",
                             lambda e, s=source: self._on_drop(e, s))
                lbl.dnd_bind("<<DropEnter>>",
                             lambda _e, s=source: self._hover(s, True))
                lbl.dnd_bind("<<DropLeave>>",
                             lambda _e, s=source: self._hover(s, False))
            except Exception:
                logging.exception("注册拖拽失败: %s", source)
        return lbl

    def _hover(self, source, on):
        if source == self.active:
            return
        self.panes[source].configure(bg=PANE_DROP if on else PANE_IDLE)

    def _update_cookie_cb(self):
        """B站 cookies 勾选只在 B站格子激活时出现，别常年占着界面。

        pack(after=entry_row) 保证显示时位置稳定在链接输入框下方，
        不会因为 pack 顺序跑到布局末尾。
        """
        if self.active == "bilibili":
            self.cookie_row.pack(anchor="w", pady=(6, 0), after=self.entry_row)
        else:
            self.cookie_row.pack_forget()

    def _hint(self):
        if not self.dnd_ok:
            self.status_var.set("拖拽组件没装上 —— 点格子后粘贴链接一样能用。")

    def _refresh_section_state(self):
        """片段下载只对 yt-dlp 系平台开放；抖音/快手走自己的解析器。"""
        supported = self.active not in ("douyin", "kuaishou")
        if not supported:
            self.section_var.set(False)
        self.section_chk.configure(state="normal" if supported else "disabled")
        on = supported and self.section_var.get()
        for widget in (self.sec_start, self.sec_end):
            widget.configure(state="normal" if on else "disabled")
        self.section_hint.configure(
            text=("如 01:30 或 1:02:03；结束留空 = 到片尾" if supported
                  else "抖音/快手暂不支持片段下载"))

    # ------------------------------------------------------------ 代理
    def _refresh_proxy_hint(self):
        """刷新代理输入框下面的灰字说明。"""
        if self.proxy_var.get().strip():
            hint = ("已手动指定。只影响 YouTube / X / Instagram / TikTok；"
                    "国内平台始终直连。")
        else:
            hint = (f"留空 = 自动探测（当前：{config.PROXY}）。"
                    "只影响 YouTube / X / Instagram / TikTok；国内平台始终直连。")
        self.proxy_hint_var.set(hint)

    def _test_proxy(self):
        """「测试」按钮：先 TCP 连通，再真发一次请求验证能翻墙。

        只做 TCP 探测是不够的 —— 那个端口可能被别的服务占着（比如 8080 上的
        本地网页服务器），TCP 通但代理用不了。
        """
        raw = self.proxy_var.get()
        proxy, host, port, err = config.resolve_proxy(raw)
        if err:
            messagebox.showerror("代理地址不对", err)
            return
        import socket
        try:
            socket.create_connection((host, port), timeout=3).close()
        except OSError:
            self.proxy_hint_var.set(
                f"连不上 {host}:{port} —— 端口是不是没开？")
            return

        _save_proxy_setting(raw.strip())
        self.proxy_hint_var.set(f"{host}:{port} 端口通，正在实际验证…")

        def work():
            try:
                import requests
                s = requests.Session()
                s.trust_env = False
                s.proxies = {"http": proxy, "https": proxy}
                r = s.get("https://x.com/", timeout=20)
                msg = f"能翻墙 ✓（x.com 返回 {r.status_code}）"
            except Exception as exc:
                msg = f"端口通但用不了：{type(exc).__name__} {str(exc)[:60]}"
            self.q.put(("proxy_test", {"text": f"{proxy} {msg}"}))

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ B站登录
    def _bili_login(self):
        """开浏览器让用户扫码，成功后把登录态写成 cookies.txt。

        起浏览器要几百毫秒，放后台线程跑；结果走队列回主线程更新界面。
        """
        if self.busy:
            self.status_var.set("正在下载，等这轮结束再登录")
            return
        self.bili_login_btn.configure(state="disabled")
        self.status_var.set("正在打开 B站登录页…")

        def work():
            try:
                import bililogin
                ok, result = bililogin.login_and_save(
                    emit=lambda kind, **kw: self.q.put((kind, kw)))
                self.q.put(("bili_login_ok" if ok else "bili_login_fail",
                            {"text": result}))
            except Exception as exc:
                logging.exception("B站登录失败")
                self.q.put(("bili_login_fail", {"text": str(exc)}))

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ 画质探测
    def _schedule_probe(self):
        """链接变了就延迟 800ms 再探画质 —— 连续输入只探最后一次。"""
        if self._probe_after is not None:
            try:
                self.root.after_cancel(self._probe_after)
            except Exception:
                pass
        self._probe_after = self.root.after(800, self._probe_qualities)

    def _probe_qualities(self):
        self._probe_after = None
        if self.busy:
            return
        source = self.active
        url = self.urls.get(source) or ""
        if not url or source not in _PROBE_SOURCES:
            self._set_quality_options(source, None)
            return
        self._probe_seq += 1
        seq = self._probe_seq
        use_cookies = bool(self.cookie_var.get()) and source == "bilibili"
        # 探测也要走用户在界面上填的代理，否则「测试」能过、下载另一套
        proxy, _, _, perr = config.resolve_proxy(self.proxy_var.get())
        if perr:
            proxy = None
        self.status_var.set("正在读取这条视频支持的画质…")

        def work():
            try:
                heights, err = backends.probe_formats(
                    url, source, use_cookies, proxy=proxy)
            except Exception as exc:
                heights, err = None, f"{type(exc).__name__}"
            self.q.put(("qualities", {"seq": seq, "source": source,
                                      "heights": heights, "err": err,
                                      "proxy": proxy}))

        threading.Thread(target=work, daemon=True).start()

    def _set_quality_options(self, source, heights):
        """按探测结果重建画质下拉框；heights 为 None 时回退固定列表。"""
        pairs = _quality_labels(source, heights)
        self._quality_map = dict(pairs)
        labels = [p[0] for p in pairs]
        widest = max(len(x) for x in labels) + 1
        self.quality_cb.configure(values=labels, width=min(18, max(8, widest)))
        if self.quality_var.get() not in self._quality_map:
            self.quality_var.set("最高")

    # ------------------------------------------------------------------ 交互
    def _on_drop(self, event, source):
        """从拖拽内容里取链接。

        浏览器拖超链接给的是 text/uri-list，tkinterdnd2 未必认；
        所以取不到就退回读剪贴板（很多时候拖拽同时也填了剪贴板）。
        """
        data = getattr(event, "data", "") or ""
        url = config.extract_url(data)
        if not url:
            try:
                url = config.extract_url(self.root.clipboard_get())
            except tk.TclError:
                url = None
        if not url:
            self.status_var.set("拖过来的内容里没找到链接，试试直接复制粘贴。")
            return
        self._set_url(url, source)

    def _select(self, source):
        self.active = source
        self.entry_var.set(self.urls[source])
        self._refresh()
        self._update_cookie_cb()
        self._refresh_section_state()
        self._schedule_probe()

    def _on_paste(self, _event=None):
        """粘贴分享文案时自动抠出链接，并切到对应平台的格子。

        返回 "break" 阻止默认粘贴 —— 默认行为会把整段中文塞进输入框。
        剪贴板里没有链接时返回 None，走默认粘贴（用户可能就是想贴文字）。
        """
        try:
            raw = self.root.clipboard_get()
        except tk.TclError:
            return None
        url = config.extract_url(raw)
        if not url:
            return None
        # 用户可能正停在 B站格子时粘了一段抖音文案，连格子一起切过去
        self._set_url(url, config.detect_source(raw) or self.active)
        return "break"

    def _on_entry_change(self, *_):
        self.urls[self.active] = self.entry_var.get()
        self._refresh()

    def _set_url(self, url, source):
        self.urls[source] = url
        self.active = source
        self.entry_var.set(url)
        self._refresh()
        self._update_cookie_cb()
        self.status_var.set(f"已识别为 {config.SOURCE_LABEL[source]}")
        self._schedule_probe()

    def _refresh(self):
        for source, pane in self.panes.items():
            url = self.urls[source]
            label = config.SOURCE_LABEL[source]
            if url:
                text = f"{label}\n\n{config.display_url(url)}"
            elif source == self.active:
                text = f"{label}\n\n（在这里粘贴链接）"
            else:
                text = f"{label}\n\n" + (
                    "把链接拖到这里" if self.dnd_ok else "点这里再粘贴")
            pane.configure(text=text,
                           bg=PANE_ACTIVE if source == self.active else PANE_IDLE)

    def _browse(self):
        path = filedialog.askdirectory(
            title="选择保存位置",
            initialdir=self.outdir_var.get() or os.path.expanduser("~"))
        if path:
            self.outdir_var.set(os.path.normpath(path))

    def _make_shortcut(self, force=False):
        """在桌面建快捷方式。起 PowerShell 要几百毫秒，丢到线程里别卡界面。"""
        self.shortcut_btn.configure(state="disabled")

        def work():
            try:
                path, existed = create_desktop_shortcut(force=force)
                self.q.put(("shortcut_ok", {"text": path, "existed": existed}))
            except ShortcutExists as exc:
                self.q.put(("shortcut_exists", {"text": exc.path}))
            except Exception as exc:
                logging.exception("创建桌面快捷方式失败")
                self.q.put(("shortcut_fail", {"text": str(exc)}))

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ 检查更新
    def _auto_check_update(self):
        """启动后静默检查一次，最多每 24 小时一次。

        放启动 4 秒后：别和启动自检、ffmpeg 检测抢那几秒。
        失败完全静默 —— 检查更新不该让用户看到任何错误。
        """
        try:
            last = float(_load_settings().get("last_update_check") or 0)
        except (TypeError, ValueError):
            last = 0
        if time.time() - last < config.UPDATE_CHECK_INTERVAL:
            return
        self._check_update(False)

    def _check_update(self, manual):
        """manual=True 是用户点按钮：要有明确反馈，且不受 24 小时限制。"""
        if self._checking_update:
            return
        self._checking_update = True
        self.update_btn.configure(state="disabled")
        if manual:
            self.status_var.set("正在检查更新…")

        def work():
            info = updater.check(config.UPDATE_JSON_URL, config.VERSION)
            # 无论成败都记时间：失败时别每次启动都重试一遍
            data = _load_settings()
            data["last_update_check"] = time.time()
            _save_settings(data)
            self.q.put(("update_result", {"info": info, "manual": manual}))

        threading.Thread(target=work, daemon=True).start()

    def _on_update_result(self, info, manual):
        self._checking_update = False
        self.update_btn.configure(state="normal")
        if info:
            self._update_info = info
            note = f"（{info['notes']}）" if info.get("notes") else ""
            self.status_var.set(
                f"发现新版 v{info['version']}{note}，点左下角「下载新版」")
            # 按钮就地变成下载入口，用户不用再去别处找
            self.update_btn.configure(
                text=f"下载新版 v{info['version']}",
                command=self._open_download)
        elif manual:
            self.status_var.set("已是最新版（或暂时连不上更新服务器）")

    def _open_download(self):
        """给两个下载入口：网盘（普通用户）/ GitHub（懂的用户，不限速）。

        不分人群一刀切：网盘是给不会用代理的人准备的，但懂 GitHub 的用户
        没必要陪着忍受百度限速。
        """
        import webbrowser
        info = self._update_info or {}
        pan = info.get("url") or config.DOWNLOAD_URL
        gh = info.get("url_github") or config.GITHUB_RELEASES_URL

        dlg = tk.Toplevel(self.root)
        dlg.title("下载新版")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        frame = ttk.Frame(dlg, padding=16)
        frame.pack()

        ttk.Label(frame, text=f"视频下载器 v{info.get('version', '')}",
                  font=("", 10)).pack(anchor="w")
        if info.get("notes"):
            ttk.Label(frame, text=info["notes"], foreground="#666").pack(
                anchor="w", pady=(2, 0))
        ttk.Label(frame, text="网盘非会员会限速；能上 GitHub 的建议走 GitHub。",
                  foreground="#aaa", font=("", 8)).pack(anchor="w", pady=(8, 10))

        row = ttk.Frame(frame)
        row.pack(fill="x")

        def go(url):
            webbrowser.open(url)
            dlg.destroy()

        ttk.Button(row, text="从网盘下载", command=lambda: go(pan)).pack(
            side="left")
        ttk.Button(row, text="从 GitHub 下载", command=lambda: go(gh)).pack(
            side="left", padx=(8, 0))
        ttk.Button(row, text="取消", command=dlg.destroy).pack(side="right")

        # 贴着主窗口居中，别弹到屏幕角落
        dlg.update_idletasks()
        x = self.root.winfo_rootx() + (
            self.root.winfo_width() - dlg.winfo_width()) // 2
        y = self.root.winfo_rooty() + (
            self.root.winfo_height() - dlg.winfo_height()) // 3
        dlg.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        dlg.grab_set()

    def _clear(self):
        if self.busy:
            # 下载中清空只会清掉界面、后台任务照跑，用户很容易以为已经取消
            self.status_var.set("正在下载，先点「取消」再清空")
            return
        self.urls = {s: "" for s in config.SOURCES}
        self.entry_var.set("")
        self.status_var.set("")
        self.detail_var.set("")
        self._set_progress(0.0)
        self._probe_seq += 1                 # 让在途的画质探测结果作废
        self._set_quality_options(self.active, None)
        self._refresh()

    def _watch_clipboard(self):
        """剪贴板一有可识别的链接就自动填好 —— 这是比拖拽更可靠的主路径。

        正在链接框里打字时跳过，免得把用户手输的内容冲掉。
        """
        if self.alive and not self.busy:
            try:
                focused = self.root.focus_get()
            except Exception:
                focused = None
            if focused is not self.entry:
                try:
                    text = self.root.clipboard_get()
                except tk.TclError:
                    text = ""
                if text and text != self._last_clip:
                    self._last_clip = text
                    url = config.extract_url(text)
                    source = config.detect_source(url) if url else None
                    if source and self.urls[source] != url:
                        self._set_url(url, source)
        if self.alive:
            self.root.after(500, self._watch_clipboard)

    # ------------------------------------------------------------------ 下载
    def _start(self):
        if self.busy:
            return
        # 每个格子里的内容再抠一次链接：拖拽和剪贴板监听已经抽过，但手动
        # 输入/粘贴可能残留整段分享文案（曾经把中文交给下载器导致报错）
        tasks = []
        for s in config.SOURCES:
            raw = (self.urls[s] or "").strip()
            if not raw:
                continue
            url = config.extract_url(raw)
            if not url:
                messagebox.showerror(
                    "链接不对",
                    f"{config.SOURCE_LABEL[s]} 那一格里没找到 http 链接。\n"
                    "可以直接粘贴整段分享文案，程序会自动提取链接。")
                return
            self.urls[s] = url
            if s == self.active:
                self.entry_var.set(url)
            tasks.append((s, url))
        if not tasks:
            messagebox.showinfo("还没有链接", "先把视频链接拖进格子，或复制链接后回来。")
            return

        # 先把所有界面变量的值取出来再交给 worker —— worker 不许碰 Tk
        outdir = self.outdir_var.get()
        use_cookies = bool(self.cookie_var.get())
        # 画质上限从当前下拉框的文字反查 —— 标签可能带「（需登录）」后缀，
        # 不能直接拿 config.QUALITY_HEIGHT 查
        max_height = self._quality_map.get(self.quality_var.get())
        # 代理：空 = 自动探测；手填要立刻校验格式，别等下载才报错
        proxy, proxy_host, proxy_port, perr = config.resolve_proxy(
            self.proxy_var.get())
        if perr:
            messagebox.showerror("代理地址不对", perr)
            return

        # 片段：勾了就必须填对开始时间，结束可空（= 到片尾）
        section = None
        if self.section_var.get():
            start = parse_time(self.sec_start.get())
            end = parse_time(self.sec_end.get())
            if start is None:
                messagebox.showerror(
                    "片段格式不对", "开始时间要填，格式如 01:30 或 1:02:03。")
                return
            if self.sec_end.get().strip() and end is None:
                messagebox.showerror(
                    "片段格式不对", "结束时间格式如 01:30 或 1:02:03。")
                return
            if end is not None and end <= start:
                messagebox.showerror("片段格式不对", "结束时间必须晚于开始时间。")
                return
            if not end:
                end = None
            section = (start, end)

        # ffmpeg（片段下载要用它拉流）不支持 SOCKS 代理。海外平台 + SOCKS
        # 基本必失败，提前说清楚，别让用户等半天看一句「ffmpeg exited with code」
        if (section and proxy and str(proxy).startswith("socks")
                and any(s in backends._PROXY_SOURCES for s, _ in tasks)):
            if not messagebox.askyesno(
                    "SOCKS 代理可能不支持片段下载",
                    "片段下载依赖 ffmpeg，而 ffmpeg 不支持 SOCKS 代理。\n"
                    "海外平台（YouTube / X / Instagram / TikTok）的片段下载"
                    "很可能失败。\n\n"
                    "可以改用 HTTP 代理（如 http://127.0.0.1:7897），"
                    "或取消「只下载片段」。\n\n仍要继续吗？"):
                return

        self.busy = True
        self.go_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        # 清掉上一轮的残留，否则新任务开始后界面上还挂着上次的
        # 「完成：xxx.mp4」和 100% 进度条，看着像没开始
        self._done = 0
        self._fail = 0
        self.status_var.set("准备中…")
        self.detail_var.set("")
        self._set_progress(0.0)
        self.job = backends.Job()
        self.worker = threading.Thread(
            target=self._run_tasks,
            args=(tasks, outdir, use_cookies, max_height, proxy, proxy_host,
                  proxy_port, section),
            daemon=True)
        self.worker.start()

    def _run_tasks(self, tasks, outdir, use_cookies, max_height=None,
                   proxy=None, proxy_host=None, proxy_port=None,
                   section=None):
        def emit(kind, **kw):
            self.q.put((kind, kw))

        try:
            for i, (source, url) in enumerate(tasks, 1):
                if self.job.cancel.is_set():
                    break
                tag = f"[{i}/{len(tasks)}] {config.SOURCE_LABEL[source]}"
                emit("status", text=f"{tag} 开始…")
                emit("progress", frac=-1.0, text="")
                emit("pane", source=source)

                problem = errors.check_prereqs(
                    source, outdir, config.COOKIES_BILI, use_cookies,
                    proxy_host or config.PROXY_HOST,
                    proxy_port or config.PROXY_PORT)
                if problem:
                    emit("failed", source=source, text=problem)
                    continue

                # 界面已对抖音/快手禁用片段选项，这里是兜底：别静默忽略用户
                # 的选择，直接说清楚为什么不生效
                if section and source in ("douyin", "kuaishou"):
                    emit("failed", source=source,
                         text="抖音/快手暂不支持片段下载，请整段下载。")
                    continue

                if source == "douyin":
                    import douyin
                    ok, result = douyin.download_douyin(
                        url, outdir, emit, self.job, self._choose_items)
                elif source == "kuaishou":
                    import kuaishou
                    ok, result = kuaishou.download_kuaishou(
                        url, outdir, emit, self.job)
                else:
                    ok, result = backends.download_ytdlp(
                        url, source, outdir, use_cookies, emit, self.job,
                        max_height, proxy, section)

                if ok:
                    emit("ok", source=source, text=result)
                else:
                    emit("failed", source=source, text=result)

                if self.job.cancel.is_set():
                    break
        except Exception:
            emit("crash", text=traceback.format_exc())
        finally:
            emit("finished")

    def _pump(self):
        """把队列抽干再刷新界面 —— 一次一条的话进度条会明显滞后。"""
        try:
            while True:
                kind, kw = self.q.get_nowait()
                self._apply(kind, kw)
        except queue.Empty:
            pass
        if self.alive:
            self.root.after(100, self._pump)

    def _apply(self, kind, kw):
        if kind == "status":
            self.status_var.set(kw.get("text", ""))
        elif kind == "progress":
            self._set_progress(kw.get("frac", -1.0))
            if kw.get("text"):
                self.detail_var.set(kw["text"])
        elif kind == "title":
            self.detail_var.set("标题：" + (kw.get("text") or ""))
        elif kind == "merge":
            self.status_var.set(kw.get("text", "正在合并音视频…"))
            self._set_progress(-1.0)
        elif kind == "log":
            logging.info("cmd: %s", kw.get("text", ""))
        elif kind == "pane":
            self.panes[kw["source"]].configure(bg=PANE_ACTIVE)
        elif kind == "ok":
            self._done += 1
            path = kw.get("text", "")
            self.panes[kw["source"]].configure(bg=PANE_DONE)
            # 状态栏必须跟着改。旧实现只改 detail_var，status_var 会一直停在
            # 后端最后一句「拿到直链，开始下载…」上，视频早下完了还那么显示
            self.status_var.set("下载完成")
            if os.path.isfile(path):
                self.detail_var.set("完成：" + os.path.basename(path))
            else:                    # 批量任务（如收藏音乐）返回的是汇总文字
                self.detail_var.set("完成：" + path)
            logging.info("OK %s -> %s", kw["source"], path)
        elif kind == "choose":
            self._show_chooser(kw["items"], kw["done"], kw["box"])
        elif kind == "tools_prog":
            self._tools_progress(kw.get("frac"), kw.get("text"))
        elif kind == "tools_done":
            self._tools_finished(True)
        elif kind == "tools_fail":
            self._tools_finished(False, kw.get("text"))
        elif kind == "failed":
            cancelled = (kw.get("text") or "").strip() == "已取消"
            self.panes[kw["source"]].configure(
                bg=PANE_IDLE if cancelled else PANE_FAIL)
            logging.warning("FAIL %s: %s", kw["source"], kw.get("text"))
            # 主动取消不算失败：不计入失败数、不弹框，状态栏交给 finished 收尾
            if cancelled:
                self.detail_var.set("已取消")
            else:
                self._fail += 1
                self.status_var.set("下载失败")
                self.detail_var.set(
                    "失败：" + (kw.get("text") or "").splitlines()[0])
                messagebox.showerror(
                    config.SOURCE_LABEL[kw["source"]] + " 下载失败",
                    kw.get("text", ""))
        elif kind == "qualities":
            if kw.get("seq") != self._probe_seq:
                return               # 用户又换了链接，这批结果已作废
            heights, err = kw.get("heights"), kw.get("err")
            self._set_quality_options(kw.get("source"), heights)
            if self.busy:
                return
            if err:
                # 探不到就直说，别让固定档位看起来像是这条视频的真实画质
                hint = errors.friendly(err, kw.get("source"),
                                       kw.get("proxy"))
                if hint.startswith("下载失败："):
                    hint = hint[len("下载失败："):]
                self.status_var.set(f"读不到画质列表：{hint}")
            else:
                self.status_var.set("")
        elif kind == "bili_login_ok":
            self.bili_login_btn.configure(state="normal")
            self.cookie_var.set(True)     # 登录完顺手勾上，省一步
            self.status_var.set("B站登录成功")
            self.detail_var.set("登录信息已保存：" + kw.get("text", ""))
            logging.info("B站登录成功 -> %s", kw.get("text"))
            messagebox.showinfo(
                "登录成功",
                "B站登录信息已保存。\n"
                "勾选「B站使用登录信息」后即可下载 1080P 及以上画质。")
            self._schedule_probe()        # 登录后「需登录」标注要重算
        elif kind == "bili_login_fail":
            self.bili_login_btn.configure(state="normal")
            self.status_var.set("B站登录未完成")
            messagebox.showerror("B站登录", kw.get("text", ""))
        elif kind == "proxy_test":
            self.proxy_hint_var.set(kw.get("text", ""))
        elif kind == "update_result":
            self._on_update_result(kw.get("info"), kw.get("manual"))
        elif kind == "crash":
            logging.error("worker 崩溃:\n%s", kw.get("text"))
            messagebox.showerror("程序出错",
                                 "下载线程出错了，详情见 logs\\app.log")
        elif kind == "shortcut_ok":
            self.shortcut_btn.configure(state="normal")
            verb = "已更新" if kw.get("existed") else "已创建"
            messagebox.showinfo("完成",
                                f"桌面快捷方式{verb}：\n{kw.get('text', '')}")
        elif kind == "shortcut_exists":
            if messagebox.askyesno(
                    "桌面已有同名快捷方式",
                    f"{kw.get('text', '')}\n\n要覆盖它吗？"):
                self._make_shortcut(force=True)   # 保持禁用，交给新一轮任务
            else:
                self.shortcut_btn.configure(state="normal")
        elif kind == "shortcut_fail":
            self.shortcut_btn.configure(state="normal")
            messagebox.showerror(
                "创建失败",
                (kw.get("text") or "") +
                "\n\n也可以手动操作：右键程序 → 发送到 → 桌面快捷方式。")
        elif kind == "finished":
            self.busy = False
            self.go_btn.configure(state="normal")
            self.cancel_btn.configure(state="disabled")
            # 收尾文案按本轮实际的成败计数算，不去猜 status_var 里剩了什么
            # 字符串（旧实现用 startswith("[") 判断，后端只要中途改过状态就失效）
            cancelled = self.job is not None and self.job.cancel.is_set()
            self.status_var.set(_summary_status(self._done, self._fail, cancelled))
            # 全成功就停在满格，别掉回 0% —— 那样看着像没下成功
            self._set_progress(
                1.0 if (self._done and not self._fail and not cancelled) else 0.0)

    def _set_progress(self, frac):
        if frac is None or frac < 0:
            if str(self.bar["mode"]) != "indeterminate":
                self.bar.stop()
                self.bar.configure(mode="indeterminate")
                self.bar.start(15)
            self.percent_var.set("…")
            return
        if str(self.bar["mode"]) != "determinate":
            self.bar.stop()
            self.bar.configure(mode="determinate")
        self.bar["value"] = frac * 100
        self.percent_var.set(f"{frac * 100:.0f}%")

    def _cancel(self):
        if self.job:
            self.status_var.set("正在取消…")
            self.job.cancel_now()

    # ------------------------------------------------------------------ 勾选
    def _choose_items(self, items):
        """worker 线程调用：把抓到的列表交给主线程弹窗勾选。

        返回选中的下标列表；用户取消返回 None。worker 在这里阻塞等待，
        但每 0.2s 醒来看一眼取消标志，点主窗口的「取消」也能退出。
        """
        done = threading.Event()
        box = {"picked": None}
        self.q.put(("choose", {"items": items, "done": done, "box": box}))
        while not done.wait(0.2):
            if self.job and self.job.cancel.is_set():
                return None
        return box["picked"]

    def _show_chooser(self, items, done, box):
        """勾选弹窗。只能在主线程建控件（Tkinter 线程约定）。"""
        win = tk.Toplevel(self.root)
        win.title("选择要下载的音频")
        win.transient(self.root)
        win.geometry("560x500")
        win.grab_set()

        ttk.Label(win, text=f"抓到 {len(items)} 条音频，"
                            "勾选要下载的（默认全选）："
                  ).pack(anchor="w", padx=12, pady=(12, 4))

        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=12)
        lb = tk.Listbox(frame, selectmode="extended", exportselection=False,
                        font=("", 10))
        sb = ttk.Scrollbar(frame, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)
        for i, (_u, t) in enumerate(items, 1):
            name = (t or "").strip() or f"（未命名音频 {i}）"
            lb.insert("end", f"{i:>3}. {name[:64]}")
        lb.selection_set(0, "end")
        lb.see(0)

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=12, pady=10)

        def _finish(picked):
            box["picked"] = picked
            done.set()
            win.destroy()

        ttk.Button(btns, text="全选",
                   command=lambda: lb.selection_set(0, "end")).pack(side="left")
        ttk.Button(btns, text="全不选",
                   command=lambda: lb.selection_clear(0, "end")
                   ).pack(side="left", padx=6)
        ttk.Button(btns, text="取消下载",
                   command=lambda: _finish(None)).pack(side="right")
        ttk.Button(btns, text="确  定",
                   command=lambda: _finish(sorted(lb.curselection()))
                   ).pack(side="right", padx=6)
        win.protocol("WM_DELETE_WINDOW", lambda: _finish(None))

    # ------------------------------------------------- 必备工具一键安装
    def _check_missing_tools(self):
        """启动后检查一次必备工具，缺了就弹一键安装窗口（每次启动至多一次）。"""
        try:
            import toolssetup
            tools = toolssetup.missing_tools()
        except Exception:
            logging.exception("工具检查失败")
            return
        if tools:
            self._pending_tools = tools
            self._show_tools_dialog(tools)

    def _bg_selfupdate(self):
        """后台静默自更新 tools\\ 里的 yt-dlp（每两周一次，失败不影响使用）。"""
        import toolssetup
        threading.Thread(target=toolssetup.maybe_self_update_ytdlp,
                         daemon=True).start()

    def _show_tools_dialog(self, tools):
        dlg = tk.Toplevel(self.root)
        dlg.title("缺少必要工具")
        dlg.transient(self.root)
        dlg.resizable(False, False)
        self.tools_dlg = dlg

        frm = ttk.Frame(dlg, padding=16)
        frm.pack(fill="both", expand=True)

        ttk.Label(frm, text=f"缺少 {len(tools)} 个必要下载工具：",
                  font=("", 11, "bold")).pack(anchor="w")
        for t in tools:
            ttk.Label(frm, text=f"● {t['name']}",
                      font=("", 10, "bold")).pack(anchor="w", pady=(8, 0))
            ttk.Label(frm, text=t["desc"], foreground="#555",
                      wraplength=430, justify="left").pack(anchor="w")
            ttk.Label(frm, text="来源：" + t["source"], foreground="#777",
                      wraplength=430, justify="left").pack(anchor="w")

        ttk.Label(frm,
                  text="点「一键下载并配置」会自动从上面的官方源下载并配置好，"
                       "无需其他操作；也可以关闭本窗口自行安装。",
                  wraplength=430, justify="left").pack(anchor="w", pady=(12, 0))

        self.tools_status = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.tools_status, foreground="#2f7fd0",
                  wraplength=430, justify="left").pack(anchor="w", pady=(8, 0))

        self.tools_bar = ttk.Progressbar(frm, mode="determinate", maximum=100)

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(12, 0))
        self.tools_cancel_evt = threading.Event()
        self.tools_install_btn = ttk.Button(btns, text="一键下载并配置",
                                            command=self._tools_install)
        self.tools_install_btn.pack(side="right")
        ttk.Button(btns, text="自行安装（关闭）",
                   command=dlg.destroy).pack(side="right", padx=6)

    def _tools_install(self):
        self.tools_install_btn.configure(state="disabled")
        self.tools_cancel_evt = threading.Event()
        self.tools_bar.pack(fill="x", pady=(8, 0))
        threading.Thread(target=self._tools_worker,
                         args=(self._pending_tools,), daemon=True).start()

    def _tools_worker(self, tools):
        import toolssetup

        def cb(frac, text):
            self.q.put(("tools_prog", {"frac": frac, "text": text}))

        try:
            for t in tools:
                self.q.put(("tools_prog",
                            {"frac": -1.0, "text": f"正在下载 {t['name']}…"}))
                toolssetup.install_tool(t["key"], cb,
                                        self.tools_cancel_evt.is_set)
            self.q.put(("tools_done", {}))
        except toolssetup._Cancelled:
            self.q.put(("tools_fail", {"text": "已取消。"}))
        except Exception as exc:
            logging.exception("一键安装失败")
            self.q.put(("tools_fail", {
                "text": f"安装失败：{exc}\n请检查网络后重试，"
                        "或按窗口里标注的来源自行下载。"}))

    def _tools_progress(self, frac, text):
        dlg = getattr(self, "tools_dlg", None)
        if not dlg:
            return
        try:
            if not dlg.winfo_exists():
                return
        except tk.TclError:
            return
        if text:
            self.tools_status.set(text)
        bar = self.tools_bar
        if frac is None or frac < 0:
            if str(bar["mode"]) != "indeterminate":
                bar.stop()
                bar.configure(mode="indeterminate")
                bar.start(12)
        else:
            if str(bar["mode"]) != "determinate":
                bar.stop()
                bar.configure(mode="determinate")
            bar["value"] = frac * 100

    def _tools_finished(self, ok, err=""):
        dlg = getattr(self, "tools_dlg", None)
        if not dlg:
            return
        try:
            if not dlg.winfo_exists():
                return
            if ok:
                self.tools_status.set("全部工具已就绪，可以开始下载了！")
                self.tools_bar.stop()
                self.tools_bar.pack_forget()
                self.tools_install_btn.configure(state="disabled")
                dlg.after(1600, dlg.destroy)
            else:
                self.tools_status.set(err or "安装失败。")
                self.tools_bar.pack_forget()
                self.tools_install_btn.configure(state="normal")
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ 收尾
    def _tk_exception(self, exc, val, tb):
        """Tkinter 回调里的异常不会走 sys.excepthook，得单独接。"""
        logging.error("界面回调异常:\n%s",
                      "".join(traceback.format_exception(exc, val, tb)))
        try:
            messagebox.showerror("出错了", "界面操作出错，详情见 logs\\app.log")
        except Exception:
            pass

    def _on_close(self):
        if self.busy and not messagebox.askokcancel(
                "还在下载", "有任务正在下载，确定要退出吗？\n未完成的文件会被删除。"):
            return
        self.alive = False          # 先停掉 after 泵，否则会打在已销毁的窗口上
        try:
            if self.job:
                self.job.cancel_now()
            if self.worker:
                self.worker.join(timeout=3)
        except Exception:
            pass
        try:
            logging.shutdown()
            _log_handle.close()
        except Exception:
            pass
        self.root.destroy()


def _selftest(argv):
    """`--selftest` 无界面自检，返回进程退出码。

    给 CI 用：只有真正跑过冻结产物，才能确认 Playwright 驱动、tkinterdnd2
    原生库、requests 这些「打包时容易静默漏掉」的东西确实进了 exe。
    冻结后 console=False，标准输出会被重定向进日志文件，所以结果同时写一份
    到文件（默认 %TEMP%\\VideoDownloader-selftest.txt，可用
    `--selftest-out <路径>` 指定），CI 读文件即可。
    """
    import tempfile
    import time as _time

    t_selftest = _time.time()
    lines = []
    ok = True

    def check(name, fn):
        nonlocal ok
        t0 = _time.time()
        try:
            fn()
            lines.append(f"PASS  {name}  ({(_time.time() - t0) * 1000:.0f} ms)")
        except Exception as exc:
            ok = False
            lines.append(f"FAIL  {name}: {type(exc).__name__}: {exc}")

    def _requests_ok():
        # 验证 email / http 这些标准库没被 build.spec 的 excludes 误排掉
        import requests          # noqa: F401
        requests.Session()

    def _dnd_ok():
        if not DND_AVAILABLE:
            raise RuntimeError("tkinterdnd2 导入失败（拖拽不可用）")
        import tkinterdnd2
        pkg = os.path.dirname(tkinterdnd2.__file__)
        tkdnd = os.path.join(pkg, "tkdnd")
        if not os.path.isdir(tkdnd):
            raise RuntimeError(f"tkdnd 原生库缺失：{tkdnd}")

    def _playwright_ok():
        # 进入 sync_playwright 就会拉起 node 驱动 —— 驱动没收进包时这里必炸
        from playwright.sync_api import sync_playwright
        with sync_playwright():
            pass

    ytdlp_ver = []

    def _ytdlp_cli_ok():
        # 端到端验证「exe 自己调用自己跑 yt-dlp」这条关键路径：
        # 内置 yt-dlp 之后所有 yt-dlp 平台都走它，漏收模块或分发写错都会在这里暴露。
        if not config.YTDLP_CMD:
            raise RuntimeError("config.YTDLP_CMD 为空（内置 yt-dlp 不可用）")
        import subprocess
        r = subprocess.run(
            list(config.YTDLP_CMD) + ["--version"],
            capture_output=True, timeout=180,
            creationflags=0x08000000 if sys.platform == "win32" else 0)
        out = (r.stdout or b"").decode("utf-8", "replace").strip()
        if r.returncode != 0 or not out:
            raise RuntimeError(
                f"yt-dlp CLI 自调用失败 rc={r.returncode} "
                f"stdout={out[:120]!r} stderr="
                f"{(r.stderr or b'')[:120]!r}")
        ytdlp_ver.append(out.splitlines()[-1])

    check("import requests（email/http 未被误排除）", _requests_ok)
    check("tkinterdnd2 原生库 tkdnd", _dnd_ok)
    check("playwright 驱动可启动", _playwright_ok)
    check("内置 yt-dlp 可执行（exe 自调用）", _ytdlp_cli_ok)

    lines += [
        f"frozen: {getattr(sys, 'frozen', False)}",
        f"base: {config.BASE}",
        f"user data: {config.USER_DATA_DIR}",
        f"yt-dlp: {' '.join(config.YTDLP_CMD) if config.YTDLP_CMD else '(不可用)'}",
        f"yt-dlp 版本: {ytdlp_ver[0] if ytdlp_ver else '(未取到)'}",
        f"ffmpeg dir: {config.FFMPEG_DIR}",
        "--- 启动耗时分解 ---",
        (f"引导程序解压: {(_T_BOOT - _T_MEIPASS_CTIME) * 1000:.0f} ms"
         if _T_MEIPASS_CTIME else "引导程序解压: 不适用（未打包）"),
        f"模块导入: {(t_selftest - _T_BOOT) * 1000:.0f} ms",
        f"自检内部: {(_time.time() - t_selftest) * 1000:.0f} ms",
        f"RESULT: {'PASS' if ok else 'FAIL'}",
    ]
    text = "\n".join(lines) + "\n"

    out = os.path.join(tempfile.gettempdir(), "VideoDownloader-selftest.txt")
    if "--selftest-out" in argv:
        idx = argv.index("--selftest-out")
        if idx + 1 < len(argv):
            out = argv[idx + 1]
    try:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)
    except Exception:
        logging.exception("自检报告写入失败")
    try:
        print(text)
    except Exception:
        pass
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(_selftest(sys.argv))

    _setup_logging()
    logging.info("=== 启动 %s ===", datetime.datetime.now())

    # sys.excepthook 接不到 Tk 回调里的异常，那个走 report_callback_exception
    sys.excepthook = lambda t, v, tb: logging.error(
        "未捕获异常:\n%s", "".join(traceback.format_exception(t, v, tb)))

    _enable_dpi_awareness()

    root = None
    dnd_ok = False
    if DND_AVAILABLE:
        try:
            root = TkinterDnD.Tk()
            dnd_ok = True
        except Exception:
            logging.exception("tkinterdnd2 初始化失败，退回无拖拽模式")
            root = None
    if root is None:
        root = tk.Tk()

    _fix_scaling(root)

    # 首次运行（或须知改版后）先过「使用须知」这道闸：不同意就直接退出。
    # 先 withdraw 再建主界面，避免弹窗背后闪出一个空白窗口。
    # 弹窗自身失败时选择放行 —— 宁可少一层告知，也不能让程序完全打不开。
    root.withdraw()
    if not _disclaimer_accepted():
        try:
            agreed, want_shortcut = _show_disclaimer(root)
        except Exception:
            logging.exception("使用须知弹窗失败，放行以免程序无法启动")
            agreed, want_shortcut = True, False   # 没弹出来就不擅自建快捷方式
        if not agreed:
            logging.info("用户未同意使用须知，程序退出")
            try:
                root.destroy()
            except Exception:
                pass
            return
        _save_disclaimer_accepted()
        if want_shortcut:
            _create_shortcut_quietly()

    App(root, dnd_ok)
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()
