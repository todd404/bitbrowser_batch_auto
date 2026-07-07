from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


PROJECT_IMPORTS = ("bitbrowser_auto", "httpx", "nicegui", "playwright", "webview", "yaml")
MIN_PYTHON = (3, 9)


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def create_venv(venv_dir: Path, python: Path) -> None:
    print(f"Creating virtualenv at {venv_dir} ...", flush=True)
    run([str(python), "-m", "venv", str(venv_dir)], cwd=venv_dir.parent)


def imports_are_available(python: Path) -> bool:
    code = "\n".join(f"import {name}" for name in PROJECT_IMPORTS)
    result = subprocess.run([str(python), "-c", code], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def needs_install(root_dir: Path, venv_python_path: Path, stamp: Path, force: bool) -> bool:
    if force or not stamp.exists():
        return True
    if (root_dir / "pyproject.toml").stat().st_mtime > stamp.stat().st_mtime:
        return True
    return not imports_are_available(venv_python_path)


def install_project(root_dir: Path, python: Path, stamp: Path) -> None:
    print("Installing project dependencies into .venv ...", flush=True)
    run([str(python), "-m", "pip", "install", "-e", str(root_dir)], cwd=root_dir)
    stamp.touch()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or refresh the project virtualenv.")
    parser.add_argument(
        "--venv",
        default=".venv",
        help="Virtualenv directory, relative to the project root unless absolute. Default: .venv",
    )
    parser.add_argument("--force", action="store_true", help="Reinstall the project even if the stamp is current.")
    parser.add_argument("--print-python", action="store_true", help="Print the venv Python path after setup.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if sys.version_info < MIN_PYTHON:
        required = ".".join(str(part) for part in MIN_PYTHON)
        current = ".".join(str(part) for part in sys.version_info[:3])
        raise SystemExit(f"Python {required}+ is required, current Python is {current}.")

    root_dir = Path(__file__).resolve().parents[1]
    venv_dir = Path(args.venv)
    if not venv_dir.is_absolute():
        venv_dir = root_dir / venv_dir

    python = venv_python(venv_dir)
    stamp = venv_dir / ".bitbrowser-auto-install-stamp"

    if not python.exists():
        create_venv(venv_dir, Path(sys.executable))

    if needs_install(root_dir, python, stamp, args.force):
        install_project(root_dir, python, stamp)
    else:
        print(f"Virtualenv is ready at {venv_dir}.")

    if args.print_python:
        print(python)


if __name__ == "__main__":
    main()
