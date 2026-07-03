from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable

from bitbrowser_auto.config import AppConfig

from .core import UiCoreService


STATUS_LABELS = {
    "": "全部",
    "pending": "待执行",
    "running": "运行中",
    "success": "成功",
    "failed": "失败",
    "partial_failed": "部分失败",
    "cancelled": "已取消",
    "idle": "空闲",
    "opening": "打开中",
    "closing": "关闭中",
    "stopping": "停止中",
    "finished": "已完成",
    "unknown": "未知",
}

FLOW_TYPE_LABELS = {
    "declarative": "声明式",
    "python": "Python",
    "agent": "Agent",
}

WEEKDAY_OPTIONS = {
    0: "周一",
    1: "周二",
    2: "周三",
    3: "周四",
    4: "周五",
    5: "周六",
    6: "周日",
}


def run_ui(*, config: AppConfig, mode: str, host: str, port: int) -> None:
    try:
        from nicegui import app, ui
    except ImportError as exc:
        raise RuntimeError("NiceGUI is required for the UI. Run `pip install -e .`.") from exc

    service = UiCoreService(config)
    artifact_root = config.paths.artifact_dir.resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    app.add_static_files("/artifacts", str(artifact_root))

    @ui.page("/")
    def build_root() -> None:
        _apply_theme(ui)
        state: dict[str, Any] = {"page": "home", "selected_batch_id": None}
        content: Any | None = None

        def navigate(page: str, **kwargs: Any) -> None:
            state.update(kwargs)
            state["page"] = page
            render()

        with ui.row().classes("app-shell w-full min-h-screen items-stretch no-wrap"):
            with ui.column().classes("sidebar shrink-0 gap-1 p-3"):
                ui.label(config.ui.title).classes("brand text-lg font-semibold mb-3")
                _nav_button(ui, "运行台", "space_dashboard", "home", navigate)
                _nav_button(ui, "新建运行", "play_circle", "new_run", navigate)
                _nav_button(ui, "计划任务", "event_repeat", "schedules", navigate)
                _nav_button(ui, "运行结果", "fact_check", "results", navigate)
                _nav_button(ui, "窗口", "language", "windows", navigate)
                _nav_button(ui, "流程库", "schema", "flows", navigate)
                _nav_button(ui, "设置", "settings", "settings", navigate)
            content = ui.column().classes("content grow gap-4")

        def render() -> None:
            assert content is not None
            content.clear()
            with content:
                page = state["page"]
                if page == "home":
                    _render_home(ui, service, content, navigate)
                elif page == "new_run":
                    _render_new_run(ui, service, navigate)
                elif page == "schedules":
                    _render_schedules(ui, service, content, navigate)
                elif page == "results":
                    _render_results(ui, service, config.paths.artifact_dir, content, state, navigate)
                elif page == "windows":
                    _render_windows(ui, service, content)
                elif page == "flows":
                    _render_flows(ui, service)
                elif page == "settings":
                    _render_settings(ui, service, content)

        async def tick() -> None:
            status = await service.poll_scheduler()
            await service.tick_schedules()
            if status.get("state") in {"finished", "failed", "cancelled"} and not status.get("_notified"):
                status["_notified"] = True

        render()
        ui.timer(5.0, tick, active=True)

    if mode == "web":
        ui.run(host=host, port=port, reload=False, show=True, title=config.ui.title)
    else:
        ui.run(
            host=host,
            port=port,
            reload=False,
            native=True,
            title=config.ui.title,
            window_size=(config.ui.window_width, config.ui.window_height),
        )


def _apply_theme(ui: Any) -> None:
    ui.colors(primary="#2563eb", secondary="#64748b", accent="#0f766e", positive="#15803d", negative="#b91c1c")
    ui.add_css(
        """
        html, body { min-height: 100%; }
        body { background: #f6f7fb; color: #111827; }
        .nicegui-content { padding: 0 !important; gap: 0 !important; max-width: none !important; }
        .app-shell { min-height: 100vh; }
        .sidebar { background: #111827; color: white; width: 232px; }
        .brand { line-height: 1.3; }
        .sidebar .nav-btn { height: 42px; padding: 0 12px; border-radius: 6px; }
        .sidebar .nav-btn .q-btn__content {
            display: grid;
            grid-template-columns: 34px 1fr;
            justify-items: start;
            width: 100%;
        }
        .sidebar .nav-btn .q-icon { justify-self: center; margin: 0; width: 24px; }
        .sidebar .nav-btn .block { align-self: center; text-align: left; }
        .content { min-width: 0; padding: 18px 22px 28px; }
        .section-panel { background: white; border: 1px solid #e5e7eb; border-radius: 8px; }
        .soft-panel { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; }
        .metric { min-width: 148px; }
        .metric .value { font-size: 28px; line-height: 1; font-weight: 700; }
        .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace; }
        .tight-table .q-table__top, .tight-table .q-table__bottom { padding: 8px 12px; }
        .flow-card { min-width: 240px; max-width: 360px; }
        .new-run-form { max-width: 1120px; }
        .step-title { font-size: 15px; font-weight: 700; color: #111827; }
        .step-index {
            width: 28px; height: 28px; border-radius: 999px; background: #2563eb;
            color: white; display: inline-flex; align-items: center; justify-content: center;
            font-size: 13px; font-weight: 700;
        }
        .window-picker-table .q-table__container { max-height: 420px; }
        .status-dot { width: 10px; height: 10px; border-radius: 999px; display: inline-block; }
        """
    )


def _nav_button(ui: Any, label: str, icon: str, page: str, navigate: Callable[..., None]) -> None:
    ui.button(label, icon=icon, on_click=lambda: navigate(page)).props("flat color=white no-caps").classes(
        "nav-btn w-full"
    )


