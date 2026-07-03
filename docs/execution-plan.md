# 执行计划

## 原则

第一版目标不是做完整平台，而是做一个本机可快速启动、可验证、可扩展的最小系统。

优先级：

1. 先跑通真实链路：比特浏览器窗口 -> ws -> Playwright -> flow。
2. 再做轻量调度：SQLite、窗口槽位、并发控制、失败恢复。
3. 再做可执行 flow：Declarative YAML/JSON、validator、trace 可观测性。
4. 再做 Python flow：承接复杂判断和循环。
5. 增加 NiceGUI 双模式 UI，让普通用户能双击打开。
6. Agent 只作为执行 runner 预留，不做 flow authoring 或固化工具。

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

目标：把已验证的手工实验沉淀为可复用代码。

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
- FlowValidator：`validate-flow`
- Declarative passthrough：
  - `action: playwright`
  - target allowlist: `page`、`context`、`locator`、`keyboard`、`mouse`
  - method allowlist 已覆盖常见导航、locator、键盘、鼠标动作
- Trace 可观测性：
  - 每次任务写入 `trace.json`
  - step 记录 action、selector/method、参数摘要、URL、耗时、成功/失败
  - 支持 `trace.screenshot_policy`: `off` / `on_error` / `every_step`
  - 失败时仍写入 `trace.json`、`error.txt` 和可用截图引用
- Python Flow Runner：
  - 加载本地 `flows/py/*.py`
  - 校验 `async def run(ctx)` 契约
  - Python flow 共用 `ctx.page`、`ctx.inputs`、`ctx.artifacts`
  - 示例：`paginate_titles`、`conditional_login`
- NiceGUI UI：
  - CLI 入口：`bitbrowser_auto ui`
  - Web 模式：`bitbrowser_auto ui --web`
  - 页面：Dashboard、Browser Windows、Tasks、Runs、Flows、Settings
  - Dashboard 可查看任务状态统计、Local Server 健康检查、最近错误
  - Browser Windows 可查看窗口列表并打开/关闭指定 `browser_id`
  - Tasks 可导入任务、筛选状态、启动/停止本轮调度、重置 running
  - Runs 可查看运行历史、`run.json`、`trace.json` 和截图 artifact
  - Flows 可列出 declarative/Python flow，并校验 declarative flow
  - Settings 可查看当前配置摘要

本机已验证命令：

```bash
.venv/bin/python -m bitbrowser_auto --help
.venv/bin/python -m bitbrowser_auto ui --help
.venv/bin/python -m bitbrowser_auto validate-flow open_and_check
.venv/bin/python -m bitbrowser_auto validate-flow open_and_get_title
.venv/bin/python -m bitbrowser_auto check
.venv/bin/python -m bitbrowser_auto check \
  --browser-id 2357d261d2d2472985d52e7916d6a580 \
  --url https://example.com
.venv/bin/python -m bitbrowser_auto run-one \
  --browser-id 2357d261d2d2472985d52e7916d6a580 \
  --task-id demo-001 \
  --flow open_and_check \
  --url https://example.com
.venv/bin/python -m bitbrowser_auto run-one \
  --browser-id 2357d261d2d2472985d52e7916d6a580 \
  --task-id passthrough-demo-001 \
  --flow open_and_get_title \
  --url https://example.com
.venv/bin/python -m bitbrowser_auto run-one \
  --browser-id 2357d261d2d2472985d52e7916d6a580 \
  --task-id python-demo-002 \
  --flow-type python \
  --flow paginate_titles \
  --url https://example.com
.venv/bin/python -m bitbrowser_auto import-tasks configs/tasks.example.yaml --replace
.venv/bin/python -m bitbrowser_auto list-tasks
.venv/bin/python -m bitbrowser_auto run --config /tmp/phase8-app.yaml --tasks /tmp/phase8-tasks.yaml --once --replace
.venv/bin/python -m bitbrowser_auto ui --web --host 127.0.0.1 --port 8765
.venv/bin/python -m unittest discover -s tests
```

真实链路验证结果：

