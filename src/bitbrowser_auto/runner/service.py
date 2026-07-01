from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Any

from bitbrowser_auto.bitbrowser import BitBrowserClient
from bitbrowser_auto.browser import PlaywrightConnector
from bitbrowser_auto.config import AppConfig
from bitbrowser_auto.observability import ArtifactManager
from bitbrowser_auto.observability.artifacts import utc_now_iso

from .declarative import DeclarativeRunner
from .flow_loader import load_declarative_flow
from .flow_validator import FlowValidator
from .python_flow import run_python_flow
from .task import RunContext, Task


async def run_one_task(
    task: Task,
    config: AppConfig,
    *,
    close_after: bool | None = None,
    raise_on_failure: bool = True,
) -> dict[str, Any]:
    artifacts = ArtifactManager(root=config.paths.artifact_dir, task_id=task.id)
    artifacts.prepare()
    started_at = utc_now_iso()
    client = BitBrowserClient(
        base_url=config.bitbrowser.base_url,
        timeout_seconds=config.bitbrowser.request_timeout_seconds,
    )
    connector = PlaywrightConnector(
        default_navigation_timeout_ms=config.playwright.default_navigation_timeout_ms,
        default_action_timeout_ms=config.playwright.default_action_timeout_ms,
    )
    close_window = config.scheduler.close_window_after_task if close_after is None else close_after
    connected = None
    opened: dict[str, Any] | None = None
    trace: list[dict[str, Any]] = []
    outputs: Any = {}

    try:
        opened = await client.open_browser(
            task.browser_id,
            queue=True,
            ignore_default_urls=True,
            new_page_url=str(task.inputs.get("url")) if task.inputs.get("url") else None,
        )
        connected = await connector.connect(str(opened["ws"]))
        ctx = RunContext(
            page=connected.page,
            context=connected.context,
            browser=connected.browser,
            task=task,
            inputs=task.inputs,
            artifacts=artifacts,
            bitbrowser=client,
        )

        if task.flow_type == "declarative":
            flow = load_declarative_flow(config.paths.declarative_flow_dir, task.flow)
            validation = FlowValidator().validate(flow)
            if not validation.ok:
                raise ValueError("Invalid declarative flow: " + "; ".join(validation.errors))
            runner = DeclarativeRunner()
            result = await runner.run(ctx, flow)
            outputs = result["outputs"]
            trace = result["trace"]
        elif task.flow_type == "python":
            outputs = await run_python_flow(ctx, config.paths.python_flow_dir, task.flow)
        elif task.flow_type == "agent":
            raise NotImplementedError("Agent flow is reserved but not enabled in this version.")
        else:
            raise ValueError(f"unknown flow_type: {task.flow_type}")

        finished_at = utc_now_iso()
        trace_path = artifacts.write_json(
            "trace.json",
            {
                "task_id": task.id,
                "browser_id": task.browser_id,
                "started_at": started_at,
                "finished_at": finished_at,
                "steps": trace,
            },
        )
        run_json = {
            "status": "success",
            "task": asdict(task),
            "opened": _opened_summary(opened),
            "outputs": outputs,
            "artifact_dir": str(artifacts.task_dir),
            "trace_path": trace_path,
            "started_at": started_at,
            "finished_at": finished_at,
        }
        artifacts.write_json("run.json", run_json)
        return run_json
    except Exception as exc:
        if connected is not None:
            try:
                await artifacts.screenshot(connected.page, "error", full_page=True)
            except Exception:
                pass
        error_path = artifacts.write_error(exc)
        finished_at = utc_now_iso()
        run_json = {
            "status": "failed",
            "task": asdict(task),
            "opened": _opened_summary(opened),
            "error": str(exc),
            "error_path": error_path,
            "artifact_dir": str(artifacts.task_dir),
            "started_at": started_at,
            "finished_at": finished_at,
        }
        artifacts.write_json("run.json", run_json)
        if raise_on_failure:
            raise
        return run_json
    finally:
        if connected is not None:
            await connected.close()
        if close_window and opened is not None:
            await client.close_browser(task.browser_id)
            await asyncio.sleep(config.scheduler.close_wait_seconds)


def task_from_mapping(data: dict[str, Any]) -> Task:
    required = ["id", "browser_id", "flow_type", "flow"]
    missing = [key for key in required if not data.get(key)]
    if missing:
        raise ValueError(f"Task missing required fields: {', '.join(missing)}")
    inputs = data.get("inputs") or {}
    if not isinstance(inputs, dict):
        raise ValueError("Task inputs must be a mapping")
    return Task(
        id=str(data["id"]),
        browser_id=str(data["browser_id"]),
        flow_type=str(data["flow_type"]),
        flow=str(data["flow"]),
        inputs=inputs,
        goal=str(data["goal"]) if data.get("goal") else None,
    )


def _opened_summary(opened: dict[str, Any] | None) -> dict[str, Any] | None:
    if not opened:
        return None
    return {
        "ws": opened.get("ws"),
        "http": opened.get("http"),
        "pid": opened.get("pid"),
        "coreVersion": opened.get("coreVersion"),
        "seq": opened.get("seq"),
        "name": opened.get("name"),
    }
