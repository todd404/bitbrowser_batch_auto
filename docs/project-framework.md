# 超多窗口自动化流程项目框架

## 项目目标

本项目用于批量管理比特浏览器窗口，并通过比特浏览器 Local Server 打开窗口、获取 DevTools WebSocket 地址，再由 Playwright 接管页面执行自动化任务。

核心流程：

1. 调用比特浏览器 Local Server 接口创建、查询或打开浏览器窗口。
2. 从 `/browser/open` 返回结果中读取 `ws` DevTools 链接。
3. 使用 Playwright `connect_over_cdp` / `connectOverCDP` 接管浏览器。
4. 按窗口或账号维度执行预设自动化流程，或交给 AI Agent 动态决策。
5. 记录任务状态、运行日志、截图、异常信息，并按策略重试、关闭或回收窗口。

## 参考文档

- 比特浏览器浏览器窗口接口: [bitbrowser-browser-api.md](bitbrowser-browser-api.md)
- 轻量任务调度系统设计: [lightweight-task-scheduler.md](lightweight-task-scheduler.md)
- 自动化流程执行与扩展设计: [automation-flow-design.md](automation-flow-design.md)
- GUI 设计与打包策略: [gui-design.md](gui-design.md)
- 执行计划: [execution-plan.md](execution-plan.md)
- 原始来源: https://doc2.bitbrowser.cn/jiekou/liu-lan-qi-jie-kou.html

## 推荐技术栈

项目目录当前为空，建议优先使用 Python 生态实现第一版：

- Python 3.11+
- Playwright for Python: 通过 CDP 接管比特浏览器已打开窗口
- httpx / aiohttp: 调用比特浏览器 Local Server
- pydantic: 管理配置、任务参数和接口响应模型
- asyncio: 控制大量窗口并发
- SQLite: 保存窗口运行态、任务状态和运行结果，优先保证本机快速启动
- NiceGUI: 本机 GUI，支持 Desktop/Web 双模式
- structlog / logging: 结构化日志
- 可选 AI Agent: OpenAI SDK、LangGraph 或自定义轻量 Planner-Executor

如果团队更熟悉 TypeScript，也可以把同样的模块边界迁移到 Node.js + Playwright，核心架构不变。

第一版不建议默认引入 Postgres、Redis、Celery 等重组件。本项目的早期核心价值是让用户在自己的电脑上快速跑起来：比特浏览器 Local Server + Playwright + SQLite + artifacts 文件夹，已经足够支撑单机多窗口并行。

GUI 第一版推荐 NiceGUI：默认 Desktop Mode 支持双击打开独立窗口，同时保留 Web Mode 和 CLI Mode。UI 只调用 core service，不直接耦合调度器、Playwright 或 SQLite 细节。

## 总体架构

```text
configs / task specs
        |
        v
+-------------------+       +-----------------------+
| Task Scheduler    | ----> | Window Pool Manager   |
+-------------------+       +-----------------------+
        |                            |
        |                            v
        |                    +-----------------------+
        |                    | BitBrowser API Client |
        |                    +-----------------------+
        |                            |
        |                            v
        |                    BitBrowser Local Server
        |
        v
+-------------------+       +-----------------------+
| Automation Runner | ----> | Playwright CDP Client |
+-------------------+       +-----------------------+
        |
        +---- Declarative Flows
        |
        +---- Python Flows
        |
        +---- AI Agent Flows
        |
        v
+-------------------+
| Result & Log Sink |
+-------------------+
```

## 模块划分

### 1. BitBrowser API Client

负责封装比特浏览器 Local Server 的 HTTP 接口。

第一阶段需要封装的接口：

- `POST /health`: 检查 Local Server 是否可用。
- `POST /browser/list`: 分页查询窗口列表。
- `POST /browser/update`: 创建或更新窗口配置。
- `POST /browser/open`: 打开窗口并获取 `ws`、`http`、`pid`、`seq` 等信息。
- `POST /browser/close`: 关闭指定窗口。
- `POST /browser/pids/alive`: 检查指定窗口进程是否仍存活。
- `POST /browser/ports`: 获取已打开窗口的 remote-debugging-port，用于恢复已有连接。
- `POST /browser/cookies/get` / `POST /browser/cookies/set`: 需要账号态迁移或检查时使用。
- `POST /windowbounds` / `POST /windowbounds/flexable`: 大量窗口可视化排列时使用。

封装要求：

