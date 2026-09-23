"""
输入区域检测——定位微信输入框位置

使用 AT-SPI (Linux 无障碍接口) 或 xdotool 辅助功能定位输入控件。
"""

from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger("input_region")


def input_outline(image) -> tuple[float, float, float, float] | None:
    """
    通过图像分析检测输入框位置。
    
    返回 (x, y, w, h) 归一化坐标（相对于窗口），
    或 None 表示无法确定。
    
    在 Ubuntu 微信上，输入框通常位于窗口底部，有一条明显的分隔线。
    """
    try:
        from PIL import Image
        import numpy as np
        
        if image is None:
            return None
        
        img_width = image.width
        img_height = image.height
        
        # 转 numpy 数组
        if hasattr(image, 'tobytes'):
            # PIL Image
            arr = np.array(image.convert("RGB"))
        else:
            return None
        
        # 在底部区域查找颜色变化（输入框通常有浅色背景）
        # 检查底部 30% 区域
        bottom_third_start = int(img_height * 0.70)
        bottom_region = arr[bottom_third_start:, :, :]
        
        # 查找水平边缘——输入框与聊天区域的分隔线
        gray = np.mean(bottom_region, axis=2)
        edges = np.abs(np.diff(gray, axis=0))
        
        # 找到最明显的水平线位置
        horizontal_edges = np.mean(edges, axis=1)
        threshold = np.mean(horizontal_edges) + np.std(horizontal_edges)
        
        significant_edges = np.where(horizontal_edges > threshold)[0]
        
        if len(significant_edges) > 0:
            # 分隔线应该在底部区域的偏上位置
            mid_line = significant_edges[len(significant_edges) // 2]
            
            input_top = (bottom_third_start + mid_line) / img_height
            input_height = (img_height - bottom_third_start - mid_line) / img_height
            
            if 0.08 < input_height < 0.25:
                return (0.0, input_top, 1.0, input_height)
        
        # 默认：底部 12% 为输入区
        return (0.0, 0.88, 1.0, 0.12)
        
    except Exception as e:
        log.debug(f"输入框检测失败: {e}")
        return None