"""界面风格附加样式——圆角、阴影、动画"""

# PyQt6 样式表片段
STYLESHEET = """
/* 全局样式 */
QWidget {
    font-family: "Noto Sans CJK SC", "Noto Sans", "Sans Serif";
    font-size: 13px;
    color: #E2E8F0;
}

/* 主窗口 */
#MainWindow {
    background-color: #1E1E2E;
    border: 1px solid #3D3D5C;
    border-radius: 12px;
}

/* 卡片容器 */
#CardWidget {
    background-color: #2D2D3F;
    border-radius: 8px;
    padding: 8px;
}

#CardWidget:hover {
    background-color: #363649;
}

/* 按钮 */
QPushButton {
    background-color: #7C3AED;
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #6D28D9;
}

QPushButton:pressed {
    background-color: #5B21B6;
}

QPushButton:disabled {
    background-color: #4B5563;
    color: #9CA3AF;
}

/* 次要按钮 */
QPushButton#SecondaryButton {
    background-color: transparent;
    border: 1px solid #3D3D5C;
    color: #94A3B8;
}

QPushButton#SecondaryButton:hover {
    background-color: #2D2D3F;
    border-color: #7C3AED;
    color: #E2E8F0;
}

/* 危险按钮 */
QPushButton#DangerButton {
    background-color: #EF4444;
}

QPushButton#DangerButton:hover {
    background-color: #DC2626;
}

/* 标签 */
QLabel {
    color: #E2E8F0;
    background: transparent;
}

QLabel#TitleLabel {
    font-size: 15px;
    font-weight: 600;
    color: #F1F5F9;
}

QLabel#SubtitleLabel {
    font-size: 11px;
    color: #64748B;
}

QLabel#RiskLabel {
    font-size: 14px;
    font-weight: 600;
}

QLabel#MessageText {
    font-size: 13px;
    color: #CBD5E1;
    line-height: 1.4;
}

/* 滚动区域 */
QScrollArea {
    border: none;
    background: transparent;
}

QScrollBar:vertical {
    background-color: #1E1E2E;
    width: 6px;
    border-radius: 3px;
}

QScrollBar::handle:vertical {
    background-color: #3D3D5C;
    border-radius: 3px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background-color: #7C3AED;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* 下拉框 */
QComboBox {
    background-color: #2D2D3F;
    border: 1px solid #3D3D5C;
    border-radius: 6px;
    padding: 4px 8px;
    color: #E2E8F0;
}

QComboBox:hover {
    border-color: #7C3AED;
}

QComboBox::drop-down {
    border: none;
    padding-right: 4px;
}

QComboBox QAbstractItemView {
    background-color: #2D2D3F;
    border: 1px solid #3D3D5C;
    selection-background-color: #7C3AED;
    selection-color: #FFFFFF;
    color: #E2E8F0;
}

/* 进度条 */
QProgressBar {
    background-color: #2D2D3F;
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
    font-size: 10px;
}

QProgressBar::chunk {
    background-color: #7C3AED;
    border-radius: 4px;
}

/* 菜单栏 */
QMenuBar {
    background-color: #1E1E2E;
    border-bottom: 1px solid #3D3D5C;
}

QMenuBar::item {
    padding: 4px 10px;
    background: transparent;
}

QMenuBar::item:selected {
    background-color: #2D2D3F;
}

QMenu {
    background-color: #2D2D3F;
    border: 1px solid #3D3D5C;
    padding: 4px;
}

QMenu::item {
    padding: 6px 24px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #7C3AED;
}

QMenu::separator {
    height: 1px;
    background-color: #3D3D5C;
    margin: 4px 8px;
}
"""


def apply_style(widget):
    """对 QWidget 应用全局样式表"""
    widget.setStyleSheet(STYLESHEET)