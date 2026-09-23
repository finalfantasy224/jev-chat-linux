#!/bin/bash
# jev-chat-linux 启动脚本
# 用法: ./start.sh

set -e

APP_NAME="jev-chat-linux"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/$APP_NAME"
DATA_DIR="$HOME/.local/share/$APP_NAME"
LOG_FILE="$DATA_DIR/$APP_NAME.log"

# 项目根目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 确定 Python 和虚拟环境
if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
    echo "ℹ 使用虚拟环境 Python"
else
    PYTHON="python3"
fi

# 确保目录存在
mkdir -p "$CONFIG_DIR" "$DATA_DIR"

# 检查依赖
check_dep() {
    if ! command -v "$1" &>/dev/null; then
        echo "❌ 缺少依赖: $1"
        echo "   请安装: sudo apt install $1"
        return 1
    fi
}

echo "🔍 检查系统依赖..."
check_dep python3 || echo "  ⚠ python3 未找到"
check_dep xdotool || echo "  ⚠ xdotool 未安装（可选，用于窗口检测和输入）"
check_dep wmctrl || echo "  ⚠ wmctrl 未安装（可选，用于窗口检测）"
check_dep tesseract || echo "  ⚠ tesseract 未安装（可选，用于 OCR）"

# 检查 Python 版本
PYTHON_VERSION=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✓ Python $PYTHON_VERSION"

# 检查 Python 依赖（虚拟环境内）
echo "🔍 检查 Python 依赖..."
$PYTHON -c "import PyQt6" 2>/dev/null || {
    echo "❌ 缺少 PyQt6"
    echo "   请运行: $SCRIPT_DIR/.venv/bin/pip install PyQt6"
    exit 1
}
$PYTHON -c "import mss" 2>/dev/null || {
    echo "❌ 缺少 mss"
    echo "   请运行: $SCRIPT_DIR/.venv/bin/pip install mss"
    exit 1
}

# 检查 tesseract 中文语言包
if command -v tesseract &>/dev/null; then
    if ! tesseract --list-langs 2>/dev/null | grep -q chi_sim; then
        echo "⚠ 缺少中文 OCR 语言包"
        echo "   请安装: sudo apt install tesseract-ocr-chi-sim"
    fi
fi

# 加载 .env
ENV_FILE="$CONFIG_DIR/env"
if [ -f "$ENV_FILE" ]; then
    echo "📄 加载配置: $ENV_FILE"
    set -a
    source "$ENV_FILE"
    set +a
fi

# 如果项目根目录有 .env 也加载
PROJECT_ENV="$(dirname "$0")/.env"
if [ -f "$PROJECT_ENV" ]; then
    set -a
    source "$PROJECT_ENV"
    set +a
fi

echo "🚀 启动 $APP_NAME..."
echo "   日志: $LOG_FILE"
echo "   Python: $PYTHON"

cd "$SCRIPT_DIR"
exec $PYTHON -m src 2>&1 | tee -a "$LOG_FILE"