# GUI 设计与打包策略

## 设计结论

Phase 9 的技术目标已经完成：NiceGUI 双模式、基础页面、任务导入、运行、结果查看都能工作。但当前 UI 的信息架构更像“CLI 命令集合的图形外壳”，普通用户需要先理解 `browser_id`、任务文件、flow 类型、SQLite 状态这些底层概念，才能完成一次批量自动化。

下一版 GUI 的目标不是增加更多按钮，而是把产品主线改成普通用户的自然工作流：

```text
选择流程 -> 选择窗口 -> 填写参数 -> 选择立即或定时 -> 运行中监控 -> 查看结果并重跑失败项
```

底层仍然沿用现有 core engine：

```text
core engine: BitBrowserClient / Scheduler / Runner / Storage
ui layer: NiceGUI 页面，调用 core service
cli layer: 命令行入口，调用同一套 core
```

GUI 不应该把用户带进底层对象。普通用户看到的是“批量运行”“计划任务”“运行结果”“窗口分组”“流程库”。高级用户仍可以在“诊断/高级设置”里看到任务表、运行 JSON、trace JSON、配置摘要和 CLI 等价命令。

## 用户画像

主要用户：

- 已经在比特浏览器里维护了一批窗口或账号。
- 想把同一个自动化流程跑到多个窗口上。
- 需要能暂停、重跑失败项、查看截图和错误。
- 不希望手写 YAML、记浏览器 ID、打开命令行。

次要用户：

- 能读懂 YAML/Python flow 的高级用户。
- 需要用 Web Mode 或 CLI 排障、批处理、接入其他脚本的开发者。

## 核心原则

- 以“运行批次”为中心，而不是以“任务文件”为中心。
- 批量执行是一等能力，单窗口运行只是批量运行的特例。
- 定时计划是一等能力，立即运行只是计划的一个触发方式。
- 默认值要安全：限制并发、避免同窗口重复占用、失败可重试、运行前预检查。
- 隐藏底层 ID：界面优先显示窗口名称、序号、分组、备注，ID 只在详情和复制按钮里出现。
- 渐进展示高级能力：普通流程只填表单，高级用户可以查看 YAML/Python、trace、JSON。
- 所有长任务都要有明确状态：等待、打开窗口、执行中、成功、失败、已停止。
- 错误要可处理：失败原因、截图、重跑失败项、复制错误、打开产物目录。

## 信息架构

目标导航：

- 运行台
  - 今日概览
  - 运行中批次
  - 待处理失败
  - 下一个计划
  - 主按钮：新建批量运行
- 新建运行
  - 使用向导创建立即运行或定时运行。
- 计划任务
  - 查看、启停、编辑、手动触发定时计划。
- 运行结果
  - 按批次查看历史结果、截图、错误、trace。
- 窗口
  - 浏览比特窗口、按分组/搜索选择、健康检测、打开/关闭。
- 流程库
  - 查看可用流程、输入项、试跑一个窗口、校验流程。
- 设置
  - 普通设置：并发数、运行结束是否关闭窗口、Local Server 地址。
  - 高级设置：路径、trace 策略、JSON 配置、诊断。

当前的 Dashboard、Browser Windows、Tasks、Runs、Flows、Settings 可以逐步迁移成上面的结构。`Tasks` 页面不再作为普通用户入口，只保留在高级诊断里。

## 当前技术状态

已落地的 Phase 9 技术版操作台：

- `bitbrowser_auto ui`：按 `ui.default_mode` 启动，默认 Desktop/native。
- `bitbrowser_auto ui --web`：Web 模式可在普通浏览器访问。
- Dashboard：任务状态统计、Local Server 健康检查、最近错误。
- Browser Windows：窗口列表、指定 `browser_id` 打开/关闭。
- Tasks：导入任务、状态筛选、启动/停止调度、重置 running。
- Runs：运行历史、`run.json`、`trace.json`、截图预览。
- Flows：Declarative/Python flow 列表，Declarative validator。
- Settings：当前配置 JSON 摘要。

这部分可以作为可用性改造的底座。后续不是重写 core，而是把普通用户入口改成批量运行、计划任务和批次结果。

## 主要工作流

### 首次打开

首次打开不要直接展示空表格。应进入一个轻量启动检查：

1. 检查比特浏览器 Local Server。
2. 读取窗口列表。
3. 检查可用流程。
4. 推荐创建第一次批量运行。

