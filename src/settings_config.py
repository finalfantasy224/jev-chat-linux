"""Settings configuration panel logic — shared data structures for the settings UI."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProviderConfig:
    """单个服务商配置"""
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    enabled: bool = False


@dataclass
class SettingsState:
    """设置状态——判断层与生成层的服务商配置"""
    # 判断层
    jev: ProviderConfig = field(default_factory=lambda: ProviderConfig(
        base_url="https://api.typesafe.ai",
        model="jev-latest",
    ))
    judge_backend: str = ""  # "cloud", "local", "skip", ""
    
    # 生成层：OpenAI 兼容
    openai: ProviderConfig = field(default_factory=lambda: ProviderConfig(
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
    ))
    
    # 生成层：Anthropic 兼容
    anthropic: ProviderConfig = field(default_factory=lambda: ProviderConfig(
        base_url="",
        model="",
    ))
    
    # 话术配置
    custom_tones: str = ""
    
    # 窗口名称
    wechat_window_name: str = "微信"


def get_active_generation_source(state: SettingsState) -> str:
    """确定当前生效的生成层来源"""
    if state.openai.enabled and state.openai.api_key:
        return "openai"
    if state.anthropic.enabled and state.anthropic.api_key:
        return "anthropic"
    return ""


def get_judge_source_label(state: SettingsState) -> str:
    """判断层来源标签"""
    if state.judge_backend == "local":
        return "本地模型 (decider-2b)"
    if state.jev.enabled and state.jev.api_key:
        return f"Jev ({state.jev.model})"
    return "未配置"