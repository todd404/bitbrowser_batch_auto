from __future__ import annotations

import unittest

from bitbrowser_auto.observability.trace import (
    is_screenshot_error,
    normalize_screenshot_policy,
    step_metadata,
    summarize_value,
)


class TraceTest(unittest.TestCase):
    def test_step_metadata_redacts_fill_value(self) -> None:
        metadata = step_metadata({"action": "fill", "selector": "#password", "value": "secret"})

        self.assertEqual(metadata["selector"], "#password")
        self.assertNotIn("secret", str(metadata))

    def test_step_metadata_summarizes_playwright_call(self) -> None:
        metadata = step_metadata(
            {
                "action": "playwright",
                "target": "page",
                "method": "locator",
                "args": ["button"],
                "chain": [{"method": "click", "kwargs": {"timeout": 1000}}],
            }
        )

        self.assertEqual(metadata["target"], "page")
        self.assertEqual(metadata["method"], "locator")
        self.assertEqual(metadata["args_summary"], ["button"])
        self.assertEqual(metadata["chain_summary"][0]["method"], "click")

    def test_normalize_screenshot_policy(self) -> None:
        self.assertEqual(normalize_screenshot_policy("off"), "off")
        self.assertEqual(normalize_screenshot_policy("bogus"), "on_error")

    def test_summarize_value_redacts_sensitive_keys(self) -> None:
        summary = summarize_value({"token": "abc", "nested": {"password": "secret"}})

        self.assertEqual(summary["token"], "<redacted>")
        self.assertEqual(summary["nested"]["password"], "<redacted>")

    def test_detects_screenshot_errors(self) -> None:
        self.assertTrue(is_screenshot_error("Page.screenshot: Timeout"))
        self.assertFalse(is_screenshot_error("Navigation timeout"))


if __name__ == "__main__":
    unittest.main()
