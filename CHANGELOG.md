# Changelog

## 0.8.0

- 插件中文展示名：「今天是什么日子」；
- 视图迁到 AstrBot 推荐的 `views/` 目录；
- 修复视图内联脚本早于 bridge SDK 执行导致“请从插件管理页打开”的问题；
- Web API 改用 `astrbot.api.web` 标准请求/响应 helper；
- 补齐 metadata 标准字段、LICENSE、requirements、.gitignore；
- 建立 GitHub 仓库并推送。

## 0.7.0

- 新增 WebUI 全局日程管理页；
- Web API state/create/update/delete/export/import；
- 打包脚本；
- 指令导入/导出。

## 0.6.0

- 指令 `/特殊日 导出`、`/特殊日 导入`；
- SQLite `export_scope` / `import_days`。

## 0.5.1

- `enabled` 改为可选更新；
- 指令写入审计；
- `require_tool_confirm`。

## 0.5.0

- LLM 工具 `special_day_manage`；
- 全局管理员权限与审计日志。

## 0.4.0

- 纪念日压制玩梗日；
- 自定义同名覆盖内置；
- 截断保留 solemn。

## 0.3.0

- 第 N 个星期几、复活节；
- 农历/法定节假日数据。

## 0.1.0

- 初始版本：公历、每周几、自定义日程和提示词注入。
