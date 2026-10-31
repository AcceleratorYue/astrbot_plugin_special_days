from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.holiday import (
    load_cache,
    merge_builtin_days,
    parse_holiday_payload,
    save_cache,
)


class HolidayTests(unittest.TestCase):
    def test_parse_holiday_cn(self):
        payload = {
            "year": 2026,
            "days": [
                {"name": "元旦", "date": "2026-01-01", "isOffDay": True},
                {"name": "元旦", "date": "2026-01-04", "isOffDay": False},
            ],
        }
        items = parse_holiday_payload(payload)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["name"], "元旦")
        self.assertEqual(items[0]["tone"], "festive")
        self.assertIn("调休上班", items[1]["name"])
        self.assertEqual(items[1]["tone"], "neutral")
        self.assertTrue(all(item["source"] == "holiday_cn" for item in items))

    def test_parse_timor_format(self):
        payload = {
            "holiday": {
                "01-01": {
                    "date": "2026-01-01",
                    "name": "元旦",
                    "holiday": True,
                }
            }
        }
        items = parse_holiday_payload(payload)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["rule"]["date"], "2026-01-01")

    def test_merge_overrides_same_date_status(self):
        base = [
            {
                "id": "cn_2026-01-01_元旦_off",
                "name": "元旦",
                "rule": {"type": "one_time", "date": "2026-01-01"},
                "tone": "festive",
                "priority": 60,
                "source": "builtin",
            },
            {
                "id": "halloween",
                "name": "万圣节",
                "rule": {"type": "solar", "month": 10, "day": 31},
                "tone": "festive",
                "priority": 50,
                "source": "builtin",
            },
        ]
        extra = parse_holiday_payload(
            {"days": [{"name": "元旦", "date": "2026-01-01", "isOffDay": True}]}
        )
        merged = merge_builtin_days(base, extra)
        self.assertEqual(len(merged), 2)
        holiday = next(item for item in merged if item["rule"]["type"] == "one_time")
        self.assertEqual(holiday["name"], "元旦")
        self.assertEqual(holiday["source"], "holiday_cn")
        self.assertTrue(any(item["id"] == "halloween" for item in merged))

    def test_merge_preserves_same_date_names(self):
        base = [
            {
                "id": "cn_2025-10-01_国庆节_off",
                "name": "国庆节",
                "rule": {"type": "one_time", "date": "2025-10-01"},
                "tone": "festive",
                "source": "builtin",
            },
            {
                "id": "cn_2025-10-01_中秋节_off",
                "name": "中秋节",
                "rule": {"type": "one_time", "date": "2025-10-01"},
                "tone": "festive",
                "source": "builtin",
            },
        ]
        merged = merge_builtin_days(base, [])
        self.assertEqual(len(merged), 2)

    def test_cache_roundtrip(self):
        items = parse_holiday_payload(
            {"days": [{"name": "春节", "date": "2027-02-06", "isOffDay": True}]}
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "holidays.json"
            save_cache(path, items)
            loaded = load_cache(path)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["name"], "春节")
        self.assertEqual(loaded[0]["source"], "holiday_cn")

    def test_empty_and_invalid(self):
        self.assertEqual(parse_holiday_payload({}), [])
        self.assertEqual(parse_holiday_payload({"days": [{"date": "bad"}]}), [])
        self.assertEqual(load_cache("not-exists.json"), [])


if __name__ == "__main__":
    unittest.main()
