from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from .task import RunContext


async def run_python_flow(ctx: RunContext, flow_dir: Path, name: str) -> Any:
    path = Path(name)
    if not path.suffix:
        path = flow_dir / f"{name}.py"
    if not path.exists():
        raise FileNotFoundError(f"Python flow not found: {path}")

    spec = importlib.util.spec_from_file_location(f"bitbrowser_auto_user_flow_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load Python flow: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run = getattr(module, "run", None)
    if run is None:
        raise AttributeError(f"Python flow must define async def run(ctx): {path}")
    result = run(ctx)
    if not hasattr(result, "__await__"):
        raise TypeError(f"Python flow run(ctx) must be async: {path}")
    return await result

