# bitbrowser-auto

本项目是一个本机 BitBrowser 自动化执行器：通过比特浏览器 Local Server 打开或接管窗口，拿到 DevTools WebSocket 地址后交给 Playwright 执行任务，并用 SQLite 与 artifacts 目录记录任务状态、截图、trace 和结果。

它适合在本机批量管理浏览器窗口、执行重复性账号任务、验证登录态、采集页面信息，或把 Codex/其他工具生成的 YAML/Python flow 稳定跑起来。

## 功能概览

- 调用 BitBrowser Local Server 检查服务、列出窗口、打开窗口、关闭窗口。
- 使用 Playwright `connect_over_cdp` 接管 BitBrowser 已打开窗口。
- 支持声明式 YAML/JSON flow、Python flow，并预留 Agent flow 类型。
- 提供任务导入、任务列表、运行 pending 任务、恢复 interrupted running 任务等 CLI。
- 提供 NiceGUI 本机界面，支持桌面模式和浏览器 Web 模式。
- 运行产物写入 `artifacts/`，调度状态写入 `data/scheduler.sqlite3`。
- 提供 macOS、Linux、Windows 启动脚本，可自动创建并刷新 `.venv`。

## 环境要求

- Python 3.9+
- 已安装并启动比特浏览器客户端
- 比特浏览器 Local Server 可访问，默认地址为 `http://127.0.0.1:54345`

Python 依赖在 `pyproject.toml` 中声明，主要包括：

- `httpx`
- `nicegui`
- `playwright`
- `pywebview`
- `PyYAML`

## 快速开始

### 1. 启动比特浏览器 Local Server

先打开比特浏览器客户端，并确认 Local Server 已启用。默认配置会访问：

```text
http://127.0.0.1:54345
```

如果你的 Local Server 地址不同，复制并修改 `configs/app.example.yaml`，然后在命令中传入 `--config`。

### 2. 自动创建虚拟环境

项目提供统一的 venv 初始化脚本：

```bash
python3 scripts/setup_venv.py
```

脚本会在项目根目录创建 `.venv`，并在 `pyproject.toml` 更新或依赖缺失时自动执行：

```bash
python -m pip install -e .
```

也可以强制重装：

```bash
python3 scripts/setup_venv.py --force
```

### 3. 启动界面

macOS：

```bash
./start_mac.command
./start_mac.command web --port 8765
```

Linux：

```bash
./start_linux.sh
./start_linux.sh web --port 8765
```

Windows：

```bat
start_windows.bat
start_windows.bat web --port 8765
```

默认 `desktop` 模式会启动本机桌面窗口；`web` 模式会在浏览器中打开 NiceGUI 界面。

## 手动安装

如果不使用启动脚本，也可以手动安装：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Windows PowerShell：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

安装后可检查 CLI：

```bash
python -m bitbrowser_auto --version
bitbrowser-auto --version
```

## 配置

默认配置文件是 `configs/app.example.yaml`。主要字段：

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
  recover_running_tasks_as: "pending"

paths:
  sqlite: "data/scheduler.sqlite3"
  artifact_dir: "artifacts"
  declarative_flow_dir: "flows/declarative"
  python_flow_dir: "flows/py"
```

建议复制一份自己的配置，避免直接改示例：

```bash
cp configs/app.example.yaml configs/app.local.yaml
```

然后运行时指定：

```bash
python -m bitbrowser_auto check --config configs/app.local.yaml
python -m bitbrowser_auto ui --config configs/app.local.yaml --web
```

## CLI 用法

检查 Local Server 是否可用：

```bash
python -m bitbrowser_auto check
```

检查指定 BitBrowser 窗口能否被 Playwright CDP 接管：

```bash
python -m bitbrowser_auto check \
  --browser-id <bitbrowser-window-id> \
  --url https://example.com
```

运行单个任务：

```bash
python -m bitbrowser_auto run-one \
  --browser-id <bitbrowser-window-id> \
  --flow-type declarative \
  --flow <flow-name> \
  --url https://example.com
```

运行 Python flow：

```bash
python -m bitbrowser_auto run-one \
  --browser-id <bitbrowser-window-id> \
  --flow-type python \
  --flow <python-flow-name> \
  --url https://example.com
```

校验声明式 flow：

```bash
python -m bitbrowser_auto validate-flow <flow-name-or-path>
```

导入任务到 SQLite：

```bash
python -m bitbrowser_auto import-tasks configs/tasks.example.yaml --replace
```

查看任务：

```bash
python -m bitbrowser_auto list-tasks
python -m bitbrowser_auto list-tasks --status pending
```

运行 pending 任务：

```bash
python -m bitbrowser_auto run --once
```

从任务文件导入并运行：

```bash
python -m bitbrowser_auto run --tasks configs/tasks.example.yaml --replace --once
```

重置异常中断的 running 任务：

```bash
python -m bitbrowser_auto reset-running --as-status pending
```

启动 UI：

```bash
python -m bitbrowser_auto ui
python -m bitbrowser_auto ui --web --host 127.0.0.1 --port 8765
```

## 任务文件

任务文件可以是 YAML 或 CSV。YAML 推荐格式：

```yaml
tasks:
  - id: "demo-001"
    browser_id: "<bitbrowser-window-id>"
    flow_type: "declarative"
    flow: "<flow-name>"
    inputs:
      url: "https://example.com"

  - id: "python-demo-001"
    browser_id: "<bitbrowser-window-id>"
    flow_type: "python"
    flow: "<python-flow-name>"
    inputs:
      urls:
        - "https://example.com"
