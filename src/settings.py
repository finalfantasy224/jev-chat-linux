"""设置窗口——PyQt6 实现

macOS 版使用原生 NSPanel，Linux 版使用 PyQt6 QDialog。
支持编辑 Jev、OpenAI、Anthropic 三组配置。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTabWidget, QWidget, QFormLayout, QGroupBox,
    QMessageBox, QComboBox, QCheckBox, QTextEdit, QProgressBar,
    QSizePolicy, QSpacerItem,
)

from src import userconfig
from src import settings_config

log = logging.getLogger("settings")


class SettingsWindow(QDialog):
    """设置窗口"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("jev-chat-linux 设置")
        self.setMinimumWidth(480)
        self.setMinimumHeight(400)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._config = userconfig.get_config()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 标题
        title = QLabel("模型设置")
        title.setStyleSheet("font-size: 16px; font-weight: 600; color: #E2E8F0;")
        layout.addWidget(title)

        subtitle = QLabel(f"配置文件: {userconfig.CONFIG_FILE}")
        subtitle.setStyleSheet("font-size: 11px; color: #64748B;")
        layout.addWidget(subtitle)

        # 标签页
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane {
                background: #2D2D3F;
                border: 1px solid #3D3D5C;
                border-radius: 6px;
            }
            QTabBar::tab {
                background: #1E1E2E;
                color: #94A3B8;
                padding: 6px 14px;
                border: 1px solid #3D3D5C;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            QTabBar::tab:selected {
                background: #2D2D3F;
                color: #E2E8F0;
            }
            QTabBar::tab:hover {
                color: #A78BFA;
            }
        """)

        # 判断 · Jev 页
        self.jev_tab = self._create_jev_tab()
        tabs.addTab(self.jev_tab, "判断 · Jev")

        # 生成 · OpenAI 页
        self.openai_tab = self._create_openai_tab()
        tabs.addTab(self.openai_tab, "生成 · OpenAI")

        # 生成 · Anthropic 页
        self.anthropic_tab = self._create_anthropic_tab()
        tabs.addTab(self.anthropic_tab, "生成 · Anthropic")

        # 通用设置页
        self.general_tab = self._create_general_tab()
        tabs.addTab(self.general_tab, "通用")

        layout.addWidget(tabs)

        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #64748B; font-size: 11px;")
        btn_layout.addWidget(self.status_label)

        self.test_btn = QPushButton("测试连接")
        self.test_btn.setObjectName("SecondaryButton")
        self.test_btn.clicked.connect(self._test_connection)
        btn_layout.addWidget(self.test_btn)

        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self._save_config)
        btn_layout.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setObjectName("DangerButton")
        self.cancel_btn.clicked.connect(self.close)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

        # 底部信息
        info = QLabel("保存后必须退出并重新打开应用。配置不保存到环境变量。")
        info.setStyleSheet("color: #64748B; font-size: 10px;")
        layout.addWidget(info)

    def _create_input(self, label: str, key: str, secret: bool = False,
                      default: str = "") -> QHBoxLayout:
        """创建一行配置输入"""
        row = QHBoxLayout()
        row.setSpacing(6)

        lbl = QLabel(label)
        lbl.setFixedWidth(80)
        lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")
        row.addWidget(lbl)

        edit = QLineEdit()
        edit.setStyleSheet("""
            QLineEdit {
                background: #363649;
                border: 1px solid #3D3D5C;
                border-radius: 4px;
                padding: 4px 8px;
                color: #E2E8F0;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #7C3AED;
            }
        """)
        if secret:
            edit.setEchoMode(QLineEdit.EchoMode.Password)

        # 设置当前值
        current = self._config.get(key, default)
        if current:
            edit.setText(current)

        edit.setObjectName(f"input_{key}")
        row.addWidget(edit)

        return row

    def _create_jev_tab(self) -> QWidget:
        """创建 Jev 配置页"""
        tab = QWidget()
        tab.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        # 当前状态
        if self._config.get("TYPESAFE_API_KEY"):
            status = QLabel("✓ 使用自己的 Jev API Key")
            status.setStyleSheet("color: #10B981; font-size: 12px; font-weight: 600;")
        else:
            status = QLabel("未配置 Jev Key，将使用本地判断模型 (decider-2b)")
            status.setStyleSheet("color: #F59E0B; font-size: 12px;")
        layout.addWidget(status)

        layout.addLayout(self._create_input("API Key", "TYPESAFE_API_KEY", secret=True))
        layout.addLayout(self._create_input("Base URL", "TYPESAFE_BASE_URL",
                                            default="https://api.typesafe.ai"))
        layout.addLayout(self._create_input("Model", "TYPESAFE_MODEL",
                                            default="jev-latest"))

        # 模型列表按钮
        model_btn = QPushButton("获取模型列表")
        model_btn.setObjectName("SecondaryButton")
        model_btn.clicked.connect(lambda: self._fetch_models("TYPESAFE_BASE_URL", "TYPESAFE_MODEL"))
        layout.addWidget(model_btn)

        # 离线判断选项
        judge_backend = self._config.get("JUDGE_BACKEND", "")
        local_cb = QCheckBox("启用离线判断（使用本地 decider-2b 模型）")
        local_cb.setChecked(judge_backend == "local")
        local_cb.setObjectName("cb_local_judge")
        local_cb.setStyleSheet("color: #94A3B8; font-size: 12px;")
        layout.addWidget(local_cb)

        # 删除模型按钮
        delete_btn = QPushButton("删除本地判断模型…")
        delete_btn.setObjectName("DangerButton")
        delete_btn.clicked.connect(self._delete_local_model)
        layout.addWidget(delete_btn)

        layout.addStretch()
        return tab

    def _create_openai_tab(self) -> QWidget:
        """创建 OpenAI 配置页"""
        tab = QWidget()
        tab.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        if self._config.get("OPENAI_API_KEY"):
            status = QLabel("✓ 使用自己的 OpenAI 兼容 Key（优先级高）")
            status.setStyleSheet("color: #10B981; font-size: 12px; font-weight: 600;")
        else:
            status = QLabel("未配置 OpenAI Key")
            status.setStyleSheet("color: #F59E0B; font-size: 12px;")
        layout.addWidget(status)

        layout.addLayout(self._create_input("API Key", "OPENAI_API_KEY", secret=True))
        layout.addLayout(self._create_input("Base URL", "OPENAI_BASE_URL",
                                            default="https://api.deepseek.com"))
        layout.addLayout(self._create_input("Model", "OPENAI_MODEL",
                                            default="deepseek-chat"))

        model_btn = QPushButton("获取模型列表")
        model_btn.setObjectName("SecondaryButton")
        model_btn.clicked.connect(lambda: self._fetch_models("OPENAI_BASE_URL", "OPENAI_MODEL",
                                                             api_key="OPENAI_API_KEY"))
        layout.addWidget(model_btn)

        layout.addStretch()
        return tab

    def _create_anthropic_tab(self) -> QWidget:
        """创建 Anthropic 配置页"""
        tab = QWidget()
        tab.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        if self._config.get("ANTHROPIC_API_KEY"):
            status = QLabel("✓ 使用自己的 Anthropic Key")
            status.setStyleSheet("color: #10B981; font-size: 12px; font-weight: 600;")
        else:
            status = QLabel("未配置 Anthropic Key")
            status.setStyleSheet("color: #F59E0B; font-size: 12px;")
        layout.addWidget(status)

        layout.addLayout(self._create_input("API Key", "ANTHROPIC_API_KEY", secret=True))
        layout.addLayout(self._create_input("Base URL", "ANTHROPIC_BASE_URL"))
        layout.addLayout(self._create_input("Model", "ANTHROPIC_MODEL"))

        model_btn = QPushButton("获取模型列表")
        model_btn.setObjectName("SecondaryButton")
        model_btn.clicked.connect(lambda: self._fetch_models("ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL",
                                                             api_key="ANTHROPIC_API_KEY",
                                                             api_type="anthropic"))
        layout.addWidget(model_btn)

        layout.addStretch()
        return tab

    def _create_general_tab(self) -> QWidget:
        """创建通用设置页"""
        tab = QWidget()
        tab.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        # 微信窗口名
        layout.addLayout(self._create_input("微信窗口名", "WECHAT_WINDOW_NAME",
                                            default="微信"))

        # 自定义话术
        lbl = QLabel("自定义话术（格式：名字=说明|名字=说明）")
        lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")
        layout.addWidget(lbl)

        tones_edit = QTextEdit()
        tones_edit.setMaximumHeight(80)
        tones_edit.setStyleSheet("""
            QTextEdit {
                background: #363649;
                border: 1px solid #3D3D5C;
                border-radius: 4px;
                padding: 4px 8px;
                color: #E2E8F0;
                font-size: 12px;
            }
        """)
        tones_edit.setText(self._config.get("JEV_TONES", ""))
        tones_edit.setObjectName("input_JEV_TONES")
        layout.addWidget(tones_edit)

        layout.addStretch()
        return tab

    def _collect_values(self) -> dict:
        """从界面收集所有配置值"""
        config = {}
        for tab in [self.jev_tab, self.openai_tab, self.anthropic_tab, self.general_tab]:
            for edit in tab.findChildren(QLineEdit):
                key = edit.objectName().replace("input_", "")
                if key:
                    config[key] = edit.text()
            for cb in tab.findChildren(QCheckBox):
                if cb.objectName() == "cb_local_judge":
                    config["JUDGE_BACKEND"] = "local" if cb.isChecked() else ""
            for te in tab.findChildren(QTextEdit):
                key = te.objectName().replace("input_", "")
                if key:
                    config[key] = te.toPlainText()
        return config

    def _save_config(self):
        """保存配置"""
        new_config = self._collect_values()

        # 读取现有配置并更新
        existing = userconfig.load_env_file()
        existing.update(new_config)

        try:
            userconfig.save_env_file(existing)
            self.status_label.setText("✓ 已保存，请重启应用")
            self.status_label.setStyleSheet("color: #10B981; font-size: 11px;")
        except Exception as e:
            self.status_label.setText(f"✗ 保存失败: {e}")
            self.status_label.setStyleSheet("color: #EF4444; font-size: 11px;")

    def _test_connection(self):
        """测试当前输入的连接"""
        config = self._collect_values()

        # 确定测试哪一组
        if config.get("OPENAI_API_KEY"):
            base = config.get("OPENAI_BASE_URL", "https://api.deepseek.com")
            key = config["OPENAI_API_KEY"]
            model = config.get("OPENAI_MODEL", "deepseek-chat")
            api_type = "openai"
        elif config.get("TYPESAFE_API_KEY"):
            base = config.get("TYPESAFE_BASE_URL", "https://api.typesafe.ai")
            key = config["TYPESAFE_API_KEY"]
            model = config.get("TYPESAFE_MODEL", "jev-latest")
            api_type = "typesafe"
        else:
            self.status_label.setText("请先输入 API Key")
            self.status_label.setStyleSheet("color: #F59E0B; font-size: 11px;")
            return

        self.status_label.setText("测试中…")
        self.status_label.setStyleSheet("color: #3B82F6; font-size: 11px;")

        def _test():
            try:
                from src.generate import Generator, http_post_json, _endpoint, jev_request_url

                if api_type == "typesafe":
                    url = jev_request_url(base)
                    body = {"model": model, "messages": [{"role": "user", "content": "你好"}],
                            "max_tokens": 10}
                    headers = {"content-type": "application/json",
                               "authorization": f"Bearer {key}"}
                    data = http_post_json(url, headers, body, 15)
                    ok = bool(data)
                else:
                    g = Generator(model=model)
                    result = g.generate("测试消息", "闲聊")
                    ok = bool(result.get("groups") or result.get("error", ""))
                    if not ok:
                        raise RuntimeError(result.get("error", "无响应"))

                self.status_label.setText("✓ 连接成功")
                self.status_label.setStyleSheet("color: #10B981; font-size: 11px;")

            except Exception as e:
                self.status_label.setText(f"✗ 连接失败: {str(e)[:50]}")
                self.status_label.setStyleSheet("color: #EF4444; font-size: 11px;")

        threading.Thread(target=_test, daemon=True).start()

    def _fetch_models(self, base_key: str, model_key: str,
                      api_key: str | None = None, api_type: str = "openai"):
        """从 API 获取模型列表"""
        config = self._collect_values()
        base = config.get(base_key, "")
        key = config.get(api_key, "") if api_key else ""

        if not base:
            self.status_label.setText("请先输入 Base URL")
            return

        self.status_label.setText("获取模型列表中…")
        self.status_label.setStyleSheet("color: #3B82F6; font-size: 11px;")

        def _fetch():
            try:
                import urllib.request
                url = f"{base.rstrip('/')}/models"
                headers = {}
                if key:
                    headers["Authorization"] = f"Bearer {key}"

                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read())

                models = []
                if "data" in data and isinstance(data["data"], list):
                    for m in data["data"]:
                        if isinstance(m, dict) and m.get("id"):
                            models.append(m["id"])
                elif isinstance(data, list):
                    models = [m.get("id", str(m)) for m in data if isinstance(m, dict)]

                if not models:
                    self.status_label.setText("未获取到模型列表，可手动输入")
                    return

                # 显示模型列表
                model_list = "\n".join(models[:20])
                QMessageBox.information(self, "可用模型",
                                        f"获取到 {len(models)} 个模型:\n\n{model_list}")

                self.status_label.setText(f"✓ 获取到 {len(models)} 个模型")
                self.status_label.setStyleSheet("color: #10B981; font-size: 11px;")

            except Exception as e:
                self.status_label.setText(f"✗ 获取失败: {str(e)[:40]}")
                self.status_label.setStyleSheet("color: #EF4444; font-size: 11px;")

        threading.Thread(target=_fetch, daemon=True).start()

    def _delete_local_model(self):
        """删除本地判断模型"""
        from src.judge import model_cache_dir, model_disk_usage

        usage = model_disk_usage()
        if usage == 0:
            QMessageBox.information(self, "提示", "本地判断模型不存在")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除本地判断模型（占用 {usage / 1e9:.1f} GB）？\n"
            f"删除后需重新下载才能使用离线判断。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            import shutil
            cache_dir = model_cache_dir()
            try:
                shutil.rmtree(cache_dir, ignore_errors=True)
                self.status_label.setText("✓ 模型已删除")
                self.status_label.setStyleSheet("color: #10B981; font-size: 11px;")
            except Exception as e:
                self.status_label.setText(f"✗ 删除失败: {e}")
                self.status_label.setStyleSheet("color: #EF4444; font-size: 11px;")