# jev-chat-linux

微信消息意图识别悬浮窗（Ubuntu Linux）：看屏 + 本地小模型判断意图和风险，再按话术生成回复候选。纯只读、不注入微信。

> 本项目是 [jev-chat/jev-chat-jarvis-mac](https://github.com/jev-chat/jev-chat-jarvis-mac) 的 Ubuntu Linux 移植版。感谢原作者的出色设计。

## 它能做什么

微信弹出一条消息 → 悬浮窗立刻告诉你**这句话的真实意图**、**风险几级**、**该怎么回**。

**纯只读、零封号风险**——不注入、不 hook、不解密数据库，只是「看屏幕 + 本地模型判断」。

- **意图 + 风险**：8 类意图识别、风险 0–9 分级 + 行动建议
- **候选回复**：多种话术并发生成（正式商务、友好亲切、简洁高效等）
- **本地 + 云端双判断**：优先使用 TypeSafe Jev API（云端），降级使用本地 decider-2b 模型
- **仅限微信前台时工作**：切到其他窗口自动隐藏

## 用法

### 安装依赖

```bash
# 系统依赖
sudo apt install python3-pyqt6 tesseract-ocr tesseract-ocr-chi-sim xdotool wmctrl

# Python 依赖
pip install mss pytesseract Pillow requests python-dotenv
pip install torch transformers huggingface-hub numpy  # 本地判断模型
```

### 启动

```bash
./start.sh
```

### 配置

复制 .env.example 到 ~/.config/jev-chat-linux/env 并编辑：

```bash
mkdir -p ~/.config/jev-chat-linux
cp .env.example ~/.config/jev-chat-linux/env
# 编辑配置
nano ~/.config/jev-chat-linux/env
```

#### 生成层配置（必需，否则没有候选回复）

```ini
# OpenAI 兼容端点（推荐 DeepSeek）
OPENAI_API_KEY="sk-你的key"
OPENAI_BASE_URL="https://api.deepseek.com"
OPENAI_MODEL="deepseek-chat"

# 或 Anthropic 兼容端点
# ANTHROPIC_API_KEY="sk-..."
# ANTHROPIC_BASE_URL="https://open.bigmodel.cn/api/anthropic"
# ANTHROPIC_MODEL="glm-4-flash"
```

#### 判断层配置（可选）

```ini
# 使用 TypeSafe Jev API（云端判断）
TYPESAFE_API_KEY="你的key"
TYPESAFE_BASE_URL="https://api.typesafe.ai"
TYPESAFE_MODEL="jev-latest"

# 不配置则使用本地 decider-2b 模型（首次运行下载约 7GB）
```

### 分层自测

```bash
python3 -m src.judge_zh_test        # 22 条中文意图回归
python3 -m src.judge "这个需求你今天跟一下"  # 单条消息判断
python3 -m src.generate --check     # 生成层凭据解析
python3 -m src.perception           # 感知层测试
```

## 架构

```
微信在前台 → 截图（mss）→ OCR（tesseract）→ 判断意图/风险（本地模型或 Jev API）
                                                          ↓
                    悬浮窗 ← 排序 ← 并发生成候选回复（LLM API）
```

- **perception.py**: 窗口检测（xdotool/wmctrl）+ 截图（mss）+ OCR（pytesseract）
- **judge.py**: 意图/风险判断（本地 decider-2b 或 Jev API fallback）
- **generate.py**: 候选回复生成（OpenAI/Anthropic 兼容 API）
- **hud.py**: PyQt6 浮动面板
- **fill.py**: 输入框填入（xdotool / AT-SPI）

## 与 macOS 版的差异

| 功能 | macOS 版 | Linux 版 |
|---|---|---|
| 截图 | Quartz/CoreGraphics | mss (Python) |
| OCR | Vision Framework | Tesseract (pytesseract) |
| 窗口检测 | Quartz Window Services | xdotool / wmctrl |
| 浮动面板 | NSPanel (macOS 原生) | PyQt6 (无边框窗口) |
| 辅助功能 | macOS Accessibility API | AT-SPI / xdotool |
| 本地模型 | MPS 加速 | CUDA / CPU |

## 已知限制

- 微信窗口布局需校准（`perception.py` 中的布局常量）
- OCR 质量依赖 tesseract 和中文语言包
- 填入功能依赖辅助功能接口，可能因微信版本变化失效
- 不支持 Wayland（使用 X11 兼容层可部分工作）

## 许可

MIT (see [LICENSE](LICENSE))

**隐私**：聊天内容只发给模型服务商——推荐自配 API key 或本地模型。内置无共享 API key（不同于 macOS 版）。