```

字段说明：

- `id`: 任务唯一 ID。
- `browser_id`: 比特浏览器窗口 ID。
- `flow_type`: `declarative`、`python` 或预留的 `agent`。
- `flow`: flow 名称或文件路径。
- `inputs`: 传给 flow 的输入参数。
- `batch_id`: 可选，用于把一组任务归到同一批次。

## 声明式 Flow

声明式 flow 放在 `flows/declarative/`，支持 `.yaml`、`.yml`、`.json`。如果任务写 `flow: open_and_check`，系统会按配置目录查找：

```text
flows/declarative/open_and_check.yaml
flows/declarative/open_and_check.yml
flows/declarative/open_and_check.json
```

最小示例：

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
  - action: screenshot
    name: "final"
```

当前核心动作包括：

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
if_visible
if_text
playwright
human_click
```

模板中可以读取输入和前置步骤输出：

```text
{{ inputs.url }}
{{ inputs.username }}
{{ outputs.title }}
```

`playwright` 动作只允许调用 allowlist 中的常用方法，避免 flow 获得无限制执行能力。复杂逻辑、循环、分页或数据清洗建议改用 Python flow。

## Python Flow

Python flow 放在 `flows/py/`，每个文件必须定义：

```python
async def run(ctx):
    page = ctx.page
    inputs = ctx.inputs

    await page.goto(inputs["url"])
    title = await page.title()
    screenshot = await ctx.artifacts.screenshot(page, "final")
    return {"title": title, "screenshot": screenshot}
```

`ctx` 由系统提供，常用字段：

- `ctx.page`: Playwright page。
- `ctx.context`: Playwright browser context。
- `ctx.browser`: Playwright browser。
- `ctx.task`: 当前任务对象。
- `ctx.inputs`: 当前任务输入。
- `ctx.artifacts`: 产物管理器，用于写截图等文件。
- `ctx.bitbrowser`: BitBrowser client。

Python flow 不负责打开或关闭 BitBrowser 窗口，只负责在系统已接管的页面里执行自动化。

## 运行产物

默认目录：

```text
data/
  scheduler.sqlite3
artifacts/
  ...
```

`data/` 保存本机任务状态；`artifacts/` 保存每次运行产生的截图、trace、错误现场和结果文件。这两个目录通常不提交到 Git。

## 项目结构

```text
configs/                  配置和任务示例
docs/                     设计文档和接口说明
flows/
  declarative/            声明式 YAML/JSON flow
  py/                     Python flow
scripts/
  setup_venv.py           跨平台虚拟环境初始化脚本
src/bitbrowser_auto/
  bitbrowser/             BitBrowser Local Server API client
  browser/                Playwright CDP 连接
  runner/                 flow 加载、执行、调度
  storage/                SQLite 状态存储
  ui/                     NiceGUI 界面
tests/                    单元测试
```

## 开发与测试

安装开发环境：

```bash
python3 scripts/setup_venv.py
```

运行测试：

```bash
.venv/bin/python -m pytest
```

Windows：

```bat
.venv\Scripts\python.exe -m pytest
```

常用调试命令：

```bash
python -m bitbrowser_auto check
python -m bitbrowser_auto validate-flow <flow-name-or-path>
python -m bitbrowser_auto run-one --browser-id <id> --flow-type declarative --flow <flow>
```

## 常见问题

### `python3 was not found`

请先安装 Python 3.9+，并确认 `python3`、`python` 或 Windows 的 `py -3` 能在终端中执行。

### `BitBrowser Local Server` 连接失败

确认比特浏览器客户端已经启动，Local Server 已启用，并检查 `configs/app.example.yaml` 中的 `bitbrowser.base_url` 是否正确。

### 找不到 flow

确认 flow 文件在配置里的目录下：

```yaml
paths:
  declarative_flow_dir: "flows/declarative"
  python_flow_dir: "flows/py"
```

声明式 flow 支持 `.yaml`、`.yml`、`.json`；Python flow 必须是 `.py` 文件。

### UI 端口冲突

可以指定端口：

```bash
python -m bitbrowser_auto ui --web --port 8765
```

或使用启动脚本：

```bash
./start_mac.command web --port 8765
./start_linux.sh web --port 8765
start_windows.bat web --port 8765
```

## 进一步阅读

- [项目框架](docs/project-framework.md)
- [BitBrowser 浏览器窗口接口](docs/bitbrowser-browser-api.md)
- [自动化流程执行与扩展设计](docs/automation-flow-design.md)
- [轻量任务调度系统设计](docs/lightweight-task-scheduler.md)
- [GUI 设计与打包策略](docs/gui-design.md)
- [人类鼠标轨迹模拟](docs/human-mouse-simulation.md)
