# -*- coding: utf-8 -*-
"""设置持久化：保存位置记住 / 失效回退（不碰真实 settings.json）。"""
import pytest

main = pytest.importorskip("main")


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(main.config, "SETTINGS_FILE",
                        str(tmp_path / "settings.json"))
    return tmp_path


class TestOutdirSetting:
    def test_no_setting_returns_empty(self, isolated_settings):
        assert main._load_outdir_setting() == ""

    def test_roundtrip(self, isolated_settings):
        d = isolated_settings / "videos"
        d.mkdir()
        main._save_outdir_setting(str(d))
        assert main._load_outdir_setting() == str(d)

    def test_missing_dir_falls_back(self, isolated_settings):
        # 用户删了文件夹、拔了移动硬盘：必须回退默认值，
        # 不能拿着一个不存在的路径启动，等到下载时才报错
        main._save_outdir_setting(str(isolated_settings / "gone"))
        assert main._load_outdir_setting() == ""

    def test_empty_value_clears(self, isolated_settings):
        d = isolated_settings / "videos"
        d.mkdir()
        main._save_outdir_setting(str(d))
        main._save_outdir_setting("")
        assert main._load_outdir_setting() == ""

    def test_other_settings_preserved(self, isolated_settings):
        # 写 outdir 不能把 proxy、同意状态这些冲掉（整体写回容易踩这个坑）
        main._save_proxy_setting("http://127.0.0.1:7897")
        d = isolated_settings / "videos"
        d.mkdir()
        main._save_outdir_setting(str(d))
        data = main._load_settings()
        assert data["proxy"] == "http://127.0.0.1:7897"
        assert data["outdir"] == str(d)
