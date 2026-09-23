"""22 条中文意图回归测试"""

INTENT_TEST_CASES = [
    ("这个需求你今天跟一下", "派活"),
    ("明天之前能给我吗", "催进度"),
    ("上次说的那个方案什么时候好", "问进度"),
    ("你做的这个完全不对", "批评"),
    ("为什么会出现这个问题", "要解释"),
    ("今天天气不错啊", "闲聊"),
    ("下午三点开个会行吗", "约会议"),
    ("你做得很好", "夸奖"),
    ("帮我查一下上个月的数据", "派活"),
    ("那个 bug 修复了吗", "问进度"),
    ("你平时用什么编辑器", "闲聊"),
    ("周五之前能上线吗", "催进度"),
    ("这份报告写得太差了", "批评"),
    ("能解释一下你的思路吗", "要解释"),
    ("这次 PPT 做得很不错", "夸奖"),
    ("明天下午两点我们碰一下", "约会议"),
    ("把这份合同审一下", "派活"),
    ("测试环境什么时候部署", "问进度"),
    ("这个事情拖太久了", "催进度"),
    ("你的方案考虑欠妥", "批评"),
    ("你这个结论的依据是什么", "要解释"),
    ("周末一起打球吗", "闲聊"),
]

# 8 类意图名称
INTENT_NAMES = ["派活", "催进度", "问进度", "批评", "要解释", "闲聊", "约会议", "夸奖"]


def run_test():
    """运行回归测试"""
    from src.judge import make_judge
    import json
    
    judge = make_judge()
    correct = 0
    results = []
    
    for msg, expected in INTENT_TEST_CASES:
        try:
            result = judge.judge(msg)
            predicted = result["intent"]
            is_correct = predicted == expected
            if is_correct:
                correct += 1
            results.append({
                "message": msg,
                "expected": expected,
                "predicted": predicted,
                "confidence": round(result["confidence"], 3),
                "correct": is_correct,
            })
        except Exception as e:
            results.append({
                "message": msg,
                "expected": expected,
                "predicted": f"ERROR: {e}",
                "correct": False,
            })
    
    accuracy = correct / len(INTENT_TEST_CASES)
    print(f"\n{'='*60}")
    print(f"意图回归测试结果: {correct}/{len(INTENT_TEST_CASES)} = {accuracy:.1%}")
    print(f"{'='*60}\n")
    
    for r in results:
        mark = "✓" if r["correct"] else "✗"
        conf = r.get("confidence", 0)
        print(f"  {mark} [{r['expected']:4s}] {r['message'][:20]:20s} -> {r['predicted']:4s} (conf={conf:.0%})")
    
    return accuracy


if __name__ == "__main__":
    run_test()