"""自定义日程 SQLite 存储。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .rules import normalize_tone, parse_rule, rule_key

_SCHEMA = """
CREATE TABLE IF NOT EXISTS custom_days (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    rule_json TEXT NOT NULL,
    tone TEXT NOT NULL DEFAULT 'neutral',
    description TEXT NOT NULL DEFAULT '',
    priority INTEGER NOT NULL DEFAULT 50,
    scope_umo TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_custom_days_scope
    ON custom_days(scope_umo, enabled);
"""


class CustomDayStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._open() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _open(self):
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def add(
        self,
        *,
        name: str,
        rule: str | dict[str, Any],
        scope_umo: str = "",
        tone: str = "neutral",
        description: str = "",
        priority: int = 50,
        enabled: bool = True,
        created_by: str = "",
    ) -> dict[str, Any]:
        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise ValueError("名称不能为空")
        if len(normalized_name) > 40:
            raise ValueError("名称太长（最多 40 字）")
        parsed_rule = parse_rule(rule)
        normalized_tone = normalize_tone(tone)
        normalized_desc = _clean_description(description)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        day_id = uuid.uuid4().hex[:8]

        with self._open() as conn:
            conn.execute(
                """
                INSERT INTO custom_days
                    (id, name, rule_json, tone, description, priority,
                     scope_umo, enabled, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    day_id,
                    normalized_name,
                    json.dumps(parsed_rule, ensure_ascii=False),
                    normalized_tone,
                    normalized_desc,
                    int(priority),
                    str(scope_umo or ""),
                    1 if enabled else 0,
                    str(created_by or ""),
                    now,
                    now,
                ),
            )
        return self.get(day_id)  # type: ignore[return-value]

    def get(self, day_id: str) -> dict[str, Any] | None:
        with self._open() as conn:
            row = conn.execute(
                "SELECT * FROM custom_days WHERE id = ?", (str(day_id),)
            ).fetchone()
        return _row_to_dict(row) if row else None

    def update(
        self,
        day_id: str,
        scope_umo: str,
        *,
        name: str | None = None,
        rule: str | dict[str, Any] | None = None,
        tone: str | None = None,
        description: str | None = None,
        priority: int | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any] | None:
        current = self.get(day_id)
        if current is None or current.get("scope_umo") != str(scope_umo or ""):
            return None

        new_name = current["name"] if name is None else str(name or "").strip()
        if not new_name:
            raise ValueError("名称不能为空")
        if len(new_name) > 40:
            raise ValueError("名称太长（最多 40 字）")
        new_rule = current["rule"] if rule is None else parse_rule(rule)
        new_tone = current["tone"] if tone is None else normalize_tone(tone)
        new_desc = (
            current["description"]
            if description is None
            else _clean_description(description)
        )
        new_priority = int(current["priority"] if priority is None else priority)
        new_enabled = bool(current["enabled"] if enabled is None else enabled)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with self._open() as conn:
            conn.execute(
                """
                UPDATE custom_days
                SET name = ?, rule_json = ?, tone = ?, description = ?,
                    priority = ?, enabled = ?, updated_at = ?
                WHERE id = ? AND scope_umo = ?
                """,
                (
                    new_name,
                    json.dumps(new_rule, ensure_ascii=False),
                    new_tone,
                    new_desc,
                    new_priority,
                    1 if new_enabled else 0,
                    now,
                    str(day_id),
                    str(scope_umo or ""),
                ),
            )
        return self.get(day_id)

    def delete(self, day_id: str, scope_umo: str | None = None) -> bool:
        query = "DELETE FROM custom_days WHERE id = ?"
        params: list[Any] = [str(day_id)]
        if scope_umo is not None:
            query += " AND scope_umo = ?"
            params.append(str(scope_umo))
        with self._open() as conn:
            cur = conn.execute(query, params)
            return cur.rowcount > 0

    def list_for_scope(self, scope_umo: str) -> list[dict[str, Any]]:
        with self._open() as conn:
            rows = conn.execute(
                """
                SELECT * FROM custom_days
                WHERE enabled = 1 AND (scope_umo = '' OR scope_umo = ?)
                ORDER BY priority DESC, created_at ASC
                """,
                (str(scope_umo or ""),),
            ).fetchall()
        return [_row_to_dict(row) for row in rows if row is not None]

    def list_all(self) -> list[dict[str, Any]]:
        with self._open() as conn:
            rows = conn.execute(
                "SELECT * FROM custom_days ORDER BY priority DESC, created_at ASC"
            ).fetchall()
        return [_row_to_dict(row) for row in rows if row is not None]

    def export_scope(
        self, scope_umo: str, *, include_global: bool = False
    ) -> list[dict[str, Any]]:
        """导出可移植的自定义日程，不带 id/created_by 等本机字段。"""
        if include_global:
            rows = self.list_for_scope(scope_umo)
        else:
            with self._open() as conn:
                db_rows = conn.execute(
                    "SELECT * FROM custom_days WHERE enabled = 1 AND scope_umo = ? "
                    "ORDER BY priority DESC, created_at ASC",
                    (str(scope_umo or ""),),
                ).fetchall()
            rows = [_row_to_dict(row) for row in db_rows if row is not None]
        return [
            {
                "name": item["name"],
                "rule": item["rule"],
                "tone": item["tone"],
                "description": item.get("description", ""),
                "priority": item.get("priority", 50),
                "enabled": item.get("enabled", True),
            }
            for item in rows
        ]

    def import_days(
        self, items: list[dict[str, Any]], scope_umo: str
    ) -> dict[str, Any]:
        """导入日程；非法条目跳过，重复（名称+规则）跳过。"""
        if not isinstance(items, list):
            raise ValueError("导入数据必须是日程列表")
        existing = {
            (str(item.get("name") or "").strip(), rule_key(item["rule"]))
            for item in self.list_for_scope(scope_umo)
        }
        imported: list[dict[str, Any]] = []
        skipped = 0
        errors: list[str] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"第 {index} 条不是对象")
                continue
            name = str(item.get("name") or "").strip()
            try:
                parsed_rule = parse_rule(item.get("rule") or "")
            except ValueError as exc:
                errors.append(f"第 {index} 条规则非法: {exc}")
                continue
            key = (name, rule_key(parsed_rule))
            if not name or key in existing:
                skipped += 1
                continue
            try:
                created = self.add(
                    name=name,
                    rule=parsed_rule,
                    scope_umo=scope_umo,
                    tone=item.get("tone") or "neutral",
                    description=item.get("description") or "",
                    priority=int(item.get("priority", 50)),
                    enabled=bool(item.get("enabled", True)),
                    created_by="import",
                )
            except (TypeError, ValueError) as exc:
                errors.append(f"第 {index} 条导入失败: {exc}")
                continue
            imported.append(created)
            existing.add(key)
        return {"imported": imported, "skipped": skipped, "errors": errors}


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["rule"] = json.loads(item.pop("rule_json"))
    item["enabled"] = bool(item.get("enabled"))
    item["source"] = "custom"
    return item


def _clean_description(value: Any, limit: int = 160) -> str:
    text = str(value or "").strip().replace("\r", " ").replace("\n", " ")
    return " ".join(text.split())[:limit]
