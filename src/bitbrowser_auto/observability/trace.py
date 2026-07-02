from __future__ import annotations

from typing import Any


SCREENSHOT_POLICIES = {"off", "on_error", "every_step"}
SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "password",
    "passwd",
    "proxyPassword",
    "secret",
    "token",
    "value",
}


def normalize_screenshot_policy(policy: str | None) -> str:
    if policy in SCREENSHOT_POLICIES:
        return str(policy)
    return "on_error"


def step_metadata(step: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in ("selector", "url", "target", "method", "save_as", "attr", "state", "key", "name", "timeout_ms"):
        if key in step:
            metadata[key] = summarize_value(step[key], key=key)
    if "args" in step:
        metadata["args_summary"] = summarize_value(step["args"], key="args")
    if "kwargs" in step:
        metadata["kwargs_summary"] = summarize_value(step["kwargs"], key="kwargs")
    if "chain" in step:
        metadata["chain_summary"] = summarize_value(step["chain"], key="chain")
    if "then" in step:
        metadata["then_steps"] = len(step["then"]) if isinstance(step["then"], list) else "invalid"
    return metadata


def summarize_value(value: Any, *, key: str | None = None, max_length: int = 160) -> Any:
    if key and _is_sensitive_key(key):
        return "<redacted>"
    if isinstance(value, str):
        if len(value) <= max_length:
            return value
        return f"{value[:max_length]}..."
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [summarize_value(item, max_length=max_length) for item in value[:10]]
    if isinstance(value, tuple):
        return [summarize_value(item, max_length=max_length) for item in value[:10]]
    if isinstance(value, dict):
        return {
            str(item_key): summarize_value(item_value, key=str(item_key), max_length=max_length)
            for item_key, item_value in value.items()
        }
    return str(value)


async def maybe_capture_step_screenshot(
    ctx: Any,
    trace: dict[str, Any],
    *,
    policy: str,
    prefix: str = "step",
) -> None:
    normalized = normalize_screenshot_policy(policy)
    if normalized == "off":
        return
    if normalized == "on_error" and trace.get("ok"):
        return
    if trace.get("screenshot"):
        return
    if is_screenshot_error(trace.get("error")):
        trace["screenshot_skipped"] = "error occurred while taking a screenshot"
        return

    try:
        index = int(trace.get("index") or 0)
        path = await ctx.artifacts.screenshot(ctx.page, f"{prefix}-{index:03d}", full_page=True)
        trace["screenshot"] = path
    except Exception as exc:
        trace["screenshot_error"] = str(exc)


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return lowered in {item.lower() for item in SENSITIVE_KEYS} or any(
        token in lowered for token in ("password", "secret", "token", "cookie")
    )


def is_screenshot_error(error: Any) -> bool:
    if not error:
        return False
    return "screenshot" in str(error).lower()
