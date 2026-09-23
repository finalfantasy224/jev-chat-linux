"""
悬浮窗主界面（HUD）—— PyQt6 实现

Linux 版使用 PyQt6 实现 macOS NSPanel 风格的浮动面板：
- 始终置顶、无边框、半透明磨砂效果
- 仅在微信前台时显示
- 显示意图、风险等级、候选回复
"""

from __future__ import annotations

import json
import logging
import os
import time
import threading
from typing import Optional
from pathlib import Path

from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    pyqtSignal, pyqtProperty, QEvent,
)
from PyQt6.QtGui import (
    QAction, QColor, QFont, QIcon, QPainter, QLinearGradient,
    QBrush, QPen, QPalette, QFontDatabase, QShowEvent,
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QSystemTrayIcon, QMenu,
    QCheckBox, QComboBox, QSizePolicy, QMainWindow, QSpacerItem,
    QGraphicsBlurEffect,
)

from src import perception
from src import userconfig
from src import styles
from src import ui_style
from src import builtin

log = logging.getLogger("hud")


class PulseWidget(QWidget):
    """带呼吸灯效果的圆点控件"""

    def __init__(self, color: QColor, size: int = 8, parent=None):
        super().__init__(parent)
        self._color = color
        self._opacity = 1.0
        self._growing = False
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._anim = QPropertyAnimation(self, b"opacity")
        self._anim.setDuration(1500)
        self._anim.setStartValue(0.4)
        self._anim.setEndValue(1.0)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)

    def get_opacity(self) -> float:
        return self._opacity

    def set_opacity(self, val: float):
        self._opacity = val
        self.update()

    opacity = pyqtProperty(float, get_opacity, set_opacity)

    def set_color(self, color: QColor):
        self._color = color
        self.update()

    def start_pulse(self):
        self._anim.start()

    def stop_pulse(self):
        self._anim.stop()
        self._opacity = 1.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self._color)
        color.setAlphaF(self._opacity)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self.rect().adjusted(1, 1, -1, -1))


class MessageCard(QFrame):
    """单条候选回复卡片"""

    clicked = pyqtSignal(str)

    def __init__(self, text: str, prob: float = 0.0, parent=None):
        super().__init__(parent)
        self.text = text
        self.prob = prob
        self._setup_ui()

    def _setup_ui(self):
        self.setObjectName("CardWidget")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # 概率标签
        if self.prob > 0:
            self.prob_label = QLabel(f"{self.prob:.0%}")
            self.prob_label.setStyleSheet(f"""
                color: {styles.COLOR_PRIMARY_LIGHT.name()};
                font-size: 10px;
                font-weight: bold;
                min-width: 28px;
            """)
            self.prob_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self.prob_label)

        # 回复文本
        self.text_label = QLabel(self.text[:80])
        self.text_label.setWordWrap(True)
        self.text_label.setStyleSheet("color: #E2E8F0; font-size: 12px;")
        self.text_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.text_label)

        # 按钮组
        btn_style = """
            QPushButton {{
                background: transparent;
                border: 1px solid {border};
                color: {text};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background: {hover};
                border-color: {primary};
            }}
        """.format(
            border=styles.COLOR_BORDER.name(),
            text=styles.COLOR_TEXT_SECONDARY.name(),
            hover=styles.COLOR_SURFACE_LIGHT.name(),
            primary=styles.COLOR_PRIMARY_LIGHT.name(),
        )

        self.copy_btn = QPushButton("复制")
        self.copy_btn.setStyleSheet(btn_style)
        self.copy_btn.clicked.connect(self._on_copy)
        layout.addWidget(self.copy_btn)

        self.fill_btn = QPushButton("填入")
        self.fill_btn.setObjectName("SecondaryButton")
        self.fill_btn.setStyleSheet(btn_style)
        self.fill_btn.clicked.connect(self._on_fill)
        layout.addWidget(self.fill_btn)

    def _on_copy(self):
        QApplication.clipboard().setText(self.text)
        log.info(f"已复制: {self.text[:30]}...")

    def _on_fill(self):
        self.clicked.emit(self.text)


