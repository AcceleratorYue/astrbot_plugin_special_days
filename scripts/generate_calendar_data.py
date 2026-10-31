"""生成 M2.1 静态日历数据。

开发期工具，不参与插件运行时。用法：

    python scripts/generate_calendar_data.py

依赖：
- lunardate（开发期）
- 网络访问 holiday-cn 的 jsDelivr 镜像

生成：
- data/lunar_festivals.json
- data/holiday_cn_days.json
"""

from __future__ import annotations

import json
import urllib.request
from datetime import date
from pathlib import Path

try:
    from lunardate import LunarDate
except Exception as exc:  # pragma: no cover
    raise SystemExit("需要先安装 lunardate: pip install lunardate") from exc

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DATA.mkdir(parents=True, exist_ok=True)

# (名称, 农历月, 农历日, tone, 描述, priority)
LUNAR_FESTIVALS = [
    ("春节", 1, 1, "festive", "农历新年，可以说一句新年相关的话。", 70),
    ("元宵节", 1, 15, "festive", "元宵节，可以聊汤圆、花灯或团圆。", 60),
    ("龙抬头", 2, 2, "neutral", "农历二月初二，可以作为聊天背景。", 40),
    ("端午节", 5, 5, "festive", "端午节，可以聊粽子、龙舟或假期。", 60),
    ("七夕节", 7, 7, "festive", "七夕，可以自然接一句，不用强行浪漫。", 55),
    ("中元节", 7, 15, "neutral", "中元节，按语境谨慎提及。", 35),
    ("中秋节", 8, 15, "festive", "中秋节，可以聊月饼、团圆或赏月。", 65),
    ("重阳节", 9, 9, "neutral", "重阳节，可以聊登高、敬老或秋天。", 45),
    ("腊八节", 12, 8, "festive", "腊八节，可以聊腊八粥。", 45),
    ("小年", 12, 23, "festive", "北方小年，可以聊年味和准备过年。", 45),
    ("南方小年", 12, 24, "festive", "南方小年，可以聊年味和准备过年。", 40),
]

# 覆盖“节日所在的公历年份”
START_SOLAR_YEAR = 2025
END_SOLAR_YEAR = 2036


def lunar_to_solar(lunar_year: int, month: int, day: int) -> date | None:
    try:
        return LunarDate(lunar_year, month, day).to_solar_date()
    except Exception:
        return None


def lunar_last_day(lunar_year: int) -> date | None:
    for day in (30, 29, 28):
        solar = lunar_to_solar(lunar_year, 12, day)
        if solar is not None:
            return solar
    return None


def build_lunar() -> list[dict]:
    out: list[dict] = []
    for lunar_year in range(START_SOLAR_YEAR - 1, END_SOLAR_YEAR + 1):
        for name, month, day, tone, desc, priority in LUNAR_FESTIVALS:
            solar = lunar_to_solar(lunar_year, month, day)
            if solar is None or not (START_SOLAR_YEAR <= solar.year <= END_SOLAR_YEAR):
                continue
            out.append(
                {
                    "id": f"lunar_{solar.isoformat()}_{name}",
                    "name": name,
                    "rule": {"type": "one_time", "date": solar.isoformat()},
                    "tone": tone,
                    "description": desc,
                    "priority": priority,
                    "source": "lunar",
                }
            )

        chuxi = lunar_last_day(lunar_year)
        if chuxi and START_SOLAR_YEAR <= chuxi.year <= END_SOLAR_YEAR:
            out.append(
                {
                    "id": f"lunar_{chuxi.isoformat()}_除夕",
                    "name": "除夕",
                    "rule": {"type": "one_time", "date": chuxi.isoformat()},
                    "tone": "festive",
                    "description": "除夕，可以聊年夜饭、守岁或回家。",
                    "priority": 70,
                    "source": "lunar",
                }
            )
    return out


def fetch_holiday_cn(year: int) -> list[dict]:
    url = (
        "https://cdn.jsdelivr.net/gh/NateScarlet/holiday-cn@master/"
        f"{year}.json"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.load(resp)
    return data.get("days", [])


def build_holiday_cn(years: tuple[int, ...] = (2025, 2026)) -> list[dict]:
    out: list[dict] = []
    for year in years:
        try:
            days = fetch_holiday_cn(year)
        except Exception as exc:  # pragma: no cover
            print(f"跳过 {year}: {exc}")
            continue
        for item in days:
            raw_date = str(item.get("date") or "")
            raw_name = str(item.get("name") or "").strip()
            if not raw_date or not raw_name:
                continue
            off = bool(item.get("isOffDay"))
            names = [part.strip() for part in raw_name.split("、") if part.strip()]
            for name in names:
                if not off:
                    display_name = f"调休上班（{name}）"
                    tone = "neutral"
                    desc = "调休补班日，可以自然提醒今天要上班。"
                    priority = 30
                else:
                    display_name = name
                    tone = "festive"
                    desc = "法定假期；按当前语境自然提及，不要主动播报。"
                    priority = 60
                out.append(
                    {
                        "id": f"cn_{raw_date}_{name}_{'off' if off else 'work'}",
                        "name": display_name,
                        "rule": {"type": "one_time", "date": raw_date},
                        "tone": tone,
                        "description": desc,
                        "priority": priority,
                        "source": "holiday_cn",
                    }
                )
    return out


def save(name: str, items: list[dict]) -> None:
    path = DATA / name
    payload = {"version": 1, "days": items}
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"写入 {path} ({len(items)} 条)")


def main() -> None:
    save("lunar_festivals.json", build_lunar())
    save("holiday_cn_days.json", build_holiday_cn())


if __name__ == "__main__":
    main()