- Local Server `http://127.0.0.1:54345` 健康检查成功。
- `/browser/list` 返回 1 个窗口。
- `/browser/open` 获取到最新 `ws`。
- Playwright `connect_over_cdp(ws)` 成功访问 `https://example.com/`。
- 已生成截图、`run.json`、`trace.json`。
- `open_and_get_title` passthrough flow 成功通过 `page.title()` 提取 `Example Domain`。
- `paginate_titles` Python flow 成功通过 `ctx.page`、`ctx.inputs`、`ctx.artifacts` 访问页面、提取 title、保存截图。
- Scheduler 路径也能执行 `flow_type: python` 任务。
- Web UI 已用本机 Microsoft Edge 验证 websocket、页面导航、任务页、窗口页、运行页、flow 页和 Dashboard 健康检查。
- 比特浏览器窗口可打开 UI 页面并截图；若具体比特窗口配置拦截 localhost websocket，UI 交互验收应使用普通浏览器。
- 当前单元测试：15 个测试通过。

下一步建议：

1. Phase 9 的技术版 UI 已完成，但需要进入普通用户可用性改造，详见 [GUI 设计与打包策略](gui-design.md)。
2. 优先实现“新建批量运行”向导：选择 1 个 flow，选择多个窗口，填写参数，生成多条底层 task 并运行。
3. 再实现批次化结果页和失败项重跑，让用户按一次批量运行复盘，而不是只看底层 task/run 表。
4. 增加定时计划：一次性、每天、每周、间隔运行，并处理错过时间和上次未结束的策略。
5. 完善 Scheduler 失败重试的 trace/run 记录和 browser_runtime 的 ws/pid 回写。
6. 扩展单元测试覆盖 Scheduler 并发、失败重试、批量生成任务和计划触发逻辑。
7. 后续做 PyInstaller `onedir` 打包和 Desktop/native 模式实机验证；flow 编写和重构仍交给 Codex 等外部成熟工具。

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

目标：让 YAML 能表达更多 Playwright 能力，不被核心动作限制。

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

## Phase 7: Trace 与可观测性

目标：记录任务执行过程，方便排障、审计和外部工具分析。

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

验收标准：

- 每次任务运行都有 trace。
- trace 能对应到 `run.json` 和截图。
- trace 只记录执行证据，不承担项目内自动固化。
- 失败任务也能生成 `trace.json` 和 `error.txt`。

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
- Python flow 也能写入基础 trace。

## Phase 9: NiceGUI 双模式 UI

目标：提供普通用户可用的 GUI，同时保留 Web 和 CLI 模式。

当前状态：双模式技术底座已完成，但页面仍偏“命令行工具的 GUI 版本”。Phase 9 后续重点改为可用性：让普通用户围绕“批量运行”和“定时计划”完成工作，而不是围绕底层任务文件和 `browser_id` 操作。

交付物：

- `bitbrowser_auto ui`
- `bitbrowser_auto ui --web`
- NiceGUI 技术页面：
  - Dashboard
  - Browser Windows
  - Tasks
  - Runs
  - Flows
  - Settings
- 普通用户页面：
  - 运行台
  - 新建运行
  - 计划任务
  - 运行结果
  - 窗口
  - 流程库
  - 设置/诊断
- 批量运行能力：
  - 选择一个 flow。
  - 选择多个比特浏览器窗口。
  - 填写所有窗口共用参数。
  - 填写每个窗口不同参数。
  - 生成多条底层 task 并启动调度。
- 定时计划能力：
  - 一次性运行。
  - 每天运行。
  - 每周运行。
  - 每隔 N 分钟或 N 小时运行。
  - 支持错过时间和上次未结束的处理策略。
- 批次化结果：
  - 按批次查看运行进度和历史结果。
  - 查看每个窗口的状态、截图、输出和错误。
  - 一键重跑失败窗口。
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
- UI 能不手填 `browser_id`，通过名称、分组、序号选择多个窗口。
- UI 能让多个窗口执行同一个 flow。
- UI 能为 flow 自动生成参数表单。
- UI 能创建一次性和重复定时计划。
- UI 能按批次查看任务状态、运行日志、截图和错误。
- UI 能一键重跑失败窗口。
- CLI 命令仍然可用。

建议拆分：

- Phase 9A：用户视角壳层，重组导航和首屏。
- Phase 9B：批量运行向导。
- Phase 9C：运行结果批次化。
- Phase 9D：定时计划。
- Phase 9E：打包和桌面体验。

## Phase 10: Agent Flow 执行接口

目标：不实现 flow authoring；只预留 Agent 作为执行 runner 的接口。

交付物：

- `flow_type: agent` schema。
- `AgentRunner` stub 或外部 runner adapter。
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
- Agent runner 如后续启用，只负责执行任务和返回结果，不生成或固化 flow。

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
