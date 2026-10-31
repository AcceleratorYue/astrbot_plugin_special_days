import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.builtin import load_builtin, load_builtin_dir, match_builtin  # noqa: E402


class BuiltinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_dir = Path(__file__).resolve().parents[1] / "data"
        cls.m1_days = load_builtin(cls.data_dir / "builtin_days.json")
        cls.days = load_builtin_dir(cls.data_dir)

    def test_m1_load_count_and_unique(self):
        self.assertGreaterEqual(len(self.m1_days), 20)
        ids = [item["id"] for item in self.m1_days]
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_days_load_and_unique(self):
        self.assertGreaterEqual(len(self.days), 200)
        ids = [item["id"] for item in self.days]
        self.assertEqual(len(ids), len(set(ids)))

    def test_match_0721(self):
        names = [item["name"] for item in match_builtin(self.days, date(2026, 7, 21))]
        self.assertIn("0721", names)

    def test_match_kfc_thursday(self):
        names = [item["name"] for item in match_builtin(self.days, date(2026, 10, 29))]
        self.assertIn("疯狂星期四", names)

    def test_no_match_normal_day(self):
        # 2026-10-28 周三，且不是特殊日期
        self.assertEqual(match_builtin(self.days, date(2026, 10, 28)), [])

    def test_solemn_tone(self):
        names = {item["name"]: item for item in self.days}
        self.assertEqual(names["南京大屠杀死难者国家公祭日"]["tone"], "solemn")

    def test_2026_spring_festival(self):
        names = [item["name"] for item in match_builtin(self.days, date(2026, 2, 17))]
        self.assertIn("春节", names)

    def test_2026_chuxi(self):
        names = [item["name"] for item in match_builtin(self.days, date(2026, 2, 16))]
        self.assertIn("除夕", names)

    def test_2026_mid_autumn(self):
        names = [item["name"] for item in match_builtin(self.days, date(2026, 9, 25))]
        self.assertIn("中秋节", names)

    def test_2026_mothers_day(self):
        names = [item["name"] for item in match_builtin(self.days, date(2026, 5, 10))]
        self.assertIn("母亲节", names)

    def test_2026_easter(self):
        names = [item["name"] for item in match_builtin(self.days, date(2026, 4, 5))]
        self.assertIn("复活节", names)

    def test_2026_makeup_workday(self):
        names = [item["name"] for item in match_builtin(self.days, date(2026, 2, 14))]
        self.assertIn("调休上班（春节）", names)

    def test_lunar_beyond_holiday_year(self):
        # 法定节假日快照只到 2026，农历仍应覆盖 2027 春节。
        names = [item["name"] for item in match_builtin(self.days, date(2027, 2, 6))]
        self.assertIn("春节", names)


if __name__ == "__main__":
    unittest.main()
