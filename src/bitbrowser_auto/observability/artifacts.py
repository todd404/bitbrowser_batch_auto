from __future__ import annotations

import json
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class ArtifactManager:
    root: Path
    task_id: str

    @property
    def task_dir(self) -> Path:
        return self.root / self.task_id

    @property
    def screenshot_dir(self) -> Path:
        return self.task_dir / "screenshots"

    def prepare(self) -> None:
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def path(self, relative: str) -> str:
        self.prepare()
        return str(self.task_dir / relative)

    async def screenshot(self, page: Any, name: str, *, full_page: bool = True) -> str:
        self.prepare()
        filename = name if name.endswith(".png") else f"{name}.png"
        path = self.screenshot_dir / filename
        await page.screenshot(path=str(path), full_page=full_page)
        return str(path)

    def write_json(self, relative: str, data: dict[str, Any]) -> str:
        self.prepare()
        path = self.task_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    def write_text(self, relative: str, text: str) -> str:
        self.prepare()
        path = self.task_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return str(path)

    def write_error(self, exc: BaseException) -> str:
        return self.write_text("error.txt", "".join(traceback.format_exception(exc)))
