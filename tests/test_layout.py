# -*- coding: utf-8 -*-
"""界面网格布局测试。

回归点：拖拽/输入长链接（如抖音、B站长 URL）时，不能导致所在列（如抖音/微博列）
被单独撑大变形，所有平台格子必须严格等宽等高。
"""
import pytest
import tkinter as tk

main = pytest.importorskip("main")
config = pytest.importorskip("config")


class TestGridLayout:
    def test_grid_uniform_and_equal_widths(self):
        root = tk.Tk()
        try:
            app = main.App(root, dnd_ok=False)
            root.update()

            grid = app.panes["youtube"].master
            for c in range(5):
                info = grid.columnconfigure(c)
                assert info.get("uniform") == "platform_cols", f"col {c} missing uniform"
            for r in range(2):
                info = grid.rowconfigure(r)
                assert info.get("uniform") == "platform_rows", f"row {r} missing uniform"

            # 初始状态所有格子应等宽
            initial_widths = [app.panes[s].winfo_width() for s in config.SOURCES]
            assert max(initial_widths) - min(initial_widths) <= 1

            # 注入抖音链接后，抖音与微博不应撑大，所有格子依然等宽
            app._set_url("https://v.douyin.com/j_T-upAd6lQ/", "douyin")
            root.update()

            widths = [app.panes[s].winfo_width() for s in config.SOURCES]
            assert max(widths) - min(widths) <= 1, f"格子宽度不一致: {widths}"

            heights = [app.panes[s].winfo_height() for s in config.SOURCES]
            assert max(heights) - min(heights) <= 1, f"格子高度不一致: {heights}"
        finally:
            root.destroy()
