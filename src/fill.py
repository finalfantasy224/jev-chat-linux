"""
填入模块——通过 AT-SPI 或 xdotool 自动填入回复到微信输入框

优先使用 at-spi2 辅助功能接口定位输入控件并写入文字，
备选方案使用 xdotool 模拟键盘输入。
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from typing import Optional

log = logging.getLogger("fill")


def locate_input(window: dict) -> dict:
    """
    通过 AT-SPI 定位微信输入框。
    
    Args:
        window: 窗口信息字典（含 wid, x, y, w, h 等）
    
    Returns:
        dict 含 rect (x, y, w, h) 或 error 信息
    """
    window_name = os.environ.get("WECHAT_WINDOW_NAME", "微信")
    
    try:
        # 方式1: 使用 xdotool 查找可输入控件
        wid = window.get("id") or window.get("xdotool_id", "")
        if wid:
            result = subprocess.run(
                ["xdotool", "getactivewindow"],
                capture_output=True, text=True, timeout=5
            )
            
            # 方式2: 使用 Python AT-SPI 库
            try:
                import pyatspi
                desktop = pyatspi.Registry.getDesktop(0)
                
                def find_text_entry(app):
                    """递归查找可编辑文本框"""
                    for i in range(app.childCount):
                        child = app[i]
                        role = child.getRoleName()
                        if role in ("text", "entry", "editable text", "password text"):
                            return child
                        if child.childCount > 0:
                            result = find_text_entry(child)
                            if result:
                                return result
                    return None
                
                # 查找微信应用
                for i in range(desktop.childCount):
                    app = desktop[i]
                    name = app.name or ""
                    if window_name in name or "wechat" in name.lower():
                        entry = find_text_entry(app)
                        if entry:
                            extents = entry.getExtents(0)
                            return {
                                "found": True,
                                "rect": (extents.x, extents.y, extents.width, extents.height),
                                "obj": entry,
                                "method": "atspi",
                            }
            except ImportError:
                log.debug("pyatspi 未安装，跳过 AT-SPI 方式")
            except Exception as e:
                log.debug(f"AT-SPI 查找失败: {e}")
        
        return {"found": False, "error": "未找到输入控件"}
        
    except Exception as e:
        return {"found": False, "error": str(e)}


def fill_text_via_xdotool(text: str) -> bool:
    """
    使用 xdotool 模拟键盘输入文本。
    
    先将窗口激活，然后输入指定文本。
    """
    try:
        # 先确保微信窗口激活
        window_name = os.environ.get("WECHAT_WINDOW_NAME", "微信")
        subprocess.run(
            ["xdotool", "search", "--name", window_name, "windowactivate"],
            capture_output=True, timeout=5
        )
        time.sleep(0.2)
        
        # 点击输入区域
        subprocess.run(
            ["xdotool", "click", "1"],
            capture_output=True, timeout=3
        )
        time.sleep(0.1)
        
        # 输入文字（处理特殊字符）
        # 使用 type 命令
        escaped_text = text.replace("'", "'\\''")
        subprocess.run(
            ["xdotool", "type", "--delay", "20", text],
            capture_output=True, timeout=10
        )
        
        return True
        
    except Exception as e:
        log.error(f"xdotool 输入失败: {e}")
        return False


def fill_text_via_clipboard(text: str) -> bool:
    """
    通过剪贴板 + 粘贴快捷键输入文字（备用方式）。
    """
    try:
        # 复制到剪贴板
        import pyperclip
        pyperclip.copy(text)
        time.sleep(0.1)
        
        # 激活微信窗口
        window_name = os.environ.get("WECHAT_WINDOW_NAME", "微信")
        subprocess.run(
            ["xdotool", "search", "--name", window_name, "windowactivate"],
            capture_output=True, timeout=5
        )
        time.sleep(0.2)
        
        # 点击输入区域
        subprocess.run(
            ["xdotool", "click", "1"],
            capture_output=True, timeout=3
        )
        time.sleep(0.1)
        
        # Ctrl+V 粘贴
        subprocess.run(
            ["xdotool", "key", "ctrl+v"],
            capture_output=True, timeout=3
        )
        
        return True
        
    except Exception as e:
        log.error(f"剪贴板粘贴失败: {e}")
        return False


def fill_text(text: str) -> tuple[bool, str]:
    """
    向微信输入框填入文字。
    
    返回 (成功与否, 消息)
    """
    # 方法1: xdotool type
    if fill_text_via_xdotool(text):
        return True, "已填入"
    
    # 方法2: 剪贴板
    if fill_text_via_clipboard(text):
        return True, "已填入（剪贴板）"
    
    return False, "无法填入，请手动复制"


if __name__ == "__main__":
    import sys
    text = sys.argv[1] if len(sys.argv) > 1 else "好的，我跟进一下"
    success, msg = fill_text(text)
    print(f"{'✓' if success else '✗'} {msg}")
    print(f"文本: {text}")