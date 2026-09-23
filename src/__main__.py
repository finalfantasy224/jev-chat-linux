"""jev-chat-linux 入口：启动悬浮窗主循环"""

import os
import sys
import logging

# 确保在 src 目录下能找到模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# 加载 .env（项目目录或 ~/.config/jev-chat-linux/env）
env_paths = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
    os.path.expanduser("~/.config/jev-chat-linux/env"),
]
for p in env_paths:
    if os.path.isfile(p):
        load_dotenv(p, override=False)
        break

logging.basicConfig(
    level=logging.DEBUG if os.environ.get("DEBUG") else logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.expanduser("~/.local/share/jev-chat-linux/jev-chat-linux.log")),
    ],
)
log = logging.getLogger("main")


def main():
    from src.hud import HUDApp
    import sys
    app = HUDApp(sys.argv)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()