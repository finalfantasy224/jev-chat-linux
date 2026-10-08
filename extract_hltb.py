#!/usr/bin/env python3
"""从《高性价比人生指南》源码中提取章节信息，供 jev-chat 调用。"""

import json
import re
import sys
from pathlib import Path

BOOK_DIR = Path("/tmp/hltb-upstream/book")
OUTPUT = Path("/home/kang-an/demo/jev-chat-linux/src/hltb_guide.py")

# 章节标题映射
CHAPTER_NAMES = {
    "01": "不要早死",
    "02": "不要慢慢死",
    "03": "不要浪费精力",
    "04": "不要浪费时间",
    "05": "不要浪费钱",
    "06": "反面清单",
    "07": "没钱的时候怎么活",
    "08": "别把自己搭进去",
    "09": "普通人容易踩的法律红线",
    "10": "恋爱和结婚划不划算",
    "11": "程序员和技术人容易踩的红线",
    "12": "创业与做生意",
    "13": "紧急情况",
    "14": "账号与信息安全",
    "15": "租房与买房",
    "16": "得了慢性病之后怎么活",
    "17": "家里有老人",
    "18": "养孩子划不划算",
    "19": "在职离职和工伤",
    "20": "刚出生的孩子怎么带",
    "21": "出国旅行与境外安全",
    "22": "怎么放松",
    "23": "学什么技能划算",
    "24": "看病",
    "25": "人走了以后要办什么",
    "26": "做一个网站或平台",
    "27": "怀孕和生产",
    "28": "别为了外形把身体搞坏",
    "29": "遭遇重大打击之后",
    "30": "上学以后的孩子",
    "31": "十八岁之后有哪几条路",
    "32": "出国留学",
    "33": "残疾之后怎么活",
    "34": "家里的常备药别吃出事",
}


def extract_entries(filepath: Path) -> list[dict]:
    """从单章文件中提取条目，每条返回 (序号, 标题, 核心建议, 证据等级)."""
    text = filepath.read_text(encoding="utf-8")
    entries = []
    # 匹配 #### 序号. 标题 这样的条目头
    pattern = re.compile(r'^###\s+(\d+)\.\s+(.+)$', re.MULTILINE)
    for m in pattern.finditer(text):
        num = m.group(1)
        title = m.group(2).strip()
        start = m.end()
        # 找下一个条目或章节结束
        next_m = pattern.search(text, start)
        if next_m:
            body = text[start:next_m.start()]
        else:
            body = text[start:start+2000]  # 截断，留核心建议
        # 提取"说人话"段落的要点
        shuohua = re.search(r'-\s*说人话[：:]\s*(.+?)(?:\n-|\Z)', body, re.DOTALL)
        core = shuohua.group(1).strip().replace('\n', ' ')[:120] if shuohua else title
        # 提取证据等级
        evidence = re.search(r'-\s*证据等级[：:]\s*([ABC])', body)
        grade = evidence.group(1) if evidence else "C"
        entries.append({"num": num, "title": title, "core": core, "grade": grade})
    return entries


def build_guide() -> dict:
    """构建完整的指南数据结构."""
    guide = {"chapters": {}, "summary": []}
    total = 0
    for f in sorted(BOOK_DIR.glob("*.md")):
        chapter_id = f.stem.split("-")[0]
        name = CHAPTER_NAMES.get(chapter_id, f.stem)
        entries = extract_entries(f)
        guide["chapters"][chapter_id] = {
            "name": name,
            "file": f.name,
            "entries": entries,
            "count": len(entries),
        }
        total += len(entries)
        # 收集 A 级条目作为精选摘要
        for e in entries:
            if e["grade"] == "A":
                guide["summary"].append(f"[{chapter_id}] {e['title']}: {e['core']}")
    guide["total_entries"] = total
    return guide


