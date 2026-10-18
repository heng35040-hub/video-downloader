# -*- coding: utf-8 -*-
"""B站登录导出 cookies 的纯逻辑测试（不起浏览器、不联网）。

Netscape cookies.txt 的格式细节很容易错（制表符分隔、HttpOnly 前缀、
会话 cookie 的过期时间），而错了 yt-dlp 会静默读不到登录态 —— 所以单测守住。
"""
import pytest

bililogin = pytest.importorskip("bililogin")

SAMPLE = [
    {"name": "SESSDATA", "value": "abc%2C123", "domain": ".bilibili.com",
     "path": "/", "expires": 1790000000, "httpOnly": True, "secure": True},
    {"name": "bili_jct", "value": "deadbeef", "domain": ".bilibili.com",
     "path": "/", "expires": -1, "httpOnly": False, "secure": False},
    {"name": "buvid3", "value": "guest", "domain": "www.bilibili.com",
     "path": "/", "expires": 0, "httpOnly": False, "secure": False},
]


class TestHasLogin:
    def test_true_with_sessdata(self):
        assert bililogin.has_login(SAMPLE) is True

    def test_false_for_guest_only(self):
        assert bililogin.has_login(
            [{"name": "buvid3", "value": "x"}]) is False

    def test_false_when_sessdata_empty(self):
        assert bililogin.has_login(
            [{"name": "SESSDATA", "value": ""}]) is False

    def test_false_for_empty_input(self):
        assert bililogin.has_login([]) is False
        assert bililogin.has_login(None) is False


class TestToNetscape:
    def test_header_present(self):
        assert bililogin.to_netscape(SAMPLE).startswith(
            "# Netscape HTTP Cookie File")

    def test_tab_separated(self):
        # 用空格分隔 yt-dlp 会读不出来，必须制表符
        row = [ln for ln in bililogin.to_netscape(SAMPLE).splitlines()
               if "SESSDATA" in ln][0]
        assert row.count("\t") == 6

    def test_httponly_prefix(self):
        assert "#HttpOnly_.bilibili.com" in bililogin.to_netscape(SAMPLE)

    def test_subdomain_flag(self):
        text = bililogin.to_netscape(SAMPLE)
        assert "\tTRUE\t/\tTRUE\t1790000000\tSESSDATA\t" in text
        # 没有前导点的域，第二列应为 FALSE
        assert "www.bilibili.com\tFALSE\t/" in text

    def test_session_cookie_expiry_zero(self):
        # Playwright 用 -1 表示会话 cookie，Netscape 格式要写 0
        text = bililogin.to_netscape(SAMPLE)
        assert "\t0\tbili_jct\t" in text

    def test_skips_entries_without_domain_or_name(self):
        text = bililogin.to_netscape(
            [{"name": "x", "value": "1", "domain": ""},
             {"name": "", "value": "1", "domain": ".b.com"}])
        assert "x\t" not in text

    def test_handles_missing_fields(self):
        text = bililogin.to_netscape([{"name": "a", "value": "b",
                                       "domain": ".b.com"}])
        assert ".b.com\tTRUE\t/\tFALSE\t0\ta\tb" in text


class TestSaveCookies:
    def test_writes_file_and_no_tmp_left(self, tmp_path):
        dest = tmp_path / "cookies" / "bilibili.txt"
        path = bililogin.save_cookies(SAMPLE, str(dest))
        assert path == str(dest)
        assert dest.is_file()
        assert "SESSDATA" in dest.read_text(encoding="utf-8")
        assert not (tmp_path / "cookies" / "bilibili.txt.tmp").exists()

    def test_creates_missing_dir(self, tmp_path):
        dest = tmp_path / "deep" / "nested" / "b.txt"
        bililogin.save_cookies(SAMPLE, str(dest))
        assert dest.is_file()
