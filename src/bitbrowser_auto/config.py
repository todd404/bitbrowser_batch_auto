from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path("configs/app.example.yaml")


@dataclass
class BitBrowserConfig:
    base_url: str = "http://127.0.0.1:54345"
    request_timeout_seconds: float = 30


@dataclass
class SchedulerConfig:
    max_concurrent_windows: int = 3
    open_interval_seconds: float = 2
    task_timeout_seconds: float = 300
    close_window_after_task: bool = False
    close_wait_seconds: float = 5
    max_retries: int = 1
    recover_running_tasks_as: str = "pending"


@dataclass
class PathsConfig:
    sqlite: Path = Path("data/scheduler.sqlite3")
    artifact_dir: Path = Path("artifacts")
    declarative_flow_dir: Path = Path("flows/declarative")
    python_flow_dir: Path = Path("flows/py")


@dataclass
class PlaywrightConfig:
    default_navigation_timeout_ms: int = 60_000
    default_action_timeout_ms: int = 30_000


@dataclass
class TraceConfig:
    enabled: bool = True
    screenshot_policy: str = "on_error"


@dataclass
class UiConfig:
    default_mode: str = "desktop"
    host: str = "127.0.0.1"
    port: int = 0
    title: str = "比特浏览器自动化"
    window_width: int = 1200
    window_height: int = 800


@dataclass
class AppConfig:
    bitbrowser: BitBrowserConfig = field(default_factory=BitBrowserConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    playwright: PlaywrightConfig = field(default_factory=PlaywrightConfig)
    trace: TraceConfig = field(default_factory=TraceConfig)
    ui: UiConfig = field(default_factory=UiConfig)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to load YAML config files. Run `pip install -e .`.") from exc

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a mapping: {path}")
    return data


def _paths_from(data: dict[str, Any]) -> PathsConfig:
    return PathsConfig(
        sqlite=Path(data.get("sqlite", PathsConfig.sqlite)),
        artifact_dir=Path(data.get("artifact_dir", PathsConfig.artifact_dir)),
        declarative_flow_dir=Path(data.get("declarative_flow_dir", PathsConfig.declarative_flow_dir)),
        python_flow_dir=Path(data.get("python_flow_dir", PathsConfig.python_flow_dir)),
    )


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    raw = _load_yaml(config_path)
    bitbrowser = raw.get("bitbrowser") or {}
    scheduler = raw.get("scheduler") or {}
    paths = raw.get("paths") or {}
    playwright = raw.get("playwright") or {}
    trace = raw.get("trace") or {}
    ui = raw.get("ui") or {}

    return AppConfig(
        bitbrowser=BitBrowserConfig(
            base_url=str(bitbrowser.get("base_url", BitBrowserConfig.base_url)),
            request_timeout_seconds=float(
                bitbrowser.get("request_timeout_seconds", BitBrowserConfig.request_timeout_seconds)
            ),
        ),
        scheduler=SchedulerConfig(
            max_concurrent_windows=int(
                scheduler.get("max_concurrent_windows", SchedulerConfig.max_concurrent_windows)
            ),
            open_interval_seconds=float(
                scheduler.get("open_interval_seconds", SchedulerConfig.open_interval_seconds)
            ),
            task_timeout_seconds=float(scheduler.get("task_timeout_seconds", SchedulerConfig.task_timeout_seconds)),
            close_window_after_task=bool(
                scheduler.get("close_window_after_task", SchedulerConfig.close_window_after_task)
            ),
            close_wait_seconds=float(scheduler.get("close_wait_seconds", SchedulerConfig.close_wait_seconds)),
            max_retries=int(scheduler.get("max_retries", SchedulerConfig.max_retries)),
            recover_running_tasks_as=str(
                scheduler.get("recover_running_tasks_as", SchedulerConfig.recover_running_tasks_as)
            ),
        ),
        paths=_paths_from(paths),
        playwright=PlaywrightConfig(
            default_navigation_timeout_ms=int(
                playwright.get(
                    "default_navigation_timeout_ms",
                    PlaywrightConfig.default_navigation_timeout_ms,
                )
            ),
            default_action_timeout_ms=int(
                playwright.get("default_action_timeout_ms", PlaywrightConfig.default_action_timeout_ms)
            ),
        ),
        trace=TraceConfig(
            enabled=bool(trace.get("enabled", TraceConfig.enabled)),
            screenshot_policy=str(trace.get("screenshot_policy", TraceConfig.screenshot_policy)),
        ),
        ui=UiConfig(
            default_mode=str(ui.get("default_mode", UiConfig.default_mode)),
            host=str(ui.get("host", UiConfig.host)),
            port=int(ui.get("port", UiConfig.port)),
            title=str(ui.get("title", UiConfig.title)),
            window_width=int(ui.get("window_width", UiConfig.window_width)),
            window_height=int(ui.get("window_height", UiConfig.window_height)),
        ),
    )