- 统一 base URL、超时、重试和错误处理。
- 统一检查 `success` 字段；`success=false` 时抛出带 `msg` 的业务异常。
- 所有请求和响应都保留结构化日志，敏感字段如代理密码、Cookie 需要脱敏。

### 2. Window Pool Manager

负责窗口生命周期和并发容量管理。

核心职责：

- 维护窗口状态机：`idle`、`opening`、`connected`、`running`、`closing`、`error`。
- 控制最大并发窗口数，避免一次性打开过多窗口导致本机资源耗尽。
- 调用 `/browser/open` 时默认传 `queue: true`，降低多线程同时启动导致的并发错误。
- 缓存 `browser_id -> ws/http/pid/seq` 映射。
- 窗口异常退出时，通过 `/browser/pids/alive` 或 Playwright 连接状态确认。
- 关闭窗口后至少等待文档建议的 5 秒，再执行重新打开或删除等操作。

### 3. Playwright CDP Client

负责把比特浏览器窗口交给 Playwright。

典型连接流程：

```python
from playwright.async_api import async_playwright

async with async_playwright() as p:
    browser = await p.chromium.connect_over_cdp(ws_url)
    context = browser.contexts[0]
    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto(task.inputs["url"])
```

注意事项：

- `/browser/open` 返回的 `ws` 是首选连接地址。
- 如果进程已打开但没有缓存 `ws`，可用 `/browser/ports` 拿端口后拼出 CDP 地址，或调用浏览器的 `/json/version` 获取完整 `webSocketDebuggerUrl`。
- 每个窗口只应有一个主控制协程，避免多个任务同时操作同一个 page。
- 对导航、点击、输入、等待元素、下载、弹窗等动作做统一封装，方便 Declarative、Python 和 Agent runner 复用。

### 4. Automation Runner

负责执行具体任务。

建议定义统一任务接口：

```text
TaskInput:
  task_id
  browser_id
  flow_type: declarative | python | agent
  flow
  goal
  inputs
  timeout_seconds

TaskResult:
  task_id
  browser_id
  status: success | failed | cancelled
  started_at
  finished_at
  artifacts
  error
```

Runner 的职责：

- 根据 `flow_type` 分发到 Declarative、Python 或 Agent runner。
- 执行前确认窗口已打开并已被 Playwright 接管。
- 执行中定期上报心跳和当前步骤。
- 出错时保存截图、页面 URL、HTML 片段、控制台日志和异常堆栈。
- 根据错误类型决定是否重试、换窗口、换代理或终止。

### 5. Declarative Flows

Declarative flow 是 JSON/YAML 动作流，适合后续批量重复执行。flow 的生成和重构可以交给 Codex 等外部成熟工具，本项目只负责校验、调度和执行。

建议每个流程包含：

- `metadata`: 名称、版本、适用站点、需要的输入字段。
- `validate_input`: 参数校验。
- `steps`: 具体动作列表，如 `goto`、`click`、`fill`、`wait_for`、`extract_text`、`screenshot`。
- `recover`: 可选的局部恢复逻辑，如重新登录、刷新页面、关闭弹窗。

Declarative flow 示例：

- 打开目标网页并检查登录态。
- 填写表单并提交。
- 搜索关键词并采集结果。
- 导入 Cookie 后刷新页面验证账号状态。

### 6. Python Flows

Python flow 适合复杂判断、循环、分页、数据清洗或调用外部 API。用户或外部 Agent 可以生成 `.py` 文件，系统通过稳定接口调用：

```python
async def run(ctx):
    page = ctx.page
    inputs = ctx.inputs
    await page.goto(inputs["url"])
    return {"ok": True}
```

Python flow 不负责打开比特浏览器窗口，只接收系统提供的 `ctx`。

### 7. AI Agent Execution Flows

AI Agent 适合页面结构变化较大、需要根据观察动态决策的执行任务。

建议采用 Planner-Executor 结构：

- Planner: 根据任务目标、页面观察、历史步骤生成下一步执行动作。
- Executor: 只执行有限动作集合，如 `click`、`type`、`select`、`goto`、`wait`、`extract`、`screenshot`。
- Guardrails: 限制域名、最大步骤数、最大耗时、禁止危险操作。
- Memory: 保存当前任务的页面摘要、已尝试动作、失败原因和关键提取结果。

AI Agent 不应直接获得无限制浏览器控制权。所有动作都通过工具层执行，并记录输入、输出和截图证据。Agent 在本项目里的边界是执行任务，不负责生成或固化 declarative/Python flow。

## 建议目录结构

