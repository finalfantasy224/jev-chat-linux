"""UI 样式定义——颜色、字体、布局常量"""

from PyQt6.QtGui import QColor, QFont

# ── 主色调 ──────────────────────────────────────────────────────
COLOR_BG = QColor("#1E1E2E")           # 深色背景
COLOR_SURFACE = QColor("#2D2D3F")      # 卡片/面板背景
COLOR_SURFACE_LIGHT = QColor("#363649") # 浅色卡片
COLOR_PRIMARY = QColor("#7C3AED")      # 主色（紫色）
COLOR_PRIMARY_LIGHT = QColor("#A78BFA") # 浅主色
COLOR_ACCENT = QColor("#10B981")       # 强调色（绿色）
COLOR_WARNING = QColor("#F59E0B")      # 警告色（黄色）
COLOR_DANGER = QColor("#EF4444")       # 危险色（红色）
COLOR_TEXT = QColor("#E2E8F0")         # 主文本
COLOR_TEXT_SECONDARY = QColor("#94A3B8") # 次要文本
COLOR_TEXT_MUTED = QColor("#64748B")   # 弱文本
COLOR_BORDER = QColor("#3D3D5C")       # 边框

# ── 风险等级颜色（0-9） ────────────────────────────────────────
RISK_COLORS = {
    0: QColor("#10B981"),  # 低风险 - 绿色
    1: QColor("#34D399"),
    2: QColor("#6EE7B7"),
    3: QColor("#FCD34D"),  # 中等风险 - 黄色
    4: QColor("#FBBF24"),
    5: QColor("#F97316"),  # 较高风险 - 橙色
    6: QColor("#F59E0B"),
    7: QColor("#EF4444"),  # 高风险 - 红色
    8: QColor("#DC2626"),
    9: QColor("#B91C1C"),
}

# ── 字体 ────────────────────────────────────────────────────────
FONT_FAMILY = "Noto Sans CJK SC, Noto Sans, Sans Serif"
FONT_SIZE_SMALL = 11
FONT_SIZE_NORMAL = 13
FONT_SIZE_LARGE = 15
FONT_SIZE_XLARGE = 18

# ── 布局 ────────────────────────────────────────────────────────
WINDOW_WIDTH = 380
WINDOW_MIN_HEIGHT = 300
WINDOW_MAX_HEIGHT = 700
PADDING = 12
MARGIN = 8
BORDER_RADIUS = 12
CARD_RADIUS = 8


def get_risk_color(level: int) -> QColor:
    """获取风险等级对应颜色"""
    return RISK_COLORS.get(max(0, min(level, 9)), RISK_COLORS[0])


def get_risk_label(level: int) -> str:
    """获取风险等级文字标签"""
    if level <= 1:
        return "安全"
    elif level <= 3:
        return "低风险"
    elif level <= 5:
        return "中等风险"
    elif level <= 7:
        return "高风险"
    else:
        return "严重风险"


def get_risk_action(level: int) -> str:
    """根据风险等级返回行动建议"""
    if level <= 1:
        return "正常回复"
    elif level <= 3:
        return "注意措辞"
    elif level <= 5:
        return "谨慎回复"
    elif level <= 7:
        return "建议延迟回复"
    else:
        return "建议不回复"