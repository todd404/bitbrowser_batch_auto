#!/usr/bin/env python3
"""Open a BitBrowser window and verify Playwright CDP control."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib import request

from playwright.sync_api import sync_playwright


def post_json(base_url: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = json.dumps(payload or {}).encode("utf-8")
    req = request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    opener = request.build_opener(request.ProxyHandler({}))
    with opener.open(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    if not data.get("success"):
        raise RuntimeError(f"BitBrowser API failed: {path}: {data.get('msg') or data}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:54345")
    parser.add_argument("--browser-id", required=True)
    parser.add_argument("--url", default="https://example.com")
    parser.add_argument("--screenshot", default="artifacts/bitbrowser-cdp-test.png")
    args = parser.parse_args()

    post_json(args.base_url, "/health")

    opened = post_json(
        args.base_url,
        "/browser/open",
        {
            "id": args.browser_id,
            "args": [],
            "queue": True,
            "ignoreDefaultUrls": True,
            "newPageUrl": args.url,
        },
    )["data"]

    ws_url = opened["ws"]
    screenshot_path = Path(args.screenshot).resolve()
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(ws_url)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()

        page.goto(args.url, wait_until="domcontentloaded", timeout=60_000)
        title = page.title()
        page.screenshot(path=str(screenshot_path), full_page=True)
        browser.close()

    print(
        json.dumps(
            {
                "connected": True,
                "browser_id": args.browser_id,
                "pid": opened.get("pid"),
                "core_version": opened.get("coreVersion"),
                "ws": ws_url,
                "final_url": args.url,
                "title": title,
                "screenshot": str(screenshot_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
