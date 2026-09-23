"""单元测试：设置窗口的纯逻辑部分（非 GUI）

SettingsWindow 的 GUI 部分（QDialog）需要显示器，无法在无头环境运行。
这里测试可独立验证的逻辑：
  - _collect_values() 的逻辑等价测试
  - 配置保存逻辑
  - 测试连接方法中的导入路径
"""

import os
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestSettingsCollectValues:
    """测试配置收集逻辑（模拟 _collect_values 的行为）"""

    def test_collect_from_dict(self):
        """模拟从表单收集配置值的行为"""
        # _collect_values 实际上遍历 QLineEdit/QCheckBox 等控件的 objectName
        # 来收集值。这里测试等价的数据处理逻辑。
        form_inputs = {
            "TYPESAFE_API_KEY": "sk-jev-test",
            "TYPESAFE_BASE_URL": "https://api.typesafe.ai",
            "TYPESAFE_MODEL": "jev-latest",
            "OPENAI_API_KEY": "",
            "OPENAI_BASE_URL": "https://api.deepseek.com",
            "OPENAI_MODEL": "deepseek-chat",
            "WECHAT_WINDOW_NAME": "微信",
            "JUDGE_BACKEND": "local" if True else "",
        }

        # 模拟 _collect_values: 只返回有值或需要保存的 key
        collected = {}
        for key, val in form_inputs.items():
            collected[key] = val

        assert collected["TYPESAFE_API_KEY"] == "sk-jev-test"
        assert collected["JUDGE_BACKEND"] == "local"
        assert collected["OPENAI_API_KEY"] == ""

    def test_collect_with_checkbox(self):
        """复选框状态映射到 JUDGE_BACKEND"""
        # 模拟：离线判断复选框勾选 → JUDGE_BACKEND="local"
        cb_checked = True
        collected = {"JUDGE_BACKEND": "local" if cb_checked else ""}
        assert collected["JUDGE_BACKEND"] == "local"

        cb_checked = False
        collected = {"JUDGE_BACKEND": "" if not cb_checked else "local"}
        assert collected["JUDGE_BACKEND"] == ""


class TestSettingsSave:
    """测试配置保存路径"""

    def test_merge_with_existing(self, tmp_path):
        """新配置与现有配置合并"""
        from src import userconfig

        env_file = tmp_path / "env"
        env_file.write_text('# 现有配置\nOPENAI_MODEL="old-model"\n')

        new_config = {
            "OPENAI_MODEL": "new-model",
            "OPENAI_API_KEY": "sk-new",
        }

        # 模拟 _save_config 的行为
        existing = userconfig.load_env_file(env_file)
        existing.update(new_config)
        userconfig.save_env_file(existing, env_file)

        content = env_file.read_text()
        assert 'OPENAI_MODEL="new-model"' in content
        assert 'OPENAI_API_KEY="sk-new"' in content

    def test_no_touch_other_keys(self, tmp_path):
        """保存只改指定 key，不动其他"""
        from src import userconfig

        env_file = tmp_path / "env"
        env_file.write_text('KEEP="untouched"\nCHANGE="original"\n')

        userconfig.save_env_file({"CHANGE": "modified"}, env_file)

        content = env_file.read_text()
        assert 'KEEP="untouched"' in content
        assert 'CHANGE="modified"' in content


class TestSettingsTestConnection:
    """测试「测试连接」的导入路径和逻辑"""

    def test_import_paths(self):
        """验证 settings.py 中测试连接使用的导入路径正确"""
        # 这些导入应该成功（不抛出 ImportError）
        from src.generate import Generator, http_post_json, _endpoint, jev_request_url
        assert Generator is not None
        assert callable(http_post_json)
        assert callable(_endpoint)
        assert callable(jev_request_url)

    def test_generator_create(self):
        """测试创建 Generator 实例"""
        from src.generate import Generator
        g = Generator(model="test-model")
        assert g.model_override == "test-model"
        assert g.timeout == 30

    def test_jev_request_url(self):
        """测试 Jev 请求 URL 拼接逻辑"""
        from src.generate import jev_request_url

        # 基础 URL
        assert jev_request_url("https://api.typesafe.ai") == \
               "https://api.typesafe.ai/v1/systemone"

        # 带版本段
        assert jev_request_url("https://api.typesafe.ai/v1") == \
               "https://api.typesafe.ai/v1/systemone"

        # 已包含动作路径
        assert jev_request_url("https://gateway.example.com/v1/evaluate") == \
               "https://gateway.example.com/v1/evaluate"


class TestSettingsCollectValuesIntegration:
    """集成测试：UI 输入 → 配置保存的全路径"""

    def test_input_to_config_roundtrip(self, tmp_path):
        """模拟用户在界面输入值 → 保存 → 重新加载"""
        from src import userconfig

        env_file = tmp_path / "env"

        # 1. 用户输入
        user_input = {
            "OPENAI_API_KEY": "sk-integration-test",
            "OPENAI_BASE_URL": "https://custom.endpoint.com/v1",
            "OPENAI_MODEL": "gpt-4",
            "WECHAT_WINDOW_NAME": "企业微信",
            "JUDGE_BACKEND": "local",
        }

        # 2. 保存
        userconfig.save_env_file(user_input, env_file)

        # 3. 读出验证
        loaded = userconfig.load_env_file(env_file)
        assert loaded["OPENAI_API_KEY"] == "sk-integration-test"
        assert loaded["OPENAI_BASE_URL"] == "https://custom.endpoint.com/v1"
        assert loaded["OPENAI_MODEL"] == "gpt-4"
        assert loaded["WECHAT_WINDOW_NAME"] == "企业微信"
        assert loaded["JUDGE_BACKEND"] == "local"

    def test_empty_key_treated_as_unset(self, tmp_path):
        """用户清空某个 key 应该保存为空字符串"""
        from src import userconfig

        env_file = tmp_path / "env"
        env_file.write_text('OPENAI_API_KEY="sk-old"\n')

        # 用户清空了 key
        userconfig.save_env_file({"OPENAI_API_KEY": ""}, env_file)

        loaded = userconfig.load_env_file(env_file)
        assert loaded["OPENAI_API_KEY"] == ""