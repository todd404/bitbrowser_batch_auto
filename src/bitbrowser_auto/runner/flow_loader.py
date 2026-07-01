from __future__ import annotations

from pathlib import Path
from typing import Any


def load_declarative_flow(flow_dir: Path, name: str) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to load declarative flows. Run `pip install -e .`.") from exc

    candidates = [Path(name)]
    if not Path(name).suffix:
        candidates = [flow_dir / f"{name}.yaml", flow_dir / f"{name}.yml", flow_dir / f"{name}.json"]
    for path in candidates:
        if path.exists():
            if path.suffix == ".json":
                import json

                data = json.loads(path.read_text(encoding="utf-8"))
            else:
                with path.open("r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
            if not isinstance(data, dict):
                raise ValueError(f"Flow must contain a mapping: {path}")
            return data
    searched = ", ".join(str(p) for p in candidates)
    raise FileNotFoundError(f"Declarative flow not found: {name}; searched {searched}")


def load_tasks(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        import csv
        import json

        with path.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        tasks: list[dict[str, Any]] = []
        for row in rows:
            task = dict(row)
            task["inputs"] = json.loads(row.get("inputs_json") or "{}")
            tasks.append(task)
        return tasks

    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to load task files. Run `pip install -e .`.") from exc

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if isinstance(data, dict):
        tasks = data.get("tasks") or []
    else:
        tasks = data
    if not isinstance(tasks, list):
        raise ValueError(f"Task file must contain a list or a tasks list: {path}")
    return tasks

