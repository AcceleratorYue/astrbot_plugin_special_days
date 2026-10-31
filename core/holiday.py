"""法定节假日自动抓取与转换。

数据源：NateScarlet/holiday-cn（根据国务院办公厅放假通知整理）。
网络请求只在插件启动后台/手动刷新时发生；失败时继续使用内置 JSON。
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

HOLIDAY_URL_TEMPLATE = (
    "https://cdn.jsdelivr.net/gh/NateScarlet/holiday-cn@master/{year}.json"
)
HOLIDAY_SOURCE = "holiday_cn"


def parse_holiday_payload(payload: Any) -> list[dict[str, Any]]:
    """把 holiday-cn / timor.tech / 精简数组格式转成插件内置日程结构。"""
    raw_items: list[Any] = []
    if isinstance(payload, dict):
        days = payload.get("days")
        if isinstance(days, list):
            raw_items = days
        else:
            holiday_map = payload.get("holiday")
            if isinstance(holiday_map, dict):
                raw_items = list(holiday_map.values())

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_items:
        if isinstance(item, (list, tuple)) and len(item) >= 3:
            raw_date, raw_name, raw_off = item[0], item[1], item[2]
        elif isinstance(item, dict):
            raw_date = item.get("date")
            raw_name = item.get("name", "")
            raw_off = item.get("isOffDay", item.get("holiday"))
        else:
            continue
        try:
            day = date.fromisoformat(str(raw_date or "")[:10])
        except ValueError:
            continue
        name = str(raw_name or "").strip() or "节假日"
        is_off = bool(raw_off)
        # 同一天同一状态只保留一条（不同数据源可能重复）
        safe_name = "".join(name.split())[:20]
        day_id = f"cn_{day.isoformat()}_{safe_name}_{'off' if is_off else 'work'}"
        if day_id in seen:
            continue
        seen.add(day_id)
        result.append(
            {
                "id": day_id,
                "name": name if is_off else f"调休上班（{name}）",
                "rule": {"type": "one_time", "date": day.isoformat()},
                "tone": "festive" if is_off else "neutral",
                "description": (
                    "法定假期（自动更新）；按当前语境自然提及，不要主动播报。"
                    if is_off
                    else "调休补班日，可以自然提醒今天要上班。"
                ),
                "priority": 60 if is_off else 30,
                "enabled": True,
                "source": HOLIDAY_SOURCE,
                "scope_umo": "",
            }
        )
    return sorted(result, key=lambda item: item["rule"]["date"])


def _is_cn_holiday(item: dict[str, Any]) -> bool:
    rule = item.get("rule") or {}
    return rule.get("type") == "one_time" and str(item.get("id") or "").startswith("cn_")


def merge_builtin_days(
    base: list[dict[str, Any]], extra: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """动态抓取按日期覆盖内置节假日；同一日期只保留数据源的一条。"""
    dynamic_dates = {
        str((item.get("rule") or {}).get("date") or "")
        for item in extra
        if _is_cn_holiday(item)
    }
    result = [
        item
        for item in base
        if not (_is_cn_holiday(item) and str((item.get("rule") or {}).get("date") or "") in dynamic_dates)
    ]
    seen_dates: set[str] = set()
    for item in extra:
        if not _is_cn_holiday(item):
            result.append(item)
            continue
        day_text = str((item.get("rule") or {}).get("date") or "")
        if day_text in seen_dates:
            continue
        seen_dates.add(day_text)
        result.append(item)
    return result


def load_cache(path: str | Path) -> list[dict[str, Any]]:
    cache_path = Path(path)
    if not cache_path.is_file():
        return []
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    days = payload.get("days") if isinstance(payload, dict) else payload
    if not isinstance(days, list):
        return []
    result: list[dict[str, Any]] = []
    for item in days:
        if not isinstance(item, dict):
            continue
        rule = item.get("rule") or {}
        if rule.get("type") != "one_time" or not rule.get("date"):
            continue
        result.append(
            {
                "id": str(item.get("id") or ""),
                "name": str(item.get("name") or "").strip(),
                "rule": {"type": "one_time", "date": str(rule["date"])[:10]},
                "tone": str(item.get("tone") or "neutral"),
                "description": str(item.get("description") or "").strip(),
                "priority": int(item.get("priority") or 50),
                "enabled": bool(item.get("enabled", True)),
                "source": HOLIDAY_SOURCE,
                "scope_umo": "",
            }
        )
    return [item for item in result if item["id"] and item["name"]]


def save_cache(path: str | Path, days: list[dict[str, Any]]) -> None:
    cache_path = Path(path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "source": "NateScarlet/holiday-cn",
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "days": sorted(days, key=lambda item: item["rule"]["date"]),
    }
    cache_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
