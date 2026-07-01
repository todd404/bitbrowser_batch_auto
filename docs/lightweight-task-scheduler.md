# 轻量任务调度系统设计

## 设计目标

这套调度系统优先解决一个问题：让普通用户在本机快速启动，稳定地并行跑多个比特浏览器窗口自动化。

它不追求一开始就做成分布式平台，也不默认引入 Postgres、Redis、消息队列、Kubernetes 这类重组件。第一版应该做到：

- 安装依赖少，最好 `pip install -r requirements.txt` 后即可运行。
- 本机单进程即可调度多个窗口。
- 任务状态可恢复，程序中断后能知道哪些成功、失败、运行中断。
- 每个比特窗口同一时间只跑一个任务，避免页面、Cookie、焦点、下载等共享状态互相污染。
- 保留清晰扩展点，后续再接入 Web UI、队列服务或远程执行器。

## 实测前提

已经验证过：

- 比特浏览器 Local Server `POST /health` 可用。
- `POST /browser/open` 会返回本次运行的 `ws`、`http`、`pid`、`coreVersion`。
- Playwright 可以通过 `chromium.connect_over_cdp(ws)` 接管窗口。
- 同一个 `browser_id` 是长期窗口身份，但每次重新打开后的 `pid`、`ws`、端口可能变化。

因此系统里要区分两种身份：

```text
browser_id: 长期身份，比特浏览器窗口配置
run_id/ws/pid/port: 本次打开窗口的运行身份
```

不要长期保存并复用旧 `ws`。每次任务开始前都应该通过 `/browser/open` 取最新 `ws`。

## 推荐第一版形态

```text
YAML/CSV 任务文件
      |
      v
单进程 Scheduler
      |
      +--> SQLite 状态库
      |
      +--> Window Slot Pool
      |
      +--> Playwright Runner
      |
      v
artifacts 日志/截图/结果文件
```

核心依赖：

- Python
- Playwright
- pydantic 或 dataclasses
- PyYAML
- 标准库 `sqlite3`
- 标准库 `asyncio`

自动化流程分三类：JSON/YAML 动作流、Python flow、未来内置 Agent flow。详细设计见 [automation-flow-design.md](automation-flow-design.md)。

不建议第一版使用：

- Postgres：部署成本高，用户启动门槛高。
- Redis / Celery：对单机窗口调度来说过重。
- 多进程 worker：Playwright 和窗口资源先用 asyncio 管好，真的遇到 CPU 瓶颈再拆。

## 最小目录结构

```text
bit_browser_auto/
  configs/
    app.yaml
    tasks.yaml
  data/
    scheduler.sqlite3
  artifacts/
    task-id/
      run.json
      trace.json
      screenshot.png
      error.txt
  src/
    bitbrowser_auto/
      main.py
      config.py
      cli.py
      bitbrowser_client.py
      scheduler.py
      window_pool.py
      runner.py
      declarative_runner.py
      python_runner.py
      flows.py
      storage.py
      ui/
        app.py
        pages/
  flows/
    declarative/
      open_and_check.yaml
    py/
      custom_flow.py
```

第一版可以先少分包，保持文件数可控。等流程稳定后再拆成更细模块。

## 配置文件

`configs/app.yaml`：

```yaml
bitbrowser:
  base_url: "http://127.0.0.1:54345"
  request_timeout_seconds: 30

scheduler:
  max_concurrent_windows: 3
  open_interval_seconds: 2
  task_timeout_seconds: 300
  close_window_after_task: false
  close_wait_seconds: 5
  max_retries: 1

paths:
  sqlite: "data/scheduler.sqlite3"
  artifact_dir: "artifacts"

ui:
  default_mode: "desktop"
  host: "127.0.0.1"
  port: 0
  title: "BitBrowser Auto"
  window_width: 1200
  window_height: 800
```

`configs/tasks.yaml`：

```yaml
tasks:
  - id: "demo-001"
    browser_id: "2357d261d2d2472985d52e7916d6a580"
    flow_type: "declarative"
    flow: "open_and_check"
    inputs:
      url: "https://example.com"

  - id: "demo-002"
    browser_id: "another-browser-id"
    flow_type: "python"
    flow: "custom_flow"
    inputs:
      url: "https://example.com"
```

如果用户从表格管理账号，也可以支持 CSV：

