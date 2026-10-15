# -*- coding: utf-8 -*-
"""errors.py 报错翻译与预检测试。"""
import errors


class TestLastMeaningful:
    def test_picks_last_non_empty_line(self):
        assert errors._last_meaningful("line one\n\nline two\n") == "line two"

    def test_strips_ytdlp_error_prefix(self):
        assert errors._last_meaningful("ERROR: boom") == "boom"

    def test_empty_inputs(self):
        assert errors._last_meaningful("") == ""
        assert errors._last_meaningful(None) == ""

    def test_truncates_overlong_line(self):
        out = errors._last_meaningful("x" * 500)
        assert len(out) == errors._TAIL_LIMIT


class TestFriendly:
    def test_youtube_login_wall(self):
        msg = errors.friendly("Sign in to confirm you're not a bot", "youtube")
        assert "登录验证" in msg

    def test_youtube_video_unavailable(self):
        assert errors.friendly("Video unavailable", "youtube") == \
            "视频不可用或已设为私享。"

    def test_youtube_proxy_hint_mentions_config(self):
        msg = errors.friendly("Connection refused", "youtube")
        assert "config.py" in msg

    def test_x_deleted_post(self):
        assert "不存在" in errors.friendly("404 Not Found", "x")

    def test_x_needs_login(self):
        msg = errors.friendly("Authentication required", "x")
        assert "登录" in msg

    def test_douyin_always_returns_guidance(self):
        msg = errors.friendly("anything at all", "douyin")
        assert "抖音" in msg

    def test_unknown_error_falls_back_to_tail(self):
        msg = errors.friendly("some weird failure", "weibo")
        assert msg == "下载失败：some weird failure"

    def test_empty_raw_gives_unknown(self):
        assert errors.friendly("", "weibo") == "下载失败：未知错误"


class TestCheckPrereqs:
    def test_missing_outdir_is_reported(self, tmp_path):
        missing = str(tmp_path / "does-not-exist")
        msg = errors.check_prereqs("douyin", missing)
        assert msg is not None
        assert "保存目录不存在" in msg

    def test_douyin_with_existing_dir_passes(self, tmp_path):
        # douyin 走 Playwright 解析，不依赖 yt-dlp/ffmpeg，也不校验代理
        assert errors.check_prereqs("douyin", str(tmp_path)) is None