def _toolbar(
    ui: Any,
    title: str,
    subtitle: str | None = None,
    refresh: Callable[[], None] | None = None,
    primary: tuple[str, str, Callable[[], None]] | None = None,
) -> None:
    with ui.row().classes("w-full items-start justify-between gap-3"):
        with ui.column().classes("gap-1"):
            ui.label(title).classes("text-2xl font-semibold")
            if subtitle:
                ui.label(subtitle).classes("text-sm text-slate-500")
        with ui.row().classes("items-center gap-2"):
            if refresh:
                ui.button(icon="refresh", on_click=refresh).props("round flat").tooltip("刷新")
            if primary:
                text, icon, handler = primary
                ui.button(text, icon=icon, on_click=handler).props("unelevated color=primary no-caps")


def _render_home(ui: Any, service: UiCoreService, content: Any, navigate: Callable[..., None]) -> None:
    async def refresh() -> None:
        content.clear()
        with content:
            _render_home(ui, service, content, navigate)

    _toolbar(
        ui,
        "运行台",
        "从这里创建批量运行、查看当前进度和最近结果。",
        refresh,
        ("新建批量运行", "play_arrow", lambda: navigate("new_run")),
    )

    dashboard = service.dashboard()
    counts = dashboard["task_counts"]
    batches = dashboard["batches"]
    schedules = dashboard["schedules"]
    next_schedule = next((item for item in schedules if item.get("enabled") and item.get("next_run_at")), None)

    with ui.row().classes("w-full gap-3"):
        _metric(ui, "待执行", counts.get("pending", 0), "hourglass_empty", "#2563eb")
        _metric(ui, "运行中", counts.get("running", 0), "sync", "#0f766e")
        _metric(ui, "成功", counts.get("success", 0), "check_circle", "#15803d")
        _metric(ui, "失败", counts.get("failed", 0), "error", "#b91c1c")

    startup_holder = ui.column().classes("section-panel w-full p-4 gap-3")

    async def load_startup() -> None:
        startup_holder.clear()
        with startup_holder:
            ui.label("启动检查").classes("font-medium")
            with ui.row().classes("items-center gap-2"):
                ui.spinner(size="sm")
                ui.label("正在检查本地服务、窗口和流程...")
        result = await service.check_startup()
        startup_holder.clear()
        with startup_holder:
            ui.label("启动检查").classes("font-medium")
            with ui.row().classes("w-full gap-3"):
                _check_item(ui, "本地服务", "正常" if result.get("health") else "未连接", bool(result.get("health")))
                total = (result.get("browser_list") or {}).get("total")
                _check_item(ui, "窗口", f"{total if total is not None else 0} 个", bool(total))
                _check_item(ui, "流程", f"{result.get('flow_count', 0)} 个", result.get("flow_count", 0) > 0)
                _check_item(ui, "待恢复", f"{result.get('running_count', 0)} 个运行中", result.get("running_count", 0) == 0)
            if not result.get("health") and result.get("error"):
                with ui.expansion("查看诊断信息", icon="info").classes("w-full"):
                    ui.code(json.dumps(result, ensure_ascii=False, indent=2), language="json").classes("w-full text-xs")

    asyncio.create_task(load_startup())

    with ui.row().classes("w-full gap-4"):
        with ui.column().classes("section-panel grow p-4 gap-3"):
            with ui.row().classes("items-center justify-between"):
                ui.label("最近批次").classes("font-medium")
                ui.button("查看全部", icon="fact_check", on_click=lambda: navigate("results")).props("flat no-caps")
            if batches:
                _batch_table(ui, batches, lambda row: navigate("results", selected_batch_id=row["id"]))
            else:
                _empty_state(ui, "还没有批量运行", "创建第一个批量运行后，这里会显示进度和结果。")
        with ui.column().classes("section-panel w-80 p-4 gap-3"):
            ui.label("下一个计划").classes("font-medium")
            if next_schedule:
                ui.label(next_schedule["name"]).classes("text-base font-medium")
                ui.badge(next_schedule["next_run_at"], color="primary")
                ui.label(f"流程：{next_schedule['flow']}").classes("text-sm text-slate-500")
                ui.button("管理计划", icon="event_repeat", on_click=lambda: navigate("schedules")).props(
                    "flat no-caps"
                )
            else:
                _empty_state(ui, "暂无启用计划", "可以在新建运行时选择定时运行。")

    with ui.column().classes("section-panel w-full p-4 gap-2"):
        ui.label("最近错误").classes("font-medium")
        errors = dashboard["recent_errors"]
        if errors:
            _zh_table(
                ui.table(
                    columns=[
                        {"name": "id", "label": "任务", "field": "id", "align": "left"},
                        {"name": "flow", "label": "流程", "field": "flow", "align": "left"},
                        {"name": "last_error", "label": "错误", "field": "last_error", "align": "left"},
                        {"name": "updated_at", "label": "更新时间", "field": "updated_at", "align": "left"},
                    ],
                    rows=errors,
                    row_key="id",
                )
            ).classes("tight-table w-full")
        else:
            ui.label("暂无最近错误").classes("text-sm text-slate-500")


