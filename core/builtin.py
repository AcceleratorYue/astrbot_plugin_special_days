"""内置日程加载与匹配。"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from .rules import parse_rule, rule_matches, rule_to_text


class BuiltinError(ValueError):
    """内置日程文件格式错误。"""


def load_builtin(path: str | Path) -> list[dict[str, Any]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    items = raw.get("days") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise BuiltinError("内置日程必须是列表，或包含 days 列表")

    days: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise BuiltinError(f"第 {index} 条内置日程不是对象")
        day_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not day_id or not name:
            raise BuiltinError(f"第 {index} 条内置日程缺少 id/name")
        if day_id in seen:
            raise BuiltinError(f"内置日程 id 重复: {day_id}")
        seen.add(day_id)
        try:
            rule = parse_rule(item.get("rule") or {})
        except ValueError as exc:
            raise BuiltinError(f"内置日程 {day_id} 的规则非法: {exc}") from exc
        days.append(
            {
                "id": day_id,
                "name": name,
                "rule": rule,
                "tone": str(item.get("tone") or "neutral"),
                "description": str(item.get("description") or "").strip(),
                "priority": _to_int(item.get("priority"), 50),
                "enabled": bool(item.get("enabled", True)),
                "source": "builtin",
                "scope_umo": "",
            }
        )
    return days


def load_builtin_dir(directory: str | Path) -> list[dict[str, Any]]:
    """加载 data 目录下的全部内置日程文件（M1 + M2 数据）。"""
    root = Path(directory)
    files = (
        "builtin_days.json",
        "lunar_festivals.json",
        "holiday_cn_days.json",
        "computed_days.json",
    )
    combined: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for name in files:
        path = root / name
        if not path.exists():
            continue
        for item in load_builtin(path):
            if item["id"] in seen_ids:
                raise BuiltinError(f"内置日程 id 跨文件重复: {item['id']}")
            seen_ids.add(item["id"])
            combined.append(item)
    return combined


def match_builtin(days: list[dict[str, Any]], current: date) -> list[dict[str, Any]]:
    return [
        day
        for day in days
        if day.get("enabled", True) and rule_matches(day["rule"], current)
    ]


def format_builtin_line(day: dict[str, Any]) -> str:
    description = str(day.get("description") or "").strip()
    suffix = f"：{description}" if description else ""
    return f"{day['name']}（{rule_to_text(day['rule'])}）{suffix}"


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
