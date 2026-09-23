"""
视觉填入（备用）——当辅助功能接口不可用时，
通过截图分析 + 鼠标操作来填入文字。
"""

from __future__ import annotations

import logging
import subprocess
import time
from typing import Optional

log = logging.getLogger("visual_fill")


def locate_input_region() -> tuple[int, int, int, int] | None:
    """
    通过屏幕截图 + 图像分析定位微信输入框位置。
    返回 (x, y, w, h) 绝对坐标。
    """
    try:
        import mss
        from PIL import Image
        import numpy as np
        
        # 先找到微信窗口
        window_name = "微信"
        result = subprocess.run(
            ["xdotool", "search", "--name", window_name],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        
        win_id = result.stdout.strip().split()[0]
        
        # 获取窗口位置
        result = subprocess.run(
            ["xdotool", "getwindowgeometry", win_id],
            capture_output=True, text=True, timeout=5
        )
        win_x, win_y, win_w, win_h = 0, 0, 0, 0
        for line in result.stdout.splitlines():
            if "Position:" in line:
                parts = line.split(":", 1)
                if len(parts) >= 2:
                    coords = parts[1].strip().replace(" ", "").split(",")
                    if len(coords) >= 2:
                        win_x, win_y = int(coords[0]), int(coords[1])
            elif "Geometry:" in line:
                parts = line.split(":", 1)
                if len(parts) >= 2:
                    geo = parts[1].strip().replace(" ", "").split("x")
                    if len(geo) >= 2:
                        win_w, win_h = int(geo[0]), int(geo[1])
        
        if win_w == 0 or win_h == 0:
            return None
        
        # 输入框通常在窗口底部、聊天区域的右侧
        # 估算输入框位置
        input_x = win_x + int(win_w * 0.30)
        input_y = win_y + int(win_h * 0.85)
        input_w = int(win_w * 0.60)
        input_h = int(win_h * 0.10)
        
        return (input_x, input_y, input_w, input_h)
        
    except Exception as e:
        log.error(f"视觉定位输入框失败: {e}")
        return None


def click_and_type(region: tuple[int, int, int, int], text: str) -> bool:
    """
    点击输入框并输入文字。
    """
    x, y, w, h = region
    click_x = x + w // 2
    click_y = y + h // 2
    
    try:
        # 移动鼠标并点击
        subprocess.run(["xdotool", "mousemove", str(click_x), str(click_y)],
                       capture_output=True, timeout=3)
        time.sleep(0.05)
        subprocess.run(["xdotool", "click", "1"],
                       capture_output=True, timeout=3)
        time.sleep(0.1)
        
        # 选择全部并删除（清除已有内容）
        subprocess.run(["xdotool", "key", "ctrl+a"],
                       capture_output=True, timeout=3)
        time.sleep(0.05)
        subprocess.run(["xdotool", "key", "Delete"],
                       capture_output=True, timeout=3)
        time.sleep(0.05)
        
        # 输入文字
        subprocess.run(["xdotool", "type", "--delay", "15", text],
                       capture_output=True, timeout=10)
        
        return True
        
    except Exception as e:
        log.error(f"鼠标输入失败: {e}")
        return False


def visual_fill(text: str) -> tuple[bool, str]:
    """
    视觉路径填入文字。
    """
    region = locate_input_region()
    if region is None:
        return False, "无法定位输入区域"
    
    if click_and_type(region, text):
        return True, "已填入（视觉路径）"
    
    return False, "点击并输入失败"


if __name__ == "__main__":
    import sys
    text = sys.argv[1] if len(sys.argv) > 1 else "好的我跟进一下"
    success, msg = visual_fill(text)
    print(f"{'✓' if success else '✗'} {msg}")