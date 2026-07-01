# 执行计划

## 原则

第一版目标不是做完整平台，而是做一个本机可快速启动、可验证、可扩展的最小系统。

优先级：

1. 先跑通真实链路：比特浏览器窗口 -> ws -> Playwright -> flow。
2. 再做轻量调度：SQLite、窗口槽位、并发控制、失败恢复。
3. 再做可固化 flow：Declarative YAML/JSON、trace、validator。
4. 再做 Python flow：承接复杂判断和循环。
5. 增加 NiceGUI 双模式 UI，让普通用户能双击打开。
6. 最后准备 Agent/Skill 扩展，不阻塞第一版闭环。

## Phase 0: 项目初始化

目标：建立可运行的 Python 项目骨架。

交付物：

- `pyproject.toml`
- `src/bitbrowser_auto/`
- `configs/app.example.yaml`
- `configs/tasks.example.yaml`
- `requirements` 或依赖声明
- CLI 入口：`python -m bitbrowser_auto`

验收标准：

- 能运行 `python -m bitbrowser_auto --help`。
- 能运行现有 CDP 验证脚本或等价 `check` 命令。

## Phase 1: BitBrowser Client + CDP 接管

目标：把已验证的手工实验固化为代码。

交付物：

- `BitBrowserClient`
  - `/health`
  - `/browser/list`
  - `/browser/open`
  - `/browser/close`
  - `/browser/pids/alive`
- `PlaywrightConnector`
- CLI: `check`

验收标准：

- `check` 能检查 Local Server。
- `check` 能列出窗口。
- 给定 `browser_id` 后能打开窗口，获取最新 `ws`。
- Playwright 能 `connect_over_cdp(ws)`，访问 `https://example.com`，保存截图。

## Phase 2: 最小 Runner

目标：支持单个任务完整执行。

交付物：

- `Task` 数据模型。
- `RunContext`
  - `page`
  - `context`
  - `browser`
  - `task`
  - `inputs`
  - `artifacts`
  - `logger`
- `ArtifactManager`
- 一个内置 `open_and_check` declarative flow。
- CLI: `run-one --browser-id ... --flow ...`

验收标准：

- 单个任务能打开指定比特窗口。
- 能接管 Playwright 并执行 flow。
- 成功时生成 `run.json` 和截图。
- 失败时生成 `error.txt` 和失败截图。

## Phase 3: SQLite Storage

目标：任务状态可持久化、可恢复。

交付物：

- `data/scheduler.sqlite3`
- 表：
  - `tasks`
  - `task_runs`
  - `browser_runtime`
- `import-tasks`
- `list-tasks`
- `reset-running`

验收标准：

- 能从 YAML/CSV 导入任务。
- 任务状态能从 `pending` -> `running` -> `success/failed`。
- 程序中断后重新启动，不会丢失任务状态。

## Phase 4: 轻量 Scheduler

目标：实现多窗口并发。

交付物：

- `Scheduler`
- `WindowSlotPool`
- 配置：
  - `max_concurrent_windows`
  - `task_timeout_seconds`
  - `max_retries`
  - `close_window_after_task`
- CLI: `run --tasks configs/tasks.yaml`

验收标准：

- 能并发运行多个不同 `browser_id` 的任务。
- 同一个 `browser_id` 同一时间不会被两个任务占用。
- 任务失败可按 `max_retries` 重试。
- 关闭窗口时遵守 `close_wait_seconds`。

## 当前实现快照

已落地第一版本机骨架：

- Python 包入口：`python -m bitbrowser_auto` / `bitbrowser-auto`
- 配置示例：`configs/app.example.yaml`
- 任务示例：`configs/tasks.example.yaml`
- 内置 declarative flow：`flows/declarative/open_and_check.yaml`
- BitBrowser API Client：
  - `/health`
  - `/browser/list`
  - `/browser/open`
  - `/browser/close`
  - `/browser/pids/alive`
  - `/browser/ports`
- Playwright CDP 接管：`check --browser-id ...`
- 最小 Runner：`run-one`
- SQLite Storage：
  - `tasks`
  - `task_runs`
  - `browser_runtime`
- 轻量 Scheduler：`run --tasks ... --once`

本机已验证命令：

```bash
.venv/bin/python -m bitbrowser_auto --help
.venv/bin/python -m bitbrowser_auto check
.venv/bin/python -m bitbrowser_auto check \
  --browser-id 2357d261d2d2472985d52e7916d6a580 \
  --url https://example.com
.venv/bin/python -m bitbrowser_auto run-one \
  --browser-id 2357d261d2d2472985d52e7916d6a580 \
  --task-id demo-001 \
  --flow open_and_check \
  --url https://example.com
.venv/bin/python -m bitbrowser_auto import-tasks configs/tasks.example.yaml --replace
.venv/bin/python -m bitbrowser_auto list-tasks
```

真实链路验证结果：

- Local Server `http://127.0.0.1:54345` 健康检查成功。
- `/browser/list` 返回 1 个窗口。
- `/browser/open` 获取到最新 `ws`。
- Playwright `connect_over_cdp(ws)` 成功访问 `https://example.com/`。
- 已生成截图、`run.json`、`trace.json`。

下一步建议：

1. 补 FlowValidator，先校验 declarative flow 的 action、必填字段和模板变量。
2. 扩展 declarative action：`playwright` passthrough、`if_text`。
3. 完善 Scheduler 失败重试的 trace/run 记录和 browser_runtime 的 ws/pid 回写。
4. 加入 Python flow 的示例任务和回归验证。