每项检查只显示普通结论：

- 本地服务正常 / 未连接。
- 找到 N 个窗口。
- 找到 N 个流程。
- 有 N 个上次中断的任务可恢复。

详细错误、原始响应、配置路径放入“诊断”抽屉。

### 多窗口执行同一个 flow

这是最重要的主路径。

用户点击“新建批量运行”后进入向导：

1. 选择流程
   - 以卡片或列表显示流程名、说明、类型、最后修改时间。
   - 默认隐藏 `declarative/python` 术语，只在详情里显示。
   - 选择后展示需要填写的参数。
2. 选择窗口
   - 支持按分组、名称、序号、备注搜索。
   - 支持全选当前筛选结果。
   - 支持只选空闲窗口、排除正在运行窗口。
   - 右侧显示已选数量和预计并发批次。
3. 填写参数
   - flow 的 `inputs` 自动生成表单。
   - 支持“所有窗口共用同一参数”。
   - 支持“每个窗口不同参数”的表格模式。
   - 支持 CSV 粘贴或导入，把列映射到 input 字段。
4. 运行选项
   - 立即运行。
   - 指定时间运行。
   - 重复运行：每天、每周、每隔 N 分钟或 N 小时。
   - 并发窗口数，默认使用配置值。
   - 失败重试次数。
   - 运行后是否关闭窗口。
5. 启动前检查
   - 窗口数量。
   - flow 校验结果。
   - 必填参数是否完整。
   - 是否存在同一窗口已在运行或排队。
   - 本地服务是否可用。
6. 提交
   - 立即运行会创建一个批次，并生成每个窗口的一条底层 task。
   - 定时运行会保存 schedule，到时间后自动生成批次。

用户不需要知道任务 YAML。导入 YAML 仍保留为高级能力。

### 定时计划

计划任务需要面向普通用户，而不是 cron 文本框。

计划类型：

- 只运行一次：指定日期和时间。
- 每天：指定时间，可选择工作日。
- 每周：选择星期几和时间。
- 间隔运行：每 N 分钟或 N 小时。
- 手动计划：保存配置，用户手动触发。

计划策略：

- 错过时间：跳过 / 程序启动后补跑一次。
- 上一次还没结束：跳过本次 / 排队下一批 / 停止旧批次后运行新批次。
- 运行窗口选择：固定窗口集合 / 每次按筛选条件重新选择。
- 失败处理：只重跑失败窗口 / 下次完整重跑。

计划列表要直接展示：

- 名称。
- 流程。
- 窗口范围。
- 下次运行时间。
- 最近结果。
- 开关。
- 手动运行按钮。

### 运行中监控

运行台应该优先展示批次，而不是单条任务表。

批次卡片或表格字段：

- 批次名称。
- 流程。
- 窗口数。
- 进度：成功 / 失败 / 运行中 / 等待。
- 当前阶段。
- 已耗时。
- 操作：暂停、停止、查看详情。

批次详情：

- 顶部摘要：总数、成功、失败、运行中、等待。
- 按窗口展示明细：窗口名称、序号、状态、当前步骤、耗时、错误。
- 失败项可一键重跑。
- 支持只查看失败、只查看运行中。
- 有截图时直接展示最后截图缩略图。

### 结果复盘

运行结果按“批次”组织，点击批次后再看窗口明细。

批次结果页：

- 摘要：成功率、总耗时、失败原因分布。
- 明细表：窗口、状态、开始时间、耗时、输出摘要、最后截图。
- 操作：重跑全部、重跑失败、导出结果、打开产物目录。

单窗口结果详情：

- 最后截图优先显示。
- 输出字段以表格展示。
- 错误、日志、trace 使用折叠区。
- `run.json` 和 `trace.json` 放在高级区。

### 流程库

流程库是用户选择流程的地方，不是文件浏览器。

每个流程应有 UI 元数据：

```yaml
name: "open_and_check"
display_name: "打开网址并截图"
description: "在选中的窗口里打开指定网址，完成后保存截图。"
version: 1
inputs:
  url:
    type: string
    label: "目标网址"
    required: true
    default: "https://example.com"
    placeholder: "https://example.com"
    per_window: false
```

Python flow 可以使用同名 `.meta.yaml` 或模块内 `FLOW_META` 提供相同元数据。第一版更推荐 `.meta.yaml`，避免 import 未信任代码只是为了读取 UI 信息。

