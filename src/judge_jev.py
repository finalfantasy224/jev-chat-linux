"""TypeSafe Jev API client — 云端判断层

Jev 是一个"无嘴模型"：只输出结构化意图/风险判断，不写文本。
通过 TypeSafe SystemOne API 调用。
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# 允许直接运行和模块运行
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import userconfig
from src import generate as gen  # 复用连接池

log = logging.getLogger("judge_jev")

# Jev 官方默认地址
DEFAULT_BASE_URL = "https://api.typesafe.ai"
DEFAULT_MODEL = "jev-latest"

# 意图定义（与本地 judge.py 保持一致）
INTENTS = {
    "派活": "对方要我做一件事或接一个任务",
    "催进度": "对方在催促我尽快完成某个已在办的事",
    "问进度": "对方在询问某件事的进展或状态",
    "批评": "对方对我的工作或结果表达不满、指出错误",
    "要解释": "对方要求我说明原因或给出解释",
    "闲聊": "对方只是在聊天、分享或表达感受，没有具体要求",
    "约会议": "对方想安排一次会议或通话",
    "夸奖": "对方在肯定、称赞我的成果",
}

RISK_LEVELS = [
    "完全没风险，怎么回都行",
    "基本没风险",
    "平淡，正常回就好",
    "需要稍微留神",
    "有点敏感，措辞注意",
    "需要谨慎，可能被挑刺",
    "比较危险，容易得罪人或踩坑",
    "很危险，说错要出问题",
    "非常危险，涉及责任或利益",
    "极度危险，先别回，想清楚再说",
]


def jev_configured() -> bool:
    """检查是否配置了 Jev API key"""
    key = userconfig.get_config_value("TYPESAFE_API_KEY")
    return bool(key)


class JevJudge:
    """通过 TypeSafe Jev API 进行意图/风险判断"""

    def __init__(self):
        self._last_url = ""
        self._last_model = ""

    def _post(self, url: str, headers: dict, body: dict) -> dict:
        """发送 POST 请求"""
        self._last_url = url
        return gen.http_post_json(url, headers, body, timeout=15)

    def judge(self, message: str, context: str | None = None) -> dict:
        """
        调用 Jev API 判断消息的意图和风险。
        使用 TypeSafe SystemOne API 格式（state + questions）。
        
        返回格式与本地 judge() 一致。
        """
        base = userconfig.get_config_value("TYPESAFE_BASE_URL", DEFAULT_BASE_URL)
        model = userconfig.get_config_value("TYPESAFE_MODEL", DEFAULT_MODEL)
        api_key = userconfig.get_config_value("TYPESAFE_API_KEY")
        
        self._last_model = model
        url = gen.jev_request_url(base)
        
        # 构造 SystemOne 请求（state + questions 格式）
        intents = list(INTENTS)
        state = message
        if context:
            state = f"Context:\n{context}\n\n{message}"
        
        body = {
            "model": model,
            "state": state,
            "questions": {
                "intent": {
                    "type": "choice",
                    "instructions": "这句话的真实意图是什么？",
                    "criteria": {name: INTENTS[name] for name in intents},
                },
                "risk": {
                    "type": "score",
                    "instructions": "如果直接回复这句话，风险有多大？",
                    "criteria": RISK_LEVELS,
                },
            },
        }
        
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {api_key}",
        }
        
        try:
            data = self._post(url, headers, body)
            return self._parse_response(data, message, intents)
        except urllib.error.HTTPError as e:
            detail = e.read()[:300].decode(errors="replace")
            raise RuntimeError(f"Jev HTTP {e.code}: {detail}")
        except Exception as e:
            raise RuntimeError(f"Jev 调用失败: {e}")

    def _parse_response(self, data: dict, message: str, intents: list[str]) -> dict:
        """解析 TypeSafe SystemOne API 响应"""
        answers = data.get("answers", {})
        
        # 解析意图（choice 类型）
        intent_answer = answers.get("intent", {})
        intent_name = intent_answer.get("choice", "")
        intent_probs = intent_answer.get("probabilities", {})
        intent_confidence = intent_answer.get("confidence", 0.0)
        
        # 如果意图名称不在列表中，使用默认
        if intent_name not in intents:
            intent_name = "闲聊"
        
        # 解析风险（score 类型）
        risk_answer = answers.get("risk", {})
        risk_value = risk_answer.get("score", 0.0)
        legend = risk_answer.get("legend", {})
        risk_probs_raw = risk_answer.get("probabilities", {})
        
        # 构建标准 risk_probs（0-9）
        risk_probs = {str(i): float(risk_probs_raw.get(str(i), 0.0))
                     for i in range(10)}
        
        # 如果没有 score 信息，回退到旧解析方式
        if not intent_name and not risk_value:
            return self._parse_response_fallback(data, message, intents)
        
        return {
            "intent": intent_name,
            "confidence": float(intent_confidence),
            "intent_probs": {n: float(intent_probs.get(n, 0.0)) for n in intents},
            "risk": float(risk_value),
            "risk_probs": risk_probs,
            "actions": [],
            "message": message,
            "backend": "jev",
        }

    def _parse_response_fallback(self, data: dict, message: str, intents: list[str]) -> dict:
        """备用解析：兼容旧版响应格式"""
        import re
        intents = list(INTENTS)
        
        content = ""
        choices = data.get("choices") or data.get("results") or []
        if choices and isinstance(choices[0], dict):
            msg = choices[0].get("message") or {}
            content = msg.get("content") or choices[0].get("text", "")
        
        if not content:
            return {
                "intent": "闲聊",
                "confidence": 0.0,
                "intent_probs": {n: 0.0 for n in intents},
                "risk": 0.0,
                "risk_probs": {str(i): 0.0 for i in range(10)},
                "actions": [],
                "message": message,
                "backend": "jev (fallback parse)",
            }
        
        intent_idx = 0
        risk_value = 0.0
        
        intent_match = re.search(r'Answer:\s*\(([A-Z])\)', content)
        if intent_match:
            letter = intent_match.group(1)
            intent_idx = ord(letter) - ord('A')
            if intent_idx >= len(intents):
                intent_idx = 0
        
        risk_match = re.findall(r'Answer:\s*\(([A-Z])\)', content)
        if len(risk_match) >= 2:
            risk_letter = risk_match[1]
            risk_idx = ord(risk_letter) - ord('A')
            risk_value = float(min(risk_idx, 9))
        
        return {
            "intent": intents[intent_idx] if intent_idx < len(intents) else "闲聊",
            "confidence": 0.9,
            "intent_probs": {n: 0.0 for n in intents},
            "risk": risk_value,
            "risk_probs": {str(i): 0.0 for i in range(10)},
            "actions": [],
            "message": message,
            "backend": "jev (fallback parse)",
        }

    def rank_candidates(self, message: str, intent: str,
                        candidates: list[str]) -> list[dict]:
        """使用 Jev 对候选回复排序（TypeSafe SystemOne API）"""
        base = userconfig.get_config_value("TYPESAFE_BASE_URL", DEFAULT_BASE_URL)
        model = userconfig.get_config_value("TYPESAFE_MODEL", DEFAULT_MODEL)
        api_key = userconfig.get_config_value("TYPESAFE_API_KEY")
        
        url = gen.jev_request_url(base)
        
        body = {
            "model": model,
            "state": f"收到：「{message}」\n判断出的意图：{intent}",
            "questions": {
                "best_reply": {
                    "type": "choice",
                    "instructions": "哪一条回复最合适？",
                    "criteria": {chr(65 + i): c for i, c in enumerate(candidates)},
                },
            },
        }
        
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {api_key}",
        }
        
        try:
            data = self._post(url, headers, body)
            answers = data.get("answers", {})
            reply_answer = answers.get("best_reply", {})
            probs = reply_answer.get("probabilities", {})
            
            # 按概率排序
            letter_to_candidate = {chr(65 + i): c for i, c in enumerate(candidates)}
            ranked = sorted(
                [{"text": letter_to_candidate.get(k, k),
                  "prob": float(v)}
                 for k, v in probs.items()],
                key=lambda r: -r["prob"]
            )
            return ranked if ranked else [
                {"text": c, "prob": 1.0 / len(candidates)} for c in candidates
            ]
        except Exception:
            return [{"text": c, "prob": 0.0} for c in candidates]


def check_jev():
    """检查 Jev 配置是否可用"""
    try:
        j = JevJudge()
        result = j.judge("测试消息")
        return {"ok": True, "intent": result["intent"]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    import sys
    result = check_jev()
    print(json.dumps(result, ensure_ascii=False, indent=2))