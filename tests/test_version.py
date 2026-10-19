# -*- coding: utf-8 -*-
"""版本号唯一来源的守卫测试。

背景：版本号曾经要手抄五处（config + build.spec 四处）。漏一处程序照跑、
190 项测试照过，只有用户会遇到问题 —— 曾经 v2026.10.16 的 exe 里嵌的
还是 2026.10.15.0，用户报版本号时根本对不上。

现在唯一来源是 version.py，这里守住三件事：
1. 格式合法（四段数字）
2. config.VERSION 就是它（re-export 没写错）
3. build.spec 里不许再出现硬编码的版本号字面量
"""
import re
from pathlib import Path

import config
import version

SPEC = Path(__file__).resolve().parent.parent / "build.spec"


class TestVersionSource:
    def test_format_is_four_numeric_parts(self):
        parts = version.VERSION.split(".")
        assert len(parts) == 4, "版本号必须是四段：YYYY.MM.DD.N"
        assert all(p.isdigit() for p in parts), "每段都必须是数字"

    def test_config_reexports_same_value(self):
        # config 里是 `from version import VERSION`，写错名字就会静默不一致
        assert config.VERSION == version.VERSION

    def test_build_spec_has_no_hardcoded_version(self):
        text = SPEC.read_text(encoding="utf-8")
        # 注释里保留历史事故的版本号（如 2026.10.15.0）是有价值的文档，
        # 只检查可执行代码部分
        code = "\n".join(line for line in text.splitlines()
                         if not line.strip().startswith("#"))
        found = re.search(r"\b20\d{2}\.\d{1,2}\.\d{1,2}\.\d{1,2}\b", code)
        assert not found, (
            f"build.spec 里又出现硬编码版本号 {found.group(0)!r} —— "
            "请改回从 version.py 读取")

    def test_build_spec_reads_from_version_module(self):
        text = SPEC.read_text(encoding="utf-8")
        assert "import version" in text
        assert "VERSION_TUPLE" in text, "filevers/prodvers 应从 version 派生"
        assert "VERSION_STR" in text, "FileVersion/ProductVersion 应从 version 派生"