流程详情：

- 流程名、说明、类型、版本。
- 输入项预览。
- 校验结果。
- 试跑一个窗口。
- 高级：查看源文件。

## 数据模型建议

现有 `Task` 模型可以继续作为执行单元：

```text
Task = browser_id + flow_type + flow + inputs
```

GUI 需要在它之上增加用户视角的对象。

### BatchRun

批量运行，一次用户发起或计划触发的运行。

建议字段：

```text
id
name
source: manual | schedule | imported
status: pending | running | success | partial_failed | failed | cancelled
flow_type
flow
window_count
options_json
created_at
started_at
ended_at
schedule_id nullable
```

每个批次会生成多条 task。建议给 `tasks` 和 `task_runs` 增加可空 `batch_id`，方便结果聚合。为了减少迁移风险，过渡期可以先用 task id 前缀保存批次关系：

```text
batch_20260703_153000__001
batch_20260703_153000__002
```

### Schedule

定时计划，负责按规则生成 BatchRun。

建议字段：

```text
id
name
enabled
flow_type
flow
window_selector_json
inputs_template_json
trigger_json
run_options_json
overlap_policy: skip | queue | replace
missed_policy: skip | run_once
last_run_at
next_run_at
created_at
updated_at
```

`trigger_json` 示例：

```json
{"type": "daily", "time": "09:30", "days": ["mon", "tue", "wed", "thu", "fri"]}
```

### Flow Metadata

声明式 flow 可以直接扩展现有 YAML 的 `inputs`。validator 已经允许额外字段，因此可以逐步增加 UI 元数据。

建议输入字段：

```text
type: string | number | boolean | choice | multiline | file | secret
label
required
default
placeholder
choices
per_window
validation
```

`per_window=true` 表示这个字段可以在批量运行中为每个窗口填写不同值。

## Core Service 接口

UI 不直接操作 SQLite、Playwright 或 BitBrowser API。建议在 `UiCoreService` 上增加面向产品工作流的方法：

```text
check_startup()
list_flow_cards()
get_flow_form(flow_type, flow)
list_window_choices(filters)
preview_batch_run(flow_type, flow, window_selector, inputs, options)
create_batch_run(flow_type, flow, browser_ids, inputs, per_window_inputs, options)
list_batches(filters)
get_batch_detail(batch_id)
stop_batch(batch_id)
rerun_failed(batch_id)
create_schedule(...)
list_schedules()
update_schedule(...)
toggle_schedule(schedule_id, enabled)
run_schedule_now(schedule_id)
```

CLI 和旧任务导入可以继续存在，但普通页面优先调用这些批量接口。

## 视觉与交互方向

整体应像一个本机任务控制台，而不是开发后台。

- 左侧导航保持稳定，但名称面向用户。
- 首屏突出“新建批量运行”和当前运行状态。
- 表格用于大量数据，向导用于创建任务。
- 结果页优先展示截图和摘要，JSON 放到高级折叠区。
- 操作按钮使用图标加短标签，危险操作需要确认。
- 运行中状态使用进度条和状态标签，不依赖用户刷新。
- 表格默认密度适中，窗口 ID 使用复制按钮，不占主列。
- 普通设置用表单控件，高级配置才展示 JSON。

建议导航中文名：

```text
运行台
新建运行
计划任务
运行结果
窗口
流程库
设置
```

## NiceGUI 实现策略

继续使用 NiceGUI。

三种启动模式不变：

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

### Web Mode

浏览器模式。

```bash
BitBrowserAuto ui --web
BitBrowserAuto ui --web --port 8765
```

适合开发调试、远程排障或局域网访问。

### CLI Mode

命令行模式。

```bash
BitBrowserAuto check
BitBrowserAuto run --tasks configs/tasks.yaml
BitBrowserAuto validate-flow open_and_check
```

适合高级用户、脚本集成和排障。

## 推荐目录结构

当前 `src/bitbrowser_auto/ui/app.py` 已经偏大。可用性改造时建议拆分：

```text
bitbrowser_auto/
  ui/
    app.py
    core.py
    state.py
    components/
      layout.py
      status.py
      flow_form.py
      window_picker.py
      run_progress.py
    pages/
      home.py
      new_run.py
      schedules.py
      results.py
      windows.py
      flows.py
      settings.py
      diagnostics.py
```

`app.py` 只负责创建服务、注册页面、全局主题和启动模式。

