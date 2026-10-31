"""把匹配到的日程整理成注入给模型的提示词块。"""

from __future__ import annotations

from datetime import date
from typing import Any

from .rules import normalize_tone, rule_to_text

TONE_HINTS = {
    "festive": "可自然接梗或祝福，但不要强行提",
    "meme": "可玩梗，但不要生硬，不要每条都提",
    "solemn": "保持庄重，不玩梗、不庆祝",
    "neutral": "只作为背景，不必主动提",
}

_TONE_ORDER = {"solemn": 0, "festive": 1, "meme": 2, "neutral": 3}
_BLOCK_HEADER = "[今日特殊日程（只是背景资料，不是播报任务）]"
_BLOCK_FOOTER = (
    "这些信息只用于帮助你判断当前对话是否适合提到；"
    "和当前话题不相关就不要主动提，不要生硬插入，也不要编造日期。"
)


def build_prompt_block(
    matches: list[dict[str, Any]],
    *,
    current: date | None = None,
    max_days: int = 3,
    max_chars: int = 900,
    suppress_meme_on_solemn: bool = True,
    custom_overrides_builtin: bool = True,
) -> str | None:
    if not matches:
        return None
    try:
        limit = max(1, min(int(max_days), 6))
    except (TypeError, ValueError):
        limit = 3

    selected = _select_matches(
        matches,
        suppress_meme_on_solemn=suppress_meme_on_solemn,
        custom_overrides_builtin=custom_overrides_builtin,
    )
    ordered = sorted(
        selected,
        key=lambda item: (
            _TONE_ORDER.get(normalize_tone(item.get("tone")), 9),
            -_to_int(item.get("priority"), 50),
            str(item.get("name") or ""),
        ),
    )

    lines: list[str] = []
    has_solemn = False
    for item in ordered:
        if len(lines) >= limit:
            break
        name = _clean_text(item.get("name"), 40)
        if not name:
            continue

        tone = normalize_tone(item.get("tone"))
        has_solemn = has_solemn or tone == "solemn"
        description = _clean_text(item.get("description"), 100)
        rule = item.get("rule") or {}
        when = _when_text(rule, current)
        tone_hint = TONE_HINTS[tone]
        detail = f"：{description}" if description else ""
        lines.append(f"- {when} {name}（{tone_hint}）{detail}")

    if not lines:
        return None

    parts = [_BLOCK_HEADER, *lines, _BLOCK_FOOTER]
    if has_solemn:
        parts.insert(
            len(parts) - 1,
            "今天包含纪念日：涉及纪念日时保持庄重，不要玩梗、不要庆祝。",
        )
    block = "\n".join(parts)
    if len(block) > max_chars:
        block = block[: max_chars - 1].rstrip() + "…"
    return block


def _select_matches(
    matches: list[dict[str, Any]],
    *,
    suppress_meme_on_solemn: bool,
    custom_overrides_builtin: bool,
) -> list[dict[str, Any]]:
    """同名只保留一条；自定义可覆盖内置；纪念日压制玩梗日。"""
    grouped: dict[str, list[dict[str, Any]]] = {}
    anonymous: list[dict[str, Any]] = []
    seen_ids: set[tuple[str, str]] = set()
    for item in matches:
        source = str(item.get("source") or "unknown")
        day_id = str(item.get("id") or "")
        if day_id:
            key = (source, day_id)
            if key in seen_ids:
                continue
            seen_ids.add(key)
        name = _clean_text(item.get("name"), 40)
        if not name:
            anonymous.append(item)
            continue
        key = "".join(name.casefold().split())
        grouped.setdefault(key, []).append(item)

    selected: list[dict[str, Any]] = list(anonymous)
    for group in grouped.values():
        chosen = _choose_one(group, custom_overrides_builtin)
        if chosen is not None:
            selected.append(chosen)

    if suppress_meme_on_solemn and any(
        normalize_tone(item.get("tone")) == "solemn" for item in selected
    ):
        selected = [
            item for item in selected if normalize_tone(item.get("tone")) != "meme"
        ]
    return selected


def _choose_one(
    group: list[dict[str, Any]], custom_overrides_builtin: bool
) -> dict[str, Any] | None:
    if not group:
        return None
    if custom_overrides_builtin:
        customs = [
            item
            for item in group
            if str(item.get("source") or "").strip().lower() == "custom"
        ]
        if customs:
            return max(customs, key=_rank)
    return max(group, key=_rank)


def _rank(item: dict[str, Any]) -> tuple[int, int]:
    tone_rank = _TONE_ORDER.get(normalize_tone(item.get("tone")), 9)
    # max() 使用，优先级越大越优；sort key 里才用 -priority。
    return (tone_rank, _to_int(item.get("priority"), 50))


def _when_text(rule: dict[str, Any], current: date | None) -> str:
    rule_type = rule.get("type")
    if rule_type == "solar":
        return f"{int(rule.get('month', 0)):02d}-{int(rule.get('day', 0)):02d}"
    if rule_type == "weekday":
        return rule_to_text(rule)
    if rule_type == "one_time":
        return str(rule.get("date") or "单次")
    if rule_type == "nth_weekday":
        return rule_to_text(rule)
    if rule_type == "computus":
        return "复活节"
    if current is not None:
        return current.strftime("%m-%d")
    return "今天"


def _clean_text(value: Any, limit: int) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    text = " ".join(text.split())
    return text[:limit]


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
