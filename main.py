"""AstrBot 特殊日程插件（今天是什么日子）。

当天有匹配的节假日、纪念日、玩梗日或自定义日程时，
在 LLM 请求的 system_prompt 末尾追加一小段背景提示；
不主动发消息、不额外调用 LLM、不修改消息链。
"""

from __future__ import annotations

import asyncio
import json
import re
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, StarTools

from astrbot.api.web import json_response, request

from .core.builtin import load_builtin_dir, match_builtin
from .core.holiday import (
    HOLIDAY_URL_TEMPLATE,
    load_cache,
    merge_builtin_days,
    parse_holiday_payload,
    save_cache,
)
from .core.prompt import build_prompt_block
from .core.rules import (
    TONE_VALUES,
    normalize_tone,
    rule_matches,
    rule_to_text,
)
from .core.store import CustomDayStore

PLUGIN_NAME = "astrbot_plugin_special_days"
LOG = f"[{PLUGIN_NAME}]"
VERSION = "0.9.0"

_HELP = """特殊日程用法：
/特殊日 今天
/特殊日 列表
/特殊日 添加 <日期> <名称> [描述] [语气]
/特殊日 删除 <id>
/特殊日 导出
/特殊日 导入 <JSON>
/特殊日 刷新节假日（管理员）
/特殊日 帮助

日期格式：7-21、7月21日、周四、每周四、5月第2个周日、复活节、2026-11-11
语气：festive / solemn / meme / neutral（也可用 节日/纪念/玩梗/普通）
示例：/特殊日 添加 7-21 0721 网络玩梗日 meme
当前会话添加的日程只在本会话生效。"""


