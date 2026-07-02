# GUI 设计与打包策略

## 目标

GUI 的目标是让普通用户能双击打开、配置任务、查看运行状态，同时保留开发者和高级用户需要的 Web/CLI 模式。

第一版 GUI 不应该侵入调度核心。核心原则：

```text
core engine: BitBrowserClient / Scheduler / Runner / Storage
ui layer: NiceGUI 页面，调用 core service
cli layer: 命令行入口，调用同一套 core
```

## 推荐选型

第一版推荐使用 NiceGUI。

原因：

- 纯 Python 开发，和现有技术栈一致。
- 适合本机任务管理面板：表格、按钮、日志、配置、截图预览。
- 支持浏览器 Web 模式。
- 支持 `native=True`，可以用独立桌面窗口承载 UI。
- 比 FastAPI + React/Vue 更快启动，比 PySide6/Qt 更贴近 Web 管理后台。

需要接受的事实：

- NiceGUI native 模式不是传统原生控件 GUI，而是本地服务 + WebView 桌面窗口。
- 深度桌面能力如托盘、原生菜单、系统级集成，不如 PySide6/Qt。
- 打包后需要针对 Windows/macOS 做实际测试。

## 三种启动模式

同一个打包产物应支持三种模式。

### Desktop Mode

普通用户默认模式。

```bash
BitBrowserAuto
```

行为：

- 启动本地 NiceGUI 服务。
- 使用 `ui.run(native=True)` 打开独立桌面窗口。
- 默认绑定 `127.0.0.1`。
- 默认自动选择可用端口。

适合：

- 双击 `.exe` / `.app`。
- 不想看到浏览器地址栏的普通用户。

### Web Mode

浏览器模式。

```bash
BitBrowserAuto ui --web
BitBrowserAuto ui --web --port 8765
```

行为：

- 启动本地 Web 服务。
- 用户通过浏览器访问。
- 默认绑定 `127.0.0.1`，需要局域网访问时显式设置 host。

适合：

- 开发调试。
- 用户希望用浏览器打开。
- 后续远程控制或局域网访问。

### CLI Mode

命令行模式。

```bash
BitBrowserAuto check
BitBrowserAuto run --tasks configs/tasks.yaml
BitBrowserAuto validate-flow open_and_check
```

适合：

- 自动化批处理。
- 排障。
- 高级用户脚本集成。

## UI 页面规划

第一版只做操作台，不做复杂可视化编辑器。

页面：

- Dashboard
  - Local Server 状态
  - 当前运行任务数
  - 成功/失败统计
  - 最近错误
- Browser Windows
  - 比特窗口列表
  - 打开/关闭/检测
  - `browser_id`、名称、序号、pid、运行状态
- Tasks
  - 导入 YAML/CSV
  - 任务列表
  - 状态筛选
  - 重试/取消/重置
- Runs
  - 运行历史
  - 日志
  - 截图预览
  - trace 下载/查看
- Flows
  - Declarative flow 文件列表
  - Python flow 文件列表
  - validator 检查结果
- Settings
  - `max_concurrent_windows`
  - `close_window_after_task`
  - artifact 路径
  - 比特浏览器 Local Server 地址

## 当前实现状态

已落地 Phase 9 的首版操作台：

- `bitbrowser_auto ui`
  - 按 `ui.default_mode` 启动，默认 Desktop/native。
  - 已显式加入 `pywebview` 依赖，后续打包时继续验证各平台 WebView。
- `bitbrowser_auto ui --web`
  - Web 模式已可在普通浏览器访问。
  - 本机验证地址：`http://127.0.0.1:8765`。
- 已实现页面：
  - Dashboard：任务状态统计、Local Server 健康检查、最近错误。
  - Browser Windows：窗口列表、指定 `browser_id` 打开/关闭。
  - Tasks：导入任务、状态筛选、启动/停止调度、重置 running。
  - Runs：运行历史、`run.json`、`trace.json`、截图预览。
  - Flows：Declarative/Python flow 列表，Declarative validator。
  - Settings：当前配置 JSON 摘要。
- 已验证：
  - `.venv/bin/python -m bitbrowser_auto ui --help`
  - `.venv/bin/python -m bitbrowser_auto ui --web --host 127.0.0.1 --port 8765`
  - 普通浏览器中 websocket、页面导航、健康检查和主要列表渲染正常。

注意：比特浏览器窗口可以打开 UI 页面，但某些窗口配置可能拦截 localhost websocket；UI 验收优先使用普通浏览器。比特浏览器仍用于自动化任务窗口，不要求承载管理 UI。

## UI 与 Core 的边界

UI 只能调用 core 层，不直接操作 Playwright 或 SQLite 细节。

推荐内部接口：

```text
CoreService
  check_environment()
  list_browser_windows()
  import_tasks(path)
  list_tasks(filters)
  start_scheduler()
  stop_scheduler()
  retry_task(task_id)
  cancel_task(task_id)
  list_runs(task_id)
  get_artifact(path)
  validate_flow(path)
```

这样 Desktop Mode、Web Mode 和 CLI Mode 都能共享同一套核心能力。

## NiceGUI 启动结构

建议提供统一入口：

```text
bitbrowser_auto/
  __main__.py
  cli.py
  ui/
    app.py
    pages/
      dashboard.py
      browsers.py
      tasks.py
      runs.py
      flows.py
      settings.py
```

伪代码：

```python
def run_ui(mode: str, host: str, port: int | None):
    build_ui()

    if mode == "web":
        ui.run(host=host, port=port or 0, reload=False)
    else:
        ui.run(
            native=True,
            host="127.0.0.1",
            port=port or 0,
            reload=False,
            title="BitBrowser Auto",
            window_size=(1200, 800),
        )
```

## 打包策略

第一版推荐 PyInstaller `onedir`，不要一开始追求 `onefile`。

推荐产物：

```text
dist/
  BitBrowserAuto/
    BitBrowserAuto.exe
    ...
```

原因：

- `onedir` 启动更快。
- 依赖文件更容易排查。
- Playwright/NiceGUI/pywebview 相关资源更容易打包成功。

后续如果用户强烈需要单文件，再评估 `onefile`。

## 平台注意事项

### Windows

- NiceGUI native 依赖 WebView。
- 通常依赖 Edge WebView2。
- 需要测试无 Python 环境的干净机器。
- 比特浏览器 Local Server 地址默认 `127.0.0.1:54345`。

### macOS

- 可以打成 `.app`。
- 分发给其他用户时需要考虑签名、公证和权限提示。
- 本机开发阶段可以先用命令行启动。

### Linux

- native window 依赖系统 WebView/GTK/Qt 环境。
- 桌面发行版差异较大。
- 第一优先级可以先保证 Web Mode。

## 配置建议

`configs/app.yaml` 增加 UI 配置：

```yaml
ui:
  default_mode: "desktop"
  host: "127.0.0.1"
  port: 0
  title: "BitBrowser Auto"
  window_width: 1200
  window_height: 800
```

`port: 0` 表示自动选择可用端口，避免端口冲突。

## 第一版验收标准

- 双击打包应用能打开独立窗口。
- `ui --web` 能在浏览器中打开同一套 UI。
- `check`、`run` 等 CLI 命令仍然可用。
- UI 能查看窗口列表。
- UI 能导入任务并启动/停止调度。
- UI 能查看任务状态、日志、截图和错误。
- UI 关闭时能优雅停止调度器或提示仍有任务运行。
