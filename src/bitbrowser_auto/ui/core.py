from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from bitbrowser_auto.bitbrowser import BitBrowserClient
from bitbrowser_auto.config import AppConfig
from bitbrowser_auto.runner.flow_loader import load_declarative_flow, load_tasks
from bitbrowser_auto.runner.flow_validator import FlowValidator
from bitbrowser_auto.runner.scheduler import Scheduler
from bitbrowser_auto.runner.service import task_from_mapping
from bitbrowser_auto.storage import Storage


class UiCoreService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.scheduler_task: asyncio.Task[dict[str, Any]] | None = None
        self.scheduler_status: dict[str, Any] = {"state": "idle"}

    async def check_startup(self) -> dict[str, Any]:
        result = await self.check_environment()
        flows = self.list_flow_cards()
        result["flow_count"] = len(flows)
        with self._storage() as storage:
            result["pending_count"] = storage.count_tasks(status="pending")
            result["running_count"] = storage.count_tasks(status="running")
            result["schedule_count"] = len(storage.list_schedules())
        return result

    async def check_environment(self) -> dict[str, Any]:
        client = self._client()
        result: dict[str, Any] = {"base_url": self.config.bitbrowser.base_url}
        try:
            await client.health()
            listing = await client.list_browsers(page=0, page_size=20)
            result["health"] = True
            result["browser_list"] = _summarize_browser_list(listing)
        except Exception as exc:
            result["health"] = False
            result["error"] = str(exc)
        return result

    async def list_browser_windows(self) -> list[dict[str, Any]]:
        client = self._client()
        listing = await client.list_browsers(page=0, page_size=100)
        data = listing.get("data") if isinstance(listing, dict) else {}
        items = []
        if isinstance(data, dict):
            raw_items = data.get("list") or data.get("items") or data.get("data") or []
            if isinstance(raw_items, list):
                items = raw_items

        runtimes = {row["browser_id"]: row for row in self.browser_runtime()}
        alive = await client.pids_alive([str(item.get("id")) for item in items if item.get("id")])
        rows = []
        for item in items:
            if not isinstance(item, dict):
                continue
            browser_id = str(item.get("id") or "")
            runtime = runtimes.get(browser_id, {})
            rows.append(
                {
                    "id": browser_id,
                    "seq": item.get("seq"),
                    "name": item.get("name") or "",
                    "remark": item.get("remark") or "",
                    "group_id": item.get("groupId") or item.get("group_id") or "",
                    "opened": item.get("opened"),
                    "pid": alive.get(browser_id) or runtime.get("pid"),
                    "runtime_status": runtime.get("status", "unknown"),
                    "current_task_id": runtime.get("current_task_id"),
                    "updated_at": runtime.get("updated_at"),
                }
            )
        return rows

    async def open_browser(self, browser_id: str) -> dict[str, Any]:
        opened = await self._client().open_browser(browser_id)
        with self._storage() as storage:
            storage.update_browser_runtime(browser_id, status="idle", opened=opened)
        return opened

    async def close_browser(self, browser_id: str) -> None:
        await self._client().close_browser(browser_id)
        with self._storage() as storage:
            storage.update_browser_runtime(browser_id, status="idle")

    def dashboard(self) -> dict[str, Any]:
        with self._storage() as storage:
            batches = storage.list_batch_runs(limit=5)
            schedules = storage.list_schedules()
            return {
                "task_counts": storage.task_status_counts(),
                "running": storage.count_tasks(status="running"),
                "recent_errors": storage.recent_errors(limit=5),
                "scheduler": dict(self.scheduler_status),
                "batches": batches,
                "schedules": schedules,
            }

    def list_tasks(self, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._storage() as storage:
            return storage.list_tasks(status=status or None, limit=limit)

    def import_tasks(self, path: str, *, replace: bool = False) -> dict[str, Any]:
        raw_tasks = load_tasks(Path(path))
        tasks = [task_from_mapping(raw) for raw in raw_tasks]
        with self._storage() as storage:
            return storage.import_tasks(tasks, replace=replace)

    def reset_running(self, status: str = "pending") -> int:
        with self._storage() as storage:
            return storage.reset_running(status=status)

    def list_runs(self, *, task_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._storage() as storage:
            return storage.list_task_runs(task_id=task_id or None, limit=limit)

    def browser_runtime(self) -> list[dict[str, Any]]:
        with self._storage() as storage:
            return storage.list_browser_runtime()

    def list_flows(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "declarative": _flow_files(self.config.paths.declarative_flow_dir, {".yaml", ".yml", ".json"}),
            "python": _flow_files(self.config.paths.python_flow_dir, {".py"}),
        }

    def list_flow_cards(self) -> list[dict[str, Any]]:
        cards = []
        for row in self.list_flows()["declarative"]:
            meta = _declarative_flow_meta(Path(row["path"]))
            cards.append({**row, **meta, "flow_type": "declarative"})
        for row in self.list_flows()["python"]:
            meta = _python_flow_meta(Path(row["path"]))
            cards.append({**row, **meta, "flow_type": "python"})
        return sorted(cards, key=lambda item: (str(item["flow_type"]), str(item["display_name"])))

    def get_flow_card(self, flow_type: str, flow: str) -> dict[str, Any] | None:
        for card in self.list_flow_cards():
            if card["flow_type"] == flow_type and card["name"] == flow:
                return card
        return None

    def validate_flow(self, name_or_path: str) -> dict[str, Any]:
        flow = load_declarative_flow(self.config.paths.declarative_flow_dir, name_or_path)
        result = FlowValidator().validate(flow)
        return {
            "status": "success" if result.ok else "failed",
            "ok": result.ok,
            "errors": result.errors,
            "warnings": result.warnings,
        }

    def read_json_file(self, path: str) -> dict[str, Any]:
        file_path = Path(path)
        if not file_path.exists():
            return {"error": f"not found: {path}"}
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"error": str(exc)}

    def preview_batch_run(
        self,
        *,
        flow_type: str,
        flow: str,
        browser_ids: list[str],
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        errors = []
        warnings = []
        card = self.get_flow_card(flow_type, flow)
        if not card:
            errors.append("请选择流程")
        if not browser_ids:
            errors.append("请选择至少一个窗口")
        if card:
            for field in card["inputs"]:
                if field.get("required") and _blank(inputs.get(field["name"])):
                    errors.append(f"请填写：{field['label']}")
            if flow_type == "declarative":
                validation = self.validate_flow(str(card["path"]))
                if not validation["ok"]:
                    errors.extend(validation["errors"])
                warnings.extend(validation.get("warnings", []))
        busy = self._busy_browser_ids()
        busy_selected = [browser_id for browser_id in browser_ids if browser_id in busy]
        if busy_selected:
            warnings.append(f"{len(busy_selected)} 个窗口正在运行任务，提交后会等待空闲或由调度器跳过冲突。")
        return {
            "ok": not errors,
            "errors": errors,
            "warnings": warnings,
            "window_count": len(browser_ids),
            "flow": flow,
        }

    async def create_batch_run(
        self,
        *,
        name: str,
        source: str,
        flow_type: str,
        flow: str,
        browser_ids: list[str],
        inputs: dict[str, Any],
        per_window_inputs: dict[str, dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        schedule_id: str | None = None,
        run_now: bool = True,
    ) -> dict[str, Any]:
        preview = self.preview_batch_run(flow_type=flow_type, flow=flow, browser_ids=browser_ids, inputs=inputs)
        if not preview["ok"]:
            raise ValueError("；".join(preview["errors"]))
        with self._storage() as storage:
            result = storage.create_batch_run(
                name=name or _default_batch_name(flow),
                source=source,
                flow_type=flow_type,
                flow=flow,
                browser_ids=browser_ids,
                inputs=inputs,
                per_window_inputs=per_window_inputs,
                options=options,
                schedule_id=schedule_id,
            )
            storage.refresh_batch_status(result["id"])
        if run_now:
            await self.start_scheduler(batch_id=result["id"])
        return result

    def list_batches(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._storage() as storage:
            return storage.list_batch_runs(limit=limit)

    def get_batch_detail(self, batch_id: str) -> dict[str, Any]:
        with self._storage() as storage:
            batch = storage.refresh_batch_status(batch_id) or storage.get_batch_run(batch_id)
            if not batch:
                raise FileNotFoundError(f"batch not found: {batch_id}")
            tasks = storage.list_tasks_for_batch(batch_id)
            runs = storage.list_task_runs_for_batch(batch_id)
        latest_runs: dict[str, dict[str, Any]] = {}
        for run in runs:
            latest_runs.setdefault(str(run["task_id"]), run)
        for task in tasks:
            run = latest_runs.get(str(task["id"]))
            task["latest_run"] = run
            if run:
                run_json = self.read_json_file(str(Path(run.get("artifact_dir") or "") / "run.json"))
                task["outputs"] = run_json.get("outputs") if isinstance(run_json, dict) else {}
                task["screenshot"] = _pick_screenshot(run_json)
        return {"batch": batch, "tasks": tasks, "runs": runs}

    async def rerun_failed_batch(self, batch_id: str) -> dict[str, Any]:
        with self._storage() as storage:
            count = storage.rerun_failed_tasks(batch_id)
        if count:
            await self.start_scheduler()
        return {"count": count}

    async def cancel_batch(self, batch_id: str) -> dict[str, Any]:
        with self._storage() as storage:
            count = storage.cancel_batch(batch_id)
        return {"count": count}

    def list_schedules(self) -> list[dict[str, Any]]:
        with self._storage() as storage:
            return storage.list_schedules()

    def create_schedule(
        self,
        *,
        name: str,
        flow_type: str,
        flow: str,
        browser_ids: list[str],
        inputs: dict[str, Any],
        per_window_inputs: dict[str, dict[str, Any]] | None,
        trigger: dict[str, Any],
        run_options: dict[str, Any],
        overlap_policy: str,
        missed_policy: str,
        enabled: bool = True,
    ) -> dict[str, Any]:
        preview = self.preview_batch_run(flow_type=flow_type, flow=flow, browser_ids=browser_ids, inputs=inputs)
        if not preview["ok"]:
            raise ValueError("；".join(preview["errors"]))
        next_run_at = _next_run_at(trigger)
        with self._storage() as storage:
            return storage.create_schedule(
                name=name or f"{flow} 计划",
                enabled=enabled,
                flow_type=flow_type,
                flow=flow,
                browser_ids=browser_ids,
                inputs=inputs,
                per_window_inputs=per_window_inputs,
                trigger=trigger,
                run_options=run_options,
                overlap_policy=overlap_policy,
                missed_policy=missed_policy,
                next_run_at=next_run_at,
            )

    async def run_schedule_now(self, schedule_id: str) -> dict[str, Any]:
        with self._storage() as storage:
            schedule = storage.get_schedule(schedule_id)
        if not schedule:
            raise FileNotFoundError(f"schedule not found: {schedule_id}")
        return await self.create_batch_run(
            name=f"{schedule['name']} 手动运行",
            source="schedule",
            flow_type=schedule["flow_type"],
            flow=schedule["flow"],
            browser_ids=schedule["browser_ids"],
            inputs=schedule["inputs"],
            per_window_inputs=schedule["per_window_inputs"],
            options=schedule["run_options"],
            schedule_id=schedule_id,
            run_now=True,
        )

    def set_schedule_enabled(self, schedule_id: str, enabled: bool) -> None:
        with self._storage() as storage:
            schedule = storage.get_schedule(schedule_id)
            if not schedule:
                raise FileNotFoundError(f"schedule not found: {schedule_id}")
            next_run_at = _next_run_at(schedule["trigger"]) if enabled else None
            storage.set_schedule_enabled(schedule_id, enabled, next_run_at=next_run_at)

    def delete_schedule(self, schedule_id: str) -> int:
        with self._storage() as storage:
            return storage.delete_schedule(schedule_id)

    async def tick_schedules(self) -> dict[str, Any]:
        now = _now_iso()
        created = 0
        skipped = 0
        batch_ids = []
        with self._storage() as storage:
            due = storage.due_schedules(now)
        for schedule in due:
            scheduler_running = bool(self.scheduler_task and not self.scheduler_task.done())
            if scheduler_running and schedule.get("overlap_policy") == "skip":
                next_run_at = _next_run_at(schedule["trigger"], after=_now() + timedelta(seconds=1))
                with self._storage() as storage:
                    storage.update_schedule_after_run(
                        schedule["id"],
                        last_run_at=now,
                        next_run_at=next_run_at,
                        enabled=next_run_at is not None,
                    )
                skipped += 1
                continue
            result = await self.create_batch_run(
                name=f"{schedule['name']} {_now().strftime('%Y-%m-%d %H:%M')}",
                source="schedule",
                flow_type=schedule["flow_type"],
                flow=schedule["flow"],
                browser_ids=schedule["browser_ids"],
                inputs=schedule["inputs"],
                per_window_inputs=schedule["per_window_inputs"],
                options=schedule["run_options"],
                schedule_id=schedule["id"],
                run_now=False,
            )
            batch_ids.append(result["id"])
            next_run_at = _next_run_at(schedule["trigger"], after=_now() + timedelta(seconds=1))
            with self._storage() as storage:
                storage.update_schedule_after_run(
                    schedule["id"],
                    last_run_at=now,
                    next_run_at=next_run_at,
                    enabled=next_run_at is not None,
                )
            created += 1
        if created:
            await self.start_scheduler(batch_id=batch_ids[0] if batch_ids else None)
        return {"created": created, "skipped": skipped, "batch_ids": batch_ids}

    async def start_scheduler(
        self,
        *,
        tasks_path: str | None = None,
        replace: bool = False,
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        if self.scheduler_task and not self.scheduler_task.done():
            return {"state": "running", "message": "scheduler already running"}

        if tasks_path:
            self.import_tasks(tasks_path, replace=replace)

        self.scheduler_status = {"state": "running", "started_from_ui": True, "batch_id": batch_id}
        self.scheduler_task = asyncio.create_task(self._run_scheduler_once(batch_id=batch_id))
        return self.scheduler_status

    async def stop_scheduler(self) -> dict[str, Any]:
        if self.scheduler_task and not self.scheduler_task.done():
            self.scheduler_task.cancel()
            self.scheduler_status = {"state": "stopping"}
            return self.scheduler_status
        self.scheduler_status = {"state": "idle"}
        return self.scheduler_status

    async def poll_scheduler(self) -> dict[str, Any]:
        if self.scheduler_task and self.scheduler_task.done():
            try:
                self.scheduler_status = self.scheduler_task.result()
            except asyncio.CancelledError:
                self.scheduler_status = {"state": "cancelled"}
            except Exception as exc:
                self.scheduler_status = {"state": "failed", "error": str(exc)}
            self.scheduler_task = None
        return self.scheduler_status

    async def _run_scheduler_once(self, *, batch_id: str | None = None) -> dict[str, Any]:
        storage = Storage(self.config.paths.sqlite)
        storage.init_schema()
        try:
            recovered = storage.reset_running(status=self.config.scheduler.recover_running_tasks_as)
            result = await Scheduler(config=self.config, storage=storage, once=True, batch_id=batch_id).run()
            result["state"] = "finished"
            result["recovered_running_tasks"] = recovered
            return result
        finally:
            storage.close()

    def settings(self) -> dict[str, Any]:
        return _jsonable(asdict(self.config))

    def _busy_browser_ids(self) -> set[str]:
        return {
            str(row["browser_id"])
            for row in self.browser_runtime()
            if row.get("status") in {"opening", "running", "closing"}
        }

    def _client(self) -> BitBrowserClient:
        return BitBrowserClient(
            base_url=self.config.bitbrowser.base_url,
            timeout_seconds=self.config.bitbrowser.request_timeout_seconds,
        )

    def _storage(self) -> Storage:
        storage = Storage(self.config.paths.sqlite)
        storage.init_schema()
        return storage


def _summarize_browser_list(listing: dict[str, Any]) -> dict[str, Any]:
    data = listing.get("data") if isinstance(listing, dict) else None
    if not isinstance(data, dict):
        return {"total": None, "items": []}
    items = data.get("list") or data.get("items") or data.get("data") or []
    summarized = []
    for item in items[:10] if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        summarized.append(
            {
                "id": item.get("id"),
                "seq": item.get("seq"),
                "name": item.get("name") or "",
                "remark": item.get("remark") or "",
                "opened": item.get("opened"),
            }
        )
    return {"total": data.get("total") or data.get("totalNum") or data.get("count"), "items": summarized}


def _flow_files(directory: Path, suffixes: set[str]) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    rows = []
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix in suffixes:
            rows.append({"name": path.stem, "path": str(path), "size": path.stat().st_size, "type": path.suffix})
    return rows


def _declarative_flow_meta(path: Path) -> dict[str, Any]:
    try:
        flow = _read_structured_file(path)
    except Exception as exc:
        return {
            "display_name": path.stem,
            "description": f"流程文件读取失败：{exc}",
            "inputs": [],
            "valid": False,
        }
    result = FlowValidator().validate(flow)
    return {
        "display_name": str(flow.get("display_name") or flow.get("name") or path.stem),
        "description": str(flow.get("description") or "声明式自动化流程"),
        "inputs": _normalize_inputs(flow.get("inputs") or {}),
        "valid": result.ok,
        "errors": result.errors,
        "warnings": result.warnings,
    }


def _python_flow_meta(path: Path) -> dict[str, Any]:
    meta = {}
    for candidate in [path.with_suffix(".meta.yaml"), path.with_suffix(".meta.yml"), path.with_suffix(".meta.json")]:
        if candidate.exists():
            try:
                meta = _read_structured_file(candidate)
            except Exception as exc:
                meta = {"description": f"元数据读取失败：{exc}"}
            break
    return {
        "display_name": str(meta.get("display_name") or meta.get("name") or path.stem),
        "description": str(meta.get("description") or "Python 自动化流程"),
        "inputs": _normalize_inputs(meta.get("inputs") or {}),
        "valid": True,
        "errors": [],
        "warnings": [],
    }


def _read_structured_file(path: Path) -> dict[str, Any]:
    if path.suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError("PyYAML is required to load YAML files. Run `pip install -e .`.") from exc
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"file must contain a mapping: {path}")
    return data


def _normalize_inputs(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    fields = []
    if not isinstance(inputs, dict):
        return fields
    for name, spec in inputs.items():
        spec = spec if isinstance(spec, dict) else {"type": "string"}
        fields.append(
            {
                "name": str(name),
                "label": str(spec.get("label") or name),
                "type": str(spec.get("type") or "string"),
                "required": bool(spec.get("required")),
                "default": spec.get("default"),
                "placeholder": str(spec.get("placeholder") or ""),
                "choices": spec.get("choices") if isinstance(spec.get("choices"), list) else [],
                "per_window": bool(spec.get("per_window")),
            }
        )
    return fields


def _pick_screenshot(run_json: dict[str, Any]) -> str | None:
    if not isinstance(run_json, dict):
        return None
    outputs = run_json.get("outputs")
    if isinstance(outputs, dict):
        for key, value in outputs.items():
            if "screenshot" in str(key) and isinstance(value, str):
                return value
    error_screenshot = run_json.get("error_screenshot")
    return str(error_screenshot) if error_screenshot else None


def _default_batch_name(flow: str) -> str:
    return f"{flow} {_now().strftime('%Y-%m-%d %H:%M')}"


def _blank(value: Any) -> bool:
    return value is None or value == "" or value == []


def _now() -> datetime:
    return datetime.now().astimezone()


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_now().tzinfo)
    return parsed.astimezone()


def _next_run_at(trigger: dict[str, Any], *, after: datetime | None = None) -> str | None:
    after = after or _now()
    trigger_type = str(trigger.get("type") or "manual")
    if trigger_type == "manual":
        return None
    if trigger_type == "once":
        run_at = _parse_datetime(trigger.get("run_at"))
        return run_at.isoformat(timespec="seconds") if run_at else None
    if trigger_type == "interval":
        minutes = max(1, int(trigger.get("minutes") or 60))
        start_at = _parse_datetime(trigger.get("start_at")) or after
        if start_at > after:
            return start_at.isoformat(timespec="seconds")
        elapsed = max(0, (after - start_at).total_seconds())
        steps = int(elapsed // (minutes * 60)) + 1
        return (start_at + timedelta(minutes=minutes * steps)).isoformat(timespec="seconds")
    if trigger_type == "daily":
        hour, minute = _parse_time(trigger.get("time") or "09:00")
        days = trigger.get("days") or list(range(7))
        days = {int(day) for day in days}
        for offset in range(8):
            candidate = (after + timedelta(days=offset)).replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate > after and candidate.weekday() in days:
                return candidate.isoformat(timespec="seconds")
        return None
    if trigger_type == "weekly":
        hour, minute = _parse_time(trigger.get("time") or "09:00")
        days = {int(day) for day in (trigger.get("days") or [])}
        if not days:
            days = {after.weekday()}
        for offset in range(15):
            candidate = (after + timedelta(days=offset)).replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate > after and candidate.weekday() in days:
                return candidate.isoformat(timespec="seconds")
    return None


def _parse_time(value: Any) -> tuple[int, int]:
    parts = str(value or "09:00").split(":", 1)
    hour = max(0, min(23, int(parts[0] or 9)))
    minute = max(0, min(59, int(parts[1] or 0))) if len(parts) > 1 else 0
    return hour, minute


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value
