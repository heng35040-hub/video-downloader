# -*- coding: utf-8 -*-
"""画质下拉框标签规则 + yt-dlp 报错精简的纯逻辑测试（不建窗口、不联网）。

回归点：曾经按「B站 1080P 起要登录」的常识给 1080p 加了「（需登录）」后缀，
实测是错的 —— 未登录用 `bv*[height<=1080]+ba` 能把 1080P 下完。标错了比不标
更误导，所以现在只列实测可用的画质，一律不加「需登录」。
"""
import pytest

main = pytest.importorskip("main")
import config  # noqa: E402


class TestQualityLabels:
    def test_always_starts_with_max(self):
        for heights in (None, [], [720], [2160, 1080]):
            assert main._quality_labels("bilibili", heights)[0] == ("最高", None)

    def test_falls_back_to_static_list(self):
        got = [p[0] for p in main._quality_labels("bilibili", None)]
        assert got == ["最高"] + list(config.QUALITY_OPTIONS[1:])

    def test_uses_probed_heights(self):
        got = main._quality_labels("youtube", [2160, 1440, 1080])
        assert got == [("最高", None), ("2160p", 2160),
                       ("1440p", 1440), ("1080p", 1080)]

    def test_never_marks_login_required(self):
        """任何平台、任何高度都不该出现「需登录」后缀。"""
        for source in ("bilibili", "youtube", "x", "weibo"):
            for heights in ([2160, 1080, 720], None):
                labels = [p[0] for p in main._quality_labels(source, heights)]
                assert not any("需登录" in x for x in labels), (source, heights)

    def test_height_mapping_is_preserved(self):
        pairs = dict(main._quality_labels("bilibili", [1080, 720]))
        assert pairs["1080p"] == 1080
        assert pairs["720p"] == 720
        assert pairs["最高"] is None

    def test_preserves_given_order(self):
        # 调用方已按从高到低排好，这里不再重排
        got = [p[1] for p in main._quality_labels("bilibili", [1080, 720, 480])]
        assert got == [None, 1080, 720, 480]


class TestShortErr:
    """yt-dlp 的报错要压成一句能塞进状态栏的话。"""

    def _err(self, text):
        backends = pytest.importorskip("backends")
        return backends._short_err(text.encode("utf-8"))

    def test_strips_error_prefix(self):
        assert self._err("ERROR: something went wrong\n") == "something went wrong"

    def test_strips_platform_prefix(self):
        got = self._err(
            "ERROR: [BiliBili] 1VEJQ6DEHk: This video may be deleted "
            "or geo-restricted.\n")
        assert got.startswith("This video may be deleted")
        assert "[" not in got

    def test_takes_last_nonempty_line(self):
        assert self._err("WARNING: x\nERROR: 真正的原因\n\n") == "真正的原因"

    def test_truncates(self):
        assert len(self._err("ERROR: " + "啊" * 500)) <= 120

    def test_empty_input(self):
        assert self._err("") == "未知原因"
