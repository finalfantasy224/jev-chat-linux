"""
感知层：微信窗口检测 + 屏幕截图 + OCR 文本识别（Linux 版）

用到的 Linux 工具：
  - xdotool / wmctrl: 查找和操作窗口
  - mss: Python 截图库（基于 X11/Wayland）
  - pytesseract: Tesseract OCR 封装

架构流程：
  1. 轮询检查微信窗口是否在前台
  2. 找到窗口后截图聊天区域
  3. Tesseract OCR 提取文字
  4. 判断消息方向（对方/自己）
  5. 返回识别到的消息文本
"""

import os
import re
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

import mss
import mss.tools
from PIL import Image

log = logging.getLogger("perception")

# 截图缓存（避免频繁调用 gnome-screenshot）
_last_screenshot_time = 0.0
_last_screenshot_image: Optional[Image.Image] = None
SCREENSHOT_CACHE_TTL = 3.0  # 秒，此间隔内复用上次截图

# ── 布局参数（根据 Ubuntu 微信版式校准） ──────────────────────
# 这些常量需要在用户的实际微信版本上校准
CHAT_AREA_LEFT_RATIO = 0.50       # 聊天区起始（Linux 侧栏约左半）
CHAT_AREA_TOP_RATIO = 0.10        # 聊天区起始（从上起比例）
CHAT_AREA_WIDTH_RATIO = 0.35      # 聊天区宽度比例
CHAT_AREA_HEIGHT_RATIO = 0.55     # 聊天区高度比例（避开输入框）

# 文本提取参数
TESSERACT_LANG = "chi_sim+eng"     # 中文简体 + 英文
TESSERACT_CONFIG = "--oem 3 --psm 6"  # LSTM 引擎 + 统一块处理

# 轮询间隔
# 轮询间隔（秒，可通过 env 配置 POLL_INTERVAL 覆盖）
_POLL_INTERVAL_DEFAULT = 3.0

def get_poll_interval() -> float:
    """获取轮询间隔（支持 env 覆盖）"""
    try:
        from src import userconfig
        val = userconfig.get_config_value("POLL_INTERVAL", str(_POLL_INTERVAL_DEFAULT))
        return float(val)
    except Exception:
        return _POLL_INTERVAL_DEFAULT

# 方向判断——通过文字在聊天区的水平位置
SELF_TEXT_RATIO_RIGHT = 0.55      # 自己发的消息靠右
OTHER_TEXT_RATIO_LEFT = 0.45      # 对方发的消息靠左


@dataclass
class ScreenCapture:
    """一次截图 + OCR 的结果"""
    text_lines: list[dict] = field(default_factory=list)
    raw_text: str = ""
    capture_time: float = 0.0
    error: Optional[str] = None

    @property
    def has_content(self) -> bool:
        return len(self.text_lines) > 0


@dataclass
class RecognizedMessage:
    """识别到的单条消息"""
    text: str
    direction: str  # "self", "other", "unknown"
    confidence: float = 0.0
    box: tuple = (0, 0, 0, 0)  # x1, y1, x2, y2


