# -*- coding: utf-8 -*-
"""片段下载：时间解析与 yt-dlp 参数测试（纯逻辑，不联网）。"""
import pytest

main = pytest.importorskip("main")
backends = pytest.importorskip("backends")


class TestParseTime:
    @pytest.mark.parametrize("text,expect", [
        ("90", 90),
        ("0", 0),
        ("1:30", 90),
        ("01:30", 90),
        ("1:02:03", 3723),
        (" 01:30 ", 90),
        ("01：30", 90),          # 全角冒号（中文输入法很容易打出来）
        ("1:59", 119),
    ])
    def test_valid(self, text, expect):
        assert main.parse_time(text) == expect

    @pytest.mark.parametrize("bad", ["", None, "abc", "1:60", "1:2:3:4",
                                     "01:60:00", "01:02:60", "-5", "1.5"])
    def test_invalid(self, bad):
        assert main.parse_time(bad) is None


class TestSectionArgs:
    def _flag(self, args):
        i = args.index("--download-sections")
        return args[i + 1]

    def test_start_and_end(self):
        args = backends._base_args("bilibili", "/tmp", False,
                                   section=(90, 180))
        assert self._flag(args) == "*90-180"

    def test_empty_end_means_inf(self):
        # 结束留空 = 从开始一直下到片尾
        args = backends._base_args("youtube", "/tmp", False, section=(90, None))
        assert self._flag(args) == "*90-inf"

    def test_no_section_no_flag(self):
        args = backends._base_args("youtube", "/tmp", False)
        assert "--download-sections" not in args

    def test_zero_start(self):
        args = backends._base_args("x", "/tmp", False, section=(0, 30))
        assert self._flag(args) == "*0-30"
