# -*- coding: utf-8 -*-
"""状态栏收尾文案的纯逻辑测试（不建窗口、不联网）。

回归点：旧实现用 `status_var.get().startswith("[")` 判断「任务是否还没开始」，
后端只要中途改过状态（抖音会发「拿到直链，开始下载…」），判断就失效 ——
视频已经下完，状态栏还挂着那句话。
"""
import pytest

main = pytest.importorskip("main")


class TestSummaryStatus:
    def test_all_success(self):
        assert main._summary_status(1, 0, False) == "全部完成"

    def test_multi_success(self):
        assert main._summary_status(3, 0, False) == "全部完成"

    def test_all_failed(self):
        assert main._summary_status(0, 1, False) == "全部失败"

    def test_mixed(self):
        assert main._summary_status(1, 1, False) == "完成 1 个，失败 1 个"

    def test_nothing_ran(self):
        # 一个任务都没跑（比如预检就退出）时不该留下任何残留文案
        assert main._summary_status(0, 0, False) == ""

    def test_cancelled_without_progress(self):
        assert main._summary_status(0, 0, True) == "已取消"

    def test_cancelled_after_partial_success(self):
        assert main._summary_status(2, 0, True) == "已取消（本轮完成 2 个）"

    def test_cancelled_wins_over_failure(self):
        # 取消优先于失败展示 —— 用户主动取消，别报「全部失败」吓人
        assert main._summary_status(1, 1, True) == "已取消（本轮完成 1 个）"

    @pytest.mark.parametrize("done,fail,cancelled", [
        (1, 0, False), (0, 1, False), (1, 1, False),
        (0, 0, False), (0, 0, True), (2, 0, True),
    ])
    def test_never_empty_when_work_happened(self, done, fail, cancelled):
        """只要有任务跑过，就必须给出一句非空文案 —— 不能留旧状态在屏幕上。"""
        if done or fail or cancelled:
            assert main._summary_status(done, fail, cancelled) != ""
