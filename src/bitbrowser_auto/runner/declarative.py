from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from bitbrowser_auto.observability.trace import maybe_capture_step_screenshot, step_metadata

from .task import RunContext


TEMPLATE_PATTERN = re.compile(r"{{\s*([^}]+?)\s*}}")

CORE_ACTION_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "goto": ("url",),
    "click": ("selector",),
    "fill": ("selector", "value"),
    "press": ("selector", "key"),
    "wait_for": ("selector",),
    "wait_for_url": ("url",),
    "extract_text": ("selector", "save_as"),
    "extract_attr": ("selector", "attr", "save_as"),
    "screenshot": (),
    "assert_text": ("selector", "text"),
    "if_visible": ("selector", "then"),
    "if_text": ("selector", "text", "then"),
    "playwright": ("target", "method"),
}

ALLOWED_PLAYWRIGHT_TARGETS = {"page", "context", "locator", "keyboard", "mouse"}
ALLOWED_PLAYWRIGHT_METHODS: dict[str, set[str]] = {
    "page": {
        "go_back",
        "go_forward",
        "goto",
        "locator",
        "reload",
        "screenshot",
        "title",
        "wait_for_load_state",
        "wait_for_timeout",
        "wait_for_url",
    },
    "context": {"new_page"},
    "locator": {
        "check",
        "click",
        "count",
        "fill",
        "first",
        "get_attribute",
        "inner_text",
        "is_visible",
        "last",
        "nth",
        "press",
        "screenshot",
        "select_option",
        "wait_for",
    },
    "keyboard": {"press", "type"},
    "mouse": {"click", "dblclick", "down", "move", "up", "wheel"},
}


@dataclass
class DeclarativeRunner:
    screenshot_policy: str = "on_error"
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
        trace.update(step_metadata(step))
        try:
            result = await self._dispatch(ctx, step, outputs)
            trace["ok"] = True
            if result is not None:
                trace["result"] = result
                if action == "screenshot" and isinstance(result, dict) and result.get("path"):
                    trace["screenshot"] = result["path"]
        except Exception as exc:
            trace["error"] = str(exc)
            raise
        finally:
            trace["url"] = getattr(ctx.page, "url", None)
            trace["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
            await maybe_capture_step_screenshot(ctx, trace, policy=self.screenshot_policy)
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

        if action == "if_text":
            selector = render_template(str(step["selector"]), ctx, outputs)
            expected = render_template(str(step["text"]), ctx, outputs)
            text = await page.locator(selector).inner_text(timeout=step.get("timeout_ms"))
            if expected in text:
                for child in step.get("then", []):
                    await self._run_step(ctx, child, outputs, len(self.trace_steps) + 1)
            return None

        if action == "playwright":
            return await self._run_playwright(ctx, step, outputs)

        raise ValueError(f"Unsupported declarative action: {action}")

    async def _run_playwright(self, ctx: RunContext, step: dict[str, Any], outputs: dict[str, Any]) -> Any:
        target_name = str(step["target"])
        method_name = str(step["method"])
        target = _resolve_target(ctx, target_name)
        result = await _call_allowed(target_name, target, method_name, step, ctx, outputs)

        current_target_name = _next_target_name(target_name, method_name)
        for link in step.get("chain", []) or []:
            if not current_target_name:
                raise ValueError(f"Cannot chain after {target_name}.{method_name}")
            method_name = str(link["method"])
            result = await _call_allowed(current_target_name, result, method_name, link, ctx, outputs)
            current_target_name = _next_target_name(current_target_name, method_name)

        save_as = step.get("save_as")
        if save_as:
            outputs[str(save_as)] = await _serialize_result(result)
            return {"save_as": save_as}
        return await _traceable_result(result)


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


def _resolve_target(ctx: RunContext, target_name: str) -> Any:
    if target_name == "page":
        return ctx.page
    if target_name == "context":
        return ctx.context
    if target_name == "keyboard":
        return ctx.page.keyboard
    if target_name == "mouse":
        return ctx.page.mouse
    if target_name == "locator":
        return ctx.page
    raise ValueError(f"Unsupported Playwright target: {target_name}")


async def _call_allowed(
    target_name: str,
    target: Any,
    method_name: str,
    spec: dict[str, Any],
    ctx: RunContext,
    outputs: dict[str, Any],
) -> Any:
    if method_name not in ALLOWED_PLAYWRIGHT_METHODS.get(target_name, set()):
        raise ValueError(f"Playwright method not allowed: {target_name}.{method_name}")

    if target_name == "locator" and target is ctx.page:
        selector = spec.get("selector")
        if not selector:
            raise ValueError("locator target requires selector")
        target = ctx.page.locator(render_template(str(selector), ctx, outputs))

    args = _render_value(spec.get("args", []), ctx, outputs)
    kwargs = _render_value(spec.get("kwargs", {}), ctx, outputs)
    if not isinstance(args, list):
        raise ValueError("playwright args must be a list")
    if not isinstance(kwargs, dict):
        raise ValueError("playwright kwargs must be a mapping")

    method = getattr(target, method_name)
    result = method(*args, **kwargs)
    if hasattr(result, "__await__"):
        result = await result
    return result


def _render_value(value: Any, ctx: RunContext, outputs: dict[str, Any]) -> Any:
    if isinstance(value, str):
        return render_template(value, ctx, outputs)
    if isinstance(value, list):
        return [_render_value(item, ctx, outputs) for item in value]
    if isinstance(value, dict):
        return {key: _render_value(item, ctx, outputs) for key, item in value.items()}
    return value


def _next_target_name(target_name: str, method_name: str) -> str | None:
    if target_name == "page" and method_name == "locator":
        return "locator"
    if target_name == "context" and method_name == "new_page":
        return "page"
    if target_name == "locator" and method_name in {"first", "last", "nth"}:
        return "locator"
    return None


async def _serialize_result(result: Any) -> Any:
    if isinstance(result, (str, int, float, bool)) or result is None:
        return result
    if isinstance(result, list):
        return [await _serialize_result(item) for item in result]
    if isinstance(result, dict):
        return {str(key): await _serialize_result(value) for key, value in result.items()}
    return str(result)


async def _traceable_result(result: Any) -> Any:
    serialized = await _serialize_result(result)
    if serialized is None:
        return None
    return {"result": serialized}
