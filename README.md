# 今天是什么日子 · `astrbot_plugin_special_days`

[![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.24%2C%3C5-5b6cff)](https://github.com/AstrBotDevs/AstrBot)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub](https://img.shields.io/badge/GitHub-AcceleratorYue%2Fastrbot__plugin__special__days-181717)](https://github.com/AcceleratorYue/astrbot_plugin_special_days)

给 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 加一个轻量的“今天是什么日子”感知：

- 当天命中节假日、纪念日、玩梗日或自定义日程时，在 LLM 请求的 `system_prompt` 末尾追加一小段背景提示；
- 由模型根据当前聊天上下文决定要不要提，不主动推送、不强制回复；
- 不额外调用 LLM，不修改消息链，不写对话历史；
- 内置日程只读本地 JSON，运行时不联网。

当前版本 **0.9.0**。

## 功能

- **内置日程 262 条**
  - 公历固定日期：元旦、情人节、妇女节、劳动节、儿童节、国庆节、万圣节、平安夜、圣诞节、跨年等；
  - 纪念日：汶川地震纪念日、九一八、抗战胜利纪念日、国家公祭日等，默认 `solemn`；
  - 玩梗日：疯狂星期四（每周四）、0721、520/521、618、双十一、程序员节等；
  - 农历节日（2025–2036）：春节、元宵、除夕、端午、七夕、中秋、重阳、腊八、小年等；
  - 计算型节日：母亲节、父亲节、感恩节、复活节、美国阵亡将士纪念日等；
  - 中国法定节假日/调休（2025–2026 快照）。
- **当前会话自定义日程**：指令或 LLM 工具维护，SQLite 持久化；
- **全局日程**：管理员维护，所有会话可见；
- **同日多日程保护**：有 `solemn` 纪念日时压制 `meme` 玩梗日；自定义同名优先；
- **LLM 工具** `special_day_manage`：只有用户明确要求时才写入；
- **WebUI 管理页**：全局日程增删改查、导出/导入 JSON；
- **指令导出/导入**：当前会话数据迁移。

## 安装

### 方式一：插件市场

在 AstrBot WebUI →「插件」→「插件市场」搜索 今天是什么日子，安装后重载。

### 方式二：GitHub

```bash
cd <AstrBot根目录>/data/plugins
git clone https://github.com/AcceleratorYue/astrbot_plugin_special_days
```

### 方式三：本地目录

```bash
# 把本目录复制到
<AstrBot根目录>/data/plugins/astrbot_plugin_special_days
```

然后在 AstrBot WebUI →「插件管理」重载插件，或重启 AstrBot。

本插件无额外第三方依赖，`requirements.txt` 仅作占位说明。

## 使用

### 指令

```text
/特殊日 今天
/特殊日 列表
/特殊日 添加 <日期> <名称> [描述] [语气]
/特殊日 删除 <id>
/特殊日 导出
/特殊日 导入 <JSON>
/特殊日 刷新节假日（管理员）
/特殊日 帮助
```

日期格式：

| 写法 | 含义 |
|---|---|
| `7-21`、`7月21日` | 每年 7 月 21 日 |
| `周四`、`每周四` | 每周四 |
| `2026-11-11` | 仅 2026-11-11 单次 |
| `5月第2个周日` | 每年 5 月第 2 个周日 |
| `复活节` | 按复活节计算 |

语气：

| 值 | 含义 |
|---|---|
| `festive` / `节日` | 可自然接梗或祝福 |
| `meme` / `玩梗` | 可玩梗，但不要生硬 |
| `solemn` / `纪念` | 保持庄重，不玩梗、不庆祝 |
| `neutral` / `普通` | 只作为背景 |

示例：

```text
/特殊日 添加 7-21 0721 网络玩梗日 meme
/特殊日 添加 2026-11-11 光棍节 单次玩梗 meme
/特殊日 添加 每周四 疯狂星期四 自定义每周提醒 meme
```

### WebUI

插件自带「今天是什么日子」管理页，在 AstrBot 插件详情页打开：

- 管理**全局**自定义日程；
- 新增、编辑、启用/停用、删除；
- 导出全局 JSON；
- 粘贴 JSON 导入全局；
- 查看内置数量、版本、时区。

会话内日程仍通过 `/特殊日` 或 LLM 工具维护。

### LLM 工具

`special_day_manage`：

```text
create / update / delete / list / today
```

参数：`action`、`name`、`date`、`description`、`tone`、`day_id`、`scope`、`enabled`、`confirm`。

- 只有用户明确要求“记住/添加/修改/删除某个特殊日期”时才应调用；
- 默认写当前会话；
- `scope=global` 仅管理员；
- 所有写入写审计日志：`data/plugin_data/astrbot_plugin_special_days/audit.log`；
- `enabled` 留空表示不修改启用状态；
- 开启 `require_tool_confirm` 后写入必须传 `confirm=true`。

## 配置

配置文件：`data/config/astrbot_plugin_special_days_config.json`

| 键 | 默认 | 说明 |
|---|---|---|
| `enable` | `true` | 总开关 |
| `enable_builtin` | `true` | 内置日程开关 |
| `timezone` | `Asia/Shanghai` | 判断“今天”的时区 |
| `max_days` | `3` | 一次最多注入几条 |
| `inject_in_group` | `true` | 群聊注入 |
| `inject_in_private` | `true` | 私聊注入 |
| `allow_user_custom` | `true` | 允许普通用户维护本会话自定义日程 |
| `suppress_meme_on_solemn` | `true` | 同日有纪念日时丢弃玩梗日 |
| `custom_overrides_builtin` | `true` | 同日同名时自定义覆盖内置 |
| `require_tool_confirm` | `false` | LLM 工具写入是否需要 `confirm=true` |
| `holiday_auto_update` | `true` | 启动后台抓取当年/前后一年法定节假日 |
| `holiday_update_url` | 空 | 自定义节假日 URL 模板，支持 `{year}` |
| `debug_log` | `false` | 记录注入日志 |

## 注入示例

命中时，模型会额外收到：

```text
[今日特殊日程（只是背景资料，不是播报任务）]
- 10-31 万圣节（可自然接梗或祝福，但不要强行提）：万圣节，可以自然玩梗或接一句节日气氛。
这些信息只用于帮助你判断当前对话是否适合提到；和当前话题不相关就不要主动提，不要生硬插入，也不要编造日期。
```

没有命中时不会注入任何内容。

## 法定节假日自动更新

数据源：`https://cdn.jsdelivr.net/gh/NateScarlet/holiday-cn@master/{year}.json`

- 默认启动后台更新 2025/2026/2027 等年份；
- 成功写入缓存，重启后先加载缓存；
- 网络失败不影响插件，继续用 `data/holiday_cn_days.json` 兜底；
- 缓存路径：`data/plugin_data/astrbot_plugin_special_days/holidays_cache.json`；
- 管理命令：`/特殊日 刷新节假日`。

## 数据文件

```text
data/builtin_days.json       固定规则/纪念日/玩梗日
data/lunar_festivals.json    农历节日 one_time 快照（2025–2036）
data/holiday_cn_days.json    中国法定节假日/调休 one_time 快照（2025–2026）
data/computed_days.json      第 N 个星期几/复活节规则
```

内置 JSON 是离线兜底；启动后会后台从 [NateScarlet/holiday-cn](https://github.com/NateScarlet/holiday-cn) 抓取当年/前后一年法定节假日，写入 `plugin_data/astrbot_plugin_special_days/holidays_cache.json`，失败时继续用内置/缓存。管理员可用 `/特殊日 刷新节假日` 手动刷新。

## 开发

```bash
python -m unittest discover -s tests -v
python scripts/package_plugin.py
```

目录：

```text
astrbot_plugin_special_days/
├─ main.py                    插件入口、指令、注入、LLM 工具、WebUI API
├─ core/                      规则、存储、内置数据、提示词
├─ data/                      内置日程 JSON
├─ views/special_days/        WebUI 视图
├─ tests/                     单元测试
├─ scripts/                   数据生成/打包脚本
├─ _conf_schema.json          配置 schema
└─ metadata.yaml              AstrBot 插件元数据
```

## 设计边界

- 只做“日期背景注入”，不做定时祝福、生活日程、天气；
- 不修改消息链、不改 `message_str`，对防抖/上下文/记忆/表情插件友好；
- `on_llm_request(priority=-100)`，排在其他 prompt 注入之后；
- 自定义描述会做长度限制和换行清理，降低提示词注入风险；
- WebUI 全局写接口依赖 AstrBot Dashboard 登录，不做独立账号体系。

## License

[MIT](LICENSE)

## 致谢

- [AstrBot](https://github.com/AstrBotDevs/AstrBot) 插件框架；
- 农历/节假日数据由本地脚本生成，法定节假日以官方发布为准。
