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


if __name__ == "__main__":
    unittest.main()

