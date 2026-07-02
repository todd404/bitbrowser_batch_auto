from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable

from bitbrowser_auto.config import AppConfig

from .core import UiCoreService


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
        state: dict[str, Any] = {"page": "dashboard"}
        content: Any | None = None

        def navigate(page: str) -> None:
            state["page"] = page
            render()

        with ui.row().classes("app-shell w-full min-h-screen items-stretch no-wrap"):
            with ui.column().classes("sidebar shrink-0 gap-1 p-3"):
                ui.label(config.ui.title).classes("text-lg font-semibold mb-3")
                _nav_button(ui, "Dashboard", "dashboard", "dashboard", navigate)
                _nav_button(ui, "Browser Windows", "language", "browsers", navigate)
                _nav_button(ui, "Tasks", "assignment", "tasks", navigate)
                _nav_button(ui, "Runs", "history", "runs", navigate)
                _nav_button(ui, "Flows", "schema", "flows", navigate)
                _nav_button(ui, "Settings", "settings", "settings", navigate)
            content = ui.column().classes("content grow gap-4")

        def render() -> None:
            assert content is not None
            content.clear()
            with content:
                page = state["page"]
                if page == "dashboard":
                    _render_dashboard(ui, service, content)
                elif page == "browsers":
                    _render_browsers(ui, service, content)
                elif page == "tasks":
                    _render_tasks(ui, service, content)
                elif page == "runs":
                    _render_runs(ui, service, config.paths.artifact_dir, content)
                elif page == "flows":
                    _render_flows(ui, service, content)
                elif page == "settings":
                    _render_settings(ui, service)

        render()
        ui.timer(3.0, lambda: asyncio.create_task(_poll_scheduler(ui, service)), active=True)

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
    ui.colors(primary="#2563eb", secondary="#475569", accent="#0f766e", positive="#15803d", negative="#b91c1c")
    ui.add_css(
        """
        html, body { min-height: 100%; }
        body { background: #f8fafc; color: #0f172a; }
        .nicegui-content { padding: 0 !important; gap: 0 !important; max-width: none !important; }
        .app-shell { min-height: 100vh; }
        .sidebar { background: #0f172a; color: white; width: 232px; }
        .sidebar .q-btn { justify-content: flex-start; }
        .content { min-width: 0; padding: 18px 22px 28px; }
        .section-panel { background: white; border: 1px solid #e2e8f0; border-radius: 8px; }
        .metric { min-width: 140px; border-left: 3px solid #2563eb; }
        .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace; }
        .tight-table .q-table__top, .tight-table .q-table__bottom { padding: 8px 12px; }
        """
    )


def _nav_button(ui: Any, label: str, icon: str, page: str, navigate: Callable[[str], None]) -> None:
    ui.button(label, icon=icon, on_click=lambda: navigate(page)).props("flat color=white").classes("w-full")


def _toolbar(ui: Any, title: str, refresh: Callable[[], None] | None = None) -> None:
    with ui.row().classes("w-full items-center justify-between"):
        ui.label(title).classes("text-xl font-semibold")
        if refresh:
            ui.button(icon="refresh", on_click=refresh).props("round flat").tooltip("Refresh")


def _render_dashboard(ui: Any, service: UiCoreService, content: Any) -> None:
    async def refresh() -> None:
        content.clear()
        with content:
            _render_dashboard(ui, service, content)

    _toolbar(ui, "Dashboard", lambda: asyncio.create_task(refresh()))
    dashboard = service.dashboard()
    counts = dashboard["task_counts"]
    with ui.row().classes("w-full gap-3"):
        _metric(ui, "Pending", counts.get("pending", 0))
        _metric(ui, "Running", counts.get("running", 0))
        _metric(ui, "Success", counts.get("success", 0))
        _metric(ui, "Failed", counts.get("failed", 0))

    async def check() -> None:
        result = await service.check_environment()
        status_label.set_text("OK" if result.get("health") else "FAILED")
        status_detail.set_content(json.dumps(result, ensure_ascii=False, indent=2))

    with ui.column().classes("section-panel w-full gap-3 p-4"):
        with ui.row().classes("items-center gap-2"):
            ui.label("Local Server").classes("font-medium")
            status_label = ui.badge("unchecked", color="secondary")
            ui.button(icon="health_and_safety", on_click=check).props("round flat").tooltip("Check Local Server")
        status_detail = ui.code("", language="json").classes("w-full text-xs")

    with ui.column().classes("section-panel w-full gap-2 p-4"):
        ui.label("Recent Errors").classes("font-medium")
        rows = dashboard["recent_errors"]
        if rows:
            ui.table(
                columns=[
                    {"name": "id", "label": "Task", "field": "id", "align": "left"},
                    {"name": "flow", "label": "Flow", "field": "flow", "align": "left"},
                    {"name": "last_error", "label": "Error", "field": "last_error", "align": "left"},
                    {"name": "updated_at", "label": "Updated", "field": "updated_at", "align": "left"},
                ],
                rows=rows,
                row_key="id",
            ).classes("tight-table w-full")
        else:
            ui.label("No recent errors").classes("text-sm text-slate-500")


