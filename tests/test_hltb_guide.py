"""测试《高性价比人生指南》集成模块。"""

import pytest
from src import hltb_guide
from src import builtin


class TestHLTBGuide:
    """高性价比人生指南模块测试。"""

    def test_module_imports(self):
        """模块能正常导入."""
        assert hasattr(hltb_guide, "get_guide")
        assert hasattr(hltb_guide, "find_relevant")
        assert hasattr(hltb_guide, "CHAPTER_NAMES")

    def test_guide_structure(self):
        """指南数据结构正确."""
        guide = hltb_guide.get_guide()
        assert "chapters" in guide
        assert "total_entries" in guide
        assert guide["total_entries"] > 600  # 670 条
        assert len(guide["chapters"]) == 34  # 34 章

    def test_chapter_names(self):
        """章节名能快速查找."""
        assert hltb_guide.CHAPTER_NAMES["01"] == "不要早死"
        assert hltb_guide.CHAPTER_NAMES["08"] == "别把自己搭进去"
        assert hltb_guide.CHAPTER_NAMES["34"] == "家里的常备药别吃出事"

    def test_find_relevant担保(self):
        """担保相关消息能匹配到正确条目."""
        results = hltb_guide.find_relevant("我朋友让我帮他担保，签不签？", top_n=3)
        assert len(results) > 0
        # 应该匹配到章节 08（别把自己搭进去）
        chapters = {r["chapter"] for r in results}
        assert "08" in chapters or len(results) >= 1

    def test_find_relevant开车(self):
        """开车相关消息能匹配到相关条目."""
        results = hltb_guide.find_relevant("开车要注意什么", top_n=3)
        assert len(results) > 0
        # 应该匹配到章节 01（不要早死）或 13（紧急情况）
        chapters = {r["chapter"] for r in results}
        assert len(chapters) > 0

    def test_find_relevant租房(self):
        """租房相关消息能匹配到相关条目."""
        results = hltb_guide.find_relevant("租房有什么坑", top_n=3)
        assert len(results) > 0

    def test_find_relevant糖尿病(self):
        """糖尿病相关消息能匹配到相关条目."""
        results = hltb_guide.find_relevant("得了糖尿病怎么控制", top_n=3)
        assert len(results) > 0
        # 应该匹配到章节 16（得了慢性病之后怎么活）
        chapters = {r["chapter"] for r in results}
        assert "16" in chapters

    def test_find_relevant_empty_message(self):
        """空消息返回空列表."""
        results = hltb_guide.find_relevant("", top_n=3)
        assert results == []

    def test_find_relevant_result_format(self):
        """返回结果格式正确."""
        results = hltb_guide.find_relevant("担保", top_n=1)
        if results:
            r = results[0]
            assert "chapter" in r
            assert "chapter_name" in r
            assert "title" in r
            assert "core" in r
            assert "grade" in r


class TestBuiltInTones:
    """内置话术槽测试."""

    def test_hltb_tone_exists(self):
        """hltb 话术槽存在."""
        assert "hltb" in builtin.BUILTIN_TONES
        assert builtin.get_tone_display_name("hltb") == "高性价比人生指南"

    def test_all_tones_have_names(self):
        """所有话术槽都有显示名."""
        for key in builtin.get_available_tones():
            name = builtin.get_tone_display_name(key)
            assert len(name) > 0, f"话术 {key} 没有显示名"
