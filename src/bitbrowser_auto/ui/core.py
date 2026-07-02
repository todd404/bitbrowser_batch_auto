from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from bitbrowser_auto.bitbrowser import BitBrowserClient
from bitbrowser_auto.config import AppConfig
from bitbrowser_auto.runner.flow_loader import load_tasks
from bitbrowser_auto.runner.flow_loader import load_declarative_flow
from bitbrowser_auto.runner.flow_validator import FlowValidator
from bitbrowser_auto.runner.scheduler import Scheduler
from bitbrowser_auto.runner.service import task_from_mapping
from bitbrowser_auto.storage import Storage


class UiCoreService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.scheduler_task: asyncio.Task[dict[str, Any]] | None = None
        self.scheduler_status: dict[str, Any] = {"state": "idle"}

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
            return {
                "task_counts": storage.task_status_counts(),
                "running": storage.count_tasks(status="running"),
                "recent_errors": storage.recent_errors(limit=5),
                "scheduler": dict(self.scheduler_status),
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

    async def start_scheduler(self, *, tasks_path: str | None = None, replace: bool = False) -> dict[str, Any]:
        if self.scheduler_task and not self.scheduler_task.done():
            return {"state": "running", "message": "scheduler already running"}

        if tasks_path:
            self.import_tasks(tasks_path, replace=replace)

        self.scheduler_status = {"state": "running", "started_from_ui": True}
        self.scheduler_task = asyncio.create_task(self._run_scheduler_once())
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

    async def _run_scheduler_once(self) -> dict[str, Any]:
        storage = Storage(self.config.paths.sqlite)
        storage.init_schema()
        try:
            recovered = storage.reset_running(status=self.config.scheduler.recover_running_tasks_as)
            result = await Scheduler(config=self.config, storage=storage, once=True).run()
            result["state"] = "finished"
            result["recovered_running_tasks"] = recovered
            return result
        finally:
            storage.close()

    def settings(self) -> dict[str, Any]:
        return _jsonable(asdict(self.config))

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


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value
