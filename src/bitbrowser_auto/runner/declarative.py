from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from .task import RunContext


TEMPLATE_PATTERN = re.compile(r"{{\s*([^}]+?)\s*}}")


@dataclass
class DeclarativeRunner:
    trace_steps: list[dict[str, Any]] = field(default_factory=list)

    async def run(self, ctx: RunContext, flow: dict[str, Any]) -> dict[str, Any]:
        outputs: dict[str, Any] = {}
        steps = flow.get("steps") or []
        if not isinstance(steps, list):
            raise ValueError("Declarative flow `steps` must be a list")
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                raise ValueError(f"Step {index} must be a mapping")
            await self._run_step(ctx, step, outputs, index)
        return {"outputs": outputs, "trace": self.trace_steps}

    async def _run_step(
        self,
        ctx: RunContext,
        step: dict[str, Any],
        outputs: dict[str, Any],
        index: int,
    ) -> None:
        action = step.get("action")
        if not action:
            raise ValueError(f"Step {index} missing action")

        started = time.perf_counter()
        trace: dict[str, Any] = {"index": index, "action": action, "ok": False}
        try:
            result = await self._dispatch(ctx, step, outputs)
            trace["ok"] = True
            if result is not None:
                trace["result"] = result
        except Exception as exc:
            trace["error"] = str(exc)
            raise
        finally:
            trace["url"] = getattr(ctx.page, "url", None)
            trace["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
            self.trace_steps.append(trace)

    async def _dispatch(self, ctx: RunContext, step: dict[str, Any], outputs: dict[str, Any]) -> Any:
        action = step["action"]
        page = ctx.page

        if action == "goto":
            url = render_template(str(step["url"]), ctx, outputs)
            await page.goto(url, wait_until=step.get("wait_until", "domcontentloaded"), timeout=step.get("timeout_ms"))
            return {"url": page.url}

        if action == "click":
            await page.locator(render_template(str(step["selector"]), ctx, outputs)).click(timeout=step.get("timeout_ms"))
            return None

        if action == "fill":
            await page.locator(render_template(str(step["selector"]), ctx, outputs)).fill(
                render_template(str(step.get("value", "")), ctx, outputs),
                timeout=step.get("timeout_ms"),
            )
            return None

        if action == "press":
            await page.locator(render_template(str(step["selector"]), ctx, outputs)).press(
                str(step["key"]),
                timeout=step.get("timeout_ms"),
            )
            return None

        if action == "wait_for":
            state = step.get("state", "visible")
            await page.locator(render_template(str(step["selector"]), ctx, outputs)).wait_for(
                state=state,
                timeout=step.get("timeout_ms"),
            )
            return None

        if action == "wait_for_url":
            url = render_template(str(step["url"]), ctx, outputs)
            await page.wait_for_url(url, timeout=step.get("timeout_ms"))
            return {"url": page.url}

        if action == "extract_text":
            selector = render_template(str(step["selector"]), ctx, outputs)
            value = await page.locator(selector).inner_text(timeout=step.get("timeout_ms"))
            outputs[str(step["save_as"])] = value
            return {"save_as": step["save_as"]}

        if action == "extract_attr":
            selector = render_template(str(step["selector"]), ctx, outputs)
            attr = str(step["attr"])
            value = await page.locator(selector).get_attribute(attr, timeout=step.get("timeout_ms"))
            outputs[str(step["save_as"])] = value
            return {"save_as": step["save_as"]}

        if action == "screenshot":
            name = render_template(str(step.get("name", "screenshot")), ctx, outputs)
            path = await ctx.artifacts.screenshot(page, name, full_page=bool(step.get("full_page", True)))
            outputs[f"screenshot_{name}"] = path
            return {"path": path}

        if action == "assert_text":
            selector = render_template(str(step["selector"]), ctx, outputs)
            expected = render_template(str(step["text"]), ctx, outputs)
            text = await page.locator(selector).inner_text(timeout=step.get("timeout_ms"))
            if expected not in text:
                raise AssertionError(f"Expected text {expected!r} in {selector!r}, got {text!r}")
            return None

        if action == "if_visible":
            selector = render_template(str(step["selector"]), ctx, outputs)
            if await page.locator(selector).is_visible(timeout=step.get("timeout_ms", 1000)):
                for child in step.get("then", []):
                    await self._run_step(ctx, child, outputs, len(self.trace_steps) + 1)
            return None

        raise ValueError(f"Unsupported declarative action: {action}")


def render_template(value: str, ctx: RunContext, outputs: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        expr = match.group(1).strip()
        if expr.startswith("inputs."):
            key = expr.removeprefix("inputs.")
            if key not in ctx.inputs:
                raise KeyError(f"Missing template input: {expr}")
            return str(ctx.inputs[key])
        if expr.startswith("outputs."):
            key = expr.removeprefix("outputs.")
            if key not in outputs:
                raise KeyError(f"Missing template output: {expr}")
            return str(outputs[key])
        if expr == "task.id":
            return ctx.task.id
        raise KeyError(f"Unsupported template variable: {expr}")

    return TEMPLATE_PATTERN.sub(replace, value)
