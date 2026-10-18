# -*- coding: utf-8 -*-
"""抖音抓流的纯逻辑回归测试（不联网、不起浏览器）。

重点守住 2026-10-18 那次回归：抖音 CDN 改成 HTTP Range 分段请求后返回
**206**，而抓流回调只认 200，导致「页面明明在正常播放，一个流都抓不到」。
"""
import pytest

import douyin


class TestOkStatus:
    def test_accepts_200(self):
        assert 200 in douyin._OK_STATUS

    def test_accepts_206_partial_content(self):
        # 这条是回归点：抖音现在对视频/音频走 Range，返回 206
        assert 206 in douyin._OK_STATUS

    def test_rejects_error_and_redirect(self):
        for bad in (301, 302, 403, 404, 500):
            assert bad not in douyin._OK_STATUS


class TestMediaSize:
    def test_prefers_content_range_total(self):
        # 206 的 content-length 只是这一段，真实总长在 Content-Range 末尾
        headers = {"content-range": "bytes 0-1048575/24848369",
                   "content-length": "1048576"}
        assert douyin._media_size(headers) == 24848369

    def test_falls_back_to_content_length(self):
        assert douyin._media_size({"content-length": "5000"}) == 5000

    def test_handles_missing_headers(self):
        assert douyin._media_size({}) == 0
        assert douyin._media_size(None) == 0

    def test_handles_malformed_content_range(self):
        assert douyin._media_size({"content-range": "bytes */",
                                   "content-length": "12"}) == 12

    def test_handles_non_numeric_content_length(self):
        assert douyin._media_size({"content-length": "abc"}) == 0


class TestLoggedIn:
    """_logged_in 只做 cookie 名匹配，用假上下文验证，不起浏览器。"""

    class _Ctx:
        def __init__(self, cookies):
            self._c = cookies

        def cookies(self):
            return self._c

    def test_true_when_session_cookie_present(self):
        ctx = self._Ctx([{"name": "ttwid", "value": "x"},
                         {"name": "sessionid", "value": "abc"}])
        assert douyin._logged_in(ctx) is True

    def test_false_when_only_guest_cookies(self):
        ctx = self._Ctx([{"name": "ttwid", "value": "x"},
                         {"name": "passport_csrf_token", "value": "y"}])
        assert douyin._logged_in(ctx) is False

    def test_false_on_empty_value(self):
        ctx = self._Ctx([{"name": "sessionid", "value": ""}])
        assert douyin._logged_in(ctx) is False

    def test_false_when_cookies_raises(self):
        class Bad:
            def cookies(self):
                raise RuntimeError("boom")
        assert douyin._logged_in(Bad()) is False
