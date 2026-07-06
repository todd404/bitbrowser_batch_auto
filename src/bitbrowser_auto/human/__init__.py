"""Human-like cursor helpers.

See ``docs/human-mouse-simulation.md`` for the algorithm rationale
(Bézier path + WindMouse jitter, minimum-jerk velocity, Fitts' law timing,
overshoot correction, tremor, click dwell).
"""

from .mouse import (
    ClickResult,
    CursorTracker,
    MoveResult,
    MouseConfig,
    human_click,
    human_move,
)

__all__ = [
    "ClickResult",
    "CursorTracker",
    "MoveResult",
    "MouseConfig",
    "human_click",
    "human_move",
]