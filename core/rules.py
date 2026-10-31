"""日期规则：M1 支持公历每年、每周几、单次日期。"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

WEEKDAY_NAMES = (
    "周一",
    "周二",
    "周三",
    "周四",
    "周五",
    "周六",
    "周日",
)

_WEEKDAY_ALIASES = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "日": 7,
    "天": 7,
    "1": 1,
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
}

TONE_VALUES = ("festive", "solemn", "meme", "neutral")
TONE_ALIASES = {
    "节日": "festive",
    "庆祝": "festive",
    "纪念": "solemn",
    "庄重": "solemn",
    "玩梗": "meme",
    "梗": "meme",
    "普通": "neutral",
    "中性": "neutral",
}


def normalize_tone(value: Any, default: str = "neutral") -> str:
    text = str(value or "").strip().lower()
    if not text:
        return default
    if text in TONE_VALUES:
        return text
    return TONE_ALIASES.get(text, default)


def parse_rule(value: str | dict[str, Any]) -> dict[str, Any]:
    """把命令输入或 JSON 规则规范化。

    Returns:
        {"type": "solar", "month": 7, "day": 21}
        {"type": "weekday", "weekday": 4}
        {"type": "one_time", "date": "2026-11-11"}
        {"type": "nth_weekday", "month": 5, "weekday": 7, "nth": 2}
        {"type": "computus"}

    Raises:
        ValueError: 规则无法识别或日期非法。
    """
    if isinstance(value, dict):
        rule = dict(value)
        rule["type"] = str(rule.get("type") or "").strip().lower()
    else:
        rule = _parse_text_rule(str(value or "").strip())

    rule_type = rule.get("type")
    if rule_type == "solar":
        month = _to_int(rule.get("month"))
        day = _to_int(rule.get("day"))
        if month is None or day is None:
            raise ValueError("公历日期缺少 month/day")
        if not 1 <= month <= 12:
            raise ValueError("月份必须在 1-12")
        _validate_month_day(month, day)
        return {"type": "solar", "month": month, "day": day}

    if rule_type == "weekday":
        weekday = _to_int(rule.get("weekday"))
        if weekday is None or not 1 <= weekday <= 7:
            raise ValueError("weekday 必须是 1-7（周一=1）")
        return {"type": "weekday", "weekday": weekday}

    if rule_type == "one_time":
        raw = str(rule.get("date") or "").strip()
        try:
            parsed = date.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError("one_time 日期必须是 YYYY-MM-DD") from exc
        return {"type": "one_time", "date": parsed.isoformat()}

    if rule_type == "nth_weekday":
        month = _to_int(rule.get("month"))
        weekday = _to_int(rule.get("weekday"))
        nth = _to_int(rule.get("nth"))
        if month is None or not 1 <= month <= 12:
            raise ValueError("nth_weekday 的 month 必须是 1-12")
        if weekday is None or not 1 <= weekday <= 7:
            raise ValueError("nth_weekday 的 weekday 必须是 1-7")
        if nth is None or not 1 <= nth <= 5:
            raise ValueError("nth_weekday 的 nth 必须是 1-5")
        return {"type": "nth_weekday", "month": month, "weekday": weekday, "nth": nth}

    if rule_type == "computus":
        return {"type": "computus"}

    raise ValueError(f"不支持的规则类型: {rule_type or '空'}")


def _parse_text_rule(text: str) -> dict[str, Any]:
    if not text:
        raise ValueError("日期不能为空")

    # 复活节
    if text in ("复活节", "easter", "Easter"):
        return {"type": "computus"}

    # 5月第2个周日 / 5月第二个星期日
    m = re.fullmatch(
        r"(\d{1,2})月(?:的)?第([1-5一二三四五])个?(?:周|星期)([一二三四五六日天])",
        text,
    )
    if m:
        nth = _NTH_ALIASES[m.group(2)]
        return {
            "type": "nth_weekday",
            "month": int(m.group(1)),
            "weekday": _WEEKDAY_ALIASES[m.group(3)],
            "nth": nth,
        }

    # 每周几 / 周四
    m = re.fullmatch(r"(?:每)?(?:周|星期)([一二三四五六日天1-7])", text)
    if m:
        return {"type": "weekday", "weekday": _WEEKDAY_ALIASES[m.group(1)]}

    # 单次完整日期：2026-11-11
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if m:
        raw = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return {"type": "one_time", "date": raw}

    # 每年日期：7-21 / 07/21 / 7.21
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})", text)
    if m:
        return {
            "type": "solar",
            "month": int(m.group(1)),
            "day": int(m.group(2)),
        }

    # 中文日期：7月21日 / 7月21
    m = re.fullmatch(r"(\d{1,2})月(\d{1,2})日?", text)
    if m:
        return {
            "type": "solar",
            "month": int(m.group(1)),
            "day": int(m.group(2)),
        }

    raise ValueError(
        "日期格式无法识别，可用：7-21、7月21日、周四、每周四、5月第2个周日、复活节、2026-11-11"
    )


_NTH_ALIASES = {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5}


def nth_weekday_date(year: int, month: int, weekday: int, nth: int) -> date | None:
    """返回某年某月第 N 个星期几；不存在时返回 None。"""
    try:
        first = date(year, month, 1)
    except ValueError:
        return None
    offset = (weekday - first.isoweekday()) % 7
    day = 1 + offset + (nth - 1) * 7
    try:
        return date(year, month, day)
    except ValueError:
        return None


def easter_date(year: int) -> date | None:
    """公历（西方）复活节日期，Anonymous Gregorian 算法。"""
    if not 1583 <= year <= 4099:
        return None
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _validate_month_day(month: int, day: int) -> None:
    try:
        date(2000, month, day)  # 2000 是闰年，2-29 也可通过
    except ValueError as exc:
        raise ValueError(f"非法日期: {month}-{day}") from exc


def rule_matches(rule: dict[str, Any], current: date) -> bool:
    rule_type = rule.get("type")
    if rule_type == "solar":
        return current.month == rule.get("month") and current.day == rule.get("day")
    if rule_type == "weekday":
        return current.isoweekday() == rule.get("weekday")
    if rule_type == "one_time":
        return current.isoformat() == rule.get("date")
    if rule_type == "nth_weekday":
        target = nth_weekday_date(
            current.year,
            int(rule.get("month", 0)),
            int(rule.get("weekday", 0)),
            int(rule.get("nth", 0)),
        )
        return target == current
    if rule_type == "computus":
        return easter_date(current.year) == current
    return False


def rule_to_text(rule: dict[str, Any]) -> str:
    rule_type = rule.get("type")
    if rule_type == "solar":
        return f"每年 {int(rule['month']):02d}-{int(rule['day']):02d}"
    if rule_type == "weekday":
        idx = int(rule["weekday"])
        return WEEKDAY_NAMES[idx - 1] if 1 <= idx <= 7 else f"每周{idx}"
    if rule_type == "one_time":
        return f"{rule['date']} 单次"
    if rule_type == "nth_weekday":
        return (
            f"{int(rule['month'])}月第{int(rule['nth'])}个"
            f"{WEEKDAY_NAMES[int(rule['weekday']) - 1]}"
        )
    if rule_type == "computus":
        return "复活节"
    return "未知规则"


def rule_key(rule: dict[str, Any]) -> str:
    rule_type = rule.get("type")
    if rule_type == "solar":
        return f"solar:{rule['month']:02d}-{rule['day']:02d}"
    if rule_type == "weekday":
        return f"weekday:{rule['weekday']}"
    if rule_type == "one_time":
        return f"one_time:{rule['date']}"
    if rule_type == "nth_weekday":
        return f"nth_weekday:{rule['month']}:{rule['weekday']}:{rule['nth']}"
    if rule_type == "computus":
        return "computus"
    return "unknown"
