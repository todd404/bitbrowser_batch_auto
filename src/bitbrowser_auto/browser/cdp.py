from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ConnectedBrowser:
    playwright: Any
    browser: Any
    context: Any
    page: Any

    async def close(self) -> None:
        await self.browser.close()
        await self.playwright.stop()


@dataclass
class PlaywrightConnector:
    default_navigation_timeout_ms: int = 60_000
    default_action_timeout_ms: int = 30_000

    async def connect(self, ws_url: str) -> ConnectedBrowser:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError("playwright is required for CDP control. Run `pip install -e .`.") from exc

        playwright = await async_playwright().start()
        try:
            browser = await playwright.chromium.connect_over_cdp(ws_url)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = context.pages[0] if context.pages else await context.new_page()
            page.set_default_navigation_timeout(self.default_navigation_timeout_ms)
            page.set_default_timeout(self.default_action_timeout_ms)
            return ConnectedBrowser(playwright=playwright, browser=browser, context=context, page=page)
        except Exception:
            await playwright.stop()
            raise
