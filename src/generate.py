"""候选回复生成层——通过 LLM API 并发为每条话术生成回复

支持 OpenAI 和 Anthropic 两种 API 格式，
复用 macOS 原版的提示词模板。
"""

from __future__ import annotations

import concurrent.futures
import http.client
import io
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# 允许直接运行（python src/generate.py）和模块运行（python -m src.generate）
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import builtin
from src import userconfig

log = logging.getLogger("generate")

# ── 常量 ────────────────────────────────────────────────────────
DEFAULT_OPENAI_BASE = "https://api.openai.com/v1"
DEFAULT_ANTHROPIC_BASE = "https://api.anthropic.com"
DEFAULT_MODEL = "deepseek-chat"

PER_TONE = 2  # 每条话术生成 2 条候选
MISSING_HINT = ("未配置生成层 Key：候选回复需要它，判断/风险不需要。"
                "设置 OPENAI_API_KEY 后重启，见 README 配置章节。")
BUILTIN_SOURCE = "内置默认"

PROMPT_ONE = """刚收到一条微信消息，你要帮我回。

{context_line}消息：「{message}」
{intent_line}
请写 {n} 条回复候选，语气统一成下面这一种，但两条的胆量要有差别：
「{tone}」{instruction}

硬性要求：
- 前一条稳妥、可以直接发出去；后一条把这个语气做足，更皮、更夸张一点也行
- 每条不超过 30 个字，是微信里打字的语气，不要客套话、不要解释
- 只输出 {n} 行，每行一条，不要编号、不要引号、不要任何前后缀
- 不要写出语气名称（不要写「{tone}：」这类前缀），直接从回复内容开始"""

# 内置话术预设
PRESETS = {
    "正式商务": "使用正式、礼貌的商务用语，措辞严谨，适合工作场合",
    "友好亲切": "语气友好亲切，像朋友一样自然交流，不要过于正式",
    "简洁高效": "回复简短直接，直击要点，不说废话",
    "温暖关怀": "表达关心和温暖的语气，适合问候和安抚对方",
    "幽默风趣": "适当加入幽默元素，让对话轻松愉快，不要过度开玩笑",
    "专业严谨": "用专业术语和严谨表达，展示专业素养，适合技术讨论",
    "客服礼貌": "像专业客服一样礼貌得体，耐心解答，不情绪化",
    "坚定自信": "表达坚定自信的态度，不卑不亢，适合需要表明立场的场合",
    "共情理解": "先表达理解和共情，再给出回应，适合安抚和安慰",
    "鼓励激励": "充满鼓励和正能量的语气，适合打气和激励对方",
}

NONE_LABEL = "不用"
DEFAULT_SLOTS = ["正式商务", "友好亲切", "简洁高效"]

_STYLE_LABEL = re.compile(
    r"^[*_#\s]*(稳妥|轻松|简短|简洁)[^，。！？；、,.!?;：:]{0,5}[*_#\s]*[:：]\s*")
_STYLE_LABEL_SHORT = re.compile(r"^[*_#\s]*(简|稳|轻)\s*(型|洁)?[*_#\s]*[:：]\s*")
_QUOTES = re.compile(r"""^["“”「『'‘]+|["”」』'’]+$""")


def strip_label(s: str) -> str:
    """去除模型在回复开头加的话术标签"""
    s = _STYLE_LABEL.sub("", s)
    s = _STYLE_LABEL_SHORT.sub("", s)
    return s


def _strip_quotes(s: str) -> str:
    return _QUOTES.sub("", s)


_VERSION_SEG = re.compile(r"v\d+[a-z]*")


def _base_segments(base: str) -> list[str]:
    return [s for s in urllib.parse.urlsplit((base or "").rstrip("/")).path.split("/") if s]


def base_has_version_segment(base: str) -> bool:
    segs = _base_segments(base)
    return bool(segs) and bool(_VERSION_SEG.fullmatch(segs[-1].lower()))


def base_is_verbatim_action(base: str) -> bool:
    segs = _base_segments(base)
    if not segs:
        return False
    if len(segs) >= 2 and bool(_VERSION_SEG.fullmatch(segs[-2].lower())):
        return True
    return segs[-1].lower() in {"systemone", "evaluate", "decisions"}


def jev_request_url(base: str) -> str:
    b = (base or "").rstrip("/")
    if base_is_verbatim_action(b):
        return b
    return b + ("/systemone" if base_has_version_segment(b) else "/v1/systemone")


def _endpoint(base: str, api: str) -> str:
    b = (base or "").rstrip("/")
    has_version = base_has_version_segment(b)
    if api == "anthropic":
        return b + ("/messages" if has_version else "/v1/messages")
    return b + ("/chat/completions" if has_version else "/v1/chat/completions")


def pick_api_format(base: str, configured: str | None) -> str:
    if configured:
        c = configured.strip().lower()
        if c in ("openai", "anthropic"):
            return c
    return "anthropic" if "anthropic" in (base or "").lower() else "openai"