def write_module(guide: dict):
    """把指南数据写入 Python 模块（纯数据，无依赖）."""
    lines = [
        '"""《高性价比人生指南》数据结构 —— 由 extract_hltb.py 生成',
        '不要手动编辑此文件，编辑 extract_hltb.py 后重新运行。',
        '"""',
        '',
        'import json',
        '',
        '# 原始 JSON 数据（嵌入式，零外部依赖）',
        '_DATA = ' + repr(json.dumps(guide, ensure_ascii=False)),
        '',
        '_guide_cache: dict | None = None',
        '',
        'def get_guide() -> dict:',
        '    """返回完整指南数据（字典）."""',
        '    global _guide_cache',
        '    if _guide_cache is None:',
        '        _guide_cache = json.loads(_DATA)',
        '    return _guide_cache',
        '',
        '# 章节名快速查找（从数据动态派生，无需手动维护）',
        'def get_chapter_names() -> dict[str, str]:',
        '    """返回 {章节ID: 章节名} 映射，来自指南数据本身。"""',
        '    g = get_guide()',
        '    return {cid: ch["name"] for cid, ch in g["chapters"].items()}',
        '',
        'def get_chapter_summary(chapter_id: str) -> list[dict]:',
        '    """返回指定章节的条目列表."""',
        '    g = get_guide()',
        '    return g["chapters"].get(chapter_id, {}).get("entries", [])',
        '',
        'def find_relevant(message: str, top_n: int = 3) -> list[dict]:',
        '    """根据消息关键词匹配相关条目（简单实现，可扩展为向量检索).',
        '    返回格式: [{"chapter": "01", "title": "...", "core": "...", "grade": "A"}].',
        '',
        '    策略：从消息中提取 2-4 字连续中文，同时提取消息中的关键实词（人名、名词、动词等），',
        '    在章节标题和条目内容中做模糊匹配。',
        '    """',
        '    import re',
        '    g = get_guide()',
        '    # 太长时截断，避免滑动窗口组合爆炸',
        '    msg_lower = message.lower()[:500]',
        '',
        '    # 提取多种粒度的关键词',
        '    keywords = set()',
        '',
        '    # 先按标点/空格分割成中文词组，再提取子串',
        '    # 这样"帮我担保"不会被切成"我帮他担"',
        '    parts = re.split(r"[^\\u4e00-\\u9fa5]+", msg_lower)',
        '    for part in parts:',
        '        # 从每个连续中文片段中提取所有 2-4 字子串',
        '        for length in range(2, 5):',
        '            for i in range(len(part) - length + 1):',
        '                keywords.add(part[i:i+length])',
        '',
        '    # 数字+单位（如"30万"）',
        '    keywords.update(re.findall(r"\\d+[万亿千百万亿]?", msg_lower))',
        '',
        '    # 过滤掉太常见无意义的词',
        '    stop_words = {"什么", "怎么", "这个", "那个", "还有", "一个", "不用", "可以", "需要", "知道", "觉得", "应该", "因为", "所以", "但是", "然后", "一起", "大家", "你们", "我们", "他们", "就是", "不是", "这个", "那个", "帮我", "朋友", "让我"}',
        '    keywords = {kw for kw in keywords if len(kw) >= 2 and kw not in stop_words}',
        '',
        '    if not keywords:',
        '        return []',
        '',
        '    # 计算每个条目的匹配分数',
        '    scored_entries = []',
        '    for cid, ch in g["chapters"].items():',
        '        ch_score = 0',
        '        ch_name_lower = ch["name"].lower()',
        '',
        '        # 章节标题命中加高分',
        '        for kw in keywords:',
        '            if kw in ch_name_lower:',
        '                ch_score += 5',
        '',
        '        # 条目匹配',
        '        entry_scores = []',
        '        for e in ch["entries"]:',
        '            score = 0',
        '            title_lower = e["title"].lower()',
        '            core_lower = e["core"].lower()',
        '',
        '            for kw in keywords:',
        '                if kw in title_lower:',
        '                    score += 3',
        '                if kw in core_lower:',
        '                    score += 1',
        '',
        '            if score > 0:',
        '                entry_scores.append((score, e))',
        '',
        '        # 取本章最高分的 2 条',
        '        entry_scores.sort(reverse=True, key=lambda x: x[0])',
        '        for score, e in entry_scores[:2]:',
        '            scored_entries.append({',
        '                "chapter": cid,',
        '                "chapter_name": ch["name"],',
        '                "score": score + ch_score,',
        '                **e',
        '            })',
        '',
        '    # 按分数排序，去重（同一章节多条只取最高分）',
        '    scored_entries.sort(reverse=True, key=lambda x: x["score"])',
        '',
        '    # 每个章节最多取 2 条，最多 top_n 章',
        '    result = []',
        '    chapter_count = {}',
        '    for entry in scored_entries:',
        '        cid = entry["chapter"]',
        '        if chapter_count.get(cid, 0) >= 2:',
        '            continue',
        '        if len(result) >= top_n * 2:',
        '            break',
        '        result.append(entry)',
        '        chapter_count[cid] = chapter_count.get(cid, 0) + 1',
        '',
        '    # 清理分数字段',
        '    return [{k: v for k, v in e.items() if k != "score"} for e in result]',
        '',
    ]
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"✓ 已生成 {OUTPUT}（{guide['total_entries']} 条，{len(guide['chapters'])} 章）")


if __name__ == "__main__":
    if not BOOK_DIR.is_dir():
        print(f"错误：找不到书源目录 {BOOK_DIR}")
        sys.exit(1)
    guide = build_guide()
    write_module(guide)
    print(f"  总计 {guide['total_entries']} 条建议，A 级精选 {len(guide['summary'])} 条")
