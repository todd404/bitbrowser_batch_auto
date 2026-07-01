from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .bitbrowser import BitBrowserClient
from .browser import PlaywrightConnector
from .config import load_config
from .runner.flow_loader import load_tasks
from .runner.flow_loader import load_declarative_flow
from .runner.flow_validator import FlowValidator
from .runner.scheduler import Scheduler
from .runner.service import run_one_task, task_from_mapping
from .runner.task import Task
from .storage import Storage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bitbrowser_auto")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    check = subparsers.add_parser("check", help="Check BitBrowser Local Server and optional CDP control.")
    check.add_argument("--config", default=None, help="Path to app config YAML.")
    check.add_argument("--base-url", default=None, help="Override BitBrowser Local Server base URL.")
    check.add_argument("--browser-id", default=None, help="Open this browser id and verify Playwright CDP.")
    check.add_argument("--url", default="https://example.com", help="URL used for the CDP navigation test.")
    check.add_argument("--screenshot", default="artifacts/check/example.png", help="Screenshot path for CDP test.")
    check.add_argument("--list-page-size", type=int, default=10, help="How many browser windows to list.")

    run_one = subparsers.add_parser("run-one", help="Run one task through BitBrowser and Playwright.")
    run_one.add_argument("--config", default=None, help="Path to app config YAML.")
    run_one.add_argument("--browser-id", required=True)
    run_one.add_argument("--flow", default="open_and_check")
    run_one.add_argument("--flow-type", default="declarative", choices=["declarative", "python", "agent"])
    run_one.add_argument("--task-id", default="manual-run")
    run_one.add_argument("--url", default="https://example.com")
    run_one.add_argument("--input", action="append", default=[], help="Extra input as key=value. Can be repeated.")
    run_one.add_argument("--close-window", action="store_true", help="Close BitBrowser window after task.")

    run_tasks = subparsers.add_parser("run-tasks-file", help="Run tasks from a YAML/CSV file serially.")
    run_tasks.add_argument("--config", default=None, help="Path to app config YAML.")
    run_tasks.add_argument("--tasks", required=True, help="Path to tasks YAML or CSV.")
    run_tasks.add_argument("--limit", type=int, default=None)

    import_tasks = subparsers.add_parser("import-tasks", help="Import YAML/CSV tasks into SQLite.")
    import_tasks.add_argument("--config", default=None, help="Path to app config YAML.")
    import_tasks.add_argument("tasks", help="Path to tasks YAML or CSV.")
    import_tasks.add_argument("--replace", action="store_true", help="Replace existing tasks with the same id.")

    list_tasks_parser = subparsers.add_parser("list-tasks", help="List tasks from SQLite.")
    list_tasks_parser.add_argument("--config", default=None, help="Path to app config YAML.")
    list_tasks_parser.add_argument("--status", default=None, help="Filter by task status.")
    list_tasks_parser.add_argument("--limit", type=int, default=50)

    reset = subparsers.add_parser("reset-running", help="Reset interrupted running tasks.")
    reset.add_argument("--config", default=None, help="Path to app config YAML.")
    reset.add_argument("--as-status", choices=["pending", "failed"], default=None)

    run = subparsers.add_parser("run", help="Run pending tasks from SQLite, optionally importing a task file first.")
    run.add_argument("--config", default=None, help="Path to app config YAML.")
    run.add_argument("--tasks", default=None, help="Optional YAML/CSV task file to import before running.")
    run.add_argument("--replace", action="store_true", help="Replace existing tasks when importing --tasks.")
    run.add_argument("--once", action="store_true", help="Exit after current pending tasks finish.")

    validate_flow = subparsers.add_parser("validate-flow", help="Validate a declarative flow file.")
    validate_flow.add_argument("flow", help="Flow name or YAML/JSON path.")
    validate_flow.add_argument("--config", default=None, help="Path to app config YAML.")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return

    try:
        if args.command == "check":
            result = asyncio.run(_cmd_check(args))
        elif args.command == "run-one":
            result = asyncio.run(_cmd_run_one(args))
        elif args.command == "run-tasks-file":
            result = asyncio.run(_cmd_run_tasks_file(args))
        elif args.command == "import-tasks":
            result = _cmd_import_tasks(args)
        elif args.command == "list-tasks":
            result = _cmd_list_tasks(args)
        elif args.command == "reset-running":
            result = _cmd_reset_running(args)
        elif args.command == "run":
            result = asyncio.run(_cmd_run(args))
        elif args.command == "validate-flow":
            result = _cmd_validate_flow(args)
        else:
            parser.error(f"unknown command: {args.command}")
            return
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status") == "failed":
        raise SystemExit(1)