class SpecialDaysPlugin(Star):
    def __init__(self, context: Context, config: dict[str, Any] | None = None):
        super().__init__(context)
        self.config = config or {}
        self.timezone = self._load_timezone()
        self.data_dir = Path(StarTools.get_data_dir(PLUGIN_NAME))
        self.data_dir.mkdir(parents=True, exist_ok=True)

        builtin_path = Path(__file__).resolve().parent / "data"
        try:
            self.builtin_days = load_builtin_dir(builtin_path)
        except Exception as exc:  # noqa: BLE001
            logger.error("%s 内置日程加载失败: %s", LOG, exc)
            self.builtin_days = []

        self._holiday_cache_path = self.data_dir / "holidays_cache.json"
        self._holiday_task: asyncio.Task | None = None
        cached_holidays = load_cache(self._holiday_cache_path)
        if cached_holidays:
            self.builtin_days = merge_builtin_days(self.builtin_days, cached_holidays)
            logger.info("%s 已从缓存加载 %d 条自动节假日", LOG, len(cached_holidays))

        try:
            self.store = CustomDayStore(self.data_dir / "special_days.db")
        except Exception as exc:  # noqa: BLE001
            logger.error("%s 自定义日程数据库初始化失败: %s", LOG, exc)
            self.store = None

        self._register_web_apis()

        logger.info(
            "%s v%s 已加载 | 内置 %d 条 | 时区 %s | 自定义库 %s",
            LOG,
            VERSION,
            len(self.builtin_days),
            self.timezone,
            "ok" if self.store else "failed",
        )

    async def initialize(self) -> None:
        """插件启用后后台更新法定节假日数据，失败不影响启动。"""
        if not self._cfg_bool("holiday_auto_update", True):
            return
        self._holiday_task = asyncio.create_task(self._refresh_holidays())

    async def terminate(self) -> None:
        if self._holiday_task is not None and not self._holiday_task.done():
            self._holiday_task.cancel()

    def _load_timezone(self) -> ZoneInfo:
        name = str(self.config.get("timezone") or "Asia/Shanghai").strip()
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            logger.warning("%s 时区 %s 无效，回退 Asia/Shanghai", LOG, name)
            return ZoneInfo("Asia/Shanghai")

    def _now_date(self) -> date:
        return datetime.now(self.timezone).date()

    def _cfg_bool(self, key: str, default: bool = True) -> bool:
        value = self.config.get(key, default)
        if isinstance(value, str):
            return value.strip().lower() not in ("false", "0", "no", "off", "")
        return bool(value)

    def _cfg_int(self, key: str, default: int) -> int:
        try:
            return int(self.config.get(key, default))
        except (TypeError, ValueError):
            return default

    async def _refresh_holidays(self) -> str:
        """抓取当年/前后一年法定节假日；失败时保留内置和缓存。"""
        template = str(self.config.get("holiday_update_url") or "").strip() or HOLIDAY_URL_TEMPLATE
        current = self._now_date()
        years = (current.year - 1, current.year, current.year + 1)
        extra: list[dict[str, Any]] = []
        fetched_years: list[int] = []
        seen_urls: set[str] = set()
        for year in years:
            url = template.format(year=year) if "{year}" in template else template
            if url in seen_urls:
                continue
            seen_urls.add(url)
            payload = await self._fetch_json(url)
            if payload is None:
                continue
            entries = parse_holiday_payload(payload)
            if not entries:
                continue
            extra.extend(entries)
            fetched_years.append(year)
        if not extra:
            logger.info("%s 节假日自动更新未拿到有效数据，继续使用内置/缓存", LOG)
            return "节假日更新失败：没有拿到有效数据，继续使用内置/缓存。"

        cached = load_cache(self._holiday_cache_path)
        combined = merge_builtin_days(cached, extra)
        self.builtin_days = merge_builtin_days(self.builtin_days, combined)
        try:
            save_cache(self._holiday_cache_path, combined)
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s 写入节假日缓存失败: %s", LOG, exc)
        logger.info(
            "%s 节假日已更新 %d 条（年份 %s）",
            LOG,
            len(extra),
            ",".join(str(y) for y in fetched_years),
        )
        return f"节假日数据已更新：新增/覆盖 {len(extra)} 条（年份 {','.join(map(str, fetched_years))}）。"

    @staticmethod
    async def _fetch_json(url: str) -> Any:
        def _fetch() -> Any:
            request = urllib.request.Request(
                url, headers={"User-Agent": "astrbot_plugin_special_days"}
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))

        try:
            return await asyncio.to_thread(_fetch)
        except Exception as exc:  # noqa: BLE001
            logger.debug("%s 拉取节假日失败 %s: %s", LOG, url, exc)
            return None

    def _matches(self, current: date, scope_umo: str) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        if self._cfg_bool("enable_builtin", True):
            matches.extend(match_builtin(self.builtin_days, current))
        if self.store is not None:
            for item in self.store.list_for_scope(scope_umo):
                try:
                    if rule_matches(item["rule"], current):
                        matches.append(item)
                except Exception:
                    continue
        return matches

    @filter.on_llm_request(priority=-100)
    async def inject_special_days(
        self, event: AstrMessageEvent, req: ProviderRequest
    ) -> None:
        if not self._cfg_bool("enable", True):
            return
        is_private = event.is_private_chat()
        if is_private and not self._cfg_bool("inject_in_private", True):
            return
        if not is_private and not self._cfg_bool("inject_in_group", True):
            return

        current = self._now_date()
        matches = self._matches(current, str(event.unified_msg_origin or ""))
        block = build_prompt_block(
            matches,
            current=current,
            max_days=self._cfg_int("max_days", 3),
            suppress_meme_on_solemn=self._cfg_bool(
                "suppress_meme_on_solemn", True
            ),
            custom_overrides_builtin=self._cfg_bool(
                "custom_overrides_builtin", True
            ),
        )
        if not block:
            return

        base = str(getattr(req, "system_prompt", "") or "").rstrip()
        req.system_prompt = f"{base}\n\n{block}" if base else block
        if self._cfg_bool("debug_log", False):
            logger.info("%s 注入 %d 条日程: %s", LOG, len(matches), block[:200])

    # ------------------------------------------------------------------ #
    # 指令
    # ------------------------------------------------------------------ #

    @filter.command("特殊日", alias=["特殊日程", "specialday"])
    async def special_day_command(self, event: AstrMessageEvent):
        event.should_call_llm(False)
        body = self._command_body(event)
        if not body:
            yield event.plain_result(_HELP)
            return

        parts = body.split()
        action = parts[0].lower()
        if action in ("今天", "today", "今日"):
            yield event.plain_result(self._today_text(event))
            return
        if action in ("列表", "list"):
            yield event.plain_result(self._list_text(event))
            return
        if action in ("添加", "add", "新增"):
            yield event.plain_result(self._add_from_command(event, parts))
            return
        if action in ("删除", "delete", "del"):
            yield event.plain_result(self._delete_from_command(event, parts))
            return
        if action in ("导出", "export"):
            yield event.plain_result(self._export_text(event))
            return
        if action in ("导入", "import"):
            raw = body[len(parts[0]) :].strip()
            yield event.plain_result(self._import_text(event, raw))
            return
        if action in ("刷新节假日", "更新节假日", "节假日刷新"):
            if not self._is_admin(event):
                yield event.plain_result("只有管理员可以刷新节假日数据。")
            else:
                yield event.plain_result(await self._refresh_holidays())
            return
        if action in ("帮助", "help", "?"):
            yield event.plain_result(_HELP)
            return
        yield event.plain_result("不认识的子命令。\n\n" + _HELP)

    def _command_body(self, event: AstrMessageEvent) -> str:
        text = str(getattr(event, "message_str", "") or "").strip()
        text = re.sub(
            r"^[/!！]?\s*(?:特殊日|特殊日程|specialday)(?:\s+|$)",
            "",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
        return text.strip()

    def _can_manage_custom(self, event: AstrMessageEvent) -> bool:
        if self._cfg_bool("allow_user_custom", True):
            return True
        is_admin = getattr(event, "is_admin", None)
        try:
            return bool(is_admin() if callable(is_admin) else is_admin)
        except Exception:
            return False

    def _today_text(self, event: AstrMessageEvent) -> str:
        current = self._now_date()
        matches = self._matches(current, str(event.unified_msg_origin or ""))
        if not matches:
            return f"今天（{current:%m-%d}）没有匹配的特殊日程。"
        lines = [f"今天的特殊日程（{current:%Y-%m-%d}）："]
        for item in sorted(
            matches,
            key=lambda x: (
                0 if normalize_tone(x.get("tone")) == "solemn" else 1,
                -int(x.get("priority") or 50),
                str(x.get("name") or ""),
            ),
        ):
            source = "内置" if item.get("source") in ("builtin", "holiday_cn", "lunar") else "自定义"
            tone = normalize_tone(item.get("tone"))
            desc = str(item.get("description") or "").strip()
            suffix = f"：{desc}" if desc else ""
            lines.append(
                f"- [{source}] {item.get('name')}（{rule_to_text(item['rule'])} / {tone}）{suffix}"
            )
        return "\n".join(lines)

    def _list_text(self, event: AstrMessageEvent) -> str:
        if self.store is None:
            return "自定义日程库不可用。"
        scope = str(event.unified_msg_origin or "")
        items = self.store.list_for_scope(scope)
        if not items:
            return "当前会话没有自定义日程。\n" + (
                "用 /特殊日 添加 <日期> <名称> 添加；M1 暂不支持修改内置日程。"
            )
        lines = ["当前会话的自定义日程："]
        for item in items:
            scope_text = "全局" if not item.get("scope_umo") else "本会话"
            lines.append(
                f"- {item['id']} | {item['name']} | {rule_to_text(item['rule'])} | "
                f"{normalize_tone(item.get('tone'))} | {scope_text}"
            )
        lines.append(f"内置日程 {len(self.builtin_days)} 条，当前只读。")
        return "\n".join(lines)

    def _export_text(self, event: AstrMessageEvent) -> str:
        if self.store is None:
            return "自定义日程库不可用。"
        scope = str(event.unified_msg_origin or "")
        items = self.store.export_scope(scope)
        if not items:
            return "当前会话没有可导出的自定义日程。"
        payload = {"version": 1, "days": items}
        return (
            "特殊日程导出（当前会话）：\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )

    def _import_text(self, event: AstrMessageEvent, raw: str) -> str:
        if not self._can_manage_custom(event):
            return "当前配置不允许普通用户维护自定义日程。"
        if self.store is None:
            return "自定义日程库不可用。"
        text = str(raw or "").strip()
        if not text:
            return "用法：/特殊日 导入 <JSON>\n先用 /特殊日 导出 获取 JSON。"
        # 兼容 ```json ... ``` 代码块
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            return f"JSON 解析失败：{exc}"
        items = data.get("days") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return "导入数据必须是日程列表，或包含 days 列表。"
        try:
            result = self.store.import_days(
                items, str(event.unified_msg_origin or "")
            )
        except ValueError as exc:
            return f"导入失败：{exc}"
        for item in result["imported"]:
            self._audit(event, "command_import", item)
        summary = (
            f"导入完成：新增 {len(result['imported'])} 条，"
            f"跳过 {result['skipped']} 条。"
        )
        if result["errors"]:
            summary += "\n错误：" + "；".join(result["errors"][:5])
        return summary

    def _add_from_command(self, event: AstrMessageEvent, parts: list[str]) -> str:
        if not self._can_manage_custom(event):
            return "当前配置不允许普通用户维护自定义日程。"
        if self.store is None:
            return "自定义日程库不可用。"
        if len(parts) < 3:
            return "用法：/特殊日 添加 <日期> <名称> [描述] [语气]\n" + _HELP

        rule_text = parts[1]
        name = parts[2]
        rest = parts[3:]
        tone = "neutral"
        if rest and rest[-1].lower() in TONE_VALUES:
            tone = rest.pop().lower()
        elif rest and rest[-1] in ("节日", "庆祝", "纪念", "庄重", "玩梗", "梗", "普通", "中性"):
            tone = normalize_tone(rest.pop())
        description = " ".join(rest).strip()

        try:
            created = self.store.add(
                name=name,
                rule=rule_text,
                scope_umo=str(event.unified_msg_origin or ""),
                tone=tone,
                description=description,
                created_by=str(event.get_sender_id() or ""),
            )
            self._audit(event, "command_create", created)
            return (
                f"已添加自定义日程：{created['name']} | "
                f"{rule_to_text(created['rule'])} | {normalize_tone(created['tone'])} | id={created['id']}"
            )
        except ValueError as exc:
            return f"添加失败：{exc}"

    def _delete_from_command(self, event: AstrMessageEvent, parts: list[str]) -> str:
        if not self._can_manage_custom(event):
            return "当前配置不允许普通用户维护自定义日程。"
        if self.store is None:
            return "自定义日程库不可用。"
        if len(parts) < 2:
            return "用法：/特殊日 删除 <id>"
        day_id = parts[1]
        deleted = self.store.delete(day_id, str(event.unified_msg_origin or ""))
        if deleted:
            self._audit(event, "command_delete", {"id": day_id})
        return "已删除。" if deleted else "没找到这个 id，或它不属于当前会话。"

    # ------------------------------------------------------------------ #
    # LLM 工具：只在用户明确要求时维护自定义日期
    # ------------------------------------------------------------------ #

    @filter.llm_tool(name="special_day_manage")
    async def special_day_manage(
        self,
        event: AstrMessageEvent,
        action: str,
        name: str = "",
        date: str = "",
        description: str = "",
        tone: str = "",
        day_id: str = "",
        scope: str = "session",
        enabled: str = "",
        confirm: bool = False,
    ) -> str:
        """管理当前会话的自定义特殊日程。

        只有用户明确要求“记住/添加/修改/删除某个特殊日期”时才调用。
        不要因为聊天里随便提到一个日期就创建日程；不要替用户猜测日期。
        action=create 需要 name 和 date；update/delete 需要 day_id；
        list/today 只读。默认只写当前会话；global 需要管理员权限。

        Args:
            action(string): create、update、delete、list、today 之一。
            name(string): 日程名称，例如“0721”“项目纪念日”。
            date(string): 日期规则，例如 7-21、7月21日、周四、5月第2个周日、复活节、2026-11-11。
            description(string): 简短说明，最多 160 字。
            tone(string): festive、meme、solemn、neutral 或 节日/玩梗/纪念/普通。
            day_id(string): update/delete 时的日程 ID。
            scope(string): session（当前会话）或 global（全局，仅管理员）。
            enabled(string): update 时可填 true/false；留空表示不修改启用状态。
            confirm(bool): 插件开启二次确认时，写入必须传 true。
        """
        if not self._cfg_bool("enable", True):
            return "特殊日程插件当前已关闭。"
        if self.store is None:
            return "自定义日程库不可用。"

        action = str(action or "").strip().lower()
        scope = str(scope or "session").strip().lower()
        if scope not in ("session", "global"):
            return "scope 只能是 session 或 global。"
        if scope == "global" and not self._is_admin(event):
            return "只有管理员可以管理全局日程。"

        if action in ("list", "列表"):
            return self._tool_list(event, scope)
        if action in ("today", "今天"):
            return self._tool_today(event, scope)
        if action not in ("create", "add", "update", "delete", "del"):
            return "action 只能是 create/update/delete/list/today。"

        if not self._can_manage_custom(event):
            return "当前配置不允许普通用户维护自定义日程。"
        if (
            self._cfg_bool("require_tool_confirm", False)
            and action in ("create", "add", "update", "delete", "del")
            and not confirm
        ):
            return "本次未写入：请先向用户确认，再次调用时传 confirm=true。"
        scope_key = self._scope_key(event, scope)

        enabled_value: bool | None = None
        enabled_text = str(enabled or "").strip().lower()
        if enabled_text:
            enabled_value = enabled_text in ("1", "true", "yes", "on", "启用")

        try:
            if action in ("create", "add"):
                if not str(name or "").strip() or not str(date or "").strip():
                    return "create 需要 name 和 date。"
                created = self.store.add(
                    name=name,
                    rule=date,
                    scope_umo=scope_key,
                    tone=tone or "neutral",
                    description=description,
                    created_by=str(event.get_sender_id() or ""),
                )
                self._audit(event, "create", created)
                return (
                    f"已创建：{created['name']} | {rule_to_text(created['rule'])} | "
                    f"{normalize_tone(created['tone'])} | id={created['id']}"
                )

            if action == "update":
                if not str(day_id or "").strip():
                    return "update 需要 day_id。"
                updated = self.store.update(
                    day_id,
                    scope_key,
                    name=name or None,
                    rule=date or None,
                    tone=tone or None,
                    description=description or None,
                    enabled=enabled_value,
                )
                if updated is None:
                    return "没找到这个 id，或它不属于当前范围。"
                self._audit(event, "update", updated)
                return (
                    f"已更新：{updated['name']} | {rule_to_text(updated['rule'])} | "
                    f"{normalize_tone(updated['tone'])} | id={updated['id']}"
                )

            if not str(day_id or "").strip():
                return "delete 需要 day_id。"
            deleted = self.store.delete(day_id, scope_key)
            if not deleted:
                return "没找到这个 id，或它不属于当前范围。"
            self._audit(event, "delete", {"id": day_id, "scope": scope})
            return f"已删除日程 id={day_id}。"
        except ValueError as exc:
            return f"操作失败：{exc}"

    def _tool_list(self, event: AstrMessageEvent, scope: str) -> str:
        scope_key = self._scope_key(event, scope)
        items = self.store.list_for_scope(scope_key) if self.store else []
        if not items:
            return "当前范围没有自定义日程。"
        lines = ["当前范围的自定义日程："]
        for item in items:
            scope_text = "全局" if not item.get("scope_umo") else "本会话"
            lines.append(
                f"- {item['id']} | {item['name']} | {rule_to_text(item['rule'])} | "
                f"{normalize_tone(item.get('tone'))} | {scope_text} | enabled={item.get('enabled')}"
            )
        return "\n".join(lines)

    def _tool_today(self, event: AstrMessageEvent, scope: str) -> str:
        current = self._now_date()
        scope_key = self._scope_key(event, scope)
        matches = []
        if self._cfg_bool("enable_builtin", True):
            matches.extend(match_builtin(self.builtin_days, current))
        if self.store is not None:
            for item in self.store.list_for_scope(scope_key):
                if rule_matches(item["rule"], current):
                    matches.append(item)
        if not matches:
            return f"今天（{current:%m-%d}）没有匹配的特殊日程。"
        lines = [f"今天（{current:%Y-%m-%d}）的特殊日程："]
        for item in matches:
            lines.append(
                f"- {item['name']}（{rule_to_text(item['rule'])} / "
                f"{normalize_tone(item.get('tone'))}）"
            )
        return "\n".join(lines)

    def _scope_key(self, event: AstrMessageEvent, scope: str) -> str:
        if str(scope or "").strip().lower() == "global":
            return ""
        return str(event.unified_msg_origin or "")

    def _is_admin(self, event: AstrMessageEvent) -> bool:
        is_admin = getattr(event, "is_admin", None)
        try:
            return bool(is_admin() if callable(is_admin) else is_admin)
        except Exception:
            return False

    def _audit(self, event: AstrMessageEvent, action: str, detail: dict[str, Any]) -> None:
        try:
            record = {
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "action": action,
                "umo": str(event.unified_msg_origin or ""),
                "sender": str(event.get_sender_id() or ""),
                "detail": detail,
            }
            path = self.data_dir / "audit.log"
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            logger.info(
                "%s audit %s %s",
                PLUGIN_NAME,
                action,
                detail.get("id") or detail.get("name"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("%s 审计日志写入失败: %s", LOG, exc)

    # ------------------------------------------------------------------ #
    # WebUI 管理页 API（全局自定义日程）
    # ------------------------------------------------------------------ #

    def _register_web_apis(self) -> None:
        specs = (
            ("webui/state", self._webui_state, ["GET"], "读取特殊日程状态"),
            ("webui/create", self._webui_create, ["POST"], "创建全局特殊日程"),
            ("webui/update", self._webui_update, ["POST"], "修改全局特殊日程"),
            ("webui/delete", self._webui_delete, ["POST"], "删除全局特殊日程"),
            ("webui/export", self._webui_export, ["GET"], "导出全局特殊日程"),
            ("webui/import", self._webui_import, ["POST"], "导入全局特殊日程"),
        )
        for route, handler, methods, desc in specs:
            try:
                self.context.register_web_api(
                    f"/{PLUGIN_NAME}/{route}", handler, methods, desc
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s WebUI 路由注册失败 %s: %s", LOG, route, exc)

    def _webui_payload(self) -> dict[str, Any]:
        if self.store is None:
            return {"ok": False, "error": "自定义日程库不可用"}
        items = [
            {
                "id": item["id"],
                "name": item["name"],
                "rule": item["rule"],
                "rule_text": rule_to_text(item["rule"]),
                "tone": normalize_tone(item.get("tone")),
                "description": item.get("description", ""),
                "enabled": bool(item.get("enabled", True)),
            }
            for item in self.store.list_for_scope("")
        ]
        return {
            "ok": True,
            "version": VERSION,
            "timezone": str(self.timezone),
            "builtin_count": len(self.builtin_days),
            "days": items,
        }

    async def _webui_state(self):
        return json_response(self._webui_payload())

    async def _webui_create(self):
        if self.store is None:
            return json_response({"ok": False, "error": "自定义日程库不可用"})
        data = await request.json(default={})
        if not isinstance(data, dict):
            return json_response({"ok": False, "error": "请求体必须是 JSON 对象"})
        try:
            created = self.store.add(
                name=data.get("name", ""),
                rule=data.get("date") or data.get("rule") or "",
                scope_umo="",
                tone=data.get("tone") or "neutral",
                description=data.get("description") or "",
                priority=int(data.get("priority", 50)),
                enabled=_as_bool(data.get("enabled", True)),
                created_by="webui",
            )
            self._webui_audit("webui_create", created)
            return json_response({"ok": True, "day": self._webui_item(created), **self._webui_payload()})
        except (TypeError, ValueError) as exc:
            return json_response({"ok": False, "error": str(exc)})

    async def _webui_update(self):
        if self.store is None:
            return json_response({"ok": False, "error": "自定义日程库不可用"})
        data = await request.json(default={})
        if not isinstance(data, dict):
            return json_response({"ok": False, "error": "请求体必须是 JSON 对象"})
        day_id = str(data.get("id") or data.get("day_id") or "").strip()
        if not day_id:
            return json_response({"ok": False, "error": "缺少 id"})
        try:
            updated = self.store.update(
                day_id,
                "",
                name=data.get("name") or None,
                rule=data.get("date") or data.get("rule") or None,
                tone=data.get("tone") or None,
                description=data.get("description") if "description" in data else None,
                priority=int(data["priority"]) if "priority" in data else None,
                enabled=_as_bool(data["enabled"]) if "enabled" in data else None,
            )
            if updated is None:
                return json_response({"ok": False, "error": "没找到该全局日程"})
            self._webui_audit("webui_update", updated)
            return json_response({"ok": True, "day": self._webui_item(updated), **self._webui_payload()})
        except (TypeError, ValueError) as exc:
            return json_response({"ok": False, "error": str(exc)})

    async def _webui_delete(self):
        if self.store is None:
            return json_response({"ok": False, "error": "自定义日程库不可用"})
        data = await request.json(default={})
        if not isinstance(data, dict):
            return json_response({"ok": False, "error": "请求体必须是 JSON 对象"})
        day_id = str(data.get("id") or data.get("day_id") or "").strip()
        if not day_id:
            return json_response({"ok": False, "error": "缺少 id"})
        deleted = self.store.delete(day_id, "")
        if deleted:
            self._webui_audit("webui_delete", {"id": day_id})
        return json_response({"ok": deleted, "error": "" if deleted else "没找到该全局日程", **self._webui_payload()})

    async def _webui_export(self):
        if self.store is None:
            return json_response({"ok": False, "error": "自定义日程库不可用"})
        return json_response(
            {
                "ok": True,
                "version": VERSION,
                "days": self.store.export_scope("", include_global=True),
            }
        )

    async def _webui_import(self):
        if self.store is None:
            return json_response({"ok": False, "error": "自定义日程库不可用"})
        data = await request.json(default={})
        if not isinstance(data, dict):
            return json_response({"ok": False, "error": "请求体必须是 JSON 对象"})
        payload = data.get("data", data)
        if isinstance(payload, str):
            if len(payload) > 1_000_000:
                return json_response({"ok": False, "error": "导入内容超过 1MB 限制"})
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as exc:
                return json_response({"ok": False, "error": f"JSON 解析失败：{exc}"})
        items = payload.get("days") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            return json_response({"ok": False, "error": "数据必须是日程列表或包含 days"})
        try:
            result = self.store.import_days(items, "")
        except ValueError as exc:
            return json_response({"ok": False, "error": str(exc)})
        for item in result["imported"]:
            self._webui_audit("webui_import", item)
        return json_response(
            {
                "ok": True,
                "imported": len(result["imported"]),
                "skipped": result["skipped"],
                "errors": result["errors"],
                **self._webui_payload(),
            }
        )

    @staticmethod
    def _webui_item(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item["id"],
            "name": item["name"],
            "rule": item["rule"],
            "rule_text": rule_to_text(item["rule"]),
            "tone": normalize_tone(item.get("tone")),
            "description": item.get("description", ""),
            "enabled": bool(item.get("enabled", True)),
        }

    def _webui_audit(self, action: str, detail: dict[str, Any]) -> None:
        try:
            record = {
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "action": action,
                "umo": "webui",
                "sender": "dashboard",
                "detail": detail,
            }
            with (self.data_dir / "audit.log").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            logger.info("%s audit %s %s", PLUGIN_NAME, action, detail.get("id") or detail.get("name"))
        except Exception as exc:  # noqa: BLE001
            logger.debug("%s WebUI 审计写入失败: %s", LOG, exc)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in ("1", "true", "yes", "on", "启用")