class _KeepAlivePool:
    """HTTP 连接池（复用 http.client 连接）"""

    def __init__(self, max_idle: int = 4):
        self._lock = threading.Lock()
        self._idle: dict[tuple, list] = {}
        self._max_idle = max_idle

    def _checkout(self, scheme, host, port, timeout):
        key = (scheme, host, port)
        with self._lock:
            idle = self._idle.get(key)
            if idle:
                return key, idle.pop()
        cls = (http.client.HTTPSConnection if scheme == "https"
               else http.client.HTTPConnection)
        return key, cls(host, port, timeout=timeout)

    def _checkin(self, key, conn):
        with self._lock:
            idle = self._idle.setdefault(key, [])
            if len(idle) < self._max_idle:
                idle.append(conn)
                return
        conn.close()

    def post_json(self, url: str, headers: dict, body: dict, timeout: float) -> dict:
        p = urllib.parse.urlparse(url)
        scheme = p.scheme or "https"
        port = p.port or (443 if scheme == "https" else 80)
        path = p.path + (("?" + p.query) if p.query else "")
        payload = json.dumps(body).encode()
        last_exc: Exception | None = None
        for _attempt in range(2):
            key, conn = self._checkout(scheme, p.hostname, port, timeout)
            try:
                conn.request("POST", path, body=payload, headers=headers)
                resp = conn.getresponse()
                data = resp.read()
            except (http.client.HTTPException, OSError) as e:
                conn.close()
                last_exc = e
                continue
            if resp.will_close:
                conn.close()
            else:
                self._checkin(key, conn)
            if resp.status >= 300:
                raise urllib.error.HTTPError(
                    url, resp.status, resp.reason, resp.headers, io.BytesIO(data))
            return json.loads(data)
        assert last_exc is not None
        raise last_exc


_POOL = _KeepAlivePool()


def http_post_json(url: str, headers: dict, body: dict, timeout: float) -> dict:
    return _POOL.post_json(url, headers, body, timeout)


class ThinkingOnlyError(Exception):
    """思考模型把 max_tokens 额度全用在思考上，正文为空"""


