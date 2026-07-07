#!/usr/bin/env python3
from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT_MARKERS = ("pyproject.toml", ".git")
NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def find_repo_root(start: Path) -> Path:
    for path in (start, *start.parents):
        if any((path / marker).exists() for marker in ROOT_MARKERS):
            return path
    return start


REPO_ROOT = find_repo_root(Path(__file__).resolve())
SRC = REPO_ROOT / "src"
if SRC.exists():
    sys.path.insert(0, str(SRC))


def load_spec(path: str) -> dict[str, Any]:
    if path == "-":
        raw = sys.stdin.read()
        suffix = ".json"
    else:
        spec_path = Path(path)
        raw = spec_path.read_text(encoding="utf-8")
        suffix = spec_path.suffix.lower()

    if suffix in {".yaml", ".yml"}:
        import yaml

        data = yaml.safe_load(raw) or {}
    else:
        data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Spec must be a mapping")
    return data


def safe_name(value: str) -> str:
    name = value.strip().replace(" ", "_")
    if not name:
        raise ValueError("Flow name is required")
    if not NAME_RE.match(name):
        raise ValueError("Flow name may contain only letters, digits, underscore, and hyphen")
    return name


def load_config(config_path: str | None) -> Any:
    from bitbrowser_auto.config import load_config as load_project_config

    return load_project_config(config_path)


def dump_yaml(path: Path, data: dict[str, Any]) -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )


def ensure_can_write(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")


def materialize_declarative(spec: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    from bitbrowser_auto.runner.flow_validator import FlowValidator

    name = safe_name(args.name or str(spec.get("name") or ""))
    config = load_config(args.config)
    flow_dir = Path(args.declarative_dir) if args.declarative_dir else config.paths.declarative_flow_dir
    path = flow_dir / f"{name}.yaml"
    ensure_can_write(path, args.overwrite)

    flow: dict[str, Any] = {"name": name}
    for key in ("display_name", "description", "category", "version", "start_url", "inputs", "steps"):
        if key in spec:
            flow[key] = spec[key]
    flow.setdefault("version", 1)

    validation = FlowValidator().validate(flow)
    result = {
        "flow_type": "declarative",
        "name": name,
        "path": str(path),
        "validation": {
            "ok": validation.ok,
            "errors": validation.errors,
            "warnings": validation.warnings,
        },
    }
    if not validation.ok and not args.allow_invalid:
        result["status"] = "failed"
        result["message"] = "Flow was not written because validation failed. Use --allow-invalid to write anyway."
        return result

    dump_yaml(path, flow)
    result["status"] = "success" if validation.ok else "written_with_validation_errors"
    return result


def materialize_python(spec: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    name = safe_name(args.name or str(spec.get("name") or ""))
    config = load_config(args.config)
    flow_dir = Path(args.python_dir) if args.python_dir else config.paths.python_flow_dir
    path = flow_dir / f"{name}.py"
    meta_path = flow_dir / f"{name}.meta.yaml"

    source = spec.get("python") or spec.get("source")
    if args.python_file:
        source = Path(args.python_file).read_text(encoding="utf-8")
    if not isinstance(source, str) or "async def run" not in source:
        raise ValueError("Python specs must provide source containing `async def run(ctx)`")

    validation = {"ok": True, "errors": []}
    try:
        validate_python_source(source, path)
    except Exception as exc:
        validation = {"ok": False, "errors": [str(exc)]}
        if not args.allow_invalid:
            return {
                "status": "failed",
                "flow_type": "python",
                "name": name,
                "path": str(path),
                "validation": validation,
                "message": "Python flow was not written because import validation failed. Use --allow-invalid to write it anyway.",
            }

    ensure_can_write(path, args.overwrite)
    if meta_path.exists() and not args.overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {meta_path}")

    flow_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(source.rstrip() + "\n", encoding="utf-8")

    meta: dict[str, Any] = {}
    for key in ("display_name", "description", "category", "inputs"):
        if key in spec:
            meta[key] = spec[key]
    if meta:
        dump_yaml(meta_path, meta)

    return {
        "status": "success" if validation["ok"] else "written_with_validation_errors",
        "flow_type": "python",
        "name": name,
        "path": str(path),
        "meta_path": str(meta_path) if meta else None,
        "validation": validation,
    }


def validate_python_source(source: str, path: Path) -> None:
    namespace: dict[str, Any] = {"__file__": str(path), "__name__": f"bitbrowser_auto_user_flow_{path.stem}"}
    code = compile(source, str(path), "exec")
    exec(code, namespace)
    run = namespace.get("run")
    if run is None:
        raise AttributeError(f"Python flow must define async def run(ctx): {path}")
    if not inspect.iscoroutinefunction(run):
        raise TypeError(f"Python flow run(ctx) must be async: {path}")


def infer_flow_type(spec: dict[str, Any], explicit: str | None) -> str:
    if explicit:
        return explicit
    if spec.get("flow_type"):
        return str(spec["flow_type"])
    if "steps" in spec:
        return "declarative"
    if "python" in spec or "source" in spec:
        return "python"
    raise ValueError("Could not infer flow type; set flow_type to declarative or python")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize a flow spec into this BitBrowser project.")
    parser.add_argument("--spec", required=True, help="JSON/YAML spec path, or '-' for stdin.")
    parser.add_argument("--type", choices=["declarative", "python"], default=None, help="Override spec flow_type.")
    parser.add_argument("--name", default=None, help="Override spec name.")
    parser.add_argument("--config", default=None, help="Optional project config path.")
    parser.add_argument("--declarative-dir", default=None, help="Override declarative flow output directory.")
    parser.add_argument("--python-dir", default=None, help="Override Python flow output directory.")
    parser.add_argument("--python-file", default=None, help="Read Python source from this file for Python specs.")
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting existing flow files.")
    parser.add_argument("--allow-invalid", action="store_true", help="Write files even when validation fails.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        spec = load_spec(args.spec)
        flow_type = infer_flow_type(spec, args.type)
        if flow_type == "declarative":
            result = materialize_declarative(spec, args)
        elif flow_type == "python":
            result = materialize_python(spec, args)
        else:
            raise ValueError(f"Unsupported flow type: {flow_type}")
    except Exception as exc:
        result = {"status": "failed", "error": str(exc)}
        print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"success", "written_with_validation_errors"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