class ToneGroup(QFrame):
    """话术分组（含话术名 + 该话术生成的候选回复）"""

    def __init__(self, tone: str, texts: list[str], prob: float = 0.0, parent=None,
                 on_fill: callable = None):
        super().__init__(parent)
        self.tone = tone
        self._on_fill_callback = on_fill
        self._setup_ui(tone, texts, prob)

    def _setup_ui(self, tone: str, texts: list[str], prob: float):
        self.setObjectName("CardWidget")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # 话术标题行
        header = QHBoxLayout()
        tone_label = QLabel(tone)
        tone_label.setStyleSheet(f"""
            color: {styles.COLOR_PRIMARY_LIGHT.name()};
            font-size: 12px;
            font-weight: 600;
        """)
        header.addWidget(tone_label)
        header.addStretch()
        layout.addLayout(header)

        # 候选回复
        for i, text in enumerate(texts):
            card = MessageCard(text, prob if i == 0 else 0.0)
            if self._on_fill_callback:
                card.clicked.connect(self._on_fill_callback)
            layout.addWidget(card)

    def update_texts(self, texts: list[str]):
        """更新候选回复"""
        # 清除旧的卡片
        layout = self.layout()
        if not layout:
            return
        # 保留标题，移除卡片
        while layout.count() > 1:
            item = layout.takeAt(layout.count() - 1)
            if item and item.widget():
                item.widget().deleteLater()
        for i, text in enumerate(texts):
            card = MessageCard(text)
            layout.addWidget(card)