class Generator:
    """候选回复生成器"""

    def __init__(self, model: str | None = None, timeout: int = 30,
                 api: str | None = None):
        self.model_override = model
        self.api_override = api if api in ("openai", "anthropic") else None
        self.timeout = timeout
        self._creds: tuple[str, str, str] | None = None
        self._last_url = ""

    def load_credentials(self) -> tuple[str, str, str, str, str]:
        """加载凭据：(base_url, api_key, model, source, api_format)"""
        oai_key = userconfig.get_config_value("OPENAI_API_KEY")
        oai_base = userconfig.get_config_value("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE)
        oai_model = userconfig.get_config_value("OPENAI_MODEL", DEFAULT_MODEL)
        
        anth_key = userconfig.get_config_value("ANTHROPIC_API_KEY")
        anth_base = userconfig.get_config_value("ANTHROPIC_BASE_URL", DEFAULT_ANTHROPIC_BASE)
        anth_model = userconfig.get_config_value("ANTHROPIC_MODEL")
        
        if oai_key:
            return oai_base, oai_key, oai_model, "OPENAI_API_KEY", "openai"
        if anth_key:
            base = anth_base or DEFAULT_ANTHROPIC_BASE
            model = anth_model or "claude-3-haiku-20240307"
            return base, anth_key, model, "ANTHROPIC_API_KEY", "anthropic"
        
        base = oai_base or DEFAULT_OPENAI_BASE
        return base, "", DEFAULT_MODEL, "none", pick_api_format(base, None)

    def _call(self, prompt: str) -> str:
        """一次 API 调用，返回原始回复文本"""
        base, key, model, _src, api = self.load_credentials()
        if self.model_override:
            model = self.model_override
        if self.api_override:
            api = self.api_override
        
        if not key:
            return ""
        
        if api == "anthropic":
            url = _endpoint(base, "anthropic")
            body = {"model": model, "max_tokens": 300, "temperature": 0.9,
                    "messages": [{"role": "user", "content": prompt}]}
            headers = {"content-type": "application/json", "x-api-key": key,
                       "anthropic-version": "2023-06-01"}
            data = http_post_json(url, headers, body, self.timeout)
            self._last_url = url
            parts = data.get("content") or []
            return "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        
        # OpenAI 格式
        url = _endpoint(base, "openai")
        body = {"model": model, "max_tokens": 300, "temperature": 0.9,
                "messages": [{"role": "user", "content": prompt}]}
        
        # 可选额外参数
        extra_raw = userconfig.get_config_value("OPENAI_EXTRA_BODY")
        if extra_raw:
            try:
                extra = json.loads(extra_raw)
                if isinstance(extra, dict):
                    body.update(extra)
            except ValueError:
                pass
        
        headers = {"content-type": "application/json", "authorization": f"Bearer {key}"}
        data = http_post_json(url, headers, body, self.timeout)
        self._last_url = url
        
        choices = data.get("choices") or []
        if not choices:
            return ""
        msg = choices[0].get("message") or {}
        return msg.get("content") or ""

    @staticmethod
    def _parse(raw: str) -> list[str]:
        """解析模型返回的多行文本为回复列表"""
        out = []
        for line in raw.splitlines():
            s = line.strip()
            if not s:
                continue
            s = re.sub(r"^[\d]+[.、)．]\s*", "", s)
            s = _strip_quotes(s)
            s = strip_label(s)
            s = _strip_quotes(s)
            if s:
                out.append(s.strip())
        return out

    def _one_tone(self, message: str, intent: str, tone: str, instruction: str,
                  context: str | None = None) -> tuple[list[str], str]:
        """为一种话术生成回复"""
        context_line = f"最近的对话：\n{context}\n\n" if context else ""
        intent_line = f"判断出的意图：{intent}\n" if intent else ""
        prompt = PROMPT_ONE.format(
            message=message, context_line=context_line,
            intent_line=intent_line,
            n=PER_TONE, tone=tone, instruction=instruction,
        )
        
        try:
            raw = self._call(prompt)
        except urllib.error.HTTPError as e:
            detail = e.read()[:160].decode(errors="replace")
            return [], f"HTTP {e.code}: {detail}"
        except Exception as e:
            return [], f"{type(e).__name__}: {e}"
        
        texts = self._parse(raw)[:PER_TONE]
        return texts, ""

    def generate(self, message: str, intent: str = "",
                 slot_tones: list[str] | None = None,
                 context: str | None = None) -> dict:
        """并发为所选话术生成回复"""
        # 确定话术列表
        if slot_tones:
            slots = list(slot_tones)
        else:
            slots = DEFAULT_SLOTS + [NONE_LABEL]
        
        # 过滤掉"不用"的话术
        active = [(i, t) for i, t in enumerate(slots) if t in PRESETS or t in builtin.BUILTIN_TONES]
        
        # 检查自定义话术
        custom_tones = {}
        env_tones = userconfig.get_config_value("JEV_TONES")
        if env_tones:
            for part in env_tones.split("|"):
                part = part.strip()
                if "=" in part:
                    name, _, desc = part.partition("=")
                    custom_tones[name.strip()] = desc.strip()
        
        if not active:
            return {"groups": [], "error": "没有选择任何话术", "elapsed_s": 0.0}
        
        _base, key, _model, _src, _api = self.load_credentials()
        if not key:
            return {"groups": [], "error": MISSING_HINT, "elapsed_s": 0.0}
        
        t0 = time.perf_counter()
        groups: list[dict] = []
        
        def run(i: int, tone: str):
            # 查找指令：自定义话术 > 内置 PRESETS > builtin
            if tone in custom_tones:
                instruction = custom_tones[tone]
            elif tone in PRESETS:
                instruction = PRESETS[tone]
            elif tone in builtin.BUILTIN_TONES:
                instruction = builtin.BUILTIN_TONES[tone][1]
            else:
                instruction = "保持自然礼貌的语气"
            return self._one_tone(message, intent, tone, instruction, context)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(active)) as ex:
            futures = {i: ex.submit(run, i, tone) for i, tone in active}
            for i, tone in active:
                try:
                    texts, err = futures[i].result()
                except Exception as e:
                    texts, err = [], f"{type(e).__name__}: {e}"
                groups.append({"slot": i, "tone": tone, "texts": texts, "error": err})
        
        error = ""
        if not any(g["texts"] for g in groups):
            seen: list[str] = []
            for g in groups:
                e = (g.get("error") or "").strip()
                if e and e not in seen:
                    seen.append(e)
            error = " · ".join(seen)
        
        return {"groups": groups, "error": error, "elapsed_s": time.perf_counter() - t0}


def credential_status() -> str:
    """检查凭据状态"""
    base, key, model, src, api = Generator().load_credentials()
    shape = ("Anthropic" if api == "anthropic" else "OpenAI")
    if not key:
        return (f"❌ 未配置 API Key\n"
                f"   端点: {base} ({shape})\n"
                f"   模型: {model}\n"
                f"   {MISSING_HINT}")
    return (f"✅ 来源: {src}\n"
            f"   端点: {base}\n"
            f"   接口: {shape}\n"
            f"   模型: {model}\n"
            f"   Key: {key[:6]}…{key[-4:]}")


if __name__ == "__main__":
    import sys
    
    if "--check" in sys.argv:
        print(credential_status())
        raise SystemExit(0 if Generator().load_credentials()[1] else 1)
    
    g = Generator()
    msg = sys.argv[1] if len(sys.argv) > 1 else "这个需求你今天跟一下"
    intent = sys.argv[2] if len(sys.argv) > 2 else "派活"
    print(json.dumps(g.generate(msg, intent), ensure_ascii=False, indent=2))