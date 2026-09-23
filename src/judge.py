"""Judge: 本地 decider-2b 模型 + Jev API 云端判断

意图/风险双输出，一次模型前向推理完成。
本地模型基于 Mapika/decider-2b，云端基于 TypeSafe Jev API。
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
from pathlib import Path

import numpy as np

# 允许直接运行（python src/judge.py）和模块运行（python -m src.judge）
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import userconfig

log = logging.getLogger("judge")


def model_cache_dir(repo: str = "Mapika/decider-2b") -> str:
    """模型缓存目录路径"""
    base = os.environ.get("HF_HUB_CACHE")
    if not base:
        home = os.environ.get("HF_HOME")
        base = os.path.join(home, "hub") if home else os.path.expanduser(
            "~/.cache/huggingface/hub")
    return os.path.join(base, "models--" + repo.replace("/", "--"))


def model_cached(repo: str = "Mapika/decider-2b") -> bool:
    """检查模型是否已缓存到本地"""
    snapshots = os.path.join(model_cache_dir(repo), "snapshots")
    try:
        for entry in os.listdir(snapshots):
            path = os.path.join(snapshots, entry)
            if not os.path.isdir(path):
                continue
            try:
                if any(f.endswith((".safetensors", ".bin"))
                       and os.path.isfile(os.path.join(path, f))
                       for f in os.listdir(path)):
                    return True
            except OSError:
                continue
    except OSError:
        pass
    return False


def model_disk_usage(repo: str = "Mapika/decider-2b") -> int:
    """模型占用的磁盘空间（字节）"""
    root = model_cache_dir(repo)
    seen: set[str] = set()
    total = 0
    if not os.path.isdir(root):
        return 0
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            path = os.path.join(dirpath, name)
            try:
                real = os.path.realpath(path)
                if real in seen:
                    continue
                size = os.stat(path).st_size
            except OSError:
                continue
            seen.add(real)
            total += size
    return total


def download_block_reason(repo: str = "Mapika/decider-2b") -> str | None:
    """为什么不能下载本地模型，或 None 表示可以下载"""
    pref = userconfig.get_config_value("JUDGE_BACKEND").strip().lower()
    if pref == "local":
        return None
    if pref == "cloud":
        return ("已选择在线判断（JUDGE_BACKEND=cloud），本地模型未使用 · "
                "如需离线判断，可在模型设置的「判断 · Jev」页启用")
    if model_cached(repo):
        return None
    return ("离线判断模型尚未下载（约 7 GB）· 可配置 TYPESAFE_API_KEY 走云端判断，"
            "或在模型设置的「判断 · Jev」页启用离线模型")


# 意图定义（与 Jev 保持一致）
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

ACTION_MAP = {
    "派活": ["接住", "问清交付标准和期限", "先给个时间点"],
    "催进度": ["先给当前状态", "给明确的完成时间", "别解释太多"],
    "问进度": ["直接说事实", "给下个节点", "有卡点就说卡点"],
    "批评": ["先认下来", "别急着辩解", "给补救方案"],
    "要解释": ["说清原因", "别找借口", "给改进措施"],
    "闲聊": ["轻松回应", "可以互动", "不用当真"],
    "约会议": ["确认时间", "说清议程", "准备好材料"],
    "夸奖": ["接住并感谢", "别过度谦虚", "可以顺带提下一步"],
}


class Judge:
    """本地判断模型（decider-2b）封装"""

    def __init__(self, repo: str = "Mapika/decider-2b", device: str | None = None):
        self._torch = None  # lazy import
        self._device = device
        self.device = device or "cpu"
        self.repo = repo
        self.temperature = 1.3
        self._loaded = False
        self.load_status = None
        self._load_lock = threading.RLock()

    @property
    def torch(self):
        if self._torch is None:
            import torch
            self._torch = torch
        return self._torch

    def _load(self):
        if self._loaded:
            return
        with self._load_lock:
            if self._loaded:
                return
            from transformers import AutoModelForCausalLM, AutoTokenizer

            self.load_status = "加载判断模型…"
            try:
                t = self.torch
                self.tok = AutoTokenizer.from_pretrained(self.repo)
                dtype = t.float16 if self.device == "cuda" else t.float32
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.repo, dtype=dtype,
                    low_cpu_mem_usage=True).to(self.device).eval()
                self._letters = [self.tok.encode(c, add_special_tokens=False)[0]
                                 for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
                self._loaded = True
                log.info(f"本地判断模型已加载到 {self.device}")
            except Exception as e:
                log.error(f"加载判断模型失败: {e}")
                raise
            finally:
                self.load_status = None

    def warm(self) -> None:
        """预热模型"""
        with self._load_lock:
            self._load()
            self.load_status = "预热判断模型…"
            try:
                self.judge("预热")
            finally:
                self.load_status = None

    def _slot_probs(self, logits_by_slot: list, n_options: int, slot: int) -> np.ndarray:
        logits = logits_by_slot[slot]
        ids = self._letters[:n_options]
        probs = self.torch.softmax(logits[ids].float() / self.temperature, -1)
        return probs.cpu().numpy()

    def _forward(self, prompt: str, n_slots: int):
        ids = self.tok(prompt, return_tensors="pt", return_offsets_mapping=True).to(self.device)
        offsets = ids.pop("offset_mapping")[0].tolist()
        with self.torch.no_grad():
            out = self.model(**ids)
        slot_token_idx = []
        for m in re.finditer(r"Answer: \(", prompt):
            char_pos = m.start() + len("Answer: ")
            for i, (s, e) in enumerate(offsets):
                if s <= char_pos < e:
                    slot_token_idx.append(i)
                    break
        if len(slot_token_idx) < n_slots:
            raise RuntimeError(f"expected {n_slots} answer slots, found {len(slot_token_idx)}")
        return out.logits[0], slot_token_idx

    def judge(self, message: str, context: str | None = None) -> dict:
        """判断一条消息的意图和风险"""
        self._load()
        intents = list(INTENTS)
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

        prompt = f"Context:\n{context + chr(10) + chr(10) if context else ''}{message}\n\n"
        prompt += "Question: 这句话的真实意图是什么？\nOptions:\n"
        for i, name in enumerate(intents):
            prompt += f"({letters[i]}) {name} - {INTENTS[name]}\n"
        prompt += "Answer: ("
        prompt += "\n\nQuestion: 如果直接回复这句话，风险有多大？\nOptions:\n"
        for i, lv in enumerate(RISK_LEVELS):
            prompt += f"({letters[i]}) {lv}\n"
        prompt += "Answer: ("

        logits, slot_token_idx = self._forward(prompt, 2)
        intent_probs = self._slot_probs([logits[slot_token_idx[0]]], len(intents), 0)
        risk_probs = self._slot_probs([logits[slot_token_idx[1]]], len(RISK_LEVELS), 0)

        intent_idx = int(np.argmax(intent_probs))
        risk_value = float((np.arange(len(RISK_LEVELS)) * risk_probs).sum())

        return {
            "intent": intents[intent_idx],
            "confidence": float(intent_probs[intent_idx]),
            "intent_probs": {n: float(p) for n, p in zip(intents, intent_probs)},
            "risk": round(risk_value, 1),
            "risk_probs": {str(i): float(p) for i, p in enumerate(risk_probs)},
            "actions": ACTION_MAP.get(intents[intent_idx], []),
            "message": message,
            "backend": "local",
        }

    def rank_candidates(self, message: str, intent: str,
                        candidates: list[str]) -> list[dict]:
        """排序候选回复（本地模型）"""
        self._load()
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        prompt = f"Context:\n收到：「{message}」\n判断出的意图：{intent}\n\n"
        prompt += "Question: 哪一条回复最合适？\nOptions:\n"
        for i, c in enumerate(candidates):
            prompt += f"({letters[i]}) {c}\n"
        prompt += "Answer: ("

        logits, slots = self._forward(prompt, 1)
        probs = self._slot_probs([logits[slots[0]]], len(candidates), 0)
        ranked = sorted(
            ({"text": c, "prob": float(p)} for c, p in zip(candidates, probs)),
            key=lambda r: -r["prob"])
        return ranked


class FallbackJudge:
    """优先用 Jev API，失败后降级到本地判断模型"""

    def __init__(self):
        from src import judge_jev
        self.primary = judge_jev.JevJudge()
        self.local = None
        self.fell_back = False
        self.reason = ""

    @property
    def load_status(self):
        return self.local.load_status if self.local is not None else None

    def _fallback(self):
        if self.local is None:
            self.local = Judge()
        return self.local

    def judge(self, message: str, context: str | None = None) -> dict:
        if not self.fell_back:
            try:
                result = self.primary.judge(message, context)
                result["backend"] = "jev"
                return result
            except Exception as e:
                self.fell_back = True
                self.reason = f"{type(e).__name__}: {str(e)[:80]}"
                log.warning(f"Jev 不可用，降级到本地模型: {self.reason}")
        out = self._fallback().judge(message, context)
        out["backend"] = f"local (Jev 不可用: {self.reason})"
        return out

    def rank_candidates(self, message: str, intent: str, candidates: list[str]) -> list[dict]:
        if not self.fell_back:
            try:
                return self.primary.rank_candidates(message, intent, candidates)
            except Exception as e:
                self.fell_back = True
                self.reason = f"{type(e).__name__}: {str(e)[:80]}"
        return self._fallback().rank_candidates(message, intent, candidates)

    def warm(self) -> None:
        """预热（Jev 无需预热，本地模型需要）"""
        if not self.fell_back:
            try:
                from src import judge_jev
                if judge_jev.jev_configured():
                    return  # Jev 不预热
            except ImportError:
                pass
            except Exception:
                pass
        self._fallback().warm()


def make_judge():
    """创建判断器：优先用 Jev API，否则本地模型"""
    try:
        from src import judge_jev
        if judge_jev.jev_configured():
            return FallbackJudge()
    except Exception:
        pass
    return Judge()


if __name__ == "__main__":
    import sys

    j = make_judge()
    msg = sys.argv[1] if len(sys.argv) > 1 else "这个需求你今天跟一下"
    result = j.judge(msg)
    result.pop("intent_probs", None)
    result.pop("risk_probs", None)
    print(json.dumps(result, ensure_ascii=False, indent=2))