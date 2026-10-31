import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.prompt import build_prompt_block  # noqa: E402


def day(name, tone="neutral", desc="", priority=50, rule=None, source="builtin", day_id=None):
    return {
        "id": day_id or name,
        "name": name,
        "tone": tone,
        "description": desc,
        "priority": priority,
        "rule": rule or {"type": "solar", "month": 7, "day": 21},
        "source": source,
    }


class PromptTests(unittest.TestCase):
    def test_no_matches(self):
        self.assertIsNone(build_prompt_block([]))

    def test_basic_block(self):
        block = build_prompt_block([day("0721", "meme", "网络玩梗日", 70)])
        self.assertIn("[今日特殊日程", block)
        self.assertIn("07-21 0721", block)
        self.assertIn("玩梗", block)
        self.assertIn("不是播报任务", block)

    def test_solemn_suppresses_meme(self):
        items = [
            day("汶川地震纪念日", "solemn", priority=100, day_id="a"),
            day("疯狂星期四", "meme", priority=80, day_id="b"),
        ]
        block = build_prompt_block(items)
        self.assertIn("汶川地震纪念日", block)
        self.assertNotIn("疯狂星期四", block)

    def test_solemn_suppression_can_disable(self):
        items = [
            day("汶川地震纪念日", "solemn", priority=100, day_id="a"),
            day("疯狂星期四", "meme", priority=80, day_id="b"),
        ]
        block = build_prompt_block(
            items, suppress_meme_on_solemn=False
        )
        self.assertIn("汶川地震纪念日", block)
        self.assertIn("疯狂星期四", block)

    def test_custom_overrides_builtin(self):
        items = [
            day("春节", "festive", "内置描述", 70, day_id="builtin_spring"),
            day(
                "春节",
                "festive",
                "自定义描述",
                50,
                day_id="custom_spring",
                source="custom",
            ),
        ]
        block = build_prompt_block(items)
        self.assertIn("自定义描述", block)
        self.assertNotIn("内置描述", block)

    def test_custom_override_can_disable(self):
        items = [
            day("春节", "festive", "内置描述", 70, day_id="builtin_spring"),
            day(
                "春节",
                "festive",
                "自定义描述",
                50,
                day_id="custom_spring",
                source="custom",
            ),
        ]
        block = build_prompt_block(items, custom_overrides_builtin=False)
        self.assertIn("内置描述", block)
        self.assertNotIn("自定义描述", block)

    def test_max_days_keeps_solemn(self):
        items = [
            day("纪念", "solemn", priority=1, day_id="solemn"),
            *[day(f"d{i}", "festive", priority=100 - i, day_id=f"d{i}") for i in range(5)],
        ]
        block = build_prompt_block(items, max_days=3)
        lines = [x for x in block.splitlines() if x.startswith("- ")]
        self.assertEqual(len(lines), 3)
        self.assertIn("纪念", lines[0])

    def test_max_days(self):
        items = [day(f"d{i}", priority=100 - i, day_id=f"d{i}") for i in range(6)]
        block = build_prompt_block(items, max_days=3)
        self.assertEqual(block.count("\n- "), 3)

    def test_solemn_priority_and_warning(self):
        items = [
            day("普通", "festive", priority=100),
            day("纪念", "solemn", priority=10),
        ]
        block = build_prompt_block(items)
        first_line = [x for x in block.splitlines() if x.startswith("- ")][0]
        self.assertIn("纪念", first_line)
        self.assertIn("保持庄重", block)

    def test_clean_newlines_and_truncate(self):
        block = build_prompt_block([day("a\nb", "neutral", "x" * 500)])
        self.assertNotIn("\n- a\nb", block)
        self.assertLessEqual(len(block), 900)

    def test_dedup_same_source_id(self):
        a = day("同名", "neutral", day_id="same")
        b = day("同名2", "neutral", day_id="same")
        block = build_prompt_block([a, b])
        self.assertEqual(block.count("- "), 1)

    def test_dedup_same_name_across_sources(self):
        # 内置公历“国庆节”和 holiday-cn 的 one_time 条目同日同名时只保留一条。
        a = day("国庆节", "festive", priority=60, day_id="solar_1001")
        b = day(
            "国庆节",
            "festive",
            priority=75,
            day_id="cn_2026-10-01_国庆节_off",
            source="holiday_cn",
            rule={"type": "one_time", "date": "2026-10-01"},
        )
        block = build_prompt_block([a, b])
        self.assertEqual(block.count("- "), 1)


if __name__ == "__main__":
    unittest.main()