```csv
id,browser_id,flow_type,flow,goal,inputs_json
demo-001,2357d261d2d2472985d52e7916d6a580,declarative,open_and_check,,{"url":"https://example.com"}
```

## SQLite 数据表

SQLite 足够支撑第一版：本机单用户、几百到几万条任务、可恢复状态、可查询结果。

```sql
create table if not exists tasks (
  id text primary key,
  browser_id text not null,
  flow_type text not null,
  flow text not null,
  goal text,
  inputs_json text not null default '{}',
  status text not null,
  retry_count integer not null default 0,
  last_error text,
  created_at text not null,
  updated_at text not null,
  started_at text,
  finished_at text
);

create table if not exists task_runs (
  id text primary key,
  task_id text not null,
  browser_id text not null,
  status text not null,
  ws text,
  pid integer,
  port text,
  started_at text not null,
  finished_at text,
  error text,
  artifact_dir text,
  trace_path text
);

create table if not exists browser_runtime (
  browser_id text primary key,
  status text not null,
  current_task_id text,
  ws text,
  pid integer,
  port text,
  updated_at text not null
);
```

状态枚举保持简单：

```text
task.status:
  pending
  running
  success
  failed
  cancelled

browser_runtime.status:
  idle
  opening
  running
  closing
  error
```

程序启动时，把历史遗留的 `running` 任务改成 `failed` 或 `pending`，取决于配置：

```yaml
scheduler:
  recover_running_tasks_as: "pending"
```

建议默认改回 `pending`，方便用户因断电、程序崩溃后继续跑。

## 调度模型

第一版使用“窗口槽位池”，不要上复杂队列。

规则：

1. 一个 `browser_id` 同一时间只能占用一个槽位。
2. 一个任务绑定一个 `browser_id`。
3. Scheduler 每轮从 SQLite 取 `pending` 任务。
4. 如果任务的 `browser_id` 不在运行中，且当前运行窗口数小于 `max_concurrent_windows`，就启动该任务。
5. 任务结束后释放槽位。

伪代码：

```python
while True:
    running_count = storage.count_running_tasks()
    free_capacity = max_concurrent_windows - running_count

    if free_capacity > 0:
        tasks = storage.claim_pending_tasks(limit=free_capacity)
        for task in tasks:
            if window_pool.is_busy(task.browser_id):
                storage.release_to_pending(task.id)
                continue
            asyncio.create_task(run_task(task))

    await asyncio.sleep(1)
```

`claim_pending_tasks` 要在 SQLite 事务里完成，把任务从 `pending` 改成 `running`，避免重复领取。单进程场景很简单，但这样写未来也更稳。

## 单个任务生命周期

```text
pending
  |
  v
claim task -> running
  |
  v
open browser: /browser/open
  |
  v
connect Playwright over CDP
  |
  v
run flow
  |
  +--> success
  |
  +--> failed -> retry or final failed
```

具体步骤：

1. 标记 `browser_runtime.status = opening`。
2. 调 `/browser/open`，参数里使用 `queue: true`。
3. 保存本次返回的 `ws`、`pid`、`http` 端口到 `task_runs` 和 `browser_runtime`。
4. `connect_over_cdp(ws)`。
5. 找到已有 page 或创建新 page。
6. 按 `flow_type` 分发并执行 flow。
7. 成功后写入结果，任务状态改为 `success`。
8. 失败后保存截图和错误，按 `max_retries` 判断是否回到 `pending`。
9. 按配置决定是否调用 `/browser/close`。
10. 释放 `browser_runtime`。

## 窗口打开策略

默认推荐：

```json
{
  "id": "<browser_id>",
  "args": [],
  "queue": true,
  "ignoreDefaultUrls": true,
  "newPageUrl": "<task inputs.url>"
}
```

注意：

- 每次都以 `/browser/open` 返回的最新 `ws` 为准。
- 不要认为同一个窗口的旧 `ws` 永远可用。
- 如果窗口已打开，仍然可以调用 `/browser/open` 获取当前可连接信息，但任务系统应该避免同一个 `browser_id` 被两个任务同时调用。
- 如果需要远程机器连接，可以在 `args` 里加 `--remote-debugging-address=0.0.0.0`，但本机第一版不需要。

## Runner 设计

Runner 只做三件事：

1. 接管浏览器。
2. 执行 flow。
3. 保存 artifacts。

