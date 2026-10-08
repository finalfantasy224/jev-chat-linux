"""内置话术（Tone profiles）——面板下拉框可选的回复风格"""

# 话术格式：{名字: (显示名, 说明)}
# 说明直接喂给生成层模型，写清「什么语气 + 别变成什么」
BUILTIN_TONES: dict[str, tuple[str, str]] = {
    "formal": ("正式商务", "使用正式、礼貌的商务用语，措辞严谨，适合工作场合"),
    "friendly": ("友好亲切", "语气友好亲切，像朋友一样自然交流，不要过于正式"),
    "concise": ("简洁高效", "回复简短直接，直击要点，不说废话"),
    "warm": ("温暖关怀", "表达关心和温暖的语气，适合问候和安抚对方"),
    "humorous": ("幽默风趣", "适当加入幽默元素，让对话轻松愉快，不要过度开玩笑"),
    "professional": ("专业严谨", "用专业术语和严谨表达，展示专业素养，适合技术讨论"),
    "customer_service": ("客服礼貌", "像专业客服一样礼貌得体，耐心解答，不情绪化"),
    "assertive": ("坚定自信", "表达坚定自信的态度，不卑不亢，适合需要表明立场的场合"),
    "empathetic": ("共情理解", "先表达理解和共情，再给出回应，适合安抚和安慰"),
    "motivational": ("鼓励激励", "充满鼓励和正能量的语气，适合打气和激励对方"),
    "hltb": ("高性价比人生指南", "参考下方指南条目中的真实证据来回复，把证据自然地融入回复里，不要直接复制粘贴。强调性价比和实际行动。语气接地气、说人话，别太文绉绉。"),
}

# 默认启用的话术（在面板中默认展开）
DEFAULT_ACTIVE_TONES = ["formal", "friendly", "concise", "warm", "humorous"]


def get_tone_instruction(name: str) -> str:
    """根据话术名称获取模型指令"""
    if name in BUILTIN_TONES:
        return BUILTIN_TONES[name][1]
    return "保持自然礼貌的语气"


def get_available_tones() -> list[str]:
    """获取所有可用话术名称列表"""
    return list(BUILTIN_TONES.keys())


def get_tone_display_name(name: str) -> str:
    """获取话术的显示名"""
    if name in BUILTIN_TONES:
        return BUILTIN_TONES[name][0]
    return name


def parse_custom_tones(env_value: str | None) -> dict[str, tuple[str, str]]:
    """
    解析环境变量中的自定义话术。
    格式：名字1=说明1|名字2=说明2
    同名覆盖内置话术。
    """
    if not env_value:
        return {}
    tones = {}
    for part in env_value.split("|"):
        part = part.strip()
        if "=" in part:
            name, _, desc = part.partition("=")
            name = name.strip()
            desc = desc.strip()
            if name and desc:
                tones[name] = (name, desc)
    return tones