def _render_new_run(ui: Any, service: UiCoreService, navigate: Callable[..., None]) -> None:
    _toolbar(ui, "新建运行", "选择一个流程和多个窗口，立即运行或保存为计划。")
    flows = service.list_flow_cards()
    if not flows:
        _empty_state(ui, "还没有可用流程", "请先把 YAML/JSON flow 放入 declarative 目录，或把 Python flow 放入 py 目录。")
        return

    selected_browser_ids: set[str] = set()
    input_controls: dict[str, Any] = {}
    windows_cache: list[dict[str, Any]] = []
    visible_window_rows: list[dict[str, Any]] = []
    flow_options = {f"{row['flow_type']}:{row['name']}": row["display_name"] for row in flows}
    selected_flow: Any | None = None

    def current_flow() -> dict[str, Any]:
        assert selected_flow is not None
        flow_type, flow = str(selected_flow.value).split(":", 1)
        return service.get_flow_card(flow_type, flow) or flows[0]

    with ui.column().classes("new-run-form w-full gap-4"):
        with ui.column().classes("section-panel w-full p-4 gap-4"):
            _step_header(ui, 1, "选择流程", "先选要在窗口里执行的自动化流程。")
            selected_flow = ui.select(flow_options, value=next(iter(flow_options)), label="流程").props(
                "outlined"
            ).classes("w-full max-w-2xl")
            flow_detail = ui.column().classes("soft-panel w-full p-3 gap-2")

            def render_flow_detail() -> None:
                card = current_flow()
                flow_detail.clear()
                with flow_detail:
                    with ui.row().classes("items-center gap-2"):
                        ui.label(card["display_name"]).classes("font-medium")
                        ui.badge(_flow_type_label(card["flow_type"]), color="accent")
                        ui.badge(
                            "可用" if card.get("valid") else "需检查",
                            color="positive" if card.get("valid") else "negative",
                        )
                    ui.label(card.get("description") or "").classes("text-sm text-slate-500")
                    if card.get("warnings"):
                        ui.label("校验警告：" + "；".join(card["warnings"])).classes("text-sm text-amber-700")
                    if card.get("errors"):
                        ui.label("校验错误：" + "；".join(card["errors"])).classes("text-sm text-red-700")
                render_inputs()

            selected_flow.on_value_change(lambda _: render_flow_detail())

        with ui.column().classes("section-panel w-full p-4 gap-4"):
            _step_header(ui, 2, "填写参数", "这些参数会默认应用到所有已选窗口。")
            inputs_holder = ui.column().classes("w-full gap-3")

            def render_inputs() -> None:
                card = current_flow()
                input_controls.clear()
                inputs_holder.clear()
                with inputs_holder:
                    if not card["inputs"]:
                        ui.label("这个流程没有声明参数。").classes("text-sm text-slate-500")
                    for field in card["inputs"]:
                        control = _input_control(ui, field)
                        input_controls[field["name"]] = control

        with ui.column().classes("section-panel w-full p-4 gap-4"):
            with ui.row().classes("w-full items-start justify-between gap-3"):
                _step_header(ui, 3, "选择窗口", "可以搜索窗口，也可以全选当前筛选结果。")
                selected_count = ui.badge("已选 0", color="primary").classes("text-sm")
            with ui.row().classes("w-full gap-3 items-end"):
                search = ui.input("搜索名称、序号、备注").props("outlined dense clearable").classes("grow")
                only_idle = ui.checkbox("只看空闲窗口", value=True)
            table_holder = ui.column().classes("w-full")

            def update_selected_count() -> None:
                selected_count.set_text(f"已选 {len(selected_browser_ids)}")

            def display_rows() -> list[dict[str, Any]]:
                query = str(search.value or "").strip().lower()
                rows = []
                for row in windows_cache:
                    text = " ".join(str(row.get(key) or "") for key in ["seq", "name", "remark", "id"]).lower()
                    if query and query not in text:
                        continue
                    if only_idle.value and row.get("runtime_status") not in {"idle", "unknown", None}:
                        continue
                    rows.append(
                        {
                            "id": str(row["id"]),
                            "seq": row.get("seq") or "",
                            "name": row.get("name") or "未命名",
                            "remark": row.get("remark") or "",
                            "status": _status_label(row.get("runtime_status")),
                            "pid": row.get("pid") or "",
                        }
                    )
                return rows

            def handle_window_selection(event: Any) -> None:
                selected_browser_ids.clear()
                selected_browser_ids.update(str(row["id"]) for row in event.selection)
                update_selected_count()

            def render_window_table() -> None:
                visible_window_rows[:] = display_rows()
                table_holder.clear()
                with table_holder:
                    if not visible_window_rows:
                        _empty_state(ui, "没有符合条件的窗口", "调整搜索条件，或取消“只看空闲窗口”。")
                        update_selected_count()
                        return
                    table = _zh_table(
                        ui.table(
                            columns=[
                                {"name": "seq", "label": "序号", "field": "seq", "align": "left"},
                                {"name": "name", "label": "名称", "field": "name", "align": "left"},
                                {"name": "remark", "label": "备注", "field": "remark", "align": "left"},
                                {"name": "status", "label": "状态", "field": "status", "align": "left"},
                                {"name": "pid", "label": "PID", "field": "pid", "align": "left"},
                            ],
                            rows=visible_window_rows,
                            row_key="id",
                            selection="multiple",
                            pagination={"rowsPerPage": 8},
                            on_select=handle_window_selection,
                        )
                    ).classes("tight-table window-picker-table w-full")
                    table.selected = [row for row in visible_window_rows if row["id"] in selected_browser_ids]
                    table.update()
                update_selected_count()

            async def load_windows() -> None:
                table_holder.clear()
                with table_holder:
                    with ui.row().classes("items-center gap-2 p-2"):
                        ui.spinner(size="sm")
                        ui.label("正在读取窗口...")
                try:
                    windows_cache[:] = await service.list_browser_windows()
                    render_window_table()
                except Exception as exc:
                    table_holder.clear()
                    with table_holder:
                        ui.label(f"读取窗口失败：{exc}").classes("text-sm text-red-700 p-2")

            def select_visible() -> None:
                selected_browser_ids.update(row["id"] for row in visible_window_rows)
                render_window_table()

            def clear_selection() -> None:
                selected_browser_ids.clear()
                render_window_table()

            with ui.row().classes("gap-2"):
                ui.button("刷新窗口", icon="refresh", on_click=load_windows).props("flat no-caps")
                ui.button("全选当前", icon="done_all", on_click=select_visible).props("flat no-caps")
                ui.button("清空", icon="clear", on_click=clear_selection).props("flat no-caps")
            search.on_value_change(lambda _: render_window_table())
            only_idle.on_value_change(lambda _: render_window_table())
            asyncio.create_task(load_windows())

        with ui.column().classes("section-panel w-full p-4 gap-4"):
            _step_header(ui, 4, "运行方式", "立即运行会创建批次；定时运行会保存计划。")
            with ui.row().classes("w-full gap-3 items-end"):
                batch_name = ui.input("名称", value="").props("outlined").classes("grow")
                mode = ui.select(
                    {
                        "now": "立即运行",
                        "once": "指定时间运行一次",
                        "daily": "每天/工作日运行",
                        "weekly": "每周运行",
                        "interval": "按间隔重复运行",
                        "manual": "保存为手动计划",
                    },
                    value="now",
                    label="方式",
                ).props("outlined").classes("w-56")
                max_retries = ui.number("失败重试", value=service.config.scheduler.max_retries, min=0, max=10).props(
                    "outlined"
                ).classes("w-32")
            schedule_holder = ui.row().classes("w-full gap-3 items-end")

            def render_schedule_fields() -> None:
                schedule_holder.clear()
                with schedule_holder:
                    if mode.value == "once":
                        schedule_holder.run_at = ui.input("运行时间", placeholder="2026-07-03 09:30").props(
                            "outlined"
                        ).classes("w-72")
                    elif mode.value == "daily":
                        schedule_holder.time = ui.input("时间", value="09:00").props("outlined").classes("w-40")
                        schedule_holder.days = ui.select(
                            WEEKDAY_OPTIONS,
                            value=[0, 1, 2, 3, 4],
                            multiple=True,
                            label="运行日",
                        ).props("outlined").classes("w-80")
                    elif mode.value == "weekly":
                        schedule_holder.time = ui.input("时间", value="09:00").props("outlined").classes("w-40")
                        schedule_holder.days = ui.select(
                            WEEKDAY_OPTIONS,
                            value=[0],
                            multiple=True,
                            label="星期",
                        ).props("outlined").classes("w-80")
                    elif mode.value == "interval":
                        schedule_holder.minutes = ui.number("每隔多少分钟", value=60, min=1).props(
                            "outlined"
                        ).classes("w-48")
                    else:
                        ui.label("立即运行会马上创建批次；手动计划会保存配置，之后在计划任务页手动触发。").classes(
                            "text-sm text-slate-500"
                        )

            mode.on_value_change(lambda _: render_schedule_fields())
            render_schedule_fields()

            with ui.expansion("高级：每个窗口不同参数", icon="table_view").classes("w-full"):
                ui.label("可选。填写 JSON：键是窗口 ID，值是该窗口覆盖的参数。").classes("text-sm text-slate-500")
                per_window_text = ui.textarea(
                    "每窗口参数 JSON",
                    placeholder='{"browser-id-1": {"url": "https://example.com"}}',
                ).props("outlined").classes("w-full")

        with ui.column().classes("section-panel w-full p-4 gap-3"):
            with ui.row().classes("w-full items-center justify-between gap-3"):
                with ui.column().classes("gap-1"):
                    ui.label("提交前检查").classes("font-medium")
                    ui.label("检查会验证流程、参数和窗口选择。").classes("text-sm text-slate-500")
                actions_holder = ui.row().classes("gap-2")
            preview_box = ui.column().classes("soft-panel w-full p-3 gap-2")

        def collect_inputs() -> dict[str, Any]:
            values = {}
            for name, control in input_controls.items():
                values[name] = control.value
            return values

        def collect_per_window_inputs() -> dict[str, dict[str, Any]]:
            text = str(per_window_text.value or "").strip()
            if not text:
                return {}
            data = json.loads(text)
            if not isinstance(data, dict):
                raise ValueError("每窗口参数必须是 JSON 对象")
            return data

        def render_preview() -> None:
            card = current_flow()
            preview = service.preview_batch_run(
                flow_type=card["flow_type"],
                flow=card["name"],
                browser_ids=sorted(selected_browser_ids),
                inputs=collect_inputs(),
            )
            preview_box.clear()
            with preview_box:
                if preview["ok"]:
                    ui.label(f"可以提交。将为 {preview['window_count']} 个窗口创建运行任务。").classes(
                        "text-sm text-green-700"
                    )
                else:
                    ui.label("请先处理以下问题：").classes("text-sm font-medium text-red-700")
                for error in preview["errors"]:
                    ui.label(error).classes("text-sm text-red-700")
                for warning in preview["warnings"]:
                    ui.label(warning).classes("text-sm text-amber-700")

        async def submit() -> None:
            try:
                card = current_flow()
                values = collect_inputs()
                per_window_inputs = collect_per_window_inputs()
                browser_ids = sorted(selected_browser_ids)
                options = {"max_retries": int(max_retries.value or 0)}
                if mode.value == "now":
                    result = await service.create_batch_run(
                        name=str(batch_name.value or ""),
                        source="manual",
                        flow_type=card["flow_type"],
                        flow=card["name"],
                        browser_ids=browser_ids,
                        inputs=values,
                        per_window_inputs=per_window_inputs,
                        options=options,
                        run_now=True,
                    )
                    ui.notify("批量运行已启动", color="positive")
                    navigate("results", selected_batch_id=result["id"])
                else:
                    trigger = _collect_trigger(mode.value, schedule_holder)
                    result = service.create_schedule(
                        name=str(batch_name.value or f"{card['display_name']} 计划"),
                        flow_type=card["flow_type"],
                        flow=card["name"],
                        browser_ids=browser_ids,
                        inputs=values,
                        per_window_inputs=per_window_inputs,
                        trigger=trigger,
                        run_options=options,
                        overlap_policy="skip",
                        missed_policy="skip",
                        enabled=mode.value != "manual",
                    )
                    ui.notify("计划已保存", color="positive")
                    navigate("schedules", selected_schedule_id=result["id"])
            except Exception as exc:
                render_preview()
                ui.notify(str(exc), color="negative")

        render_flow_detail()
        render_preview()
        with actions_holder:
            ui.button("检查", icon="rule", on_click=render_preview).props("flat no-caps")
            ui.button("提交", icon="check", on_click=submit).props("unelevated color=primary no-caps")


