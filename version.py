# -*- coding: utf-8 -*-
"""版本号唯一来源。

**只放常量，不写任何代码。** 这个模块会被两处导入：
- config.py（运行期判断「我是谁」）
- build.spec（构建期生成 exe 的版本资源）

所以它必须没有任何副作用 —— 不能建目录、不能探测代理、不能读环境变量。
config.py 导入时会做那些事，因此 build.spec 绝不能直接 import config。
"""

VERSION = "2026.10.18.9"
