#!/bin/bash
# jev-chat-linux 打包脚本
# 用法: ./packaging/build.sh

set -e

APP_NAME="jev-chat-linux"
VERSION=$(python3 -c "import sys; sys.path.insert(0, 'src'); from __init__ import __version__; print(__version__)" 2>/dev/null || echo "0.1.0")
BUILD_DIR="dist/$APP_NAME"

echo "📦 打包 $APP_NAME v$VERSION"

# 清理
rm -rf "$BUILD_DIR" "dist/${APP_NAME}-linux-x86_64.tar.gz"

# 创建目录结构
mkdir -p "$BUILD_DIR/src"
mkdir -p "$BUILD_DIR/packaging"

# 复制文件
cp -r src/*.py "$BUILD_DIR/src/"
cp pyproject.toml "$BUILD_DIR/"
cp start.sh "$BUILD_DIR/"
cp .env.example "$BUILD_DIR/"

# 复制打包脚本
cp packaging/*.sh "$BUILD_DIR/packaging/" 2>/dev/null || true

# 创建 README 快捷方式
cat > "$BUILD_DIR/README.txt" << 'EOF'
jev-chat-linux - 微信消息意图识别悬浮窗

启动: ./start.sh
配置: ~/.config/jev-chat-linux/env

依赖:
  sudo apt install python3-pyqt6 tesseract-ocr tesseract-ocr-chi-sim xdotool wmctrl
  pip install mss pytesseract Pillow requests python-dotenv torch transformers huggingface-hub numpy

更多信息见 README.md
EOF

chmod +x "$BUILD_DIR/start.sh"

# 打包
cd dist
tar czf "${APP_NAME}-linux-x86_64.tar.gz" "$APP_NAME"
echo "✅ 打包完成: dist/${APP_NAME}-linux-x86_64.tar.gz"
echo "   大小: $(du -sh "${APP_NAME}-linux-x86_64.tar.gz" | cut -f1)"