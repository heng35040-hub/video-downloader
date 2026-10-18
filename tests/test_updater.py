# -*- coding: utf-8 -*-
"""版本号解析/比较与更新检查测试（纯逻辑，不联网）。"""
import pytest

updater = pytest.importorskip("updater")


class TestParseVersion:
    @pytest.mark.parametrize("text,expect", [
        ("2026.10.18.4", (2026, 10, 18, 4)),
        ("v2026.10.19", (2026, 10, 19)),
        (" V2026.10.19 ", (2026, 10, 19)),
        ("2026", (2026,)),
    ])
    def test_valid(self, text, expect):
        assert updater.parse_version(text) == expect

    @pytest.mark.parametrize("bad", ["", None, "v", "abc",
                                     "2026.a.1", "2026..1", "2026.10.x"])
    def test_invalid(self, bad):
        assert updater.parse_version(bad) is None


class TestIsNewer:
    def test_shorter_remote_is_newer(self):
        # 2026.10.19 > 2026.10.18.4：长度不同必须补零比较
        assert updater.is_newer("2026.10.19", "2026.10.18.4")

    def test_equal_is_not_newer(self):
        assert not updater.is_newer("2026.10.18.4", "2026.10.18.4")

    def test_older_is_not_newer(self):
        assert not updater.is_newer("2026.10.18.3", "2026.10.18.4")

    def test_numeric_not_string_compare(self):
        # 按字符串比 "2026.10.9" > "2026.10.10"（错）；按数字比才对
        assert updater.is_newer("2026.10.10", "2026.10.9")
        assert not updater.is_newer("2026.10.9", "2026.10.10")

    def test_invalid_never_newer(self):
        assert not updater.is_newer(None, "2026.10.18.4")
        assert not updater.is_newer("garbage", "2026.10.18.4")
        assert not updater.is_newer("2026.10.19", "")


class TestCheck:
    def test_empty_url_returns_none(self):
        assert updater.check("", "2026.10.18.4") is None

    def test_unreachable_url_returns_none(self):
        # 连不上必须静默返回 None，绝不抛异常打断调用方
        assert updater.check("http://127.0.0.1:1/version.json",
                             "2026.10.18.4", timeout=0.5) is None
