import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.rules import (  # noqa: E402
    normalize_tone,
    parse_rule,
    rule_key,
    rule_matches,
    rule_to_text,
)


class RuleParseTests(unittest.TestCase):
    def test_solar_forms(self):
        self.assertEqual(
            parse_rule("7-21"), {"type": "solar", "month": 7, "day": 21}
        )
        self.assertEqual(
            parse_rule("7月21日"), {"type": "solar", "month": 7, "day": 21}
        )
        self.assertEqual(
            parse_rule("07/21"), {"type": "solar", "month": 7, "day": 21}
        )

    def test_weekday_forms(self):
        self.assertEqual(parse_rule("周四"), {"type": "weekday", "weekday": 4})
        self.assertEqual(
            parse_rule("每周四"), {"type": "weekday", "weekday": 4}
        )

    def test_one_time(self):
        self.assertEqual(
            parse_rule("2026-11-11"),
            {"type": "one_time", "date": "2026-11-11"},
        )

    def test_nth_weekday_forms(self):
        self.assertEqual(
            parse_rule("5月第2个周日"),
            {"type": "nth_weekday", "month": 5, "weekday": 7, "nth": 2},
        )
        self.assertEqual(
            parse_rule("6月第三个星期日"),
            {"type": "nth_weekday", "month": 6, "weekday": 7, "nth": 3},
        )
        self.assertEqual(parse_rule("复活节"), {"type": "computus"})

    def test_invalid(self):
        for value in ("", "不是日期", "13-40", "周八", "2026-13-01"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_rule(value)

    def test_normalize_tone(self):
        self.assertEqual(normalize_tone("玩梗"), "meme")
        self.assertEqual(normalize_tone("纪念"), "solemn")
        self.assertEqual(normalize_tone("festive"), "festive")
        self.assertEqual(normalize_tone("xxx"), "neutral")


class RuleMatchTests(unittest.TestCase):
    def test_solar_matches(self):
        rule = {"type": "solar", "month": 7, "day": 21}
        self.assertTrue(rule_matches(rule, date(2026, 7, 21)))
        self.assertFalse(rule_matches(rule, date(2026, 7, 22)))

    def test_weekday_matches(self):
        rule = {"type": "weekday", "weekday": 4}
        self.assertTrue(rule_matches(rule, date(2026, 10, 29)))  # 周四
        self.assertFalse(rule_matches(rule, date(2026, 10, 30)))  # 周五

    def test_one_time_matches(self):
        rule = {"type": "one_time", "date": "2026-11-11"}
        self.assertTrue(rule_matches(rule, date(2026, 11, 11)))
        self.assertFalse(rule_matches(rule, date(2027, 11, 11)))

    def test_leap_day(self):
        rule = {"type": "solar", "month": 2, "day": 29}
        self.assertTrue(rule_matches(rule, date(2028, 2, 29)))
        self.assertFalse(rule_matches(rule, date(2027, 2, 28)))

    def test_nth_weekday_and_easter_match(self):
        mother = {"type": "nth_weekday", "month": 5, "weekday": 7, "nth": 2}
        father = {"type": "nth_weekday", "month": 6, "weekday": 7, "nth": 3}
        thanksgiving = {"type": "nth_weekday", "month": 11, "weekday": 4, "nth": 4}
        self.assertTrue(rule_matches(mother, date(2026, 5, 10)))
        self.assertTrue(rule_matches(father, date(2026, 6, 21)))
        self.assertTrue(rule_matches(thanksgiving, date(2026, 11, 26)))
        self.assertFalse(rule_matches(mother, date(2026, 5, 17)))
        easter = {"type": "computus"}
        self.assertTrue(rule_matches(easter, date(2026, 4, 5)))
        self.assertFalse(rule_matches(easter, date(2026, 4, 4)))

    def test_rule_text_and_key(self):
        self.assertEqual(rule_to_text({"type": "solar", "month": 7, "day": 21}), "每年 07-21")
        self.assertEqual(rule_to_text({"type": "weekday", "weekday": 4}), "周四")
        self.assertEqual(rule_key({"type": "weekday", "weekday": 4}), "weekday:4")


if __name__ == "__main__":
    unittest.main()