```text
bit_browser_auto/
  docs/
    bitbrowser-browser-api.md
    project-framework.md
  src/
    bitbrowser_auto/
      __init__.py
      config.py
      bitbrowser/
        client.py
        models.py
        errors.py
      browser/
        pool.py
        cdp.py
        state.py
      runner/
        scheduler.py
        task.py
        result.py
      flows/
        declarative/
          open_and_check.yaml
        py/
          custom_flow.py
        agent/
          planner.py
          executor.py
          tools.py
      storage/
        db.py
        repositories.py
      observability/
        logging.py
        artifacts.py
      ui/
        app.py
        pages/
  configs/
    app.example.yaml
    tasks.example.yaml
  tests/
```

## 配置设计

建议把运行配置和任务配置分开。

运行配置示例：

```yaml
bitbrowser:
  base_url: "http://127.0.0.1:54345"
  request_timeout_seconds: 30

runtime:
  max_open_windows: 20
  open_queue: true
  task_timeout_seconds: 300
  close_wait_seconds: 5
  artifact_dir: "./artifacts"

playwright:
  default_navigation_timeout_ms: 60000
  default_action_timeout_ms: 30000
```

任务配置示例：

```yaml
tasks:
  - id: "demo-001"
    browser_id: "3baa6e990fee4e839c72722c8dc18019"
    flow_type: "declarative"
    flow: "open_and_check"
    inputs:
      url: "https://example.com"
```

## 标准执行流程

1. 启动程序，加载配置。
2. 调用 `/health` 检查比特浏览器 Local Server。
3. 加载任务列表，按 `browser_id` 去重并建立窗口计划。
4. Window Pool Manager 按并发限制打开窗口。
5. 调用 `/browser/open`，保存返回的 `ws`、`pid`、`seq`。
6. Playwright 使用 `ws` 接管浏览器。
7. Automation Runner 执行 Declarative、Python 或 Agent flow。
8. 每个任务保存结构化结果和 artifacts。
9. 根据策略决定保留窗口、关闭窗口或继续执行下一个任务。
10. 程序退出前优雅关闭 Playwright 连接，并按配置关闭比特浏览器窗口。

## 并发与稳定性策略

- 打开窗口使用队列模式，避免 Local Server 并发启动冲突。
- 调度层限制同时 `opening` 和 `running` 的数量。
- 一个 `browser_id` 同一时间只允许一个任务占用。
- 每个动作设置超时，禁止任务无限挂起。
- 对可恢复错误做有限次数重试；对账号、权限、验证码等业务错误直接标记失败。
- 定期巡检 `pid` 和 Playwright 连接状态，发现窗口死亡后释放资源。
- 保存失败现场，优先让后续分析能复现问题，而不是盲目重试。

## 数据模型草案

轻量第一版以 SQLite 为默认存储。详细调度模型见 [lightweight-task-scheduler.md](lightweight-task-scheduler.md)。

```text
browser_windows
  id
  seq
  name
  group_id
  last_ws
  last_pid
  status
  updated_at

tasks
  id
  browser_id
  flow_type
  flow
  goal
  inputs_json
  status
  retry_count
  created_at
  started_at
  finished_at

task_runs
  id
  task_id
  browser_id
  status
  current_step
  error_type
  error_message
  artifact_dir
  started_at
  finished_at
```

## 第一阶段里程碑

1. 完成 `BitBrowserClient`，覆盖 `/health`、`/browser/list`、`/browser/open`、`/browser/close`。
2. 完成 Playwright CDP 连接样例，能打开一个指定窗口并访问目标 URL。
3. 完成最小任务 Runner，支持从 YAML 读取任务并串行执行。
4. 增加窗口池和并发限制，支持同时运行多个窗口。
5. 增加 artifacts：截图、日志、任务结果 JSON。
6. 增加第一个 Declarative flow。
7. 增加 Python flow 加载能力。
8. 在前两类 flow 稳定后，再按需接入 AI Agent 执行层。

## 风险点

- 本机 CPU、内存和网络代理质量会直接限制可同时运行窗口数量。
- 比特浏览器窗口的 `opened` 状态可能因网络或进程异常不完全准确，需要结合 `/browser/pids/alive` 校验。
- Playwright 通过 CDP 接管的是已有浏览器，默认 context/page 结构可能与普通 `launch` 不同。
- AI Agent 容易产生不可控动作，必须限制工具集、域名、步骤数和超时时间。
- Cookie、代理账号密码、平台账号密码都属于敏感信息，日志和 artifacts 需要脱敏或加密保存。
