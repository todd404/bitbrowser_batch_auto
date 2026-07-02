from __future__ import annotations

import importlib.util
import inspect
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bitbrowser_auto.observability.trace import maybe_capture_step_screenshot, summarize_value

from .task import RunContext


@dataclass
class PythonRunner:
    flow_dir: Path
    screenshot_policy: str = "on_error"
    trace_steps: list[dict[str, Any]] = field(default_factory=list)

    async def run(self, ctx: RunContext, name: str) -> Any:
        path = resolve_python_flow_path(self.flow_dir, name)
        run = load_python_flow_run(path)
        trace: dict[str, Any] = {
            "index": 1,
            "action": "python_flow",
            "flow": path.stem,
            "path": str(path),
            "inputs_summary": summarize_value(ctx.inputs),
            "ok": False,
        }
        started = time.perf_counter()
        try:
            outputs = await run(ctx)
            trace["ok"] = True
            trace["result_summary"] = summarize_value(outputs)
            return outputs if outputs is not None else {}
        except Exception as exc:
            trace["error"] = str(exc)
            raise
        finally:
            trace["url"] = getattr(ctx.page, "url", None)
            trace["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
            await maybe_capture_step_screenshot(ctx, trace, policy=self.screenshot_policy, prefix="python-flow")
            self.trace_steps.append(trace)


async def run_python_flow(ctx: RunContext, flow_dir: Path, name: str) -> Any:
    return await PythonRunner(flow_dir=flow_dir).run(ctx, name)


def resolve_python_flow_path(flow_dir: Path, name: str) -> Path:
    path = Path(name)
    if not path.suffix:
        path = flow_dir / f"{name}.py"
    if not path.exists():
        raise FileNotFoundError(f"Python flow not found: {path}")
    if path.suffix != ".py":
        raise ValueError(f"Python flow must be a .py file: {path}")
    return path


def load_python_flow_run(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(f"bitbrowser_auto_user_flow_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load Python flow: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run = getattr(module, "run", None)
    if run is None:
        raise AttributeError(f"Python flow must define async def run(ctx): {path}")
    if not inspect.iscoroutinefunction(run):
        raise TypeError(f"Python flow run(ctx) must be async: {path}")
    return run
