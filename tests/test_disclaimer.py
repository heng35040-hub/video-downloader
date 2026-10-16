# -*- coding: utf-8 -*-
"""使用须知与桌面快捷方式的纯逻辑测试。

不弹窗、不建真实快捷方式 —— 只覆盖两块无 GUI 依赖的逻辑：
「同意状态的读写」与「快捷方式目标解析」。真正的弹窗与建 .lnk 由人工验证。
"""
import json
import os

import pytest

import config

# main 会 import tkinter；万一环境没有就跳过，不让整份测试变红
main = pytest.importorskip("main", reason="main 依赖 tkinter")


class TestDisclaimerConstants:
    def test_version_not_empty(self):
        assert config.DISCLAIMER_VERSION.strip()

    def test_text_covers_key_clauses(self):
        text = config.DISCLAIMER_TEXT
        for kw in ("个人学习", "版权", "服务条款", "不破解", "自行承担"):
            assert kw in text, f"须知正文缺少关键表述：{kw}"

    def test_title_not_empty(self):
        assert config.DISCLAIMER_TITLE.strip()

    def test_settings_file_under_user_data_dir(self):
        assert os.path.dirname(config.SETTINGS_FILE) == config.USER_DATA_DIR


class TestDisclaimerPersistence:
    @pytest.fixture
    def settings(self, tmp_path, monkeypatch):
        path = tmp_path / "settings.json"
        monkeypatch.setattr(config, "SETTINGS_FILE", str(path))
        return path

    def test_missing_file_means_not_accepted(self, settings):
        assert main._disclaimer_accepted() is False

    def test_save_then_read_back(self, settings):
        main._save_disclaimer_accepted()
        assert main._disclaimer_accepted() is True
        assert config.DISCLAIMER_VERSION in settings.read_text(encoding="utf-8")

    def test_broken_json_means_not_accepted(self, settings):
        settings.write_text("{ 这不是 json", encoding="utf-8")
        assert main._disclaimer_accepted() is False

    def test_old_version_means_not_accepted(self, settings):
        settings.write_text('{"disclaimer_version": "0.0.1"}',
                            encoding="utf-8")
        assert main._disclaimer_accepted() is False

    def test_non_dict_json_means_not_accepted(self, settings):
        settings.write_text('["unexpected"]', encoding="utf-8")
        assert main._disclaimer_accepted() is False

    def test_save_preserves_other_keys(self, settings):
        settings.write_text('{"keep": 1}', encoding="utf-8")
        main._save_disclaimer_accepted()
        data = json.loads(settings.read_text(encoding="utf-8"))
        assert data["keep"] == 1
        assert data["disclaimer_version"] == config.DISCLAIMER_VERSION

    def test_save_creates_file_when_absent(self, settings):
        assert not settings.exists()
        main._save_disclaimer_accepted()
        assert settings.exists()


class TestShortcutTarget:
    def test_returns_existing_target_and_workdir(self):
        target, args, workdir, icon = main._shortcut_target()
        assert os.path.isfile(target), f"目标程序不存在：{target}"
        assert os.path.isdir(workdir), f"工作目录不存在：{workdir}"
        assert icon == target

    def test_dev_mode_points_at_main_py(self):
        # 单元测试一定不是 frozen 环境，走的是源码分支
        assert not getattr(__import__("sys"), "frozen", False)
        _target, args, workdir, _icon = main._shortcut_target()
        assert "main.py" in args
        assert os.path.isfile(os.path.join(workdir, "main.py"))


class TestShortcutExists:
    def test_carries_path(self):
        exc = main.ShortcutExists(r"C:\Users\x\Desktop\视频下载器.lnk")
        assert exc.path.endswith(".lnk")
        assert str(exc).endswith(".lnk")