def find_wechat_window() -> Optional[dict]:
    """
    通过 xdotool 查找微信窗口。
    返回窗口信息字典或 None。
    """
    window_name = os.environ.get("WECHAT_WINDOW_NAME", "微信")
    
    try:
        import subprocess
        # 使用 wmctrl 查找窗口
        result = subprocess.run(
            ["wmctrl", "-l", "-x"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.split(None, 3)
                if len(parts) >= 4:
                    win_id, desktop, pid_or_class, title = parts[0], parts[1], parts[2], parts[3]
                    if window_name in title or "wechat" in title.lower() or "WeChat" in title:
                        return {
                            "id": win_id,
                            "title": title,
                            "wm_class": pid_or_class,
                        }
        
        # 备选：xdotool
        result = subprocess.run(
            ["xdotool", "search", "--name", window_name],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            win_ids = result.stdout.strip().split()
            if win_ids:
                return {
                    "id": win_ids[0],
                    "title": window_name,
                    "xdotool_id": win_ids[0],
                }
        
        # 备选：xdotool 搜索 classname
        result = subprocess.run(
            ["xdotool", "search", "--class", "wechat"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            win_ids = result.stdout.strip().split()
            if win_ids:
                return {
                    "id": win_ids[0],
                    "title": "wechat",
                    "xdotool_id": win_ids[0],
                }
    except Exception as e:
        log.debug(f"查找窗口失败: {e}")
    
    return None


def is_wechat_foreground() -> bool:
    """
    检查微信窗口是否在前台。
    """
    window_name = os.environ.get("WECHAT_WINDOW_NAME", "微信")
    try:
        import subprocess
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            active_title = result.stdout.strip()
            return window_name in active_title or "WeChat" in active_title or "wechat" in active_title.lower()
    except Exception as e:
        log.debug(f"检查前台窗口失败: {e}")
    return False


def capture_wechat_chat(win_info: dict | None = None) -> Optional[Image.Image]:
    """
    截图微信聊天区域。
    可传入 find_wechat_window() 返回的窗口信息，避免重复搜索。
    返回 PIL Image 对象或 None。
    """
    global _last_screenshot_time, _last_screenshot_image
    
    # 截图缓存：短时间内复用上次结果
    now = time.time()
    if _last_screenshot_image is not None and (now - _last_screenshot_time) < SCREENSHOT_CACHE_TTL:
        return _last_screenshot_image
    
    try:
        import subprocess
        
        # 获取窗口 ID
        if win_info and win_info.get("id"):
            win_id = win_info["id"]
        else:
            window_name = os.environ.get("WECHAT_WINDOW_NAME", "微信")
            result = subprocess.run(
                ["xdotool", "search", "--name", window_name],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0 or not result.stdout.strip():
                log.debug("未找到微信窗口")
                return None
            win_id = result.stdout.strip().split()[0]
        
        # 获取窗口位置和大小
        result = subprocess.run(
            ["xdotool", "getwindowgeometry", win_id],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return None
        
        # 解析 geometry 输出
        # 格式:
        #   Window 12582978
        #     Position: 36,126 (screen: 0)
        #     Geometry: 692x960
        win_x, win_y, win_w, win_h = 0, 0, 0, 0
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Position:"):
                pos_str = line.split(":", 1)[1].strip()
                # 提取 "36,126" 部分（去掉 (screen: N)）
                pos_clean = pos_str.split("(")[0].strip()
                coord_parts = [p.strip() for p in pos_clean.split(",")]
                if len(coord_parts) >= 2:
                    win_x = int(coord_parts[0])
                    win_y = int(coord_parts[1])
            elif line.startswith("Geometry:"):
                geo_str = line.split(":", 1)[1].strip()
                geo_parts = [p.strip() for p in geo_str.split("x")]
                if len(geo_parts) >= 2:
                    win_w = int(geo_parts[0])
                    win_h = int(geo_parts[1])
        
        if win_w == 0 or win_h == 0:
            log.debug("无法获取窗口大小")
            return None
        
        # 计算聊天区域（去掉标题栏、左侧列表、输入区）
        title_bar_height = 40  # 估计标题栏高度
        
        # 聊天区：从左侧列表之后开始，到输入区之前
        left = int(win_x + win_w * CHAT_AREA_LEFT_RATIO)
        top = int(win_y + title_bar_height + win_h * CHAT_AREA_TOP_RATIO)
        width = int(win_w * CHAT_AREA_WIDTH_RATIO)
        height = int(win_h * CHAT_AREA_HEIGHT_RATIO)
        
        # 截图前尝试将微信窗口提到最前（避免其他窗口重叠干扰）
        if win_info and win_info.get("id"):
            import subprocess as _sp
            _sp.run(['xdotool', 'windowraise', win_info['id']],
                    capture_output=True, timeout=3)
        
        # 截图方式：优先 gnome-screenshot（Wayland），降级 mss（X11）
        img = _capture_region(left, top, width, height)
        if img is None:
            log.debug("截图失败")
            return None
        # 更新截图缓存
        _last_screenshot_time = time.time()
        _last_screenshot_image = img
        return img
            
    except Exception as e:
        log.error(f"截图失败: {e}")
        return None


def _capture_region(left: int, top: int, width: int, height: int) -> Optional[Image.Image]:
    """
    截取屏幕指定区域。
    在 Wayland 下使用 gnome-screenshot 截全屏后裁剪，
    在 X11 下使用 mss 直接截取。
    """
    import subprocess
    import tempfile
    
    # 尝试 gnome-screenshot（Wayland 兼容）
    try:
        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        tmp_path = tmp.name
        tmp.close()
        
        r = subprocess.run(['gnome-screenshot', '-f', tmp_path],
                          capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            from PIL import Image as PILImage
            full = PILImage.open(tmp_path)
            # 裁剪到窗口聊天区域
            chat = full.crop((left, top, left + width, top + height))
            os.unlink(tmp_path)
            return chat
        os.unlink(tmp_path)
    except Exception as e:
        log.debug(f"gnome-screenshot 失败: {e}")
        pass
    
    # 降级 mss（仅 X11 有效）
    try:
        import mss
        with mss.mss() as sct:
            monitor = {"left": left, "top": top, "width": width, "height": height}
            sct_img = sct.grab(monitor)
            from PIL import Image as PILImage
            return PILImage.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
    except Exception as e:
        log.debug(f"mss 截图失败: {e}")
    
    return None


def ocr_image(image: Image.Image, lang: str = TESSERACT_LANG) -> ScreenCapture:
    """
    对图片进行 OCR 文本识别。
    返回 ScreenCapture 包含识别出的文本行。
    """
    import pytesseract
    
    result = ScreenCapture(capture_time=time.time())
    
    try:
        # 原始图像直接 OCR——暗色主题微信截图在无预处理时效果最好
        data = pytesseract.image_to_data(
            image,
            lang=lang,
            config=TESSERACT_CONFIG,
            output_type=pytesseract.Output.DICT
        )
        
        img_width = image.width
        
        # 处理每一行
        text_lines = []
        current_line_num = -1
        current_text = ""
        current_box = None
        
        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            if not text:
                continue
            
            line_num = data["line_num"][i]
            conf = int(data["conf"][i]) if data["conf"][i] != "-1" else 0
            x = data["left"][i]
            y = data["top"][i]
            w = data["width"][i]
            h = data["height"][i]
            
            # 同行的文本合并
            if line_num == current_line_num:
                current_text += " " + text
                if current_box:
                    current_box = (
                        min(current_box[0], x),
                        min(current_box[1], y),
                        max(current_box[2], x + w),
                        max(current_box[3], y + h),
                    )
            else:
                if current_text:
                    # 根据水平位置判断方向
                    center_x = (current_box[0] + current_box[2]) / 2 / img_width if current_box else 0.5
                    if center_x > SELF_TEXT_RATIO_RIGHT:
                        direction = "self"
                    elif center_x < OTHER_TEXT_RATIO_LEFT:
                        direction = "other"
                    else:
                        direction = "unknown"
                    
                    text_lines.append({
                        "text": clean_ocr_text(current_text),
                        "direction": direction,
                        "confidence": conf,
                        "box": current_box or (0, 0, 0, 0),
                    })
                
                current_line_num = line_num
                current_text = text
                current_box = (x, y, x + w, y + h)
        
        # 加入最后一行
        if current_text:
            center_x = (current_box[0] + current_box[2]) / 2 / img_width if current_box else 0.5
            if center_x > SELF_TEXT_RATIO_RIGHT:
                direction = "self"
            elif center_x < OTHER_TEXT_RATIO_LEFT:
                direction = "other"
            else:
                direction = "unknown"
            
            text_lines.append({
                "text": clean_ocr_text(current_text),
                "direction": direction,
                "confidence": conf if 'conf' in dir() else 0,
                "box": current_box or (0, 0, 0, 0),
            })
        
        result.text_lines = text_lines
        result.raw_text = " ".join([t["text"] for t in text_lines])
        
        log.debug(f"OCR: 识别到 {len(text_lines)} 行文本")
        
    except Exception as e:
        result.error = str(e)
        log.error(f"OCR 失败: {e}")
    
    return result


def clean_ocr_text(text: str) -> str:
    """清理 OCR 结果：去除中文字符间的空格，保留英文单词间的空格"""
    import re
    # 反复去除中文字符之间的空格（直到不再变化）
    # 处理"提 醒 要 过 期 了" → "提醒要过期了"
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', text)
    # 去除中文字符与相邻英文/数字之间的空格
    text = re.sub(r'([\u4e00-\u9fff])\s+([a-zA-Z0-9])', r'\1\2', text)
    text = re.sub(r'([a-zA-Z0-9])\s+([\u4e00-\u9fff])', r'\1\2', text)
    return text.strip()


def _is_meaningful_text(text: str) -> bool:
    """判断 OCR 文本是否有意义（含足够的中文或英文单词）"""
    import re
    if not text.strip():
        return False
    # 中文字符数
    cjk = len(re.findall(r'[\u4e00-\u9fff]', text))
    # 英文单词数（>=2 字母）
    words = len(re.findall(r'\b[a-zA-Z]{2,}\b', text))
    # 总长度
    total_len = len(text.replace(' ', ''))
    # 有效：至少有 2 个中文字符，或至少 1 个英文单词
    if cjk >= 2 or words >= 1:
        return True
    # 或者总长度 >= 3 且不含纯特殊字符
    if total_len >= 3 and cjk + words > 0:
        return True
    return False


def get_latest_other_message(capture: ScreenCapture) -> Optional[RecognizedMessage]:
    """
    从 OCR 结果中获取最新的对方消息（用于触发判断）。
    过滤掉无意义的噪声文字，只保留含中文或英文单词的有效文本。
    """
    other_messages = [
        t for t in capture.text_lines 
        if t["direction"] == "other" and _is_meaningful_text(t["text"])
    ]
    if not other_messages:
        return None
    
    latest = other_messages[-1]
    return RecognizedMessage(
        text=latest["text"],
        direction="other",
        confidence=latest["confidence"],
        box=latest["box"],
    )


def get_latest_message(capture: ScreenCapture) -> Optional[RecognizedMessage]:
    """
    群聊模式：获取 OCR 结果中最新一条有效消息（不限方向）。
    """
    meaningful = [
        t for t in capture.text_lines 
        if _is_meaningful_text(t["text"])
    ]
    if not meaningful:
        return None
    
    latest = meaningful[-1]
    return RecognizedMessage(
        text=latest["text"],
        direction=latest.get("direction", "unknown"),
        confidence=latest["confidence"],
        box=latest["box"],
    )


def poll_wechat_chat(win_info: dict | None = None) -> Optional[RecognizedMessage]:
    """
    一次完整的感知轮询：
    1. 检查微信在前台
    2. 截图
    3. OCR
    4. 提取对方消息
    
    Args:
        win_info: 可选的窗口信息（来自 find_wechat_window()），避免重复查找
    """
    if not is_wechat_foreground():
        log.debug("微信不在前台，跳过")
        return None
    
    # 如果没有窗口信息，先查找一次（供截图复用）
    if win_info is None:
        win_info = find_wechat_window()
    
    img = capture_wechat_chat(win_info)
    if img is None:
        return None
    
    capture = ocr_image(img)
    if not capture.has_content:
        log.debug("OCR 未识别到内容")
        return None
    
    # 提取所有有效文本行作为完整上下文
    all_texts = [t["text"] for t in capture.text_lines if _is_meaningful_text(t["text"])]
    if not all_texts:
        log.debug("未识别到有效消息")
        return None
    
    # 合并所有消息为一条（用换行分隔），以便 HUD 做去重和展示
    combined = "\n".join(all_texts)
    first_line = all_texts[-1]  # 最新一行作为主要消息
    
    log.info(f"识别到 {len(all_texts)} 条消息: {first_line[:40]}{'...' if len(first_line) > 40 else ''}")
    return RecognizedMessage(
        text=combined,
        direction="other",
        confidence=80.0,
    )


def get_chat_context(window_name: str = "微信") -> list[str]:
    """
    获取当前聊天的上下文消息（最近几条），供判断和生成使用。
    返回消息文本列表，最新消息在最后。
    """
    img = capture_wechat_chat()
    if img is None:
        return []
    
    capture = ocr_image(img)
    return [t["text"] for t in capture.text_lines]