class HUDWidget(QWidget):
    """主悬浮窗面板"""

    # 线程安全信号：后台线程通过它们更新 UI
    candidates_ready = pyqtSignal(object)   # groups
    judge_ready = pyqtSignal(object)       # judge_result
    timing_ready = pyqtSignal(float, float) # judge_ms, gen_ms

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MainWindow")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # 允许点击窗口内的控件时获取焦点（下拉框等需要）
        self.setAttribute(Qt.WidgetAttribute.WA_X11NetWmWindowTypePopupMenu)
        # 鼠标悬停时停止轮询隐藏
        self._user_interacting = False

        # 状态
        self._chat_title = ""
        self._current_message = ""
        self._judge_result = None
        self._candidates = []
        self._analyzing = False
        self._prev_fingerprint = None
        self._prev_layout = None
        self._previous_wid = None

        # 窗口尺寸
        self._width = styles.WINDOW_WIDTH
        self._min_height = styles.WINDOW_MIN_HEIGHT
        self._max_height = styles.WINDOW_MAX_HEIGHT

        # 拖拽
        self._drag_pos = None

        self._setup_ui()
        self._setup_timers()
        self._setup_signals()
        self._setup_tray()

    def _setup_ui(self):
        self.setFixedWidth(self._width)
        self.setMinimumHeight(self._min_height)
        self.setMaximumHeight(self._max_height)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(styles.PADDING, styles.PADDING,
                                       styles.PADDING, styles.PADDING)
        main_layout.setSpacing(6)

        # ── 顶部：聊天名 + 状态 ──
        top_bar = QHBoxLayout()
        top_bar.setSpacing(4)

        self.chat_label = QLabel("等待消息…")
        self.chat_label.setObjectName("TitleLabel")
        self.chat_label.setStyleSheet(f"""
            color: {styles.COLOR_TEXT.name()};
            font-size: 14px;
            font-weight: 600;
        """)
        top_bar.addWidget(self.chat_label)

        top_bar.addStretch()

        # 风险圆点
        self.risk_dot = PulseWidget(styles.COLOR_ACCENT, 8)
        top_bar.addWidget(self.risk_dot)

        # 设置按钮
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setFixedSize(24, 24)
        self.settings_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {styles.COLOR_TEXT_SECONDARY.name()};
                font-size: 16px;
            }}
            QPushButton:hover {{
                color: {styles.COLOR_PRIMARY_LIGHT.name()};
            }}
        """)
        self.settings_btn.clicked.connect(self._open_settings)
        top_bar.addWidget(self.settings_btn)

        main_layout.addLayout(top_bar)

        # ── 状态行 ──
        self.status_label = QLabel("等待微信消息…")
        self.status_label.setObjectName("SubtitleLabel")
        self.status_label.setStyleSheet(f"""
            color: {styles.COLOR_TEXT_MUTED.name()};
            font-size: 11px;
            padding: 0;
        """)
        self.status_label.setWordWrap(True)
        main_layout.addWidget(self.status_label)

        # ── 消息文本 ──
        self.message_label = QLabel("")
        self.message_label.setObjectName("MessageText")
        self.message_label.setWordWrap(True)
        self.message_label.setMaximumHeight(60)
        self.message_label.setStyleSheet(f"""
            color: {styles.COLOR_TEXT.name()};
            font-size: 13px;
            background: {styles.COLOR_SURFACE_LIGHT.name()};
            border-radius: 6px;
            padding: 6px 8px;
        """)
        self.message_label.setVisible(False)
        main_layout.addWidget(self.message_label)

        # ── 判断结果 ──
        judge_row = QHBoxLayout()
        judge_row.setSpacing(8)

        self.intent_label = QLabel("")
        self.intent_label.setStyleSheet(f"""
            color: {styles.COLOR_PRIMARY_LIGHT.name()};
            font-size: 13px;
            font-weight: 600;
        """)
        judge_row.addWidget(self.intent_label)

        self.confidence_label = QLabel("")
        self.confidence_label.setStyleSheet(f"""
            color: {styles.COLOR_TEXT_MUTED.name()};
            font-size: 11px;
        """)
        judge_row.addWidget(self.confidence_label)

        judge_row.addStretch()

        self.risk_label = QLabel("")
        self.risk_label.setObjectName("RiskLabel")
        judge_row.addWidget(self.risk_label)

        main_layout.addLayout(judge_row)

        # ── 行动建议 ──
        self.action_label = QLabel("")
        self.action_label.setStyleSheet(f"""
            color: {styles.COLOR_WARNING.name()};
            font-size: 11px;
        """)
        self.action_label.setWordWrap(True)
        self.action_label.setVisible(False)
        main_layout.addWidget(self.action_label)

        # ── 话术选择 ──
        tones_layout = QHBoxLayout()
        tones_layout.setSpacing(4)

        self.tone_selector = QComboBox()
        self.tone_selector.addItem("不用", "不用")
        for tone_name in builtin.BUILTIN_TONES:
            display = builtin.get_tone_display_name(tone_name)
            self.tone_selector.addItem(display, tone_name)
        self.tone_selector.setStyleSheet(f"""
            QComboBox {{
                background: {styles.COLOR_SURFACE.name()};
                border: 1px solid {styles.COLOR_BORDER.name()};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 11px;
                color: {styles.COLOR_TEXT.name()};
                max-width: 100px;
            }}
        """)
        # 加载上次保存的话术并连接保存信号
        self._load_active_tones()
        self.tone_selector.currentIndexChanged.connect(self._save_active_tones)
        tones_layout.addWidget(QLabel("话术:"))
        tones_layout.addWidget(self.tone_selector)
        tones_layout.addStretch()

        main_layout.addLayout(tones_layout)

        # ── 候选回复区域 ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.candidates_widget = QWidget()
        self.candidates_widget.setStyleSheet("background: transparent;")
        self.candidates_layout = QVBoxLayout(self.candidates_widget)
        self.candidates_layout.setContentsMargins(0, 0, 0, 0)
        self.candidates_layout.setSpacing(4)
        self.candidates_layout.addStretch()

        scroll.setWidget(self.candidates_widget)
        main_layout.addWidget(scroll, stretch=1)

        # ── 底部状态 ──
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(4)

        self.timing_label = QLabel("")
        self.timing_label.setStyleSheet(f"""
            color: {styles.COLOR_TEXT_MUTED.name()};
            font-size: 9px;
        """)
        bottom_bar.addWidget(self.timing_label)

        bottom_bar.addStretch()

        self.close_btn = QPushButton("退出")
        self.close_btn.setObjectName("DangerButton")
        self.close_btn.setFixedHeight(20)
        self.close_btn.setStyleSheet("""
            QPushButton {
                font-size: 10px;
                padding: 2px 8px;
                border-radius: 3px;
            }
        """)
        self.close_btn.clicked.connect(QApplication.quit)
        bottom_bar.addWidget(self.close_btn)

        main_layout.addLayout(bottom_bar)

    def _setup_timers(self):
        """设置轮询定时器"""
        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll_wechat)
        self._poll_timer.start(int(perception.get_poll_interval() * 1000))

        # 窗口位置更新定时器
        self._pos_timer = QTimer()
        self._pos_timer.timeout.connect(self._update_position)
        self._pos_timer.start(500)

        # 初始定位
        QTimer.singleShot(100, self._update_position)

    def _setup_signals(self):
        """连接线程安全信号到主线程槽"""
        self.candidates_ready.connect(self._update_candidates, Qt.ConnectionType.QueuedConnection)
        self.judge_ready.connect(self._update_judge_result, Qt.ConnectionType.QueuedConnection)
        self.timing_ready.connect(self._update_timing, Qt.ConnectionType.QueuedConnection)

    def _setup_tray(self):
        """系统托盘图标"""
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(QIcon.fromTheme("dialog-information"))
        self.tray.setToolTip("jev-chat-linux")

        tray_menu = QMenu()
        show_action = tray_menu.addAction("显示面板")
        show_action.triggered.connect(self.show)
        settings_action = tray_menu.addAction("设置")
        settings_action.triggered.connect(self._open_settings)
        tray_menu.addSeparator()
        quit_action = tray_menu.addAction("退出")
        quit_action.triggered.connect(QApplication.quit)

        self.tray.setContextMenu(tray_menu)
        self.tray.show()

    def _update_position(self):
        """将悬浮窗定位在微信窗口右侧或屏幕右侧"""
        try:
            win = perception.find_wechat_window()
            if win:
                wid = win.get("id", "") if "id" in win else win.get("xdotool_id", "")
                import subprocess
                result = subprocess.run(
                    ["xdotool", "getwindowgeometry", str(wid)],
                    capture_output=True, text=True, timeout=3
                )
                if result.returncode == 0:
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

                    if win_w > 0 and win_h > 0:
                        # 放在微信窗口右侧
                        hud_x = win_x + win_w + 6
                        hud_y = win_y + 80
                        self.move(hud_x, hud_y)
                        return

            # 默认：屏幕右侧
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                self.move(geo.right() - self._width - 20, geo.top() + 60)
        except Exception as e:
            log.debug(f"定位失败: {e}")

    def _poll_wechat(self):
        """轮询微信消息——用户正在交互时跳过隐藏"""
        if self._analyzing:
            return

        # 如果用户正在与悬浮窗交互（鼠标在窗口内或下拉框开着），不隐藏
        if self._user_interacting:
            return

        # 如果悬浮窗本身是活动窗口（用户点了里面的控件），不隐藏
        if self.isActiveWindow():
            return

        if not perception.is_wechat_foreground():
            self.hide()
            return

        if not self.isVisible():
            self.show()
            self._update_position()

        try:
            # 一次感知轮询
            message = perception.poll_wechat_chat()

            if message is None:
                self.status_label.setText("等待可确认的对方消息…")
                return

            # 检查是否新消息
            if message.text == self._current_message:
                return

            self._current_message = message.text
            # 显示全部识别的消息列表
            lines = message.text.split("\n")
            if len(lines) > 1:
                display = " | ".join(lines[-3:])  # 显示最近3条
            else:
                display = message.text[:100]
            self.message_label.setText(display)
            self.message_label.setVisible(True)
            self.status_label.setText("分析中…")
            self._analyzing = True

            # 异步分析：传最新一行做判断，所有行做上下文
            latest_msg = lines[-1] if len(lines) > 1 else message.text
            threading.Thread(target=self._run_analysis,
                           args=(latest_msg, message.text), daemon=True).start()

        except Exception as e:
            log.error(f"轮询失败: {e}")
            self.status_label.setText(f"感知错误: {str(e)[:40]}")

    def _run_analysis(self, message: str, context: str | None = None):
        """异步运行判断 + 生成
        Args:
            message: 最新一条消息文本
            context: 完整聊天上下文（多条消息，换行分隔）
        """
        from src.judge import make_judge
        from src.generate import Generator

        t0 = time.perf_counter()
        self._update_status("正在判断意图…")

        try:
            judge = make_judge()
            # 使用传入的完整上下文（多条消息）
            context_messages = context.split("\n") if context else []

            # 判断
            judge_result = judge.judge(
                message,
                context="\n".join(context_messages) if context_messages else None
            )
            t_judge = time.perf_counter()

            # 通过信号更新 UI（自动在主线程执行）
            self.judge_ready.emit(judge_result)

            # 生成候选回复
            self._update_status("正在生成回复…")

            generator = Generator()
            # 获取当前选中的话术（已保存的配置）
            active_tones = self._get_active_tones()
            if not active_tones:
                active_tones = ["友好亲切"]

            gen_result = generator.generate(
                message=message,
                intent=judge_result["intent"],
                slot_tones=active_tones,
                context="\n".join(context_messages) if context_messages else None
            )
            t_gen = time.perf_counter()

            # 通过信号更新候选和耗时
            if gen_result.get("groups"):
                self.candidates_ready.emit(gen_result["groups"])
                self.timing_ready.emit(t_judge - t0, t_gen - t_judge)
                self._update_status("就绪")
            else:
                error = gen_result.get("error", "候选生成失败")
                self._update_status(f"生成失败: {error[:40]}")

        except Exception as e:
            log.error(f"分析失败: {e}")
            self._update_status(f"分析失败: {str(e)[:40]}")
        finally:
            self._analyzing = False

    def _load_active_tones(self):
        """从配置加载上次选择的话术"""
        saved = userconfig.get_config_value("ACTIVE_TONES", "友好亲切,简洁高效,正式商务")
        if not saved:
            saved = "友好亲切,简洁高效,正式商务"
        # 只取第一个做单下拉框的选中项
        first_tone = saved.split(",")[0].strip()
        for i in range(self.tone_selector.count()):
            if self.tone_selector.itemData(i) == first_tone:
                self.tone_selector.setCurrentIndex(i)
                break

    def _save_active_tones(self):
        """保存当前选择的话术到配置"""
        tone = self.tone_selector.currentData()
        if not tone:
            return
        config = userconfig.load_env_file()
        config["ACTIVE_TONES"] = tone
        try:
            userconfig.save_env_file(config)
            log.info(f"话术已保存: {tone}")
        except Exception as e:
            log.error(f"保存话术失败: {e}")

    def _get_active_tones(self) -> list[str]:
        """获取当前生效的话术列表"""
        tone = self.tone_selector.currentData()
        if not tone or tone == "不用":
            return []
        return [tone]

    def _update_judge_result(self, result: dict):
        """更新判断结果显示"""
        self._judge_result = result

        intent = result.get("intent", "")
        confidence = result.get("confidence", 0)
        risk = result.get("risk", 0)
        actions = result.get("actions", [])

        self.intent_label.setText(f"意图: {intent}")
        self.confidence_label.setText(f"{confidence:.0%}")

        risk_color = styles.get_risk_color(int(risk))
        risk_label = styles.get_risk_label(int(risk))
        self.risk_label.setText(f"风险 {risk:.0f}: {risk_label}")
        self.risk_label.setStyleSheet(f"""
            color: {risk_color.name()};
            font-size: 13px;
            font-weight: 600;
        """)
        self.risk_dot.set_color(risk_color)
        self.risk_dot.start_pulse()

        if actions:
            self.action_label.setText("建议: " + " · ".join(actions[:3]))
            self.action_label.setVisible(True)
        else:
            self.action_label.setVisible(False)

    def _update_candidates(self, groups: list[dict]):
        """更新候选回复区域"""
        # 清除旧内容
        layout = self.candidates_layout
        while layout.count() > 1:  # 保留最后的 stretcher
            item = layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        for group in groups:
            tone = group.get("tone", "通用")
            texts = group.get("texts", [])
            if texts:
                tone_group = ToneGroup(tone, texts, on_fill=self._paste_to_wechat)
                layout.insertWidget(layout.count() - 1, tone_group)

    def _paste_to_wechat(self, text: str):
        """将文字填入微信输入框"""
        import subprocess
        try:
            window_name = userconfig.get_config_value("WECHAT_WINDOW_NAME", "微信")
            # 查找微信窗口
            r = subprocess.run(['xdotool', 'search', '--name', window_name],
                              capture_output=True, text=True, timeout=5)
            if r.returncode != 0 or not r.stdout.strip():
                log.warning("未找到微信窗口")
                return
            win_ids = r.stdout.strip().split()
            win_id = win_ids[-1]  # 取最后一个（通常是实际聊天窗口）
            
            # 获取窗口位置
            r2 = subprocess.run(['xdotool', 'getwindowgeometry', win_id],
                               capture_output=True, text=True, timeout=5)
            win_x = win_y = win_w = win_h = 0
            for line in r2.stdout.splitlines():
                line = line.strip()
                if line.startswith('Position:'):
                    pos = line.split(':', 1)[1].strip().split('(')[0].strip()
                    parts = [p.strip() for p in pos.split(',')]
                    win_x, win_y = int(parts[0]), int(parts[1])
                elif line.startswith('Geometry:'):
                    geo = line.split(':', 1)[1].strip()
                    dims = [p.strip() for p in geo.split('x')]
                    win_w, win_h = int(dims[0]), int(dims[1])
            if win_w == 0:
                log.warning("无法获取窗口大小")
                return
            
            # 聚焦窗口
            subprocess.run(['xdotool', 'windowfocus', win_id], timeout=5)
            import time
            time.sleep(0.15)
            
            # 点击输入框（窗口底部中央）
            click_x = win_x + win_w // 2
            click_y = win_y + win_h - 40
            subprocess.run(['xdotool', 'mousemove', str(click_x), str(click_y), 'click', '1'],
                          timeout=5)
            time.sleep(0.15)
            
            # 填入文字：复制到剪贴板后 Ctrl+V（比 xdotool type 更可靠）
            subprocess.run(['xclip', '-selection', 'clipboard'],
                          input=text.encode('utf-8'), timeout=5)
            time.sleep(0.1)
            subprocess.run(['xdotool', 'key', 'ctrl+v'], timeout=5)
            log.info(f"已填入({len(text)}字): {text[:30]}...")
        except Exception as e:
            log.error(f"填入失败: {e}")

    def _update_timing(self, judge_ms: float, gen_ms: float):
        """更新耗时信息"""
        self.timing_label.setText(
            f"判断 {judge_ms*1000:.0f}ms · 生成 {gen_ms*1000:.0f}ms")

    def _update_status(self, text: str):
        """更新状态行（线程安全）"""
        def _set():
            self.status_label.setText(text)
        QTimer.singleShot(0, _set)

    def _open_settings(self):
        """打开设置窗口"""
        from src.settings import SettingsWindow
        self._settings_win = SettingsWindow()
        self._settings_win.show()

    # ── 鼠标拖拽 ──
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        """绘制磨砂背景效果"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 半透明背景
        painter.setBrush(QBrush(QColor(30, 30, 46, 230)))
        painter.setPen(QPen(QColor(61, 61, 92, 200), 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)

        super().paintEvent(event)

    # ── 用户交互跟踪 ──
    def enterEvent(self, event):
        """鼠标进入悬浮窗——标记为交互中，防止被轮询隐藏"""
        self._user_interacting = True
        super().enterEvent(event)

    def leaveEvent(self, event):
        """鼠标离开悬浮窗——延迟取消交互标记"""
        # 延迟取消，避免下拉框弹出时触发离开事件导致窗口隐藏
        QTimer.singleShot(200, self._clear_interaction)
        super().leaveEvent(event)

    def _clear_interaction(self):
        """清除交互标记——检查鼠标是否真的离开了窗口"""
        if self.underMouse() or self.isActiveWindow():
            return  # 鼠标还在窗口内
        # 检查是否有弹出窗口（下拉框等）
        for widget in QApplication.topLevelWidgets():
            if widget is not self and widget.isVisible() and widget.isWindow():
                return  # 有弹出窗口，保持交互状态
        self._user_interacting = False

    def changeEvent(self, event):
        """窗口状态变化时跟踪激活状态"""
        if event.type() == QEvent.Type.ActivationChange:
            if self.isActiveWindow():
                self._user_interacting = True
        super().changeEvent(event)


class HUDApp(QApplication):
    """应用程序入口"""

    def __init__(self, argv):
        super().__init__(argv)
        self.setApplicationName("jev-chat-linux")
        self.setOrganizationName("jev-chat")

        # 确保数据目录存在
        data_dir = os.path.expanduser("~/.local/share/jev-chat-linux")
        os.makedirs(data_dir, exist_ok=True)

        # 加载字体
        QFontDatabase.addApplicationFont(":/fonts/NotoSansCJKsc-Regular.otf")

        # 创建主窗口
        self.hud = HUDWidget()
        self.hud.show()

        # 预热
        QTimer.singleShot(2000, self._warm)

    def _warm(self):
        """后台预热判断模型"""
        try:
            from src.judge import make_judge
            judge = make_judge()
            self.hud._update_status("预热判断模型…")
            threading.Thread(target=judge.warm, daemon=True).start()
        except Exception as e:
            log.info(f"预热跳过: {e}")


if __name__ == "__main__":
    import sys

    app = HUDApp(sys.argv)
    sys.exit(app.exec())