接口保持简单：

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

第一版建议实现两种 runner：

- `declarative`: 执行 JSON/YAML 动作流，适合用户用 Agent 跑通后固化；包含核心语义动作和 Playwright passthrough。
- `python`: 加载用户或 Agent 生成的 `.py` 文件，适合判断、循环、复杂提取。

`agent` 类型在第一版只保留 schema 和分发入口，未启用时返回清晰错误即可。不要一开始就做插件系统或复杂 Agent 框架。

## 失败处理

错误分三类即可：

```text
recoverable:
  网络超时、页面加载失败、浏览器临时启动失败

business:
  密码错误、账号封禁、需要验证码、权限不足

fatal:
  Local Server 不可用、Playwright 无法连接、配置错误
```

推荐策略：

- `recoverable`: 按 `max_retries` 重试。
- `business`: 不重试，标记 `failed`，记录原因。
- `fatal`: 暂停调度或快速失败，提示用户检查环境。

每次失败至少保存：

- 当前 URL
- 截图
- 错误堆栈
- task/run JSON
- trace JSON

## 是否关闭窗口

默认建议第一版配置为：

```yaml
close_window_after_task: false
```

原因：

- 调试时用户能直接看到窗口状态。
- 连续任务跑同一个账号时可以复用打开状态。
- 关闭后文档建议等待 5 秒，吞吐会下降。

但批量长跑时可以切换为：

```yaml
close_window_after_task: true
```

此时任务结束后调用 `/browser/close`，并等待 `close_wait_seconds`，避免马上重开导致状态混乱。

## 快速启动命令

建议最终提供这些命令：

```bash
python -m bitbrowser_auto check
python -m bitbrowser_auto import-tasks configs/tasks.yaml
python -m bitbrowser_auto run
python -m bitbrowser_auto ui
python -m bitbrowser_auto ui --web
```

含义：

- `check`: 检查 conda/Python、Playwright、Local Server、窗口列表、CDP 接管。
- `import-tasks`: 把 YAML/CSV 任务导入 SQLite。
- `run`: 按并发配置运行任务。
- `ui`: 默认 Desktop Mode，使用 NiceGUI native window。
- `ui --web`: Web Mode，用浏览器访问本机 UI。
- `trace-to-flow`: 把成功运行的 trace 转成可编辑的 JSON/YAML 动作流。

也可以保留一个更低门槛的一步命令：

```bash
python -m bitbrowser_auto run --tasks configs/tasks.yaml
```

它会自动初始化 SQLite、导入任务并开始执行。

## 第一版实现顺序

1. `BitBrowserClient`: 封装 `/health`、`/browser/list`、`/browser/open`、`/browser/close`。
2. `Storage`: 初始化 SQLite，导入任务，更新任务状态。
3. `Runner`: 给定一个 task，打开窗口、CDP 接管、按 `flow_type` 分发。
4. `Scheduler`: 加上 `max_concurrent_windows` 并发控制。
5. `DeclarativeRunner`: 支持 `goto`、`click`、`fill`、`wait_for`、`extract_text`、`screenshot` 等核心动作，以及受 allowlist 限制的 Playwright passthrough。
6. `PythonRunner`: 支持加载 `async def run(ctx)` 的本地 Python flow。
7. `FlowValidator`: 校验 Declarative flow schema、模板变量、必填字段和 passthrough allowlist。
8. `Artifacts`: 失败截图、run.json、trace.json、error.txt。
9. `CLI`: `check`、`run --tasks`、`trace-to-flow`。
10. `NiceGUI UI`: 支持 Desktop Mode 和 Web Mode，调用同一套 core service。
11. 准备 `bitbrowser-flow-author` skill，让外部 Agent 能生成固化 flow。
12. 再增加更多 flow 和 AI Agent。

## 后续再升级的条件

只有出现这些情况，才值得升级到更重的系统：

- 多台机器同时跑任务。
- 多人共享任务池。
- 需要 Web UI 实时查看和操作任务。
- 单机 SQLite 写入成为瓶颈。
- 需要复杂优先级、延迟任务、任务依赖。

升级路径可以是：

```text
SQLite -> Postgres
单进程 Scheduler -> Scheduler + Worker
本地 artifacts -> 对象存储
本地 CLI -> Web UI
```

但第一版不必提前支付这些复杂度。
