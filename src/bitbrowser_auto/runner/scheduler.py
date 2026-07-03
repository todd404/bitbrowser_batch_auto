from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from bitbrowser_auto.config import AppConfig
from bitbrowser_auto.storage import Storage

from .service import run_one_task
from .task import Task
from .window_pool import WindowSlotPool


@dataclass
class Scheduler:
    config: AppConfig
    storage: Storage
    once: bool = False
    batch_id: str | None = None
    poll_interval_seconds: float = 1
    pool: WindowSlotPool = field(init=False)
    _running: set[asyncio.Task[Any]] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.pool = WindowSlotPool(self.config.scheduler.max_concurrent_windows)

    async def run(self) -> dict[str, Any]:
        started = 0
        completed = 0
        failed = 0

        while True:
            done = [task for task in self._running if task.done()]
            for task in done:
                try:
                    result = task.result()
                    if result.get("status") == "success":
                        completed += 1
                    else:
                        failed += 1
                except Exception:
                    failed += 1
                self._running.discard(task)

            free_capacity = self.config.scheduler.max_concurrent_windows - len(self._running)
            if free_capacity > 0:
                busy = await self.pool.busy_browser_ids()
                tasks = self.storage.claim_pending_tasks(
                    limit=free_capacity,
                    busy_browser_ids=busy,
                    batch_id=self.batch_id,
                )
                for task in tasks:
                    acquired = await self.pool.acquire(task.browser_id)
                    if not acquired:
                        self.storage.release_to_pending(task.id)
                        continue
                    started += 1
                    worker = asyncio.create_task(self._run_claimed_task(task))
                    self._running.add(worker)

            pending_count = self.storage.count_tasks(status="pending", batch_id=self.batch_id)
            if self.once and pending_count == 0 and not self._running:
                break

            if not self._running and pending_count == 0:
                break

            await asyncio.sleep(self.poll_interval_seconds)

        if self._running:
            results = await asyncio.gather(*self._running, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception) or result.get("status") != "success":
                    failed += 1
                else:
                    completed += 1

        return {
            "status": "success",
            "started": started,
            "completed": completed,
            "failed": failed,
            "pending": self.storage.count_tasks(status="pending", batch_id=self.batch_id),
            "running": self.storage.count_tasks(status="running"),
            "batch_id": self.batch_id,
        }

    async def _run_claimed_task(self, task: Task) -> dict[str, Any]:
        run_id: str | None = None
        if task.batch_id:
            self.storage.refresh_batch_status(task.batch_id)
        self.storage.update_browser_runtime(task.browser_id, status="opening", current_task_id=task.id)
        try:
            run_id = self.storage.create_task_run(task)
            self.storage.update_browser_runtime(task.browser_id, status="running", current_task_id=task.id)
            result = await asyncio.wait_for(
                run_one_task(task, self.config, raise_on_failure=False),
                timeout=self.config.scheduler.task_timeout_seconds,
            )
            if run_id:
                self.storage.finish_task_run(run_id, result)
            if result.get("status") == "success":
                self.storage.mark_task_success(task.id)
            else:
                self._mark_failure(task, str(result.get("error") or "task failed"))
            if task.batch_id:
                self.storage.refresh_batch_status(task.batch_id)
            return result
        except Exception as exc:
            result = {
                "status": "failed",
                "task_id": task.id,
                "browser_id": task.browser_id,
                "error": str(exc),
            }
            if run_id:
                self.storage.finish_task_run(run_id, result)
            self._mark_failure(task, str(exc))
            if task.batch_id:
                self.storage.refresh_batch_status(task.batch_id)
            return result
        finally:
            self.storage.update_browser_runtime(task.browser_id, status="idle")
            await self.pool.release(task.browser_id)

    def _mark_failure(self, task: Task, error: str) -> None:
        retry_count = self.storage.get_retry_count(task.id)
        should_retry = retry_count < self.config.scheduler.max_retries
        self.storage.mark_task_failed(task.id, error, retry=should_retry)
