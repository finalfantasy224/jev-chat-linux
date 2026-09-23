"""用户配置管理 — 读写 ~/.config/jev-chat-linux/env"""

import os
import re
import logging
from pathlib import Path

log = logging.getLogger("userconfig")

# 配置文件路径
CONFIG_DIR = Path.home() / ".config" / "jev-chat-linux"
CONFIG_FILE = CONFIG_DIR / "env"

# 默认配置
DEFAULT_CONFIG = {
    "TYPESAFE_API_KEY": "",
    "TYPESAFE_BASE_URL": "https://api.typesafe.ai",
    "TYPESAFE_MODEL": "jev-latest",
    "OPENAI_API_KEY": "",
    "OPENAI_BASE_URL": "https://api.deepseek.com",
    "OPENAI_MODEL": "deepseek-chat",
    "ANTHROPIC_API_KEY": "",
    "ANTHROPIC_BASE_URL": "",
    "ANTHROPIC_MODEL": "",
    "JEV_TONES": "",
    "ACTIVE_TONES": "友好亲切,简洁高效,正式商务",
    "POLL_INTERVAL": "3",  # 截图轮询间隔（秒）
    "WECHAT_WINDOW_NAME": "微信",
    "JUDGE_BACKEND": "",
    "DEBUG": "",
}


def ensure_config_dir():
    """确保配置目录存在"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_env_file(path: Path | None = None) -> dict[str, str]:
    """
    读取 env 文件，返回键值对字典。
    只解析 export KEY=VALUE 或 KEY=VALUE 格式的行。
    """
    path = path or CONFIG_FILE
    if not path.exists():
        return {}
    
    config = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # 跳过注释和空行
            if not line or line.startswith("#"):
                continue
            # 去掉 export 前缀
            if line.startswith("export "):
                line = line[7:].strip()
            # 解析 KEY=VALUE
            m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
            if m:
                key = m.group(1)
                value = m.group(2)
                # 去掉引号
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                config[key] = value
    return config


def save_env_file(config: dict[str, str], path: Path | None = None, header: str | None = None) -> None:
    """
    保存配置到 env 文件。
    保留现有文件中的注释和无关行，只替换已知 key 的值。
    文件权限设为 600。
    """
    path = path or CONFIG_FILE
    os.makedirs(path.parent, exist_ok=True)
    
    # 读取现有内容
    existing_lines = []
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            existing_lines = f.readlines()
    
    # 构建新的行
    new_lines = []
    written_keys = set()
    
    for line in existing_lines:
        stripped = line.strip()
        m = re.match(r'^(?:export )?([A-Za-z_][A-Za-z0-9_]*)=', stripped)
        if m and m.group(1) in config:
            key = m.group(1)
            value = config[key]
            if stripped.startswith("export "):
                new_lines.append(f'export {key}="{value}"\n')
            else:
                new_lines.append(f'{key}="{value}"\n')
            written_keys.add(key)
        else:
            new_lines.append(line)
    
    # 添加新 key
    for key, value in config.items():
        if key not in written_keys:
            new_lines.append(f'{key}="{value}"\n')
    
    # 写入文件
    content = "".join(new_lines)
    if header:
        content = header + "\n" + content
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    
    # 设置权限 600
    os.chmod(path, 0o600)


def get_config() -> dict[str, str]:
    """
    获取合并配置：环境变量 > 用户文件 > 默认值。
    返回完整的配置字典。
    """
    config = dict(DEFAULT_CONFIG)
    
    # 从用户文件加载
    file_config = load_env_file()
    config.update(file_config)
    
    # 环境变量覆盖
    for key in config:
        env_val = os.environ.get(key)
        if env_val is not None:
            config[key] = env_val
    
    return config


def get_config_value(key: str, default: str = "") -> str:
    """获取单个配置值（环境变量优先）"""
    env_val = os.environ.get(key)
    if env_val is not None:
        return env_val
    file_config = load_env_file()
    return file_config.get(key, default)


def mask_key(key: str, visible_chars: int = 4) -> str:
    """掩码显示 API key"""
    if not key:
        return "(未设置)"
    if len(key) <= visible_chars + 4:
        return key[:visible_chars] + "****"
    return key[:visible_chars] + "..." + key[-4:] if len(key) > 12 else key[:visible_chars] + "****"