# 贡献指南

欢迎贡献！本项目是一个**个人学习/研究用途**的视频下载工具，遵循 MIT 协议开源。

---

## 🎯 贡献方向（欢迎）

| 类型 | 例子 |
|------|------|
| **平台修复** | 某站反爬更新导致下载失败，修复提取器（`backends.py` / `douyin.py` / `kuaishou.py`） |
| **冒烟测试链接更新** | `smoke_test.py` 里的固定链接失效（SKIP 变常驻），换新公开链接 |
| **代理/网络兼容性** | 新代理软件端口支持、系统代理探测增强、IPv6 兼容 |
| **UI/交互改进** | 进度条、拖拽、剪贴板监听、多语言、无障碍 |
| **打包/分发** | PyInstaller 配置、便携版、Windows 安装包、Scoop/WinGet 清单 |
| **文档/翻译** | README 多语言、ARCHITECTURE.md 补充、错误信息本地化 |
| **测试/CI** | 新平台冒烟用例、边缘情况覆盖、性能基准 |

---

## ❌ 不接受的方向

| 方向 | 理由 |
|------|------|
| 批量/并发下载器 | 法律风险 + 封禁风险陡增，个人工具不需要 |
| 破解 DRM/付费/会员内容 | 违反平台 ToS 与版权法，作者不背锅 |
| 接入验证码打码平台 | 灰产链条，拒绝 |
| 云同步/账号系统/遥测 | 违背「零遥测、零上报、本地优先」核心原则 |
| 非 Windows 平台主流支持 | 代码强依赖 Windows 注册表代理探测、taskkill、CREATE_NO_WINDOW 等；欢迎抽象层 PR 但不承诺维护 |

---

## 🛠️ 开发环境搭建

```bash
# 1. 克隆
git clone https://github.com/heng35040-hub/video-downloader.git
cd video-downloader

# 2. Python 3.10+（勾选 Add to PATH，自带 tkinter）
# 3. 装依赖（yt-dlp 也在其中，程序内置使用，不需要额外下载）
pip install -r requirements.txt

# 4. 运行
python main.py
```

> 抖音不需要 `playwright install chromium`：程序会直接用系统自带的
> Edge / Chrome（`douyin.py` 的 `_BROWSER_CHANNELS`）。

**首次启动**：yt-dlp 已经随依赖装好；程序只会自检 `ffmpeg`，缺了会弹窗 →
点「一键下载并配置」即可（装进 `tools/` 立即生效）。

---

## 🧪 测试

```bash
# 全部平台冒烟测试（需代理 + 网络通）
python smoke_test.py

# 单平台测试
python smoke_test.py kuaishou douyin

# 结果三档：
# ✅ PASS   下载成功
# ⏭ SKIP   链接失效/内容被删/环境不具备（非程序锅）
# ❌ FAIL   解析或下载失败 —— 很可能反爬变了，需要修
```

**注意**：GitHub Actions runner 在海外，YouTube/X/TikTok 直连没问题；国内平台（抖音/快手等）从海外访问表现与国内不同，若 CI 誤報，以本地跑 `python smoke_test.py` 为准。

---

## 📝 代码规范

| 规范 | 说明 |
|------|------|
| **编码** | UTF-8，文件头 `# -*- coding: utf-8 -*-` |
| **类型提示** | 关键函数建议加类型注解（Python 3.10+ 支持 `\|` 语法） |
| **线程安全** | **Worker 线程绝不碰 Tkinter 对象** —— 只往队列塞事件，主线程 `_pump` 统一消费 |
| **异常处理** | 捕获具体异常，`logging.exception` 记录堆栈，用户侧给友好提示（见 `errors.friendly`） |
| **安全闸** | 任何新增外发网络请求，必须走 `toolssetup._assert_public_host` 或同等校验 |
| **注释风格** | 模块 docstring：英文 + 一句中文摘要；核心非显而易见决策：代码旁简洁注释；完整踩坑记录：迁移至 `docs/ARCHITECTURE.md` |

---

## 🔀 PR 流程

1. **Fork** → 新建分支 `fix/xxx` 或 `feat/xxx`
2. **本地跑通** `python smoke_test.py`（相关平台至少 PASS）
3. **提交 PR**，描述：
   - 解决什么问题
   - 怎么测试的
   - 是否涉及安全/隐私变更
4. **CI 过**（GitHub Actions 自动跑冒烟测试）
5. **Review 合并**

---

## 🏷️ 版本发布

- **无固定发布周期**，有实质修复/功能时打 Tag
- Tag 格式：`vYYYY.MM.DD`（如 `v2026.10.15`）
- `CHANGELOG.md` 由维护者手工维护

---

## 📄 许可证

贡献代码即视为同意以 **MIT License** 授权（同项目主协议）。

---

## 💬 沟通渠道

- **GitHub Issues**：Bug 报告、功能建议、冒烟测试链接更新
- **GitHub Discussions**：用法交流、经验分享
- **不提供**：微信群、QQ 群、邮件列表、商业支持

---

*保持简单、保持本地、保持自由。* 🎬