import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.store import CustomDayStore  # noqa: E402


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = CustomDayStore(Path(self.tmp.name) / "days.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_get_list_delete(self):
        created = self.store.add(
            name="0721",
            rule="7-21",
            scope_umo="umo-A",
            tone="meme",
            description="玩梗日",
        )
        self.assertEqual(created["name"], "0721")
        self.assertEqual(created["rule"], {"type": "solar", "month": 7, "day": 21})
        self.assertEqual(created["tone"], "meme")

        self.assertIsNotNone(self.store.get(created["id"]))
        listed = self.store.list_for_scope("umo-A")
        self.assertEqual([item["id"] for item in listed], [created["id"]])
        # 其他会话看不到
        self.assertEqual(self.store.list_for_scope("umo-B"), [])

        self.assertTrue(self.store.delete(created["id"], "umo-A"))
        self.assertIsNone(self.store.get(created["id"]))

    def test_update(self):
        created = self.store.add(name="旧名字", rule="7-21", scope_umo="umo-A")
        updated = self.store.update(
            created["id"],
            "umo-A",
            name="新名字",
            rule="5月第2个周日",
            tone="festive",
            description="改过了",
            priority=70,
            enabled=False,
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated["name"], "新名字")
        self.assertEqual(updated["rule"]["type"], "nth_weekday")
        self.assertEqual(updated["tone"], "festive")
        self.assertFalse(updated["enabled"])

    def test_update_wrong_scope(self):
        created = self.store.add(name="本会话", rule="7-21", scope_umo="umo-A")
        self.assertIsNone(self.store.update(created["id"], "umo-B", name="越权"))

    def test_export_import(self):
        self.store.add(name="A", rule="7-21", scope_umo="umo-A", tone="meme")
        self.store.add(name="B", rule="5月第2个周日", scope_umo="umo-A", tone="festive")
        exported = self.store.export_scope("umo-A")
        self.assertEqual(len(exported), 2)
        self.assertNotIn("id", exported[0])
        self.assertNotIn("scope_umo", exported[0])

        result = self.store.import_days(exported, "umo-B")
        self.assertEqual(len(result["imported"]), 2)
        self.assertEqual(result["skipped"], 0)
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(self.store.export_scope("umo-B")), 2)

        duplicate = self.store.import_days(exported, "umo-B")
        self.assertEqual(len(duplicate["imported"]), 0)
        self.assertEqual(duplicate["skipped"], 2)

    def test_import_invalid_item_skipped(self):
        result = self.store.import_days(
            [{"name": "坏", "rule": "不是日期"}, {"name": "好", "rule": "7-21"}],
            "umo-A",
        )
        self.assertEqual(len(result["imported"]), 1)
        self.assertEqual(len(result["errors"]), 1)

    def test_export_excludes_global_by_default(self):
        self.store.add(name="全局", rule="1-1", scope_umo="")
        self.store.add(name="本会话", rule="7-21", scope_umo="umo-A")
        exported = self.store.export_scope("umo-A")
        self.assertEqual([item["name"] for item in exported], ["本会话"])

    def test_global_scope_visible_everywhere(self):
        created = self.store.add(name="全局日", rule="2026-11-11", scope_umo="")
        self.assertIn(created["id"], [x["id"] for x in self.store.list_for_scope("any")])

    def test_validation(self):
        with self.assertRaises(ValueError):
            self.store.add(name="", rule="7-21")
        with self.assertRaises(ValueError):
            self.store.add(name="x" * 41, rule="7-21")
        with self.assertRaises(ValueError):
            self.store.add(name="bad", rule="不是日期")

    def test_persistence(self):
        created = self.store.add(name="持久", rule="周四", scope_umo="umo-A")
        again = CustomDayStore(Path(self.tmp.name) / "days.db")
        self.assertIsNotNone(again.get(created["id"]))

    def test_delete_wrong_scope(self):
        created = self.store.add(name="本会话", rule="7-21", scope_umo="umo-A")
        self.assertFalse(self.store.delete(created["id"], "umo-B"))
        self.assertTrue(self.store.delete(created["id"], "umo-A"))


if __name__ == "__main__":
    unittest.main()