## 分阶段实施

### Phase 9A: 用户视角壳层

目标：把现有页面重组为普通用户能理解的入口。

交付物：

- 导航改为“运行台 / 新建运行 / 计划任务 / 运行结果 / 窗口 / 流程库 / 设置”。
- 运行台展示批次视角的摘要，即使底层暂时仍从 tasks/runs 聚合。
- 设置拆成普通设置和高级诊断。
- 窗口页隐藏 ID 主导地位，增加搜索、分组、状态筛选。

验收标准：

- 普通用户打开后能知道下一步是“新建批量运行”。
- 不需要复制 `browser_id` 就能选择窗口。
- JSON 不出现在普通首屏。

### Phase 9B: 批量运行向导

目标：支持多个窗口执行同一个 flow。

交付物：

- 新建批量运行向导。
- 流程卡片列表。
- 窗口选择器。
- flow inputs 自动表单。
- 每窗口参数表格模式。
- 提交后生成多条底层 task，并启动 scheduler。

验收标准：

- 用户可以选择 1 个 flow 和 N 个窗口立即运行。
- 同一个窗口不会被重复生成冲突任务。
- 启动前能看到预检查结果。
- 运行后能跳转到批次详情。

### Phase 9C: 运行结果批次化

目标：结果不再只是运行记录表，而是批次复盘。

交付物：

- `batch_runs` 或等价聚合层。
- 批次列表和批次详情。
- 重跑失败项。
- 导出结果。
- 截图缩略图和产物入口。

验收标准：

- 用户能按一次批量运行查看整体成功率。
- 用户能快速定位失败窗口和失败原因。
- 用户能一键重跑失败窗口。

### Phase 9D: 定时计划

目标：让批量运行可被计划触发。

交付物：

- `schedules` 存储。
- 计划创建/编辑页。
- 后台 schedule poller。
- 下次运行时间计算。
- 重叠策略和错过策略。

验收标准：

- 用户能创建一次性、每天、每周、间隔运行计划。
- UI 关闭或程序重启后，计划不会丢失。
- 到点后能自动生成一个批次并进入运行队列。
- 上一次未结束时按用户选择的策略处理。

### Phase 9E: 打包和桌面体验

目标：让普通用户双击可用。

交付物：

- PyInstaller `onedir`。
- Desktop Mode 默认入口。
- Web Mode 命令行入口。
- 首次启动检查和错误提示。
- 关闭窗口时检测运行中批次并确认。

验收标准：

- 干净机器上能双击启动。
- Local Server 未启动时给出清晰状态，不显示堆栈。
- 关闭 UI 时不会静默中断用户正在运行的任务。

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
- Playwright、NiceGUI、pywebview 相关资源更容易打包成功。

后续如果用户强烈需要单文件，再评估 `onefile`。

## 平台注意事项

### Windows

- NiceGUI native 依赖 WebView，通常依赖 Edge WebView2。
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

`configs/app.yaml` 保留现有 UI 配置：

```yaml
ui:
  default_mode: "desktop"
  host: "127.0.0.1"
  port: 0
  title: "比特浏览器自动化"
  window_width: 1200
  window_height: 800
```

后续可以增加：

```yaml
ui:
  default_page: "home"
  show_advanced_by_default: false
  refresh_interval_seconds: 2
  max_recent_batches: 20
```

调度相关配置继续放在 `scheduler`，不要散落到 UI 配置里。

## 非目标

以下内容不进入本轮 GUI 易用性改造：

- 可视化 flow 编排器。
- 内置 flow authoring Agent。
- 多用户权限和远程团队平台。
- 云端队列、Redis、Celery。
- 第三方 flow 市场或未信任代码沙箱。

这些能力可以以后扩展，但当前最重要的是让本机普通用户能稳定完成批量运行和定时运行。

## 第一版可用性验收标准

- 用户能双击打开 Desktop Mode。
- 用户能看到 Local Server、窗口、流程是否就绪。
- 用户能选择多个窗口执行同一个 flow。
- 用户能为所有窗口填写同一组参数。
- 用户能为每个窗口填写不同参数。
- 用户能创建一次性和重复定时计划。
- 用户能查看运行中批次的进度。
- 用户能按批次查看历史结果、截图和错误。
- 用户能一键重跑失败窗口。
- 高级用户仍能导入任务文件、查看 trace JSON、使用 CLI。
