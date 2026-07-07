from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from bitbrowser_auto.config import AppConfig, PathsConfig
from bitbrowser_auto.ui.core import UiCoreService


class NoopSchedulerUiCoreService(UiCoreService):
    def __init__(self, config: AppConfig) -> None:
        super().__init__(config)
        self.started_batch_ids: list[str | None] = []

    async def start_scheduler(
        self,
        *,
        tasks_path: str | None = None,
        replace: bool = False,
        batch_id: str | None = None,
    ) -> dict[str, object]:
        self.started_batch_ids.append(batch_id)
        self.scheduler_status = {"state": "started", "batch_id": batch_id}
        return self.scheduler_status


class UiCoreServiceTest(unittest.TestCase):
    def test_create_declarative_template_writes_readable_flow_card(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(
                paths=PathsConfig(
                    sqlite=root / "scheduler.sqlite3",
                    artifact_dir=root / "artifacts",
                    declarative_flow_dir=root / "flows" / "declarative",
                    python_flow_dir=root / "flows" / "py",
                )
            )
            service = UiCoreService(config)

            created = service.create_declarative_template(
                name="open_product_page",
                display_name="打开商品页并截图",
                description="打开商品页并保存截图。",
                category="网页访问",
                default_url="https://example.com/product",
            )
            cards = service.list_flow_cards()

            self.assertEqual(created["name"], "open_product_page")
            self.assertEqual(created["display_name"], "打开商品页并截图")
            self.assertEqual(cards[0]["display_name"], "打开商品页并截图")
            self.assertEqual(cards[0]["inputs"][0]["label"], "目标网址")
            self.assertTrue((config.paths.declarative_flow_dir / "open_product_page.yaml").exists())

    def test_once_schedule_is_consumed_after_tick(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = AppConfig(
                paths=PathsConfig(
                    sqlite=root / "scheduler.sqlite3",
                    artifact_dir=root / "artifacts",
                    declarative_flow_dir=root / "flows" / "declarative",
                    python_flow_dir=root / "flows" / "py",
                )
            )
            config.paths.declarative_flow_dir.mkdir(parents=True)
            (config.paths.declarative_flow_dir / "open_and_check.json").write_text(
                json.dumps(
                    {
                        "name": "open_and_check",
                        "inputs": {
                            "url": {
                                "type": "string",
                                "label": "URL",
                                "required": True,
                            }
                        },
                        "steps": [{"action": "goto", "url": "{{ inputs.url }}"}],
                    }
                ),
                encoding="utf-8",
            )
            service = NoopSchedulerUiCoreService(config)
            schedule = service.create_schedule(
                name="Run once",
                flow_type="declarative",
                flow="open_and_check",
                browser_ids=["browser-001"],
                inputs={"url": "https://example.com"},
                per_window_inputs=None,
                trigger={"type": "once", "run_at": "2000-01-01T09:00"},
                run_options={},
                overlap_policy="skip",
                missed_policy="skip",
            )

            first = asyncio.run(service.tick_schedules())
            second = asyncio.run(service.tick_schedules())
            schedules = service.list_schedules()
            batches = service.list_batches()

            self.assertEqual(first["created"], 1)
            self.assertEqual(second["created"], 0)
            self.assertEqual(len(batches), 1)
            self.assertEqual(service.started_batch_ids, [first["batch_ids"][0]])
            self.assertEqual(schedules[0]["id"], schedule["id"])
            self.assertFalse(schedules[0]["enabled"])
            self.assertIsNone(schedules[0]["next_run_at"])


if __name__ == "__main__":
    unittest.main()
