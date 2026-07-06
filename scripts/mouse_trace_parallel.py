#!/usr/bin/env python3
"""Run two BitBrowser windows and move their Playwright mice concurrently."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import functools
import json
import math
import socket
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PAGE_PATH = Path(__file__).with_name("mouse_trace_page.html")

if str((ROOT / "src")) not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _import_human_move():
    """Import the human-cursor module lazily so the script works without Playwright."""
    from bitbrowser_auto.human import CursorTracker, MouseConfig, human_move

    return type(
        "HumanMove",
        (),
        {"CursorTracker": CursorTracker, "MouseConfig": MouseConfig, "human_move": human_move},
    )


@dataclass
class ServedPage:
    server: ThreadingHTTPServer
    thread: threading.Thread
    url: str

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


@dataclass
class WindowTarget:
    label: str
    browser_id: str
    created: bool
    ws_url: str = ""
    pid: int | None = None
    core_version: str | None = None
    screenshot: Path | None = None
    summary: dict[str, Any] | None = None


class BitBrowserAPI:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required. Run `pip install -e .`.") from exc

        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await client.post(f"{self.base_url}{path}", json=payload or {})
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict) or not data.get("success"):
            raise RuntimeError(f"BitBrowser API failed: {path}: {data}")
        return data

    async def health(self) -> None:
        await self.post("/health")

    async def create_browser(self, *, name: str, width: int, height: int, core_version: str) -> str:
        fingerprint: dict[str, Any]
        if core_version:
            fingerprint = {
                "coreProduct": "chrome",
                "coreVersion": core_version,
                "ostype": "PC",
                "os": "Win32",
                "osVersion": "11,10",
                "openWidth": width,
                "openHeight": height,
            }
        else:
            fingerprint = {}
        payload = {
            "name": name,
            "proxyMethod": 2,
            "proxyType": "noproxy",
            "workbench": "disable",
            "browserFingerPrint": fingerprint,
        }
        data = await self.post("/browser/update", payload)
        created = data.get("data")
        if not isinstance(created, dict) or not created.get("id"):
            raise RuntimeError(f"BitBrowser create response has no id: {data}")
        return str(created["id"])

    async def open_browser(
        self,
        *,
        browser_id: str,
        url: str,
        args: list[str],
        queue: bool,
    ) -> dict[str, Any]:
        data = await self.post(
            "/browser/open",
            {
                "id": browser_id,
                "args": args,
                "queue": queue,
                "ignoreDefaultUrls": True,
                "newPageUrl": url,
            },
        )
        opened = data.get("data")
        if not isinstance(opened, dict) or not opened.get("ws"):
            raise RuntimeError(f"BitBrowser open response has no ws: {data}")
        return opened

    async def close_browser(self, browser_id: str) -> None:
        await self.post("/browser/close", {"id": browser_id})

    async def delete_browser(self, browser_id: str) -> None:
        await self.post("/browser/delete", {"id": browser_id})

    async def detect_core_version(self) -> str:
        data = await self.post("/browser/list", {"page": 0, "pageSize": 100})
        payload = data.get("data") or {}
        items = payload.get("list") if isinstance(payload, dict) else None
        versions: list[int] = []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                if str(item.get("coreProduct") or "chrome") != "chrome":
                    continue
                raw = str(item.get("coreVersion") or "")
                if raw.isdigit():
                    versions.append(int(raw))
        return str(max(versions)) if versions else ""


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def serve_page(port: int) -> ServedPage:
    class QuietHandler(SimpleHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/favicon.ico":
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
                return
            super().do_GET()

        def log_message(self, format: str, *args: Any) -> None:
            return

    handler = functools.partial(QuietHandler, directory=str(PAGE_PATH.parent))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, name="mouse-trace-http", daemon=True)
    thread.start()
    return ServedPage(
        server=server,
        thread=thread,
        url=f"http://127.0.0.1:{port}/{PAGE_PATH.name}",
    )


def window_args(index: int, args: argparse.Namespace) -> list[str]:
    result = list(args.open_arg or [])
    if not args.no_window_args:
        x = args.window_left + index * (args.window_width + args.window_gap)
        y = args.window_top
        result.extend(
            [
                f"--window-size={args.window_width},{args.window_height}",
                f"--window-position={x},{y}",
            ]
        )
    if args.headless:
        result.append("--headless")
    return result


def build_url(base_url: str, *, label: str, run_id: str) -> str:
    return f"{base_url}?label={label}&run={run_id}"


def path_point(pattern: str, step: int, total: int, width: int, height: int, phase: float) -> tuple[float, float]:
    margin_x = max(48, width * 0.12)
    margin_y = max(48, height * 0.14)
    usable_w = max(80, width - margin_x * 2)
    usable_h = max(80, height - margin_y * 2)
    cx = width / 2
    cy = height / 2
    t = (step / max(1, total - 1)) * math.tau + phase

    if pattern == "circle":
        return cx + math.cos(t) * usable_w * 0.42, cy + math.sin(t) * usable_h * 0.42
    if pattern == "eight":
        return cx + math.sin(t) * usable_w * 0.44, cy + math.sin(t * 2) * usable_h * 0.28
    if pattern == "zigzag":
        band = step % 24
        row = (step // 24) % 6
        x_ratio = band / 23 if row % 2 == 0 else 1 - band / 23
        y_ratio = row / 5
        return margin_x + x_ratio * usable_w, margin_y + y_ratio * usable_h

    return cx + math.sin(t) * usable_w * 0.42, cy + math.cos(t * 0.75) * usable_h * 0.38


async def viewport_size(page: Any) -> tuple[int, int]:
    size = await page.evaluate(
        """() => ({
            width: Math.max(1, window.innerWidth),
            height: Math.max(1, window.innerHeight)
        })"""
    )
    return int(size["width"]), int(size["height"])


async def drive_mouse(
    *,
    target: WindowTarget,
    page: Any,
    pattern: str,
    start_at: float,
    moves: int,
    interval_ms: int,
    steps_per_move: int,
) -> dict[str, Any]:
    await page.evaluate(
        """info => {
            window.__mouseTrace.clear();
            window.__mouseTrace.setRunner(info);
        }""",
        {"state": "armed", "pattern": pattern, "moves": moves},
    )
    width, height = await viewport_size(page)
    x0, y0 = path_point(pattern, 0, moves, width, height, 0)
    await page.mouse.move(x0, y0)
    await asyncio.sleep(max(0, start_at - asyncio.get_running_loop().time()))
    await page.evaluate(
        "info => window.__mouseTrace.setRunner(info)",
        {"state": "running", "pattern": pattern, "moves": moves},
    )
    started = time.perf_counter()
    phase = 0 if target.label == "A" else math.pi / 3
    if pattern == "human":
        # drive the same waypoints but bridge each gap with a human-like path
        human_move_mod = _import_human_move()
        tracker = human_move_mod.CursorTracker(start=(width * 0.5, height * 0.5))
        await page.mouse.move(*tracker.position())
        for step in range(moves):
            wp_width, wp_height = await viewport_size(page)
            x, y = path_point("sine", step, moves, wp_width, wp_height, phase)
            await human_move_mod.human_move(
                page,
                (x, y),
                tracker=tracker,
                target_width_px=80.0,
                cfg=human_move_mod.MouseConfig(speed_factor=1.0, overshoot_prob=0.5),
            )
    else:
        for step in range(moves):
            width, height = await viewport_size(page)
            x, y = path_point(pattern, step, moves, width, height, phase)
            await page.mouse.move(x, y, steps=steps_per_move)
            await asyncio.sleep(interval_ms / 1000)
    finished = time.perf_counter()
    await page.evaluate(
        "info => window.__mouseTrace.setRunner(info)",
        {"state": "finished", "pattern": pattern, "moves": moves},
    )
    summary = await page.evaluate("() => window.__mouseTrace.getSummary()")
    summary["wallClockSeconds"] = finished - started
    return summary


async def prepare_targets(
    args: argparse.Namespace,
    api: BitBrowserAPI,
    run_id: str,
    core_version: str,
) -> list[WindowTarget]:
    given = list(args.browser_id or [])
    if len(given) > 2:
        raise ValueError("Please provide at most two --browser-id values.")
    targets = [
        WindowTarget(label=chr(ord("A") + index), browser_id=browser_id, created=False)
        for index, browser_id in enumerate(given)
    ]
    for index in range(len(targets), 2):
        label = chr(ord("A") + index)
        browser_id = await api.create_browser(
            name=f"mouse-trace-{run_id}-{label}",
            width=args.window_width,
            height=args.window_height,
            core_version=core_version,
        )
        targets.append(WindowTarget(label=label, browser_id=browser_id, created=True))
    return targets


async def run(args: argparse.Namespace) -> dict[str, Any]:
    if not PAGE_PATH.exists():
        raise FileNotFoundError(PAGE_PATH)

    run_id = args.run_id or uuid.uuid4().hex[:10]
    artifact_dir = (ROOT / args.artifact_dir / f"mouse-trace-{run_id}").resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)

    server = serve_page(args.port or find_free_port())
    api = BitBrowserAPI(args.base_url, args.timeout)
    targets: list[WindowTarget] = []
    browser_handles: list[Any] = []

    try:
        await api.health()
        detected_core_version = args.core_version or await api.detect_core_version()
        targets = await prepare_targets(args, api, run_id, detected_core_version)
        open_results = await asyncio.gather(
            *[
                api.open_browser(
                    browser_id=target.browser_id,
                    url=build_url(server.url, label=target.label, run_id=run_id),
                    args=window_args(index, args),
                    queue=args.queue_open,
                )
                for index, target in enumerate(targets)
            ]
        )
        for target, opened in zip(targets, open_results):
            target.ws_url = str(opened["ws"])
            target.pid = int(opened["pid"]) if opened.get("pid") is not None else None
            target.core_version = str(opened.get("coreVersion") or "")

        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError("playwright is required. Run `pip install -e .`.") from exc

        async with async_playwright() as playwright:
            pages = []
            for target in targets:
                browser = await playwright.chromium.connect_over_cdp(target.ws_url)
                browser_handles.append(browser)
                context = browser.contexts[0] if browser.contexts else await browser.new_context()
                page = context.pages[0] if context.pages else await context.new_page()
                page.set_default_timeout(args.playwright_timeout)
                page.set_default_navigation_timeout(args.playwright_timeout)
                await page.goto(build_url(server.url, label=target.label, run_id=run_id), wait_until="domcontentloaded")
                await page.wait_for_function("() => window.__mouseTraceReady === true")
                pages.append(page)

            loop = asyncio.get_running_loop()
            start_at = loop.time() + args.start_delay
            patterns = [args.pattern_a, args.pattern_b]
            summaries = await asyncio.gather(
                *[
                    drive_mouse(
                        target=target,
                        page=page,
                        pattern=patterns[index],
                        start_at=start_at,
                        moves=args.moves,
                        interval_ms=args.interval_ms,
                        steps_per_move=args.steps_per_move,
                    )
                    for index, (target, page) in enumerate(zip(targets, pages))
                ]
            )
            for target, page, summary in zip(targets, pages, summaries):
                target.summary = summary
                target.screenshot = artifact_dir / f"window-{target.label}.png"
                await page.screenshot(path=str(target.screenshot), full_page=True)

            for browser in browser_handles:
                with contextlib.suppress(Exception):
                    await browser.close()

        if args.close_windows or args.delete_created:
            await asyncio.gather(*[api.close_browser(target.browser_id) for target in targets])
        if args.delete_created:
            await asyncio.sleep(5)
            await asyncio.gather(
                *[api.delete_browser(target.browser_id) for target in targets if target.created]
            )

        return {
            "run_id": run_id,
            "page_url": server.url,
            "artifact_dir": str(artifact_dir),
            "detected_core_version": detected_core_version,
            "parallel": True,
            "targets": [
                {
                    "label": target.label,
                    "browser_id": target.browser_id,
                    "created": target.created,
                    "pid": target.pid,
                    "core_version": target.core_version,
                    "ws": target.ws_url,
                    "screenshot": str(target.screenshot) if target.screenshot else None,
                    "summary": target.summary,
                }
                for target in targets
            ],
        }
    finally:
        for browser in browser_handles:
            with contextlib.suppress(Exception):
                await browser.close()
        server.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:54345")
    parser.add_argument("--browser-id", action="append", help="Existing BitBrowser window id. Pass twice.")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--artifact-dir", default="artifacts")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--playwright-timeout", type=int, default=60_000)
    parser.add_argument("--core-version", default="")
    parser.add_argument("--window-width", type=int, default=900)
    parser.add_argument("--window-height", type=int, default=720)
    parser.add_argument("--window-left", type=int, default=40)
    parser.add_argument("--window-top", type=int, default=60)
    parser.add_argument("--window-gap", type=int, default=24)
    parser.add_argument("--no-window-args", action="store_true")
    parser.add_argument("--open-arg", action="append", default=[])
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--queue-open", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--moves", type=int, default=240)
    parser.add_argument("--interval-ms", type=int, default=35)
    parser.add_argument("--steps-per-move", type=int, default=1)
    parser.add_argument("--start-delay", type=float, default=1.0)
    parser.add_argument("--pattern-a", choices=["circle", "eight", "zigzag", "sine", "human"], default="circle")
    parser.add_argument("--pattern-b", choices=["circle", "eight", "zigzag", "sine", "human"], default="human")
    parser.add_argument("--close-windows", action="store_true")
    parser.add_argument("--delete-created", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = asyncio.run(run(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
