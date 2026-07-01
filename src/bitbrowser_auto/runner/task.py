from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bitbrowser_auto.observability import ArtifactManager


@dataclass
class Task:
    id: str
    browser_id: str
    flow_type: str
    flow: str
    inputs: dict[str, Any] = field(default_factory=dict)
    goal: str | None = None


@dataclass
class RunContext:
    page: Any
    context: Any
    browser: Any
    task: Task
    inputs: dict[str, Any]
    artifacts: ArtifactManager
    bitbrowser: Any
    logger: Any = None