def _render_schedules(ui: Any, service: UiCoreService, content: Any, navigate: Callable[..., None]) -> None:
    def refresh() -> None:
        content.clear()
        with content:
            _render_schedules(ui, service, content, navigate)

    _toolbar(
        ui,
        "计划任务",
        "查看定时计划，启停计划，或立即触发一次。",
        refresh,
        ("新建计划", "add", lambda: navigate("new_run")),
    )
    schedules = service.list_schedules()
    if not schedules:
        _empty_state(ui, "暂无计划", "在新建运行里选择定时方式，就会保存为计划。")
        return
    with ui.column().classes("w-full gap-3"):
        for schedule in schedules:
            with ui.row().classes("section-panel w-full p-4 items-center justify-between gap-3"):
                with ui.column().classes("gap-1 grow"):
                    with ui.row().classes("items-center gap-2"):
                        ui.label(schedule["name"]).classes("font-medium")
                        ui.badge("启用" if schedule["enabled"] else "停用", color="positive" if schedule["enabled"] else "secondary")
                        ui.badge(_flow_type_label(schedule["flow_type"]), color="accent")
                    ui.label(f"流程：{schedule['flow']} | 窗口：{len(schedule['browser_ids'])} 个").classes(
                        "text-sm text-slate-500"
                    )
                    ui.label(f"下次运行：{schedule.get('next_run_at') or '手动触发'}").classes("text-sm text-slate-500")
                with ui.row().classes("items-center gap-2"):
                    ui.button(
                        icon="play_arrow",
                        on_click=lambda s=schedule: _run_schedule_now(ui, service, s["id"], navigate),
                    ).props("round color=positive").tooltip("立即运行")
                    ui.button(
                        icon="pause" if schedule["enabled"] else "play_circle",
                        on_click=lambda s=schedule: _toggle_schedule(ui, service, s, refresh),
                    ).props("round flat").tooltip("启用/停用")
                    ui.button(
                        icon="delete",
                        on_click=lambda s=schedule: _delete_schedule(ui, service, s["id"], refresh),
                    ).props("round flat color=negative").tooltip("删除")