async def _cmd_check(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config(args.config)
    base_url = args.base_url or config.bitbrowser.base_url
    client = BitBrowserClient(base_url=base_url, timeout_seconds=config.bitbrowser.request_timeout_seconds)

    result: dict[str, Any] = {"base_url": base_url}
    await client.health()
    result["health"] = True

    listing = await client.list_browsers(page=0, page_size=args.list_page_size)
    result["browser_list"] = summarize_browser_list(listing)

    if not args.browser_id:
        result["cdp"] = "skipped: pass --browser-id to verify Playwright CDP"
        return result

    opened = await client.open_browser(
        args.browser_id,
        queue=True,
        ignore_default_urls=True,
        new_page_url=args.url,
    )
    connector = PlaywrightConnector(
        default_navigation_timeout_ms=config.playwright.default_navigation_timeout_ms,
        default_action_timeout_ms=config.playwright.default_action_timeout_ms,
    )
    screenshot_path = Path(args.screenshot)
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    connected = await connector.connect(str(opened["ws"]))
    try:
        await connected.page.goto(args.url, wait_until="domcontentloaded")
        title = await connected.page.title()
        await connected.page.screenshot(path=str(screenshot_path), full_page=True)
        result["cdp"] = {
            "connected": True,
            "browser_id": args.browser_id,
            "pid": opened.get("pid"),
            "core_version": opened.get("coreVersion"),
            "ws": opened.get("ws"),
            "final_url": connected.page.url,
            "title": title,
            "screenshot": str(screenshot_path),
        }
    finally:
        await connected.close()
    return result


async def _cmd_run_one(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config(args.config)
    inputs: dict[str, Any] = {"url": args.url}
    for item in args.input:
        if "=" not in item:
            raise ValueError(f"--input must be key=value, got {item!r}")
        key, value = item.split("=", 1)
        inputs[key] = value
    task = Task(
        id=args.task_id,
        browser_id=args.browser_id,
        flow_type=args.flow_type,
        flow=args.flow,
        inputs=inputs,
    )
    return await run_one_task(task, config, close_after=args.close_window)


async def _cmd_run_tasks_file(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config(args.config)
    raw_tasks = load_tasks(Path(args.tasks))
    if args.limit is not None:
        raw_tasks = raw_tasks[: args.limit]

    results = []
    for raw in raw_tasks:
        task = task_from_mapping(raw)
        results.append(await run_one_task(task, config))
    return {"status": "success", "count": len(results), "results": results}


def _open_storage(config_path: str | None) -> tuple[Any, Storage]:
    config = load_config(config_path)
    storage = Storage(config.paths.sqlite)
    storage.init_schema()
    return config, storage


def _cmd_import_tasks(args: argparse.Namespace) -> dict[str, Any]:
    config, storage = _open_storage(args.config)
    try:
        raw_tasks = load_tasks(Path(args.tasks))
        tasks = [task_from_mapping(raw) for raw in raw_tasks]
        result = storage.import_tasks(tasks, replace=args.replace)
        return {"status": "success", "sqlite": str(config.paths.sqlite), **result}
    finally:
        storage.close()


def _cmd_list_tasks(args: argparse.Namespace) -> dict[str, Any]:
    config, storage = _open_storage(args.config)
    try:
        tasks = storage.list_tasks(status=args.status, limit=args.limit)
        return {"status": "success", "sqlite": str(config.paths.sqlite), "count": len(tasks), "tasks": tasks}
    finally:
        storage.close()


def _cmd_reset_running(args: argparse.Namespace) -> dict[str, Any]:
    config, storage = _open_storage(args.config)
    try:
        reset_status = args.as_status or config.scheduler.recover_running_tasks_as
        count = storage.reset_running(status=reset_status)
        return {"status": "success", "sqlite": str(config.paths.sqlite), "reset": count, "as_status": reset_status}
    finally:
        storage.close()


def _cmd_validate_flow(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config(args.config)
    flow = load_declarative_flow(config.paths.declarative_flow_dir, args.flow)
    result = FlowValidator().validate(flow)
    return {
        "status": "success" if result.ok else "failed",
        "ok": result.ok,
        "errors": result.errors,
        "warnings": result.warnings,
    }


async def _cmd_run(args: argparse.Namespace) -> dict[str, Any]:
    config, storage = _open_storage(args.config)
    try:
        recovered = storage.reset_running(status=config.scheduler.recover_running_tasks_as)
        imported = None
        if args.tasks:
            raw_tasks = load_tasks(Path(args.tasks))
            tasks = [task_from_mapping(raw) for raw in raw_tasks]
            imported = storage.import_tasks(tasks, replace=args.replace)
        scheduler = Scheduler(config=config, storage=storage, once=args.once)
        result = await scheduler.run()
        result["sqlite"] = str(config.paths.sqlite)
        result["recovered_running_tasks"] = recovered
        if imported is not None:
            result["imported"] = imported
        return result
    finally:
        storage.close()


def summarize_browser_list(listing: dict[str, Any]) -> dict[str, Any]:
    data = listing.get("data")
    if not isinstance(data, dict):
        return {"raw": listing}

    items = data.get("list") or data.get("items") or data.get("data") or []
    summary_items = []
    if isinstance(items, list):
        for item in items[:10]:
            if not isinstance(item, dict):
                continue
            summary_items.append(
                {
                    "id": item.get("id"),
                    "seq": item.get("seq"),
                    "name": item.get("name"),
                    "remark": item.get("remark"),
                    "opened": item.get("opened"),
                }
            )

    return {
        "total": data.get("total") or data.get("totalNum") or data.get("count"),
        "items": summary_items,
    }


if __name__ == "__main__":
    main()