def _metric(ui: Any, label: str, value: Any) -> None:
    with ui.column().classes("section-panel metric p-3"):
        ui.label(str(value)).classes("text-2xl font-semibold")
        ui.label(label).classes("text-xs uppercase text-slate-500")


def _render_browsers(ui: Any, service: UiCoreService, content: Any) -> None:
    table_holder: Any | None = None

    async def refresh() -> None:
        assert table_holder is not None
        rows = await service.list_browser_windows()
        table_holder.clear()
        with table_holder:
            table = ui.table(
                columns=[
                    {"name": "seq", "label": "Seq", "field": "seq", "align": "left"},
                    {"name": "name", "label": "Name", "field": "name", "align": "left"},
                    {"name": "id", "label": "Browser ID", "field": "id", "align": "left"},
                    {"name": "pid", "label": "PID", "field": "pid", "align": "left"},
                    {"name": "runtime_status", "label": "Runtime", "field": "runtime_status", "align": "left"},
                    {"name": "current_task_id", "label": "Task", "field": "current_task_id", "align": "left"},
                ],
                rows=rows,
                row_key="id",
            ).classes("tight-table w-full")
            table.add_slot(
                "body-cell-id",
                '<q-td :props="props"><span class="mono">{{ props.value }}</span></q-td>',
            )

    _toolbar(ui, "Browser Windows", lambda: asyncio.create_task(refresh()))
    with ui.row().classes("section-panel w-full items-end gap-2 p-4"):
        browser_id = ui.input("Browser ID").classes("grow")

        async def open_selected() -> None:
            if browser_id.value:
                await service.open_browser(str(browser_id.value))
                await refresh()

        async def close_selected() -> None:
            if browser_id.value:
                await service.close_browser(str(browser_id.value))
                await refresh()

        ui.button(icon="open_in_browser", on_click=open_selected).props("round").tooltip("Open")
        ui.button(icon="close", on_click=close_selected).props("round color=negative").tooltip("Close")
    table_holder = ui.column().classes("w-full")
    asyncio.create_task(refresh())


def _render_tasks(ui: Any, service: UiCoreService, content: Any) -> None:
    table_holder: Any | None = None
    status_filter: Any | None = None

    def refresh() -> None:
        assert table_holder is not None
        assert status_filter is not None
        rows = service.list_tasks(status=status_filter.value or None, limit=100)
        table_holder.clear()
        with table_holder:
            ui.table(
                columns=[
                    {"name": "id", "label": "Task", "field": "id", "align": "left"},
                    {"name": "browser_id", "label": "Browser", "field": "browser_id", "align": "left"},
                    {"name": "flow_type", "label": "Type", "field": "flow_type", "align": "left"},
                    {"name": "flow", "label": "Flow", "field": "flow", "align": "left"},
                    {"name": "status", "label": "Status", "field": "status", "align": "left"},
                    {"name": "retry_count", "label": "Retries", "field": "retry_count", "align": "left"},
                    {"name": "updated_at", "label": "Updated", "field": "updated_at", "align": "left"},
                ],
                rows=rows,
                row_key="id",
            ).classes("tight-table w-full")

    _toolbar(ui, "Tasks", refresh)
    with ui.row().classes("section-panel w-full items-end gap-2 p-4"):
        task_path = ui.input("Task file path", value="configs/tasks.example.yaml").classes("grow")
        replace = ui.checkbox("Replace", value=False)
        status_filter = ui.select(
            ["", "pending", "running", "success", "failed", "cancelled"], value="", label="Status"
        ).classes("w-40")

        def import_selected() -> None:
            try:
                result = service.import_tasks(str(task_path.value), replace=bool(replace.value))
                ui.notify(f"created {result['created']}, updated {result['updated']}, skipped {result['skipped']}")
                refresh()
            except Exception as exc:
                ui.notify(str(exc), color="negative")

        async def run_pending() -> None:
            await service.start_scheduler()
            ui.notify("scheduler started")

        async def stop_pending() -> None:
            result = await service.stop_scheduler()
            ui.notify(f"scheduler {result['state']}")

        def reset_running() -> None:
            count = service.reset_running()
            ui.notify(f"reset {count}")
            refresh()

        ui.button(icon="upload_file", on_click=import_selected).props("round").tooltip("Import")
        ui.button(icon="play_arrow", on_click=run_pending).props("round color=positive").tooltip("Run Pending")
        ui.button(icon="stop", on_click=stop_pending).props("round color=negative").tooltip("Stop Scheduler")
        ui.button(icon="restart_alt", on_click=reset_running).props("round flat").tooltip("Reset Running")
        status_filter.on("update:model-value", lambda _: refresh())
    table_holder = ui.column().classes("w-full")
    refresh()