def _render_results(
    ui: Any,
    service: UiCoreService,
    artifact_dir: Path,
    content: Any,
    state: dict[str, Any],
    navigate: Callable[..., None],
) -> None:
    def refresh() -> None:
        content.clear()
        with content:
            _render_results(ui, service, artifact_dir, content, state, navigate)

    _toolbar(ui, "运行结果", "按批次查看进度、截图和错误。", refresh)
    batches = service.list_batches(limit=100)
    selected_id = state.get("selected_batch_id") or (batches[0]["id"] if batches else None)
    if selected_id:
        state["selected_batch_id"] = selected_id

    with ui.row().classes("w-full gap-4 items-start"):
        with ui.column().classes("section-panel w-96 p-4 gap-3"):
            ui.label("批次").classes("font-medium")
            if batches:
                for batch in batches:
                    selected = batch["id"] == selected_id
                    with ui.row().classes(
                        f"soft-panel w-full p-3 items-center justify-between cursor-pointer {'border-primary' if selected else ''}"
                    ).on("click", lambda _, b=batch: navigate("results", selected_batch_id=b["id"])):
                        with ui.column().classes("gap-1"):
                            ui.label(batch["name"]).classes("font-medium")
                            ui.label(f"{batch['flow']} | {batch['window_count']} 个窗口").classes(
                                "text-xs text-slate-500"
                            )
                        ui.badge(_status_label(batch["status"]), color=_status_color(batch["status"]))
            else:
                _empty_state(ui, "暂无批次", "从新建运行开始创建批量任务。")

        with ui.column().classes("grow gap-4"):
            if not selected_id:
                _empty_state(ui, "请选择批次", "批次详情会显示每个窗口的状态和结果。")
                return
            detail = service.get_batch_detail(str(selected_id))
            batch = detail["batch"]
            counts = batch["counts"]
            with ui.column().classes("section-panel w-full p-4 gap-3"):
                with ui.row().classes("w-full items-start justify-between gap-3"):
                    with ui.column().classes("gap-1"):
                        ui.label(batch["name"]).classes("text-xl font-semibold")
                        ui.label(f"流程：{batch['flow']} | 创建：{batch['created_at']}").classes("text-sm text-slate-500")
                    with ui.row().classes("gap-2"):
                        ui.button(
                            "重跑失败",
                            icon="restart_alt",
                            on_click=lambda: _rerun_failed(ui, service, batch["id"], refresh),
                        ).props("flat no-caps")
                        ui.button(
                            "停止等待项",
                            icon="stop",
                            on_click=lambda: _cancel_batch(ui, service, batch["id"], refresh),
                        ).props("flat color=negative no-caps")
                with ui.row().classes("gap-3"):
                    _mini_count(ui, "等待", counts.get("pending", 0), "#2563eb")
                    _mini_count(ui, "运行中", counts.get("running", 0), "#0f766e")
                    _mini_count(ui, "成功", counts.get("success", 0), "#15803d")
                    _mini_count(ui, "失败", counts.get("failed", 0), "#b91c1c")
                total = max(1, sum(counts.values()))
                done = counts.get("success", 0) + counts.get("failed", 0) + counts.get("cancelled", 0)
                ui.linear_progress(done / total).props("instant-feedback color=primary").classes("w-full")

            with ui.column().classes("section-panel w-full p-4 gap-3"):
                ui.label("窗口明细").classes("font-medium")
                rows = [_task_display_row(task) for task in detail["tasks"]]
                table = _zh_table(
                    ui.table(
                        columns=[
                            {"name": "browser", "label": "窗口", "field": "browser", "align": "left"},
                            {"name": "status", "label": "状态", "field": "status", "align": "left"},
                            {"name": "updated_at", "label": "更新时间", "field": "updated_at", "align": "left"},
                            {"name": "last_error", "label": "错误", "field": "last_error", "align": "left"},
                        ],
                        rows=rows,
                        row_key="id",
                    )
                ).classes("tight-table w-full")
                selected_task_detail = ui.column().classes("soft-panel w-full p-3 gap-2")

                def show_task(event: Any) -> None:
                    row = event.args[1]
                    task = next(item for item in detail["tasks"] if item["id"] == row["id"])
                    selected_task_detail.clear()
                    with selected_task_detail:
                        ui.label(task["id"]).classes("font-medium mono")
                        if task.get("screenshot"):
                            url = _artifact_url(task["screenshot"], artifact_dir)
                            if url:
                                ui.image(url).classes("w-full max-w-3xl border border-slate-200 rounded")
                        outputs = task.get("outputs") or {}
                        if outputs:
                            ui.label("输出").classes("font-medium")
                            ui.code(json.dumps(outputs, ensure_ascii=False, indent=2), language="json").classes(
                                "w-full text-xs"
                            )
                        if task.get("last_error"):
                            ui.label("错误").classes("font-medium")
                            ui.label(str(task["last_error"])).classes("text-sm text-red-700")
                        if task.get("latest_run"):
                            run = task["latest_run"]
                            with ui.expansion("高级：运行记录", icon="receipt_long").classes("w-full"):
                                ui.code(json.dumps(run, ensure_ascii=False, indent=2), language="json").classes(
                                    "w-full text-xs"
                                )

                table.on("rowClick", show_task)
                with selected_task_detail:
                    ui.label("选择一条窗口明细查看截图、输出和运行记录。").classes("text-sm text-slate-500")


