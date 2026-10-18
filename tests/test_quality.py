# -*- coding: utf-8 -*-
"""画质下拉框标签规则的纯逻辑测试（不建窗口、不联网）。

规则：按视频**实际支持**的画质生成选项；B站未登录时 1080P 及以上要标
「（需登录）」—— 否则用户选了 1080P 却下不动，完全不知道为什么。
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

    def test_bilibili_marks_1080_and_above_when_not_logged_in(self):
        got = [p[0] for p in main._quality_labels("bilibili", [1080, 720, 480])]
        assert "1080p（需登录）" in got
        assert "720p" in got
        assert "480p" in got

    def test_bilibili_does_not_mark_when_logged_in(self):
        got = [p[0] for p in main._quality_labels("bilibili", [1080, 720],
                                                  logged=True)]
        assert not any("需登录" in x for x in got)
        assert "1080p" in got

    def test_other_platforms_never_marked(self):
        got = [p[0] for p in main._quality_labels("youtube", [2160, 1080])]
        assert not any("需登录" in x for x in got)

    def test_height_mapping_is_preserved(self):
        # 带后缀的标签也要能反查到高度，否则 _start 取不到 max_height
        pairs = dict(main._quality_labels("bilibili", [1080, 720]))
        assert pairs["1080p（需登录）"] == 1080
        assert pairs["720p"] == 720
        assert pairs["最高"] is None

    def test_deduplicates_by_construction(self):
        # 同一高度在 yt-dlp 里会有多条编码格式，调用方已去重；
        # 这里确认重复输入不会崩
        got = main._quality_labels("youtube", [720, 720])
        assert [p[0] for p in got].count("720p") == 2
