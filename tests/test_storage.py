from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bitbrowser_auto.runner.task import Task
from bitbrowser_auto.storage import Storage


class StorageTest(unittest.TestCase):
    def test_import_and_claim_pending_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "scheduler.sqlite3")
            try:
                storage.init_schema()
                task = Task(
                    id="task-001",
                    browser_id="browser-001",
                    flow_type="declarative",
                    flow="open_and_check",
                    inputs={"url": "https://example.com"},
                )

                imported = storage.import_tasks([task])
                claimed = storage.claim_pending_tasks(limit=1)

                self.assertEqual(imported, {"created": 1, "updated": 0, "skipped": 0})
                self.assertEqual(len(claimed), 1)
                self.assertEqual(claimed[0].id, "task-001")
                self.assertEqual(storage.count_tasks(status="running"), 1)
            finally:
                storage.close()

    def test_claim_pending_tasks_can_be_limited_to_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "scheduler.sqlite3")
            try:
                storage.init_schema()
                storage.import_tasks(
                    [
                        Task(id="legacy", browser_id="browser-legacy", flow_type="declarative", flow="open_and_check"),
                        Task(
                            id="batch-task",
                            batch_id="batch-001",
                            browser_id="browser-001",
                            flow_type="declarative",
                            flow="open_and_check",
                        ),
                    ]
                )

                claimed = storage.claim_pending_tasks(limit=2, batch_id="batch-001")

                self.assertEqual([task.id for task in claimed], ["batch-task"])
                self.assertEqual(storage.count_tasks(status="pending"), 1)
                self.assertEqual(storage.count_tasks(status="pending", batch_id="batch-001"), 0)
                self.assertEqual(storage.count_tasks(status="running", batch_id="batch-001"), 1)
            finally:
                storage.close()

    def test_reset_running_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "scheduler.sqlite3")
            try:
                storage.init_schema()
                task = Task(
                    id="task-001",
                    browser_id="browser-001",
                    flow_type="declarative",
                    flow="open_and_check",
                )
                storage.import_tasks([task])
                storage.claim_pending_tasks(limit=1)

                reset_count = storage.reset_running(status="pending")

                self.assertEqual(reset_count, 1)
                self.assertEqual(storage.count_tasks(status="pending"), 1)
                self.assertEqual(storage.count_tasks(status="running"), 0)
            finally:
                storage.close()

    def test_create_batch_run_and_rerun_failed_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "scheduler.sqlite3")
            try:
                storage.init_schema()
                result = storage.create_batch_run(
                    name="Demo batch",
                    source="manual",
                    flow_type="declarative",
                    flow="open_and_check",
                    browser_ids=["browser-001", "browser-002"],
                    inputs={"url": "https://example.com"},
                )

                batch = storage.get_batch_run(result["id"])
                tasks = storage.list_tasks_for_batch(result["id"])

                self.assertIsNotNone(batch)
                self.assertEqual(batch["counts"], {"pending": 2})
                self.assertEqual(len(tasks), 2)
                self.assertEqual(tasks[0]["batch_id"], result["id"])

                storage.mark_task_failed(tasks[0]["id"], "boom", retry=False)
                count = storage.rerun_failed_tasks(result["id"])

                self.assertEqual(count, 1)
                self.assertEqual(storage.get_batch_run(result["id"])["counts"], {"pending": 2})
            finally:
                storage.close()

    def test_create_and_toggle_schedule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "scheduler.sqlite3")
            try:
                storage.init_schema()
                result = storage.create_schedule(
                    name="Daily demo",
                    enabled=True,
                    flow_type="declarative",
                    flow="open_and_check",
                    browser_ids=["browser-001"],
                    inputs={"url": "https://example.com"},
                    per_window_inputs=None,
                    trigger={"type": "daily", "time": "09:00"},
                    run_options={"max_retries": 1},
                    overlap_policy="skip",
                    missed_policy="skip",
                    next_run_at="2026-07-03T09:00:00+08:00",
                )

                schedules = storage.list_schedules()
                self.assertEqual(len(schedules), 1)
                self.assertTrue(schedules[0]["enabled"])
                self.assertEqual(schedules[0]["browser_ids"], ["browser-001"])

                storage.set_schedule_enabled(result["id"], False)

                self.assertFalse(storage.get_schedule(result["id"])["enabled"])
            finally:
                storage.close()


if __name__ == "__main__":
    unittest.main()