def _render_windows(ui: Any, service: UiCoreService, content: Any) -> None:
    table_holder: Any | None = None
    detail_holder: Any | None = None
    search: Any | None = None

    async def refresh() -> None:
        assert table_holder is not None
        assert search is not None
        rows = await service.list_browser_windows()
        query = str(search.value or "").lower().strip()
        if query:
            rows = [
                row
                for row in rows
                if query in " ".join(str(row.get(key) or "") for key in ["seq", "name", "remark", "id"]).lower()
            ]
        table_holder.clear()
        with table_holder:
            table = _zh_table(
                ui.table(
                    columns=[
                        {"name": "seq", "label": "序号", "field": "seq", "align": "left"},
                        {"name": "name", "label": "名称", "field": "name", "align": "left"},
                        {"name": "remark", "label": "备注", "field": "remark", "align": "left"},
                        {"name": "runtime_status", "label": "状态", "field": "runtime_status", "align": "left"},
                        {"name": "pid", "label": "PID", "field": "pid", "align": "left"},
                    ],
                    rows=[_browser_row(row) for row in rows],
                    row_key="id",
                )
            ).classes("tight-table w-full")
            table.on("rowClick", lambda event: show_detail(event.args[1]))

    def show_detail(row: dict[str, Any]) -> None:
        assert detail_holder is not None
        detail_holder.clear()
        with detail_holder:
            ui.label(row.get("name") or f"窗口 {row.get('seq') or ''}").classes("font-medium")
            ui.label(f"序号：{row.get('seq') or '-'}").classes("text-sm text-slate-500")
            ui.label(f"备注：{row.get('remark') or '-'}").classes("text-sm text-slate-500")
            with ui.row().classes("gap-2"):
                ui.button(
                    "打开",
                    icon="open_in_browser",
                    on_click=lambda: _open_browser(ui, service, str(row["id"]), refresh),
                ).props("flat no-caps")
                ui.button(
                    "关闭",
                    icon="close",
                    on_click=lambda: _close_browser(ui, service, str(row["id"]), refresh),
                ).props("flat color=negative no-caps")
            with ui.expansion("高级：窗口 ID", icon="key").classes("w-full"):
                ui.code(str(row["id"]), language="text").classes("w-full text-xs")

    _toolbar(ui, "窗口", "查看和管理比特浏览器窗口。", refresh)
    with ui.row().classes("section-panel w-full p-4 gap-3 items-end"):
        search = ui.input("搜索窗口").props("outlined dense").classes("grow")
        ui.button("搜索", icon="search", on_click=refresh).props("flat no-caps")
    with ui.row().classes("w-full gap-4 items-start"):
        table_holder = ui.column().classes("section-panel grow p-4")
        detail_holder = ui.column().classes("section-panel w-80 p-4 gap-3")
        with detail_holder:
            ui.label("选择一个窗口查看操作。").classes("text-sm text-slate-500")
    asyncio.create_task(refresh())


def _render_flows(ui: Any, service: UiCoreService) -> None:
    _toolbar(ui, "流程库", "查看可用流程、输入项和校验结果。")
    cards = service.list_flow_cards()
    if not cards:
        _empty_state(ui, "还没有流程", "把 YAML/JSON 放到 declarative 目录，或把 Python 文件放到 py 目录。")
        return
    with ui.row().classes("w-full gap-4"):
        for card in cards:
            with ui.column().classes("section-panel flow-card p-4 gap-3"):
                with ui.row().classes("items-center gap-2"):
                    ui.label(card["display_name"]).classes("font-medium")
                    ui.badge(_flow_type_label(card["flow_type"]), color="accent")
                ui.label(card.get("description") or "").classes("text-sm text-slate-500")
                ui.label(f"输入项：{len(card['inputs'])} 个").classes("text-sm text-slate-500")
                if card["inputs"]:
                    for field in card["inputs"]:
                        req = "必填" if field["required"] else "选填"
                        ui.label(f"{field['label']} ({field['type']}，{req})").classes("text-xs text-slate-600")
                if card["flow_type"] == "declarative":
                    ui.badge("校验通过" if card.get("valid") else "校验失败", color="positive" if card.get("valid") else "negative")
                with ui.expansion("高级：源文件", icon="code").classes("w-full"):
                    ui.label(str(card["path"])).classes("mono text-xs")
                    try:
                        ui.code(Path(card["path"]).read_text(encoding="utf-8"), language="yaml").classes("w-full text-xs")
                    except Exception as exc:
                        ui.label(str(exc)).classes("text-sm text-red-700")


