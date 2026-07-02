# 自动化流程执行与扩展设计

## 背景

本项目只负责把已经准备好的自动化流程稳定执行起来：调度比特浏览器窗口、通过 Playwright CDP 接管页面、运行 flow、保存状态和 artifacts。

flow 的编写、整理、重构和“固化”不在本项目内造轮子。用户完全可以用 Codex 或其他成熟 Agent 阅读本文档、查看 artifacts/trace，然后直接生成或修改 declarative YAML / Python flow。项目侧只提供清晰的执行契约、示例、校验器和运行结果。

当流程出现复杂判断、循环、异常分支时，可以升级为 Python flow。更开放的动态任务如果将来需要 Agent，也只作为一种执行 runner 接入，不承担 flow authoring。

所以系统需要从第一天就区分“任务调度”和“自动化实现”。调度器只负责分配窗口、打开浏览器、接管 Playwright、记录结果；具体怎么操作页面，由 flow 类型决定。

## 三层 Flow 模型

```text
Level 1: Declarative Flow
  JSON/YAML 动作流，适合复用和批量执行；支持核心语义动作，也提供 Playwright passthrough

Level 2: Python Flow
  用户或外部 Agent 生成的 .py 文件，适合判断、循环、复杂提取

Level 3: Agent Execution Flow
  预留给外部或内置 Agent 的执行入口；Agent 只执行任务，不负责固化 flow
```

三层共用同一个调度器、窗口池、BitBrowser API Client 和 Playwright CDP 连接。不同点只在 Runner 如何执行 flow。

## Level 1: JSON/YAML 动作流

适用场景：

- 打开 URL。
- 点击固定按钮。
- 输入文本。
- 等待元素出现。
- 提取文本。
- 保存截图。
- 简单条件判断。
- 需要保留 Playwright 原生能力的动作。

示例：

```yaml
name: "open_and_search"
version: 1
start_url: "https://example.com"
inputs:
  keyword:
    type: string
    required: true
steps:
  - action: goto
    url: "{{ start_url }}"

  - action: wait_for
    selector: "input[name='q']"
    timeout_ms: 10000

  - action: fill
    selector: "input[name='q']"
    value: "{{ inputs.keyword }}"

  - action: click
    selector: "button[type='submit']"

  - action: wait_for
    selector: ".result"
    timeout_ms: 30000

  - action: extract_text
    selector: ".result"
    save_as: "result_text"

  - action: screenshot
    name: "final"
```

动作集合分两层。第一层是系统建议优先使用的核心语义动作：

```text
goto
click
fill
press
wait_for
wait_for_url
extract_text
extract_attr
screenshot
assert_text
```

第二层是 Playwright passthrough，用于开放 Playwright 的常用能力，方便 Codex 这类成熟 Agent 在编写或修改 flow 时表达更细的操作。

```yaml
- action: playwright
  target: page
  method: locator
  args:
    - "button:has-text('提交')"
  chain:
    - method: click
      kwargs:
        timeout: 30000
```

当前实现已支持受 allowlist 限制的 passthrough。示例：

```yaml
name: "open_and_get_title"
version: 1
inputs:
  url:
    type: string
    required: true
steps:
  - action: goto
    url: "{{ inputs.url }}"
  - action: playwright
    target: page
    method: title
    save_as: title
```

执行前可先校验：

```bash
python -m bitbrowser_auto validate-flow open_and_get_title
```

passthrough 设计原则：

- 支持 `page`、`context`、`locator`、`keyboard`、`mouse` 等常用 target。
- 支持 `method`、`args`、`kwargs`、`chain`，让 flow 可以表达大多数 Playwright 调用。
- Runner 只执行 allowlist 中的 Playwright 方法，避免 `evaluate`、文件系统、下载路径等能力被无边界使用。
- 对 passthrough 动作也记录 trace，包含 method、selector、参数摘要、耗时、错误和截图策略。

这样 JSON/YAML 不需要复刻完整 Playwright API，但仍然给外部工具足够大的表达空间。复杂到需要任意 Python 逻辑时，再升级到 Python flow。

### 简单条件

可以支持有限的 `if_visible` / `if_text`：

