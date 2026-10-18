# -*- coding: utf-8 -*-
"""代理解析与透传的纯逻辑测试（不联网、不起浏览器）。

覆盖三类事：
1. 用户手填的代理地址怎么解析（http / socks5h / 裸 host:port / 带认证）
2. 注册表里的 ProxyServer 怎么拆（可能同时有 http= 和 socks=）
3. 用户填的代理有没有真的传给 yt-dlp（下载路径和探测路径都要传）
"""
import pytest

config = pytest.importorskip("config")
backends = pytest.importorskip("backends")


class TestResolveProxy:
    def test_empty_means_autodetect(self):
        proxy, host, port, err = config.resolve_proxy("")
        assert err == ""
        assert proxy == config.PROXY
        assert host == config.PROXY_HOST
        assert port == config.PROXY_PORT

    def test_http_preserved(self):
        assert config.resolve_proxy("http://127.0.0.1:7890")[0] == \
            "http://127.0.0.1:7890"

    def test_socks5_upgraded_to_socks5h(self):
        """socks5 → socks5h：被墙域名得让代理解析 DNS，本地解析不了。"""
        assert config.resolve_proxy("socks5://127.0.0.1:10808")[0] == \
            "socks5h://127.0.0.1:10808"

    def test_socks5h_preserved(self):
        assert config.resolve_proxy("socks5h://127.0.0.1:10808")[0] == \
            "socks5h://127.0.0.1:10808"

    def test_bare_host_port_guesses_scheme_by_port(self):
        """自建 v2ray 默认 1080/10808 是 SOCKS，别逼用户记协议名。"""
        assert config.resolve_proxy("127.0.0.1:10808")[0] == \
            "socks5h://127.0.0.1:10808"
        assert config.resolve_proxy("127.0.0.1:7897")[0] == \
            "http://127.0.0.1:7897"

    def test_credentials_preserved(self):
        got = config.resolve_proxy("socks5://user:pass@10.0.0.1:1080")
        assert got[0] == "socks5h://user:pass@10.0.0.1:1080"
        assert got[1] == "10.0.0.1"
        assert got[2] == 1080

    def test_host_and_port_extracted(self):
        proxy, host, port, err = config.resolve_proxy(
            "socks5h://192.168.1.5:1080")
        assert (host, port, err) == ("192.168.1.5", 1080, "")

    @pytest.mark.parametrize("bad", [
        "ftp://x:1",            # 协议不认识
        "abc",                  # 连端口都没有
        "http://:123",          # 没有主机
        "socks5h://abc:nope",   # 端口不是数字
    ])
    def test_bad_input_returns_error(self, bad):
        proxy, host, port, err = config.resolve_proxy(bad)
        assert proxy is None and err, bad

    def test_strips_surrounding_space(self):
        assert config.resolve_proxy("   ") == config.resolve_proxy("")
        assert config.resolve_proxy("  http://127.0.0.1:7890 ")[0] == \
            "http://127.0.0.1:7890"


class TestSplitServer:
    @pytest.mark.parametrize("raw,expect", [
        ("127.0.0.1:7890", [("http", "127.0.0.1:7890")]),
        ("127.0.0.1:7890;", [("http", "127.0.0.1:7890")]),
        ("http=127.0.0.1:7890;https=127.0.0.1:7890",
         [("http", "127.0.0.1:7890"), ("http", "127.0.0.1:7890")]),
        ("127.0.0.1:7890;socks=127.0.0.1:7891",
         [("http", "127.0.0.1:7890"), ("socks5h", "127.0.0.1:7891")]),
        ("socks=127.0.0.1:7891", [("socks5h", "127.0.0.1:7891")]),
        ("http=", []),                      # 空值要丢掉
        ("", []),
    ])
    def test_split(self, raw, expect):
        assert config._split_server(raw) == expect


class TestBaseArgsProxy:
    def _proxy(self, args):
        i = args.index("--proxy")
        return args[i + 1]

    def test_blocked_platform_uses_given_proxy(self):
        args = backends._base_args("youtube", "/tmp", False, proxy=
                                   "socks5h://127.0.0.1:10808")
        assert self._proxy(args) == "socks5h://127.0.0.1:10808"

    def test_blocked_platform_falls_back_to_detected(self):
        args = backends._base_args("x", "/tmp", False)
        assert self._proxy(args) == config.PROXY

    def test_domestic_platform_always_direct(self):
        """国内站不管用户填什么代理都必须直连，否则必挂。"""
        for source in ("bilibili", "douyin", "kuaishou", "weibo"):
            args = backends._base_args(source, "/tmp", False, proxy=
                                       "socks5h://127.0.0.1:10808")
            assert self._proxy(args) == "", source

    def test_x_instagram_tiktok_use_proxy(self):
        for source in ("x", "instagram", "tiktok"):
            args = backends._base_args(source, "/tmp", False,
                                       proxy="http://127.0.0.1:7890")
            assert self._proxy(args) == "http://127.0.0.1:7890", source