## Phase 5: Declarative Flow Runner

目标：让 YAML/JSON 动作流成为第一类自动化产物。

交付物：

- `DeclarativeRunner`
- 核心动作：
  - `goto`
  - `click`
  - `fill`
  - `press`
  - `wait_for`
  - `wait_for_url`
  - `extract_text`
  - `extract_attr`
  - `screenshot`
  - `assert_text`
- 简单条件：
  - `if_visible`
  - `if_text`
- `FlowValidator`

验收标准：

- 能执行 `flows/declarative/*.yaml`。
- validator 能发现缺字段、未知 action、模板变量不存在。
- 任务 outputs 能写入 `run.json`。

## Phase 6: Playwright Passthrough

目标：让成熟 Agent 可以表达更多 Playwright 能力，不被核心动作限制。

交付物：

- `action: playwright`
- target allowlist：
  - `page`
  - `context`
  - `locator`
  - `keyboard`
  - `mouse`
- method allowlist。
- `method + args + kwargs + chain` 执行器。

验收标准：

- YAML 能表达常见 locator 链式调用。
- 禁止未允许的危险方法。
- passthrough 动作也能写入 trace。

## Phase 7: Trace 与固化

目标：支持“Agent 跑通 -> 固化 flow”的闭环。

交付物：

- `trace.json`
- trace 记录：
  - action
  - selector/method
  - args 摘要
  - URL
  - 耗时
  - 成功/失败
  - screenshot 引用
- CLI: `trace-to-flow`

验收标准：

- 每次任务运行都有 trace。
- `trace-to-flow` 能生成可编辑 YAML 初稿。
- 可把具体值替换成 `inputs.xxx`。

## Phase 8: Python Flow Runner

目标：承接复杂判断、loop、分页、外部 API 等逻辑。

交付物：

- `PythonRunner`
- 约定 `async def run(ctx)`
- `flows/py/*.py`
- 示例：
  - 翻页抓取
  - 条件登录

验收标准：

- 能加载本地 Python flow。
- Python flow 不需要也不能自己打开比特窗口。
- Python flow 能使用 `ctx.page`、`ctx.inputs`、`ctx.artifacts`。

## Phase 9: NiceGUI 双模式 UI

目标：提供普通用户可用的 GUI，同时保留 Web 和 CLI 模式。

交付物：

- `bitbrowser_auto ui`
- `bitbrowser_auto ui --web`
- NiceGUI 页面：
  - Dashboard
  - Browser Windows
  - Tasks
  - Runs
  - Flows
  - Settings
- UI 配置：
  - `default_mode`
  - `host`
  - `port`
  - `window_width`
  - `window_height`
- 打包草案：
  - PyInstaller `onedir`
  - Desktop Mode 默认入口
  - Web Mode 命令行入口

验收标准：

- Desktop Mode 能打开独立窗口。
- Web Mode 能用浏览器访问同一套 UI。
- UI 能查看比特窗口列表。
- UI 能导入任务并启动/停止调度。
- UI 能查看任务状态、运行日志、截图和错误。
- CLI 命令仍然可用。

## Phase 10: Flow Authoring Skill

目标：给 Codex 等外部 Agent 一套生成固化 flow 的指导。

交付物：

- `bitbrowser-flow-author` skill 草案。
- `SKILL.md`
- references：
  - `declarative-flow-schema.md`
  - `playwright-passthrough.md`
  - `python-flow-contract.md`
- `validate_flow.py`

验收标准：

- Agent 能根据自然语言目标或 trace 生成 declarative flow。
- Agent 知道何时升级成 Python flow。
- 生成后能通过 `validate_flow.py` 基础校验。

## Phase 11: Agent Flow 预留接口

目标：不实现具体 Agent 技术，但接口可接入。

交付物：

- `flow_type: agent` schema。
- `AgentRunner` stub。
- 清晰错误提示：当前版本未启用 Agent runner。
- 工具接口草案：
  - `observe`
  - `click`
  - `fill`
  - `goto`
  - `extract`
  - `screenshot`
  - `finish`
  - `fail`

验收标准：

- 配置中出现 `flow_type: agent` 时不会破坏调度器。
- 用户能看到明确提示，而不是异常堆栈。

## 推荐实现顺序

```text
Phase 0
  -> Phase 1
  -> Phase 2
  -> Phase 3
  -> Phase 4
  -> Phase 5
  -> Phase 6
  -> Phase 7
  -> Phase 8
  -> Phase 9
  -> Phase 10
  -> Phase 11
```

如果想更快看到价值，可以先跳过 Phase 6、7、10：

```text
Phase 0 -> 1 -> 2 -> 3 -> 4 -> 5 -> 8 -> 9
```

这样可以先获得“多窗口并行 + YAML flow + Python flow + GUI”的可用系统。

## 第一版完成定义

第一版完成时应满足：

- 用户可以配置多个比特浏览器窗口。
- 用户可以导入任务。
- 系统可以按并发限制运行任务。
- 每个任务可以执行 declarative 或 Python flow。
- 每个任务有状态、日志、截图和 trace。
- 用户可以通过 GUI Desktop Mode 双击打开应用。
- 开发者可以通过 Web Mode 或 CLI 使用同一套能力。
- 程序中断后可以恢复。
- 不依赖 Postgres、Redis 或远程服务。