def _render_settings(ui: Any, service: UiCoreService, content: Any) -> None:
    def refresh() -> None:
        content.clear()
        with content:
            _render_settings(ui, service, content)

    _toolbar(ui, "设置", "普通设置和高级诊断。", refresh)
    with ui.row().classes("w-full gap-4 items-start"):
        with ui.column().classes("section-panel grow p-4 gap-3"):
            ui.label("运行设置").classes("font-medium")
            settings = service.settings()
            scheduler = settings["scheduler"]
            bitbrowser = settings["bitbrowser"]
            paths = settings["paths"]
            _setting_line(ui, "Local Server", bitbrowser["base_url"])
            _setting_line(ui, "最大并发窗口", scheduler["max_concurrent_windows"])
            _setting_line(ui, "失败重试", scheduler["max_retries"])
            _setting_line(ui, "运行后关闭窗口", "是" if scheduler["close_window_after_task"] else "否")
            _setting_line(ui, "产物目录", paths["artifact_dir"])
        with ui.column().classes("section-panel w-96 p-4 gap-3"):
            ui.label("手动维护").classes("font-medium")
            task_path = ui.input("任务文件路径", value="configs/tasks.example.yaml").props("outlined").classes("w-full")
            replace = ui.checkbox("覆盖已有任务", value=False)

            def import_selected() -> None:
                try:
                    result = service.import_tasks(str(task_path.value), replace=bool(replace.value))
                    ui.notify(f"已导入：新增 {result['created']}，更新 {result['updated']}，跳过 {result['skipped']}")
                except Exception as exc:
                    ui.notify(str(exc), color="negative")

            async def run_pending() -> None:
                await service.start_scheduler()
                ui.notify("调度器已启动")

            async def stop_pending() -> None:
                result = await service.stop_scheduler()
                ui.notify(f"调度器：{_status_label(result['state'])}")

            ui.button("导入任务文件", icon="upload_file", on_click=import_selected).props("flat no-caps")
            ui.button("运行待执行任务", icon="play_arrow", on_click=run_pending).props(
                "flat color=positive no-caps"
            )
            ui.button("停止调度器", icon="stop", on_click=stop_pending).props(
                "flat color=negative no-caps"
            )
            ui.button(
                "重置运行中任务",
                icon="restart_alt",
                on_click=lambda: ui.notify(f"已重置 {service.reset_running()} 个任务"),
            ).props("flat no-caps")

    with ui.expansion("高级诊断：配置 JSON", icon="data_object").classes("section-panel w-full p-2"):
        ui.code(json.dumps(service.settings(), ensure_ascii=False, indent=2), language="json").classes(
            "w-full text-xs"
        )
    with ui.expansion("高级诊断：底层任务", icon="assignment").classes("section-panel w-full p-2"):
        rows = [_task_row(row) for row in service.list_tasks(limit=100)]
        _zh_table(
            ui.table(
                columns=[
                    {"name": "id", "label": "任务", "field": "id", "align": "left"},
                    {"name": "batch_id", "label": "批次", "field": "batch_id", "align": "left"},
                    {"name": "browser_id", "label": "浏览器 ID", "field": "browser_id", "align": "left"},
                    {"name": "flow", "label": "流程", "field": "flow", "align": "left"},
                    {"name": "status", "label": "状态", "field": "status", "align": "left"},
                ],
                rows=rows,
                row_key="id",
            )
        ).classes("tight-table w-full")


def _step_header(ui: Any, number: int, title: str, detail: str) -> None:
    with ui.row().classes("items-start gap-3"):
        ui.label(str(number)).classes("step-index")
        with ui.column().classes("gap-0"):
            ui.label(title).classes("step-title")
            ui.label(detail).classes("text-sm text-slate-500")


def _metric(ui: Any, label: str, value: Any, icon: str, color: str) -> None:
    with ui.row().classes("section-panel metric p-4 items-center gap-3"):
        ui.icon(icon, color=color).classes("text-3xl")
        with ui.column().classes("gap-1"):
            ui.label(str(value)).classes("value")
            ui.label(label).classes("text-xs text-slate-500")


def _mini_count(ui: Any, label: str, value: Any, color: str) -> None:
    with ui.row().classes("soft-panel p-2 items-center gap-2"):
        ui.element("span").classes("status-dot").style(f"background:{color}")
        ui.label(f"{label} {value}").classes("text-sm")


def _check_item(ui: Any, title: str, detail: str, ok: bool) -> None:
    with ui.row().classes("soft-panel grow p-3 items-center gap-2"):
        ui.icon("check_circle" if ok else "error", color="positive" if ok else "negative")
        with ui.column().classes("gap-0"):
            ui.label(title).classes("font-medium")
            ui.label(detail).classes("text-xs text-slate-500")


def _input_control(ui: Any, field: dict[str, Any]) -> Any:
    label = field["label"] + (" *" if field["required"] else "")
    value = field.get("default")
    field_type = field.get("type")
    if field_type == "boolean":
        return ui.checkbox(label, value=bool(value))
    if field_type == "number":
        return ui.number(label, value=value).props("outlined").classes("w-full max-w-md")
    if field_type == "choice" and field.get("choices"):
        return ui.select(field["choices"], value=value, label=label).props("outlined").classes("w-full max-w-md")
    if field_type == "multiline":
        return ui.textarea(label, value=value or "", placeholder=field.get("placeholder") or "").props("outlined").classes(
            "w-full"
        )
    return ui.input(label, value=value or "", placeholder=field.get("placeholder") or "").props("outlined").classes(
        "w-full max-w-xl"
    )


