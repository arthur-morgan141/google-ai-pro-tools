# Google AI Pro / Ultra Trial Studio · 双平台智能可视化领航版

- 📖 **技术博客**：https://blog.caowo.de/
- 🛒 **发卡网（仅提供 GPT 代充）**：https://faka.cdkey.si/
- 🩺 **排错与网络手册**：[常见问题与网络环境自查手册.md](file:///Users/yanling/Downloads/google-trial-tool/常见问题与网络环境自查手册.md)

深度融合原 `google-trial-tool` 与 `Google_AI_Ultra_Pro_一键下单` 全部能力，基于 **100% Python 标准库跨平台内核 + 常驻单会话 Frida 计费引擎**打造，原生自适应 **macOS** 与 **Windows 10/11**，提供**全彩方向键控制台可视化 TUI** 与**本地浏览器图形化驾驶舱 (Web Studio)** 双交互界面。

---

## ✨ 核心特性

1. **💻 macOS / Windows 全自动零配置适配**
   - **自动寻路 & 自动补齐环境**：自动识别 macOS (`mumutool` / Homebrew / SDK) 与 Windows (`MuMuManager.exe` / 注册表 / `C:`~`G:` 多盘符 / 雷电 / 夜神 / SDK)；若电脑无 `adb` 自动下载官方 `platform-tools`；若无 `frida-tools` 自动兼容官方源与清华镜像安装；设备端缺失或大版本不一致时自动匹配模拟器架构 (`x86_64` / `arm64`) 下载部署 `frida-server` 并推送 [module.apk](file:///Users/yanling/Downloads/google-trial-tool/module.apk)。
   - **完美兼容 Frida 16.x 与 17.x**：克服 `ultra0.py` 在 Frida 17 下缺失 `Java` bridge 的问题，开箱即用无需降级。
2. **🖥️ 双可视化交互形态（随心切换）**
   - **全彩方向键控制台 TUI**：支持 `↑`/`↓` 光标高亮选择、`Tab`/`←`/`→` 分类筛选、底部实时说明卡片、MuMu 多开实例一键唤醒切换，终端内按 **`W`** 随时弹出网页版。
   - **本地图形化 Web 驾驶舱 (`--web`)**：仅监听本机 `127.0.0.1`，内置**实时模拟器屏幕画面镜像（鼠标点击画面直接远程触控模拟器）**、热门卡片墙、全量方案搜索筛选表、拖拽式多号批量流水线与实时日志流。
3. **🧙 Pro 5TB 24个月 $0 白嫖智能向导**
   - 毫秒级读取 Play 商店 `library.db`，可视化展示 `[12月首开] ━▶ [+6月叠加(18m)] ━▶ [+6月叠加(24m)] ━▶ [关续费锁死]` 四步进度链，自动判断当前账号所处阶段、检测是否漏做 Acknowledge 或误关自动续费，一键推进下一步。
4. **⚡ 常驻单会话 Frida 引擎 & 自动补单同步**
   - 单次注入常驻内存，选号后 **0.2 秒弹出收银台**，支持无限次 0.2 秒重拉；成单瞬间自动调用 `acknowledgePurchase()` 确认订单，并提供一键**查单 & 补单确认同步 (`--ack`)** 专治「付款成功但容量未刷新」。
5. **🛡️ 严格防误扣款安全红线**
   - **非 `$0` 方案绝不自动点确认**：特惠付费档（如 Ultra 30TB 1折 \$19.99）仅拉起收银台弹窗，由人工核对确认。
   - 批量跑免费试用时严格校验收银台今日应付金额为 `$0`，拦截「不符合免费试用条件」与任何非零扣款，激活后可自动取消续费。

---

## 🚀 零门槛启动（独立安装包 `.dmg` / `.exe` & 脚本双形态，缺失环境全自动补全）

### 🍎 macOS 用户
1. **原生桌面独立应用（推荐）**：打开 [dist/Google-AI-Trial-Studio-macOS.dmg](file:///Users/yanling/Downloads/google-trial-tool/dist/Google-AI-Trial-Studio-macOS.dmg)，将 `Google AI Trial Studio.app` 拖入 `/Applications` 双击运行（Universal 通用架构，原生支持 Apple Silicon 与 Intel；若缺少 Python 3、`adb`、`frida-tools` 或设备端 `frida-server` 均自动下载补全）。
2. **脚本快捷启动**：双击 [启动助手.command](file:///Users/yanling/Downloads/google-trial-tool/启动助手.command)（方向键全彩控制台）或 [网页可视化控制台.command](file:///Users/yanling/Downloads/google-trial-tool/网页可视化控制台.command)（浏览器图形化驾驶舱）。

### 🪟 Windows 用户
1. **单文件免安装独立版（推荐）**：直接双击运行 [dist/Google-AI-Trial-Studio-Win64.exe](file:///Users/yanling/Downloads/google-trial-tool/dist/Google-AI-Trial-Studio-Win64.exe)（单 `.exe` 内置全套脚本与计费模块；即使全新裸机未装 Python / ADB / Frida，也会自动拉取免安装绿色运行时并补齐全部依赖，无需管理员权限）。
2. **批处理脚本启动**：双击 [启动助手_Win.bat](file:///Users/yanling/Downloads/google-trial-tool/启动助手_Win.bat) 或 [网页可视化控制台_Win.bat](file:///Users/yanling/Downloads/google-trial-tool/网页可视化控制台_Win.bat)。

### 🛠️ 重新打包构建（可选）
修改源码后在 macOS 终端运行以下命令即可一键重新生成 `.dmg`、`.exe` 与 `.zip` 便携包：
```bash
bash packaging/build_packages.sh
```

---

## ⌨️ 命令行快捷直达（Mac / Win 通用）

```bash
# 进入方向键可视化主控台（界面内按 W 可随时开启网页版）
python3 gtool.py          # Windows 可用 py -3 gtool.py，macOS 可用 ./trial.sh

# 直接启动本地浏览器图形化驾驶舱
python3 gtool.py --web

# 全链路环境自动适配、组件补齐与网络自愈体检
python3 gtool.py --doctor

# Pro 5TB 免费 24 个月叠加三连
python3 gtool.py --preset pro12    # 第 1 步：免费 12 个月首开 (12months-eft)
python3 gtool.py --preset stack1   # 第 2 步：免费叠加 +6 个月 → 18 个月
python3 gtool.py --preset stack2   # 第 3 步：免费叠加 +6 个月 → 24 个月
python3 gtool.py --preset pro6c    # 备用包：免费叠加 +6 个月 (ss-2026)
python3 gtool.py --preset pro3     # 单开版：免费 3 个月 (g1.play.2tb.ai)

# Ultra 特惠促销档（仅拉起收银台，人工核对价格后手动确认）
python3 gtool.py --preset u1       # ★ Ultra 30TB (20x) 前3月 1折 $19.99/月
python3 gtool.py --preset u2       # Ultra 20TB (5x) 前3月 1折 $9.99/月
python3 gtool.py --preset u3       # Ultra 20TB (5x) 前3月 2折 $19.99/月
python3 gtool.py --preset u4       # Ultra 30TB (20x) 前3月 2.5折 $49.99/月

# 自定义任意 SKU 查询拉起 / 补单同步 / 取消续费
python3 gtool.py --sku g1.ai.ultra.3months_ip_90p.acq
python3 gtool.py --ack             # 查单 & 补单确认同步（解决付款成功未到账）
python3 gtool.py --cancel          # 自动取消当前账号订阅续费

# 仍 100% 保留原有纯 Bash 脚本模式
./trial.sh --shell
./auto-trial.sh --list
```

---

## 📦 批量导入格式（支持拖拽导入 & 内嵌卡）

账号支持 `----`、`|`、Tab、CSV 逗号分隔，兼容单行内嵌卡片格式：
```text
email@gmail.com----password
email@gmail.com----password----JBSWY3DPEHPK3PXP
email@gmail.com----password----recovery@gmail.com
email@gmail.com----password----JBSWY3DPEHPK3PXP----recovery@gmail.com
email@gmail.com----password----recovery@gmail.com----2FA----5450200010222396----06/29----457
```

独立卡片文件支持 `-`、空格、`|`、CSV：
```text
5450200010222396-06/29-457
5450200010222396 0629 457
```

---

## 📁 项目结构

- [gtool.py](file:///Users/yanling/Downloads/google-trial-tool/gtool.py) — 跨平台统一主入口（TUI + Web Studio + CLI）
- `gtool_core/`
  - [platform_env.py](file:///Users/yanling/Downloads/google-trial-tool/gtool_core/platform_env.py) — macOS / Windows 自动寻路、ADB/Frida/`frida-server` 自动下载与版本对齐
  - [device_ops.py](file:///Users/yanling/Downloads/google-trial-tool/gtool_core/device_ops.py) — 极速 ADB UI 引擎、屏幕镜像/远程点击、账号/绑卡/防误扣 \$0 校验/取消续费
  - [billing_engine.py](file:///Users/yanling/Downloads/google-trial-tool/gtool_core/billing_engine.py) — 常驻 Frida 计费会话、0.2s IPC、24个月智能白嫖状态机、自动 Acknowledge
  - [batch_runner.py](file:///Users/yanling/Downloads/google-trial-tool/gtool_core/batch_runner.py) — 多格式账号卡片解析、批量状态机与人工协助闸门 (`HumanGate`)
  - [tui_app.py](file:///Users/yanling/Downloads/google-trial-tool/gtool_core/tui_app.py) — 全彩方向键可视化控制台界面
  - [web_app.py](file:///Users/yanling/Downloads/google-trial-tool/gtool_core/web_app.py) — 零依赖本地浏览器图形化驾驶舱
- [启动助手.command](file:///Users/yanling/Downloads/google-trial-tool/启动助手.command) / [网页可视化控制台.command](file:///Users/yanling/Downloads/google-trial-tool/网页可视化控制台.command) — macOS 双击启动器
- [启动助手_Win.bat](file:///Users/yanling/Downloads/google-trial-tool/启动助手_Win.bat) / [网页可视化控制台_Win.bat](file:///Users/yanling/Downloads/google-trial-tool/网页可视化控制台_Win.bat) — Windows 双击启动器
- [frida-auto-trial.js](file:///Users/yanling/Downloads/google-trial-tool/frida-auto-trial.js) & [module.apk](file:///Users/yanling/Downloads/google-trial-tool/module.apk) — 常驻 `BillingClient` 注入脚本与 7.1.1 计费模块
- [trial.sh](file:///Users/yanling/Downloads/google-trial-tool/trial.sh) / [batch-trial.sh](file:///Users/yanling/Downloads/google-trial-tool/batch-trial.sh) / [auto-trial.sh](file:///Users/yanling/Downloads/google-trial-tool/auto-trial.sh) — 完整保留并兼容的 Shell 脚本套件