def _render_runs(ui: Any, service: UiCoreService, artifact_dir: Path, content: Any) -> None:
    detail: Any | None = None
    table_holder: Any | None = None

    def artifact_url(path: str | None) -> str | None:
        if not path:
            return None
        try:
            rel = Path(path).resolve().relative_to(artifact_dir.resolve())
            return f"/artifacts/{rel.as_posix()}"
        except Exception:
            return None

    def show_run(row: dict[str, Any]) -> None:
        assert detail is not None
        detail.clear()
        with detail:
            ui.label(row.get("id", "")).classes("font-medium mono")
            run_json = service.read_json_file(str(Path(row.get("artifact_dir") or "") / "run.json"))
            trace_json = service.read_json_file(str(row.get("trace_path") or ""))
            ui.code(json.dumps(run_json, ensure_ascii=False, indent=2), language="json").classes("w-full text-xs")
            final = None
            outputs = run_json.get("outputs") if isinstance(run_json, dict) else {}
            if isinstance(outputs, dict):
                final = next((value for key, value in outputs.items() if "screenshot" in key), None)
            final = final or run_json.get("error_screenshot")
            url = artifact_url(final)
            if url:
                ui.image(url).classes("w-full max-w-3xl border border-slate-200 rounded")
            with ui.expansion("Trace JSON", icon="receipt_long").classes("w-full"):
                ui.code(json.dumps(trace_json, ensure_ascii=False, indent=2), language="json").classes("w-full text-xs")

    def refresh() -> None:
        assert table_holder is not None
        rows = service.list_runs(limit=100)
        table_holder.clear()
        with table_holder:
            table = ui.table(
                columns=[
                    {"name": "started_at", "label": "Started", "field": "started_at", "align": "left"},
                    {"name": "task_id", "label": "Task", "field": "task_id", "align": "left"},
                    {"name": "browser_id", "label": "Browser", "field": "browser_id", "align": "left"},
                    {"name": "status", "label": "Status", "field": "status", "align": "left"},
                    {"name": "artifact_dir", "label": "Artifacts", "field": "artifact_dir", "align": "left"},
                ],
                rows=rows,
                row_key="id",
            ).classes("tight-table w-full")
            table.on("rowClick", lambda event: show_run(event.args[1]))

    _toolbar(ui, "Runs", refresh)
    table_holder = ui.column().classes("w-full")
    detail = ui.column().classes("section-panel w-full p-4 gap-3")
    with detail:
        ui.label("Select a run to inspect artifacts and trace").classes("text-sm text-slate-500")
    refresh()


def _render_flows(ui: Any, service: UiCoreService, content: Any) -> None:
    result_box_ref: dict[str, Any] = {}

    def refresh() -> None:
        content.clear()
        with content:
            _render_flows(ui, service, content)

    _toolbar(ui, "Flows", refresh)
    flows = service.list_flows()
    with ui.row().classes("w-full gap-4"):
        _flow_table(ui, "Declarative", flows["declarative"], service, result_box_ref)
        _flow_table(ui, "Python", flows["python"], service, result_box_ref)
    result_box = ui.column().classes("section-panel w-full p-4")
    result_box_ref["box"] = result_box
    with result_box:
        ui.label("Validation").classes("font-medium")


def _flow_table(
    ui: Any, title: str, rows: list[dict[str, Any]], service: UiCoreService, result_box_ref: dict[str, Any]
) -> None:
    with ui.column().classes("section-panel grow p-4 gap-2"):
        ui.label(title).classes("font-medium")
        table = ui.table(
            columns=[
                {"name": "name", "label": "Name", "field": "name", "align": "left"},
                {"name": "type", "label": "Type", "field": "type", "align": "left"},
                {"name": "size", "label": "Size", "field": "size", "align": "left"},
            ],
            rows=rows,
            row_key="path",
        ).classes("tight-table w-full")

        def select(event: Any) -> None:
            row = event.args[1]
            result_box = result_box_ref["box"]
            result_box.clear()
            with result_box:
                ui.label(row["path"]).classes("font-medium mono")
                if row["type"] in {".yaml", ".yml", ".json"}:
                    try:
                        result = service.validate_flow(row["path"])
                    except Exception as exc:
                        result = {"status": "failed", "errors": [str(exc)]}
                    ui.code(json.dumps(result, ensure_ascii=False, indent=2), language="json").classes("w-full text-xs")
                else:
                    ui.code(Path(row["path"]).read_text(encoding="utf-8"), language="python").classes("w-full text-xs")

        table.on("rowClick", select)


def _render_settings(ui: Any, service: UiCoreService) -> None:
    _toolbar(ui, "Settings")
    ui.code(json.dumps(service.settings(), ensure_ascii=False, indent=2), language="json").classes(
        "section-panel w-full text-xs p-4"
    )


async def _poll_scheduler(ui: Any, service: UiCoreService) -> None:
    status = await service.poll_scheduler()
    if status.get("state") in {"finished", "failed", "cancelled"}:
        if not status.get("_notified"):
            status["_notified"] = True
            ui.notify(f"scheduler {status['state']}")
