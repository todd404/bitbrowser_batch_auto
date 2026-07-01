# 自动化流程固化与扩展设计

## 背景

用户不一定一开始就会写 Playwright 脚本。更自然的路径是：

1. 用户用自己熟悉的 Agent，通过自然语言操控 Playwright。
2. 用户看着 Agent 把流程跑通。
3. 系统把这次成功流程固化成 JSON/YAML。
4. 后续调度系统反复执行这份固化流程。

当流程出现复杂判断、循环、异常分支时，可以升级为 Python flow。更复杂、更开放的自动化，则保留给系统内置 Agent 接管。

所以系统需要从第一天就区分“任务调度”和“自动化实现”。调度器只负责分配窗口、打开浏览器、接管 Playwright、记录结果；具体怎么操作页面，由 flow 类型决定。

## 三层 Flow 模型

```text
Level 1: Declarative Flow
  JSON/YAML 动作流，适合固化和复用；支持核心语义动作，也提供 Playwright passthrough

Level 2: Python Flow
  用户或 Agent 生成的 .py 文件，适合判断、循环、复杂提取

Level 3: Managed Agent Flow
  系统自带 Agent 接管，适合开放式、复杂、多分支任务
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

第二层是 Playwright passthrough，用于开放 Playwright 的大部分能力，方便 Codex 这类成熟 Agent 在固化 flow 时表达更细的操作。

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

passthrough 设计原则：

- 支持 `page`、`context`、`locator`、`keyboard`、`mouse` 等常用 target。
- 支持 `method`、`args`、`kwargs`、`chain`，让 Agent 可以表达大多数 Playwright 调用。
- Runner 只执行 allowlist 中的 Playwright 方法，避免 `evaluate`、文件系统、下载路径等能力被无边界使用。
- 对 passthrough 动作也记录 trace，包含 method、selector、参数摘要、耗时、错误和截图策略。

这样 JSON/YAML 不需要复刻完整 Playwright API，但仍然给成熟 Agent 足够大的表达空间。复杂到需要任意 Python 逻辑时，再升级到 Python flow。

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

## Flow Authoring Skill

系统应该提供一个给外部 AI Agent 使用的 skill，例如 `bitbrowser-flow-author`。用户可以让 Codex 或其他成熟 Agent 读取这个 skill，然后根据已经跑通的 Playwright 操作生成可固化 flow。

这个 skill 的目标不是操控浏览器，而是指导 Agent 输出高质量、可运行、可维护的 flow 文件。

Skill 应包含：

- Declarative flow schema。
- 核心语义动作列表。
- Playwright passthrough 写法。
- 何时使用 YAML，何时升级为 Python flow。
- selector 稳定性建议。
- 输入参数抽取规则。
- trace 到 flow 的整理规则。
- 输出文件格式要求和自检清单。

Agent 使用方式示例：

```text
Use the bitbrowser-flow-author skill to convert this successful Playwright trace into a reusable declarative flow.
Inputs that vary per task are: username, password, keyword.
Prefer semantic actions, but use Playwright passthrough when needed.
```

Skill 给 Agent 的核心规则：

- 优先生成 Declarative flow。
- 对用户每次会变化的值使用 `inputs.xxx`。
- 优先使用 role/text/test-id 等稳定 selector；CSS selector 作为备选。
- 每个关键动作后补 `wait_for` 或断言。
- 能用核心语义动作表达时，不使用 passthrough。
- 需要 Playwright 特性但不需要复杂 Python 控制流时，使用 `action: playwright`。
- 出现复杂分支、循环、递归、跨任务状态、外部 API 调用时，生成 Python flow。
- 如果生成 Python flow，必须实现 `async def run(ctx)`，不能自己打开比特浏览器窗口。

未来真正创建 skill 时，推荐目录：

```text
bitbrowser-flow-author/
  SKILL.md
  references/
    declarative-flow-schema.md
    playwright-passthrough.md
    python-flow-contract.md
  scripts/
    validate_flow.py
```

`validate_flow.py` 用于让 Agent 生成后自检 schema、必填字段、动作 allowlist 和模板变量引用。

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

## Level 3: Managed Agent Flow

适用场景：

- 目标描述开放，页面结构经常变化。
- 用户无法或不想固化流程。
- 需要 Agent 看页面、推理、操作、验证、修正。
- 超级复杂自动化，需要在运行时处理大量未知分支。

第一阶段不实现具体 Agent 技术，但设计上保留接口：

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

这个限制很重要：内置 Agent 不应该绕过系统直接随意操作 Playwright。所有动作都要被记录，方便回放、诊断和固化。

## 从 Agent 到固化流程

用户自带 Agent 或系统 Agent 跑通一次后，系统应该能收集一份 action trace：

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

固化过程不是简单把所有低层动作照抄，而是做一次整理：

- 把具体输入值替换成 `inputs.xxx`。
- 删除无意义等待和重复点击。
- 给关键步骤补上 `wait_for` 和 `assert_text`。
- 把不稳定 selector 标记出来，提示用户确认。
- 生成 YAML 初稿，让用户编辑后保存。

推荐固化命令：

```bash
python -m bitbrowser_auto trace-to-flow artifacts/demo-001/trace.json \
  --out flows/declarative/demo.yaml
```

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

为了支持“看着 Agent 跑通后固化”，第一版就应该记录 trace，即使只实现 declarative 和 Python。

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

## 第一版要做和不要做

第一版要做：

- 任务 schema 支持 `flow_type`、`flow`、`goal`、`inputs`。
- Runner 分发层支持 `declarative` 和 `python`。
- 预留 `agent` 类型，遇到时给出清晰错误：当前版本未启用。
- 每个任务保存 `trace.json`。
- Declarative flow 支持核心语义动作和 Playwright passthrough。
- 提供 flow validator，至少检查 schema、模板变量、动作 allowlist 和必填字段。
- 准备 `bitbrowser-flow-author` skill 的结构和参考文档，让外部 Agent 能生成固化 flow。
- Python flow 支持 `async def run(ctx)`。

第一版不要做：

- 不做复杂可视化流程编辑器。
- 不做完整 Python 沙箱。
- 不做 Agent 技术选型绑定。
- 不把 YAML 动作流扩展成复杂编程语言；复杂控制流交给 Python flow。
- 不为了未来 Agent 改重调度器。

## 设计原则

- 调度器稳定，不关心页面细节。
- Runner 可插拔，但接口统一。
- Declarative flow 既要可读、可固化，也要通过 Playwright passthrough 给成熟 Agent 足够表达力。
- Python flow 承接复杂逻辑。
- Agent flow 承接开放任务。
- Trace 是连接三者的桥：能诊断、能回放、能固化。
