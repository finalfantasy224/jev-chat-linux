"""单元测试：设置数据模型 (settings_config.py)"""

import pytest

from src.settings_config import (
    ProviderConfig,
    SettingsState,
    get_active_generation_source,
    get_judge_source_label,
)


class TestProviderConfig:
    """测试 ProviderConfig 数据类"""

    def test_default_values(self):
        p = ProviderConfig()
        assert p.api_key == ""
        assert p.base_url == ""
        assert p.model == ""
        assert p.enabled is False

    def test_custom_values(self):
        p = ProviderConfig(api_key="sk-test", base_url="https://example.com",
                           model="gpt-4", enabled=True)
        assert p.api_key == "sk-test"
        assert p.base_url == "https://example.com"
        assert p.model == "gpt-4"
        assert p.enabled is True

    def test_mutable(self):
        p = ProviderConfig()
        p.api_key = "new-key"
        assert p.api_key == "new-key"


class TestSettingsState:
    """测试 SettingsState 数据类"""

    def test_defaults(self):
        s = SettingsState()
        assert s.jev.base_url == "https://api.typesafe.ai"
        assert s.jev.model == "jev-latest"
        assert s.openai.base_url == "https://api.deepseek.com"
        assert s.openai.model == "deepseek-chat"
        assert s.anthropic.base_url == ""
        assert s.judge_backend == ""
        assert s.custom_tones == ""
        assert s.wechat_window_name == "微信"

    def test_independent_instances(self):
        """每次创建的默认实例互不干扰"""
        s1 = SettingsState()
        s2 = SettingsState()
        s1.openai.api_key = "key-1"
        s2.openai.api_key = "key-2"
        assert s1.openai.api_key != s2.openai.api_key


class TestGetActiveGenerationSource:
    """测试 get_active_generation_source()"""

    def test_no_source(self):
        s = SettingsState()
        assert get_active_generation_source(s) == ""

    def test_openai_enabled(self):
        s = SettingsState()
        s.openai.enabled = True
        s.openai.api_key = "sk-test"
        assert get_active_generation_source(s) == "openai"

    def test_anthropic_enabled(self):
        s = SettingsState()
        s.anthropic.enabled = True
        s.anthropic.api_key = "sk-anthropic"
        assert get_active_generation_source(s) == "anthropic"

    def test_openai_preferred_over_anthropic(self):
        """OpenAI 优先级高于 Anthropic"""
        s = SettingsState()
        s.openai.enabled = True
        s.openai.api_key = "sk-openai"
        s.anthropic.enabled = True
        s.anthropic.api_key = "sk-anthropic"
        assert get_active_generation_source(s) == "openai"

    def test_enabled_but_no_key(self):
        """已启用但无 key 不算有效源"""
        s = SettingsState()
        s.openai.enabled = True
        s.openai.api_key = ""
        assert get_active_generation_source(s) == ""


class TestGetJudgeSourceLabel:
    """测试 get_judge_source_label()"""

    def test_not_configured(self):
        s = SettingsState()
        assert get_judge_source_label(s) == "未配置"

    def test_local_model(self):
        s = SettingsState()
        s.judge_backend = "local"
        assert "本地模型" in get_judge_source_label(s)

    def test_jev_enabled(self):
        s = SettingsState()
        s.jev.enabled = True
        s.jev.api_key = "sk-jev"
        s.jev.model = "jev-2.0"
        label = get_judge_source_label(s)
        assert "Jev" in label
        assert "jev-2.0" in label

    def test_local_overrides_jev(self):
        """JUDGE_BACKEND=local 优先于 Jev 配置"""
        s = SettingsState()
        s.judge_backend = "local"
        s.jev.enabled = True
        s.jev.api_key = "sk-jev"
        label = get_judge_source_label(s)
        assert "本地模型" in label