```yaml
- action: if_visible
  selector: ".login-dialog"
  then:
    - action: fill
      selector: "#username"
      value: "{{ inputs.username }}"
    - action: fill
      selector: "#password"
      value: "{{ inputs.password }}"
    - action: click
      selector: "button.login"
```

如果条件开始变多，或者出现循环、分页、重试分支，就应该升级到 Python flow。

## Flow Authoring 边界

本项目不内置 flow authoring skill，也不提供 `trace-to-flow` 这类自动固化命令。原因很简单：成熟的 Codex 或其他通用 Agent 已经更适合做代码/配置生成、重构和审阅，本项目不需要重复造轮子。

项目侧只维护三类稳定输入：

- flow schema 和示例。
- `validate-flow` 校验命令。
- 运行后的 `run.json`、`trace.json`、截图和错误现场。

外部 Agent 可以读取这些资料后直接生成或修改 `flows/declarative/*.yaml`、`flows/py/*.py`。生成后的 flow 通过本项目的 validator 和 runner 验证即可。

## Level 2: Python Flow

适用场景：

- 多层判断。
- 循环翻页。
- 根据页面内容动态决定下一步。
- 复杂数据清洗。
- 调用外部 API。
- 需要复用函数和模块。

Python flow 的接口必须稳定、简单：

```python
async def run(ctx):
    page = ctx.page
    inputs = ctx.inputs
    artifacts = ctx.artifacts

    await page.goto(inputs["url"])
    await page.screenshot(path=artifacts.path("final.png"))
    return {"ok": True, "url": page.url}
```

`ctx` 由系统提供，不让 flow 自己打开比特浏览器窗口：

```text
ctx.page
ctx.context
ctx.browser
ctx.task
ctx.inputs
ctx.logger
ctx.artifacts
ctx.bitbrowser
```

这样可以保持边界清晰：调度器负责浏览器生命周期，Python flow 只负责页面自动化。

当前实现包含两个示例：

- `flows/py/paginate_titles.py`: 从 `inputs.url` 或 `inputs.urls` 打开页面，提取标题并保存截图。
- `flows/py/conditional_login.py`: 按输入 selector 判断登录框是否出现，出现时填写账号密码并提交。

运行示例：

```bash
python -m bitbrowser_auto run-one \
  --browser-id <browser-id> \
  --flow-type python \
  --flow paginate_titles \
  --url https://example.com
```

### Python Flow 文件组织

```text
flows/
  py/
    login_check.py
    scrape_orders.py
  declarative/
    open_and_search.yaml
```

任务里引用：

```yaml
tasks:
  - id: "orders-001"
    browser_id: "browser-id"
    flow_type: "python"
    flow: "scrape_orders"
    inputs:
      url: "https://example.com/orders"
```

Runner 根据 `flow_type=python` 加载 `flows/py/scrape_orders.py`，调用里面的 `run(ctx)`。

### 安全边界

Python flow 本质上是本机代码，能力很强。第一版可以明确假设：用户只运行自己信任的 flow。后续如果要支持分享市场或第三方 flow，再考虑沙箱、权限声明、签名和隔离执行。

## Level 3: Agent Execution Flow

适用场景：

- 目标描述开放，页面结构经常变化。
- 用户无法或不想提前写死流程。
- 需要 Agent 看页面、推理、操作、验证、修正。
- 超级复杂自动化，需要在运行时处理大量未知分支。

第一阶段不实现具体 Agent 技术。后续如接入 Agent，也只作为执行 runner：

```yaml
tasks:
  - id: "agent-001"
    browser_id: "browser-id"
    flow_type: "agent"
    goal: "登录后台，下载昨天的订单报表"
    inputs:
      url: "https://example.com/admin"
```

Agent Runner 仍然拿到相同的 `ctx`，但只能通过系统定义的动作工具操作页面：

```text
observe
click
fill
press
goto
wait
extract
screenshot
finish
fail
```

这个限制很重要：Agent 不应该绕过系统直接随意操作 Playwright。所有动作都要被记录，方便排障、审计和人工复盘。

## Trace 的定位

系统会收集 action trace，但 trace 的目的不是在本项目内自动生成 flow，而是记录执行过程：

