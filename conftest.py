# -*- coding: utf-8 -*-
"""pytest 配置。

把仓库根目录加入 sys.path，让测试可以直接 ``import config`` / ``import errors``，
无需把项目安装成包。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
