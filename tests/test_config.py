# -*- coding: utf-8 -*-
"""config.py 纯逻辑单元测试。

覆盖 URL 抠取、平台识别、显示裁剪与平台表一致性 —— 全部无网络、无副作用。
"""
import os
import sys

import config


class TestDetectSource:
    def test_youtube(self):
        assert config.detect_source(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "youtube"
        assert config.detect_source("https://youtu.be/dQw4w9WgXcQ") == "youtube"

    def test_bilibili(self):
        assert config.detect_source(
            "https://www.bilibili.com/video/BV1GJ411x7h7") == "bilibili"
        assert config.detect_source("https://b23.tv/abc123") == "bilibili"

    def test_douyin(self):
        assert config.detect_source("https://v.douyin.com/iRNBho6/") == "douyin"
        assert config.detect_source(
            "https://www.douyin.com/music/7149936801028131598") == "douyin"

    def test_x_includes_legacy_twitter_and_shortlink(self):
        assert config.detect_source("https://x.com/user/status/123") == "x"
        assert config.detect_source("https://twitter.com/user/status/123") == "x"
        assert config.detect_source("https://t.co/abc") == "x"

    def test_instagram(self):
        assert config.detect_source(
            "https://www.instagram.com/reel/Chunk8-jurw/") == "instagram"

    def test_kuaishou(self):
        assert config.detect_source(
            "https://www.kuaishou.com/short-video/3xwrzgsfd5fyjyg") == "kuaishou"

    def test_xiaohongshu(self):
        assert config.detect_source(
            "https://www.xiaohongshu.com/explore/6411cf99") == "xiaohongshu"
        assert config.detect_source("https://xhslink.com/a/b") == "xiaohongshu"

    def test_weibo(self):
        assert config.detect_source("https://m.weibo.cn/detail/512056") == "weibo"
        assert config.detect_source("https://t.cn/abc") == "weibo"

    def test_ixigua_and_tiktok(self):
        assert config.detect_source("https://www.ixigua.com/123") == "ixigua"
        assert config.detect_source(
            "https://www.tiktok.com/@nasa/video/7664638705177150477") == "tiktok"

    def test_unknown_returns_none(self):
        assert config.detect_source("https://example.com/video") is None

    def test_empty_and_none(self):
        assert config.detect_source("") is None
        assert config.detect_source(None) is None

    def test_case_insensitive(self):
        assert config.detect_source(
            "HTTPS://WWW.YOUTUBE.COM/WATCH?V=ABC") == "youtube"


class TestExtractUrl:
    def test_plain_url(self):
        url = "https://www.bilibili.com/video/BV1GJ411x7h7"
        assert config.extract_url(url) == url

    def test_douyin_share_text(self):
        text = "7.36 复制打开抖音，看看【某某的作品】 https://v.douyin.com/iRNBho6/ 看看"
        assert config.extract_url(text) == "https://v.douyin.com/iRNBho6/"

    def test_strips_trailing_cjk_punctuation(self):
        assert config.extract_url(
            "看这个 https://x.com/a/status/1。") == "https://x.com/a/status/1"

    def test_strips_trailing_ascii_punctuation(self):
        assert config.extract_url(
            "链接：https://youtu.be/abc123,") == "https://youtu.be/abc123"

    def test_first_url_wins(self):
        text = "https://a.example.com/1 和 https://b.example.com/2"
        assert config.extract_url(text) == "https://a.example.com/1"

    def test_no_url(self):
        assert config.extract_url("这里没有链接") is None
        assert config.extract_url("") is None
        assert config.extract_url(None) is None

    def test_douyin_share_blob_with_hashtags(self):
        # 真实抖音分享文案：口令 + 标题 + 一堆话题 + 链接 + 引导语。
        # 用户直接 Ctrl+V 粘进输入框时，必须能从中抠出唯一那条链接。
        blob = ("7.69 11/24 t@r.rE eod:/ :1pm 三小只一起参加抖音创大了！ "
                "# 三角洲出征创大排面这一块 2026# 抖音创作者大会 # 抖音游戏 "
                "# 三角洲行动  https://v.douyin.com/I4oCZy1yGc4/ "
                "复制此链接，打开Dou音搜索，直接观看视频！")
        assert config.extract_url(blob) == "https://v.douyin.com/I4oCZy1yGc4/"
        assert config.detect_source(blob) == "douyin"


class TestDisplayUrl:
    def test_short_unchanged(self):
        assert config.display_url("https://x.com/a") == "https://x.com/a"

    def test_long_truncated_to_limit(self):
        url = "https://example.com/" + "a" * 200
        out = config.display_url(url, limit=72)
        assert len(out) == 72
        assert out.endswith("…")

    def test_exactly_at_limit_unchanged(self):
        url = "x" * 72
        assert config.display_url(url, limit=72) == url

    def test_empty(self):
        assert config.display_url("") == ""
        assert config.display_url(None) == ""


class TestPlatformTables:
    def test_every_source_has_a_label(self):
        assert set(config.SOURCES) == set(config.SOURCE_LABEL)

    def test_quality_tables_agree(self):
        assert set(config.QUALITY_OPTIONS) == set(config.QUALITY_HEIGHT)

    def test_top_quality_means_no_height_filter(self):
        assert config.QUALITY_HEIGHT["最高"] is None

    def test_quality_heights_are_ints(self):
        for name, height in config.QUALITY_HEIGHT.items():
            if height is not None:
                assert isinstance(height, int)

    def test_outdir_default_is_absolute(self):
        assert os.path.isabs(config.OUTDIR_DEFAULT)

    def test_tools_dir_under_user_data_dir(self):
        assert config.TOOLS_DIR.startswith(config.USER_DATA_DIR)


class TestBundledYtdlp:
    """内置 yt-dlp 的命令行解析 —— 不联网、不起子进程，纯逻辑。"""

    def test_bundled_module_is_importable(self):
        # requirements.txt 把 yt-dlp 列为依赖，装了就一定能 import
        import yt_dlp  # noqa: F401

    def test_cmd_is_a_list_and_available(self):
        assert config.ytdlp_available()
        assert isinstance(config.YTDLP_CMD, list)
        assert config.YTDLP_CMD, "YTDLP_CMD 不能为空"

    def test_dev_mode_uses_module_invocation(self):
        # 未打包时应当用「当前解释器 -m yt_dlp」，而不是外置 exe
        if not getattr(sys, "frozen", False):
            assert config.YTDLP_CMD[0] == sys.executable
            assert config.YTDLP_CMD[1:3] == ["-m", "yt_dlp"]

    def test_ffmpeg_dir_is_absolute(self):
        assert os.path.isabs(config.FFMPEG_DIR)

    def test_backend_args_start_with_ytdlp_cmd(self):
        # backends 必须把 YTDLP_CMD 原样放在参数最前面，
        # 否则内置/外置切换会静默失效
        import backends
        args = backends._base_args("bilibili", ".", False, None)
        assert args[:len(config.YTDLP_CMD)] == config.YTDLP_CMD
