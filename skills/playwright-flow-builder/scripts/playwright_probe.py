#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_MARKERS = ("pyproject.toml", ".git")


def find_repo_root(start: Path) -> Path:
    for path in (start, *start.parents):
        if any((path / marker).exists() for marker in ROOT_MARKERS):
            return path
    return start


REPO_ROOT = find_repo_root(Path(__file__).resolve())
SRC = REPO_ROOT / "src"
if SRC.exists():
    sys.path.insert(0, str(SRC))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_print(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False), flush=True)


def redact_command(command: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(command)
    selector = str(redacted.get("selector", "")).lower()
    if redacted.get("secret") or (redacted.get("action") == "fill" and "pass" in selector):
        if "value" in redacted:
            redacted["value"] = "[REDACTED]"
    return redacted


class ProbeSession:
    def __init__(self, page: Any, artifact_dir: Path) -> None:
        self.page = page
        self.artifact_dir = artifact_dir
        self.log_path = artifact_dir / "commands.jsonl"
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

    async def log(self, command: dict[str, Any], ok: bool, result: Any = None, error: str | None = None) -> None:
        entry = {
            "at": now_iso(),
            "ok": ok,
            "command": redact_command(command),
            "url": getattr(self.page, "url", None),
        }
        if result is not None:
            entry["result"] = result
        if error:
            entry["error"] = error
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    async def execute(self, command: dict[str, Any]) -> Any:
        action = command.get("action")
        if not isinstance(action, str):
            raise ValueError("Command requires string field `action`")

        if action == "goto":
            await self.page.goto(
                str(command["url"]),
                wait_until=command.get("wait_until", "domcontentloaded"),
                timeout=command.get("timeout_ms"),
            )
            return {"url": self.page.url}

        if action == "click":
            await self.page.locator(str(command["selector"])).click(timeout=command.get("timeout_ms"))
            return None

        if action == "human_click":
            from bitbrowser_auto.human import CursorTracker, MouseConfig, human_click

            tracker: CursorTracker | None = getattr(self, "_human_cursor", None)
            if tracker is None:
                tracker = CursorTracker()
                self._human_cursor = tracker  # type: ignore[attr-defined]
            cfg = MouseConfig()
            if "speed_factor" in command:
                cfg = MouseConfig(**{**cfg.__dict__, "speed_factor": float(command["speed_factor"])}).clamp()
            overshoot = command.get("overshoot", "auto")
            result = await human_click(
                self.page,
                str(command["selector"]),
                cfg=cfg,
                tracker=tracker,
                overshoot=overshoot,  # type: ignore[arg-type]
            )
            return result.as_trace()

        if action == "fill":
            await self.page.locator(str(command["selector"])).fill(
                str(command.get("value", "")),
                timeout=command.get("timeout_ms"),
            )
            return None

        if action == "press":
            await self.page.locator(str(command["selector"])).press(
                str(command["key"]),
                timeout=command.get("timeout_ms"),
            )
            return None

        if action == "select":
            values = command.get("values", command.get("value"))
            await self.page.locator(str(command["selector"])).select_option(
                values,
                timeout=command.get("timeout_ms"),
            )
            return None

        if action == "wait_for":
            await self.page.locator(str(command["selector"])).wait_for(
                state=command.get("state", "visible"),
                timeout=command.get("timeout_ms"),
            )
            return None

        if action == "wait_for_url":
            await self.page.wait_for_url(str(command["url"]), timeout=command.get("timeout_ms"))
            return {"url": self.page.url}

        if action == "text":
            return await self.page.locator(str(command["selector"])).inner_text(timeout=command.get("timeout_ms"))

        if action == "attr":
            return await self.page.locator(str(command["selector"])).get_attribute(
                str(command["attr"]),
                timeout=command.get("timeout_ms"),
            )

        if action == "title":
            return await self.page.title()

        if action == "url":
            return self.page.url

        if action == "screenshot":
            name = safe_artifact_name(str(command.get("name", "screenshot")))
            path = self.artifact_dir / f"{name}.png"
            await self.page.screenshot(path=str(path), full_page=bool(command.get("full_page", True)))
            return {"path": str(path)}

        if action == "observe":
            result = await self.observe(limit=int(command.get("limit", 30)))
            if command.get("screenshot"):
                path = self.artifact_dir / "observe.png"
                await self.page.screenshot(path=str(path), full_page=True)
                result["screenshot"] = str(path)
            return result

        if action == "pause":
            message = str(command.get("message") or "Complete the manual step in the browser, then press Enter.")
            await asyncio.to_thread(input, f"{message}\nPress Enter to continue...")
            return {"paused": True}

        if action == "note":
            return {"note": str(command.get("text", ""))}

        if action in {"exit", "quit"}:
            return {"exit": True}

        raise ValueError(f"Unsupported action: {action}")

    async def observe(self, limit: int = 30) -> dict[str, Any]:
        candidates = await self.page.evaluate(
            """
            (limit) => {
              const pick = (value, max = 120) => {
                if (!value) return "";
                return String(value).replace(/\\s+/g, " ").trim().slice(0, max);
              };
              const visible = (el) => {
                const style = window.getComputedStyle(el);
                const box = el.getBoundingClientRect();
                return style && style.visibility !== "hidden" &&
                  style.display !== "none" && box.width > 0 && box.height > 0;
              };
              const css = (el) => {
                if (el.id) return `#${CSS.escape(el.id)}`;
                const attrs = ["data-testid", "data-test", "name", "aria-label", "placeholder", "type"];
                for (const attr of attrs) {
                  const value = el.getAttribute(attr);
                  if (value) return `${el.tagName.toLowerCase()}[${attr}="${CSS.escape(value)}"]`;
                }
                return el.tagName.toLowerCase();
              };
              const nodes = Array.from(document.querySelectorAll(
                "a,button,input,textarea,select,[role='button'],[role='link'],[aria-label],[placeholder]"
              )).filter(visible).slice(0, limit);
              return nodes.map((el) => ({
                tag: el.tagName.toLowerCase(),
                selector: css(el),
                role: pick(el.getAttribute("role")),
                text: pick(el.innerText || el.textContent),
                aria_label: pick(el.getAttribute("aria-label")),
                placeholder: pick(el.getAttribute("placeholder")),
                name: pick(el.getAttribute("name")),
                type: pick(el.getAttribute("type")),
                href: pick(el.getAttribute("href")),
              }));
            }
            """,
            limit,
        )
        return {"url": self.page.url, "title": await self.page.title(), "candidates": candidates}


def safe_artifact_name(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value).strip("_")
    return safe or "screenshot"


async def open_session(args: argparse.Namespace) -> tuple[Any, Any, Any]:
    from playwright.async_api import async_playwright

    playwright = await async_playwright().start()
    close_browser_on_exit = args.close_browser_on_exit

    if args.browser_id:
        from bitbrowser_auto.bitbrowser import BitBrowserClient
        from bitbrowser_auto.config import load_config

        config = load_config(args.config)
        client = BitBrowserClient(
            base_url=config.bitbrowser.base_url,
            timeout_seconds=config.bitbrowser.request_timeout_seconds,
        )
        opened = await client.open_browser(
            args.browser_id,
            queue=True,
            ignore_default_urls=True,
            new_page_url=args.url,
        )
        browser = await playwright.chromium.connect_over_cdp(str(opened["ws"]))
        close_browser_on_exit = args.close_browser_on_exit
    elif args.ws_url:
        browser = await playwright.chromium.connect_over_cdp(args.ws_url)
    else:
        browser = await playwright.chromium.launch(headless=False)
        close_browser_on_exit = True

    context = browser.contexts[0] if browser.contexts else await browser.new_context()
    page = context.pages[0] if context.pages else await context.new_page()
    page.set_default_navigation_timeout(args.navigation_timeout_ms)
    page.set_default_timeout(args.action_timeout_ms)
    if args.url and not args.browser_id:
        await page.goto(args.url, wait_until="domcontentloaded")

    async def cleanup() -> None:
        if close_browser_on_exit:
            await browser.close()
        await playwright.stop()

    return page, cleanup, close_browser_on_exit


async def repl(args: argparse.Namespace) -> int:
    artifact_dir = Path(args.artifact_dir or f"artifacts/flow-authoring/probe-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    page, cleanup, close_browser_on_exit = await open_session(args)
    session = ProbeSession(page=page, artifact_dir=artifact_dir)

    json_print(
        {
            "status": "ready",
            "artifact_dir": str(artifact_dir),
            "url": page.url,
            "close_browser_on_exit": close_browser_on_exit,
            "hint": "Send one JSON command per line. Use {\"action\":\"help\"} or {\"action\":\"exit\"}.",
        }
    )

    try:
        while True:
            line = await asyncio.to_thread(input, "flow-playwright> ")
            if not line.strip():
                continue
            if line.strip() in {"help", "?"}:
                print_help()
                continue
            try:
                command = json.loads(line)
                if command.get("action") == "help":
                    print_help()
                    continue
                result = await session.execute(command)
                await session.log(command, ok=True, result=result)
                json_print({"ok": True, "result": result, "url": page.url})
                if isinstance(result, dict) and result.get("exit"):
                    return 0
            except Exception as exc:
                error_result: dict[str, Any] = {"ok": False, "error": str(exc), "url": page.url}
                try:
                    path = artifact_dir / f"error-{datetime.now().strftime('%H%M%S')}.png"
                    await page.screenshot(path=str(path), full_page=True)
                    error_result["screenshot"] = str(path)
                except Exception:
                    pass
                try:
                    command_for_log = json.loads(line)
                except Exception:
                    command_for_log = {"raw": line}
                await session.log(command_for_log, ok=False, error=str(exc))
                json_print(error_result)
    finally:
        await cleanup()


def print_help() -> None:
    print(
        """
Commands are JSON objects, one per line:
  {"action":"observe","limit":25}
  {"action":"goto","url":"https://example.com"}
  {"action":"click","selector":"text=Login"}
  {"action":"human_click","selector":"text=Login","speed_factor":1.0,"overshoot":"auto"}
  {"action":"fill","selector":"input[name='q']","value":"hello"}
  {"action":"press","selector":"input[name='q']","key":"Enter"}
  {"action":"wait_for","selector":".result","state":"visible","timeout_ms":30000}
  {"action":"wait_for_url","url":"**/done","timeout_ms":30000}
  {"action":"text","selector":".result"}
  {"action":"attr","selector":"a.next","attr":"href"}
  {"action":"screenshot","name":"checkpoint"}
  {"action":"pause","message":"Complete login in the browser, then press Enter."}
  {"action":"exit"}
""".strip(),
        flush=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Interactive Playwright probe for flow authoring.")
    parser.add_argument("--browser-id", default=None, help="BitBrowser browser id to open and control.")
    parser.add_argument("--ws-url", default=None, help="Existing Chrome DevTools websocket URL.")
    parser.add_argument("--url", default=None, help="Start URL.")
    parser.add_argument("--config", default=None, help="Optional project config path.")
    parser.add_argument("--artifact-dir", default=None, help="Directory for logs and screenshots.")
    parser.add_argument("--navigation-timeout-ms", type=int, default=60000)
    parser.add_argument("--action-timeout-ms", type=int, default=30000)
    parser.add_argument(
        "--close-browser-on-exit",
        action="store_true",
        help="Close the controlled browser when exiting. Default leaves BitBrowser/CDP windows open.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(repl(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
