from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bitbrowser_auto.config import AppConfig, PathsConfig
from bitbrowser_auto.ui.core import UiCoreService


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


if __name__ == "__main__":
    unittest.main()