```json
{
  "task_id": "demo-001",
  "browser_id": "browser-id",
  "started_at": "2026-07-01T15:00:00+08:00",
  "steps": [
    {
      "action": "goto",
      "url": "https://example.com",
      "ok": true
    },
    {
      "action": "fill",
      "selector": "input[name='q']",
      "value_ref": "inputs.keyword",
      "ok": true
    },
    {
      "action": "click",
      "selector": "button[type='submit']",
      "ok": true
    }
  ]
}
```

如果需要根据 trace 生成新的 flow，交给 Codex 等外部工具处理。项目只保证 trace 足够清晰、validator 足够严格、runner 执行结果可复现。

## 任务配置统一格式

为了兼容三层 flow，任务字段建议这样设计：

```yaml
tasks:
  - id: "task-001"
    browser_id: "browser-id"
    flow_type: "declarative"
    flow: "open_and_search"
    inputs:
      keyword: "playwright"

  - id: "task-002"
    browser_id: "browser-id-2"
    flow_type: "python"
    flow: "scrape_orders"
    inputs:
      url: "https://example.com/orders"

  - id: "task-003"
    browser_id: "browser-id-3"
    flow_type: "agent"
    goal: "下载昨天的订单报表"
    inputs:
      url: "https://example.com/admin"
```

数据库里也应使用通用字段：

```text
flow_type
flow
goal
inputs_json
```

不要把 schema 绑死在某一种 flow 上。

## Runner 分发接口

Runner 只关心统一入口：

```python
async def run_automation(ctx):
    if ctx.task.flow_type == "declarative":
        return await declarative_runner.run(ctx)
    if ctx.task.flow_type == "python":
        return await python_runner.run(ctx)
    if ctx.task.flow_type == "agent":
        return await agent_runner.run(ctx)
    raise ValueError(f"unknown flow_type: {ctx.task.flow_type}")
```

每个 runner 都必须返回统一结果：

```json
{
  "status": "success",
  "outputs": {},
  "artifacts": [],
  "trace_path": "artifacts/task-id/trace.json"
}
```

## Artifacts 与 Trace

为了支持排障、审计和外部工具分析，第一版就应该记录 trace，即使只实现 declarative 和 Python。

每个任务目录：

```text
artifacts/task-id/
  run.json
  trace.json
  screenshots/
    step-001.png
    final.png
  error.txt
```

trace 记录动作层级，不记录全部 DOM。截图按配置保存，避免磁盘暴涨：

```yaml
trace:
  enabled: true
  screenshot_policy: "on_error"
```

可选值：

```text
off
on_error
every_step
```

当前 trace 会记录：

- action / flow 名称。
- selector、target、method、args/kwargs/chain 摘要。
- 当前 URL。
- 耗时。
- 成功/失败状态。
- 错误消息。
- 截图引用或截图失败原因。

敏感字段如 password、token、cookie、secret 会在摘要里脱敏。

## 第一版要做和不要做

第一版要做：

- 任务 schema 支持 `flow_type`、`flow`、`goal`、`inputs`。
- Runner 分发层支持 `declarative` 和 `python`。
- 预留 `agent` 类型，遇到时给出清晰错误：当前版本未启用。
- 每个任务保存 `trace.json`。
- Declarative flow 支持核心语义动作和 Playwright passthrough。
- 提供 flow validator，至少检查 schema、模板变量、动作 allowlist 和必填字段。
- Python flow 支持 `async def run(ctx)`。

第一版不要做：

- 不做复杂可视化流程编辑器。
- 不做完整 Python 沙箱。
- 不做 Agent 技术选型绑定。
- 不做 `trace-to-flow`、flow authoring skill 或内置固化工具。
- 不把 YAML 动作流扩展成复杂编程语言；复杂控制流交给 Python flow。
- 不为了未来 Agent 改重调度器。

## 设计原则

- 调度器稳定，不关心页面细节。
- Runner 可插拔，但接口统一。
- Declarative flow 既要可读、可复用，也要通过 Playwright passthrough 给外部工具足够表达力。
- Python flow 承接复杂逻辑。
- Agent flow 只承接开放任务的执行。
- Trace 的职责是诊断、审计和复盘，不承担项目内自动固化。
