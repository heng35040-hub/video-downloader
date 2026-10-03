# -*- coding: utf-8 -*-
"""视频下载器 —— Tkinter 界面。

线程约定（很重要）：所有耗时工作都在 worker 线程里，worker 只往队列里塞事件，
绝不碰任何 widget / StringVar。Tkinter 不是线程安全的，违规的表现不是报错，
而是随机死锁或界面半死不活，很难查。
"""
import datetime
import logging
import os
import queue
import sys
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

PANE_IDLE = "#f2f2f2"
PANE_ACTIVE = "#d6e9ff"
PANE_DROP = "#bcdcf5"
PANE_FILLED_BORDER = "#2f7fd0"


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


class App:
    def __init__(self, root, dnd_ok):
        self.root = root
        self.dnd_ok = dnd_ok
        self.q = queue.Queue()
        self.job = None
        self.worker = None
        self.busy = False
        self.alive = True

        self.urls = {s: "" for s in config.SOURCES}
        self.active = "youtube"
        self.panes = {}
        self._last_clip = ""
        self._downloading_pane = None

        self.entry_var = tk.StringVar()
        self.outdir_var = tk.StringVar(value=config.OUTDIR_DEFAULT)
        self.cookie_var = tk.BooleanVar(value=False)
        self.quality_var = tk.StringVar(value=config.QUALITY_OPTIONS[0])
        self.status_var = tk.StringVar(value="")
        self.detail_var = tk.StringVar(value="")
        self.percent_var = tk.StringVar(value="0%")

        self._build()
        self._select("youtube")
        self._pump()
        self.root.after(500, self._watch_clipboard)
        self._hint()
        self.root.after(700, self._check_missing_tools)
        self.root.after(2500, self._bg_selfupdate)

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

        # B站 cookies 勾选不常驻 —— 只在 B站格子激活时出现（见 _update_cookie_cb）
        self.cookie_cb = ttk.Checkbutton(
            outer, variable=self.cookie_var,
            text="B站使用登录信息（可解锁更高画质；需先导入 cookies）")

        ttk.Separator(outer).pack(fill="x", pady=10)

        # ---- 保存位置 ----
        out_row = ttk.Frame(outer)
        out_row.pack(fill="x")
        ttk.Label(out_row, text="保存到：").pack(side="left")
        ttk.Entry(out_row, textvariable=self.outdir_var).pack(
            side="left", fill="x", expand=True, padx=4)
        ttk.Button(out_row, text="浏览…", command=self._browse).pack(side="left")

        btns = ttk.Frame(outer)
        btns.pack(fill="x", pady=10)
        ttk.Label(btns, text="画质：").pack(side="left")
        ttk.Combobox(btns, textvariable=self.quality_var,
                     values=config.QUALITY_OPTIONS, state="readonly",
                     width=6).pack(side="left", padx=(0, 10))
        self.go_btn = ttk.Button(btns, text="下  载", command=self._start)
        self.go_btn.pack(side="left")
        self.cancel_btn = ttk.Button(btns, text="取消", command=self._cancel,
                                     state="disabled")
        self.cancel_btn.pack(side="left", padx=6)
        ttk.Button(btns, text="清空", command=self._clear).pack(side="left", padx=6)

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

        # 支持作者（自愿）：config.DONATE_URL 留空则完全不显示
        if config.DONATE_URL:
            import webbrowser
            bottom = ttk.Frame(outer)
            bottom.pack(fill="x")
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
            self.cookie_cb.pack(anchor="w", pady=(6, 0), after=self.entry_row)
        else:
            self.cookie_cb.pack_forget()

    def _hint(self):
        if not self.dnd_ok:
            self.status_var.set("拖拽组件没装上 —— 点格子后粘贴链接一样能用。")

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
        path = filedialog.askdirectory(title="选择保存位置",
                                       initialdir=self.outdir_var.get() or "./")
        if path:
            self.outdir_var.set(os.path.normpath(path))

    def _clear(self):
        self.urls = {s: "" for s in config.SOURCES}
        self.entry_var.set("")
        self.status_var.set("")
        self.detail_var.set("")
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
        tasks = [(s, self.urls[s]) for s in config.SOURCES if self.urls[s]]
        if not tasks:
            messagebox.showinfo("还没有链接", "先把视频链接拖进格子，或复制链接后回来。")
            return

        # 先把所有界面变量的值取出来再交给 worker —— worker 不许碰 Tk
        outdir = self.outdir_var.get()
        use_cookies = bool(self.cookie_var.get())
        max_height = config.QUALITY_HEIGHT.get(self.quality_var.get())

        self.busy = True
        self.go_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.job = backends.Job()
        self.worker = threading.Thread(
            target=self._run_tasks,
            args=(tasks, outdir, use_cookies, max_height), daemon=True)
        self.worker.start()

    def _run_tasks(self, tasks, outdir, use_cookies, max_height=None):
        def emit(kind, **kw):
            self.q.put((kind, kw))

        try:
            for i, (source, url) in enumerate(tasks, 1):
                if self.job.cancel.is_set():
                    break
                tag = f"[{i}/{len(tasks)}] {config.SOURCE_LABEL[source]}"
                emit("status", text=f"{tag} 开始…")
                emit("progress", frac=-1.0, text="")
                emit("pane", source=source, text="下载中…")

                problem = errors.check_prereqs(
                    source, outdir, config.COOKIES_BILI, use_cookies,
                    config.PROXY_HOST, config.PROXY_PORT)
                if problem:
                    emit("failed", source=source, text=problem)
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
                        max_height)

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
            path = kw.get("text", "")
            self.panes[kw["source"]].configure(bg="#d8f5d8")
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
            self.panes[kw["source"]].configure(bg="#ffd9d9")
            self.detail_var.set("失败：" + (kw.get("text") or "").splitlines()[0])
            logging.warning("FAIL %s: %s", kw["source"], kw.get("text"))
            # 主动取消不算失败，别弹错误框吓人
            if (kw.get("text") or "").strip() != "已取消":
                messagebox.showerror(
                    config.SOURCE_LABEL[kw["source"]] + " 下载失败",
                    kw.get("text", ""))
        elif kind == "crash":
            logging.error("worker 崩溃:\n%s", kw.get("text"))
            messagebox.showerror("程序出错",
                                 "下载线程出错了，详情见 logs\\app.log")
        elif kind == "finished":
            self.busy = False
            self.go_btn.configure(state="normal")
            self.cancel_btn.configure(state="disabled")
            self._set_progress(0.0)
            if self.status_var.get().startswith("["):
                self.status_var.set("全部结束")

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


def main():
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
    App(root, dnd_ok)
    root.mainloop()


if __name__ == "__main__":
    main()