def _collect_trigger(mode: str, holder: Any) -> dict[str, Any]:
    if mode == "once":
        run_at = str(getattr(holder, "run_at").value or "").replace(" ", "T")
        return {"type": "once", "run_at": run_at}
    if mode == "daily":
        return {
            "type": "daily",
            "time": str(getattr(holder, "time").value or "09:00"),
            "days": list(getattr(holder, "days").value or list(range(7))),
        }
    if mode == "weekly":
        return {
            "type": "weekly",
            "time": str(getattr(holder, "time").value or "09:00"),
            "days": list(getattr(holder, "days").value or []),
        }
    if mode == "interval":
        return {"type": "interval", "minutes": int(getattr(holder, "minutes").value or 60)}
    return {"type": "manual"}


def _batch_table(ui: Any, batches: list[dict[str, Any]], on_select: Callable[[dict[str, Any]], None]) -> None:
    table = _zh_table(
        ui.table(
            columns=[
                {"name": "name", "label": "名称", "field": "name", "align": "left"},
                {"name": "flow", "label": "流程", "field": "flow", "align": "left"},
                {"name": "window_count", "label": "窗口数", "field": "window_count", "align": "left"},
                {"name": "status", "label": "状态", "field": "status", "align": "left"},
                {"name": "created_at", "label": "创建时间", "field": "created_at", "align": "left"},
            ],
            rows=[_batch_row(row) for row in batches],
            row_key="id",
        )
    ).classes("tight-table w-full")
    table.on("rowClick", lambda event: on_select(event.args[1]))


def _batch_row(row: dict[str, Any]) -> dict[str, Any]:
    display = dict(row)
    display["status"] = _status_label(display.get("status"))
    return display


def _browser_row(row: dict[str, Any]) -> dict[str, Any]:
    display = dict(row)
    display["runtime_status"] = _status_label(display.get("runtime_status"))
    return display


def _task_row(row: dict[str, Any]) -> dict[str, Any]:
    display = dict(row)
    display["flow_type"] = _flow_type_label(display.get("flow_type"))
    display["status"] = _status_label(display.get("status"))
    return display


def _task_display_row(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": task["id"],
        "browser": _short_text(task.get("browser_id"), 18),
        "status": _status_label(task.get("status")),
        "updated_at": task.get("updated_at"),
        "last_error": _short_text(task.get("last_error"), 100),
    }


def _short_text(value: Any, max_length: int) -> str:
    text = "" if value is None else str(value)
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 1]}..."


def _status_label(value: Any) -> str:
    text = "" if value is None else str(value)
    return STATUS_LABELS.get(text, text)


def _flow_type_label(value: Any) -> str:
    text = "" if value is None else str(value)
    return FLOW_TYPE_LABELS.get(text, text)


def _status_color(status: Any) -> str:
    return {
        "success": "positive",
        "running": "primary",
        "pending": "secondary",
        "failed": "negative",
        "partial_failed": "warning",
        "cancelled": "secondary",
    }.get(str(status), "secondary")


async def _run_schedule_now(
    ui: Any,
    service: UiCoreService,
    schedule_id: str,
    navigate: Callable[..., None],
) -> None:
    try:
        result = await service.run_schedule_now(schedule_id)
        ui.notify("计划已手动触发", color="positive")
        navigate("results", selected_batch_id=result["id"])
    except Exception as exc:
        ui.notify(str(exc), color="negative")


def _toggle_schedule(ui: Any, service: UiCoreService, schedule: dict[str, Any], refresh: Callable[[], None]) -> None:
    try:
        service.set_schedule_enabled(schedule["id"], not schedule["enabled"])
        refresh()
    except Exception as exc:
        ui.notify(str(exc), color="negative")


def _delete_schedule(ui: Any, service: UiCoreService, schedule_id: str, refresh: Callable[[], None]) -> None:
    try:
        service.delete_schedule(schedule_id)
        refresh()
    except Exception as exc:
        ui.notify(str(exc), color="negative")


async def _rerun_failed(ui: Any, service: UiCoreService, batch_id: str, refresh: Callable[[], None]) -> None:
    try:
        result = await service.rerun_failed_batch(batch_id)
        ui.notify(f"已重跑 {result['count']} 个失败窗口")
        refresh()
    except Exception as exc:
        ui.notify(str(exc), color="negative")


async def _cancel_batch(ui: Any, service: UiCoreService, batch_id: str, refresh: Callable[[], None]) -> None:
    try:
        result = await service.cancel_batch(batch_id)
        ui.notify(f"已停止 {result['count']} 个等待任务")
        refresh()
    except Exception as exc:
        ui.notify(str(exc), color="negative")


async def _open_browser(ui: Any, service: UiCoreService, browser_id: str, refresh: Callable[[], Any]) -> None:
    try:
        await service.open_browser(browser_id)
        ui.notify("窗口已打开", color="positive")
        await refresh()
    except Exception as exc:
        ui.notify(str(exc), color="negative")


async def _close_browser(ui: Any, service: UiCoreService, browser_id: str, refresh: Callable[[], Any]) -> None:
    try:
        await service.close_browser(browser_id)
        ui.notify("窗口已关闭", color="positive")
        await refresh()
    except Exception as exc:
        ui.notify(str(exc), color="negative")


def _artifact_url(path: str | None, artifact_dir: Path) -> str | None:
    if not path:
        return None
    try:
        rel = Path(path).resolve().relative_to(artifact_dir.resolve())
        return f"/artifacts/{rel.as_posix()}"
    except Exception:
        return None


def _zh_table(table: Any) -> Any:
    table.props["no-data-label"] = "暂无数据"
    return table


def _empty_state(ui: Any, title: str, detail: str) -> None:
    with ui.column().classes("soft-panel w-full p-4 gap-1"):
        ui.label(title).classes("font-medium")
        ui.label(detail).classes("text-sm text-slate-500")


def _setting_line(ui: Any, label: str, value: Any) -> None:
    with ui.row().classes("w-full items-center justify-between border-b border-slate-100 py-2"):
        ui.label(label).classes("text-sm text-slate-500")
        ui.label(str(value)).classes("text-sm font-medium mono" if "/" in str(value) else "text-sm font-medium")
