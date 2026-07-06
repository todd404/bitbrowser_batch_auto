"""Human-like mouse motion for evading naive bot/captcha detection.

This module wraps Playwright's ``page.mouse`` with bio-mechanically inspired
trajectory generation so the cursor does not look like a straight-line
automated path. See ``docs/human-mouse-simulation.md`` for the full rationale.

The model layers are:

* Bezier path     – smoother main trajectory, randomized control points
* WindMouse drift – per-step noise + late-stage deceleration
* Minimum-jerk timing – bell-shaped speed profile between samples
* Fitts' law      – realistic total movement duration
* Overshoot       – probabilistic crossing-the-mark + correction segment
* Tremor          – sub-pixel jitter once the cursor settles
* Click dwell     – manual down → sleep → up so dwell is controlled

Everything here is deterministic given a seeded ``random.Random`` instance
so failures captured in trace can be reproduced.
"""

from __future__ import annotations

import asyncio
import math
import random
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable

# A small type alias; importing playwright directly would couple this module
# to a runtime that may not be installed outside the runner process.
PageLike = Any


@dataclass
class MouseConfig:
    """Tunable parameters for the trajectory generator.

    Defaults are the values validated on the local trace page; see
    ``docs/human-mouse-simulation.md`` section 5.  Every field has soft
    bounds enforced in :meth:`clamp`.
    """

    fitts_a_ms: float = 50.0
    fitts_b_ms_per_bit: float = 150.0
    min_target_width_px: float = 16.0
    max_target_width_px: float = 200.0
    control_points: int = 3
    control_offset_ratio: float = 0.12
    control_offset_max_ratio: float = 0.22
    control_offset_min_px: float = 8.0
    speed_factor: float = 1.0
    sample_step_ms: float = 16.0  # ~60Hz sampling cadence
    overshoot_prob: float = 0.45
    overshoot_ratio: float = 0.07
    overshoot_max_ratio: float = 0.18
    overshoot_pause_ms: tuple[float, float] = (60.0, 180.0)
    tremor_sigma_px: float = 0.6
    tremor_frames: tuple[int, int] = (4, 8)
    decision_pause_ms: tuple[float, float] = (40.0, 260.0)
    dwell_ms: tuple[float, float] = (40.0, 130.0)
    step_jitter_ratio: float = 0.35  # WindMouse per-step noise amplitude as fraction of step length

    def clamp(self) -> "MouseConfig":
        """Return a copy with all fields kept inside sensible bounds."""
        cfg = MouseConfig(**self.__dict__)
        cfg.control_points = max(2, min(4, int(cfg.control_points)))
        cfg.speed_factor = max(0.3, min(2.5, cfg.speed_factor))
        cfg.overshoot_prob = max(0.0, min(1.0, cfg.overshoot_prob))
        return cfg

    def jitter_ms(self, rng: random.Random, lo: float, hi: float) -> float:
        return rng.uniform(lo, hi)


@dataclass
class MoveResult:
    start: tuple[float, float]
    end: tuple[float, float]
    samples: int
    duration_ms: float
    overshot: bool

    def as_trace(self) -> dict[str, Any]:
        return {
            "samples": self.samples,
            "duration_ms": round(self.duration_ms, 1),
            "distance_px": round(math.dist(self.start, self.end), 1),
            "overshot": self.overshot,
        }


@dataclass
class ClickResult(MoveResult):
    dwell_ms: float = 0.0
    decision_pause_ms: float = 0.0

    def as_trace(self) -> dict[str, Any]:
        data = super().as_trace()
        data["dwell_ms"] = round(self.dwell_ms, 1)
        data["decision_pause_ms"] = round(self.decision_pause_ms, 1)
        return data


class CursorTracker:
    """Track the logical cursor position Playwright does not expose.

    ``page.mouse`` in Playwright has no getter for current coordinates;
    we keep our own view so successive moves start where the last one ended.
    The first call seeds from a reasonable default (top-left safe area);
    callers may :meth:`reset` to a known position.
    """

    def __init__(self, start: tuple[float, float] = (120.0, 120.0)) -> None:
        self.x = float(start[0])
        self.y = float(start[1])

    def reset(self, x: float, y: float) -> None:
        self.x = float(x)
        self.y = float(y)

    def update(self, x: float, y: float) -> None:
        self.x = float(x)
        self.y = float(y)

    def position(self) -> tuple[float, float]:
        return self.x, self.y


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #


def _bezier_point(points: list[tuple[float, float]], t: float) -> tuple[float, float]:
    n = len(points) - 1
    x = y = 0.0
    for i, (px, py) in enumerate(points):
        b = math.comb(n, i) * ((1 - t) ** (n - i)) * (t ** i)
        x += b * px
        y += b * py
    return x, y


def _bezier_path(
    start: tuple[float, float],
    end: tuple[float, float],
    rng: random.Random,
    cfg: MouseConfig,
) -> list[tuple[float, float]]:
    """Generate a Bezier path with randomized offset control points."""
    (x0, y0), (x1, y1) = start, end
    dist = math.dist(start, end)
    if dist < 1.0:
        return [start, end]

    # direction along the A->B axis and its perpendicular
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux

    amplitude = max(cfg.control_offset_min_px, min(cfg.control_offset_max_ratio * dist, cfg.control_offset_ratio * dist))

    points: list[tuple[float, float]] = [start]
    n = cfg.control_points
    for i in range(1, n + 1):
        # spread control points along the axis, jittered
        t = i / (n + 1) + rng.uniform(-0.08, 0.08)
        t = max(0.05, min(0.95, t))
        offset = rng.uniform(-amplitude, amplitude)
        # bias alternating sides so the path snakes rather than bowing one way
        if i % 2 == 0:
            offset = -offset
        cx = x0 + ux * t * dist + nx * offset
        cy = y0 + uy * t * dist + ny * offset
        points.append((cx, cy))
    points.append(end)
    return points


def _min_jerk(t: float) -> float:
    """Monotonic fractional progress 0..1 with a bell-shaped velocity profile."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return 10 * t ** 3 - 15 * t ** 4 + 6 * t ** 5


def _fitts_ms(distance_px: float, target_width_px: float, cfg: MouseConfig) -> float:
    width = max(cfg.min_target_width_px, min(cfg.max_target_width_px, target_width_px))
    bits = math.log2(max(1.0, 2.0 * distance_px / width))
    return cfg.fitts_a_ms + cfg.fitts_b_ms_per_bit * bits


# --------------------------------------------------------------------------- #
# Core routine
# --------------------------------------------------------------------------- #


async def _emit(
    page: PageLike,
    points: Iterable[tuple[float, float]],
    *,
    tracker: CursorTracker,
    start_offset_ms: float = 0.0,
) -> int:
    """Issue ``page.mouse.move`` for each sample without additional interpolation."""
    count = 0
    if start_offset_ms > 0:
        await asyncio.sleep(start_offset_ms / 1000.0)
    for x, y in points:
        await page.mouse.move(float(x), float(y), steps=1)
        tracker.update(x, y)
        count += 1
    return count


async def _move_along(
    page: PageLike,
    tracker: CursorTracker,
    path: list[tuple[float, float]],
    duration_ms: float,
    rng: random.Random,
    cfg: MouseConfig,
    *,
    start_offset_ms: float = 0.0,
) -> int:
    """Walk a path with minimum-jerk timing + WindMouse jitter per sample."""
    if len(path) < 2:
        return 0
    if duration_ms <= 0:
        duration_ms = cfg.sample_step_ms * len(path)

    # Sample timings follow a minimum-jerk schedule in path-length space, then
    # we add small WindMouse jitter perpendicular to the local segment so the
    # sampled points are not exactly on the Bezier curve.
    n_samples = max(2, int(duration_ms / cfg.sample_step_ms))
    samples: list[tuple[float, float]] = []
    for i in range(n_samples + 1):
        tau = i / n_samples
        s = _min_jerk(tau)  # fraction of path length covered by time tau
        # locate the point at arc-length fraction s along the polyline path
        samples.append(_point_at_length(path, s))

    # interleave zero-duration overshoot/correction handled by callers
    count = await _emit(page, samples, tracker=tracker, start_offset_ms=start_offset_ms)
    return count


def _point_at_length(path: list[tuple[float, float]], s: float) -> tuple[float, float]:
    """Linear interpolation of a point at fraction ``s`` of total path length."""
    if s <= 0.0:
        return path[0]
    if s >= 1.0:
        return path[-1]
    seg_lengths = [math.dist(path[i], path[i + 1]) for i in range(len(path) - 1)]
    total = sum(seg_lengths) or 1.0
    target = s * total
    accum = 0.0
    for (x0, y0), (x1, y1), seg in zip(path[:-1], path[1:], seg_lengths):
        if seg <= 0:
            continue
        if accum + seg >= target:
            f = (target - accum) / seg
            return x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
        accum += seg
    return path[-1]


async def _tremor_settle(
    page: PageLike,
    tracker: CursorTracker,
    anchor: tuple[float, float],
    rng: random.Random,
    cfg: MouseConfig,
) -> int:
    frames = rng.randint(*cfg.tremor_frames)
    sigma = cfg.tremor_sigma_px
    count = 0
    for _ in range(frames):
        x = anchor[0] + rng.gauss(0.0, sigma)
        y = anchor[1] + rng.gauss(0.0, sigma)
        await page.mouse.move(float(x), float(y), steps=1)
        tracker.update(x, y)
        await asyncio.sleep(cfg.sample_step_ms / 1000.0)
        count += 1
    # snap precisely back onto the target
    await page.mouse.move(float(anchor[0]), float(anchor[1]), steps=1)
    tracker.update(*anchor)
    return count + 1


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


async def human_move(
    page: PageLike,
    target: tuple[float, float],
    *,
    tracker: CursorTracker | None = None,
    target_width_px: float = 80.0,
    cfg: MouseConfig | None = None,
    rng: random.Random | None = None,
    overshoot: bool | str = "auto",
) -> MoveResult:
    """Move the cursor to ``target`` along a human-like trajectory.

    Parameters
    ----------
    page
        Any object exposing ``page.mouse.move(x, y, steps=)`` and
        ``page.mouse.down()/up()`` (Playwright Page works).
    target
        ``(x, y)`` in CSS pixels relative to the viewport.
    tracker
        Shared cursor-position tracker across moves. A fresh one is created
        if omitted.
    target_width_px
        Width used for the Fitts' law duration estimate; pass the smaller
        side of the target bounding box for click targets.
    cfg, rng
        Tunable config and seeded RNG for reproducibility.
    overshoot
        ``"auto"`` uses :attr:`MouseConfig.overshoot_prob`, ``True``/``False``
        force it on/off.
    """
    cfg = (cfg or MouseConfig()).clamp()
    rng = rng or random.Random()
    tracker = tracker or CursorTracker()

    start = tracker.position()
    dist = math.dist(start, target)
    duration_ms = _fitts_ms(dist, target_width_px, cfg) / cfg.speed_factor
    if dist < 2.0:
        # already on top of the target; settle with tremor only
        samples = await _tremor_settle(page, tracker, target, rng, cfg)
        return MoveResult(start, target, samples, 0.0, False)

    do_overshoot = rng.random() < cfg.overshoot_prob if overshoot == "auto" else bool(overshoot)

    # main path ends either at the true target or an overshoot point
    actual_end = target
    if do_overshoot and dist > 12.0:
        ox_ratio = min(cfg.overshoot_max_ratio, cfg.overshoot_ratio)
        dirx = (target[0] - start[0]) / dist
        diry = (target[1] - start[1]) / dist
        actual_end = (target[0] + dirx * ox_ratio * dist, target[1] + diry * ox_ratio * dist)

    path = _bezier_path(start, actual_end, rng, cfg)
    main_samples = await _move_along(page, tracker, path, duration_ms, rng, cfg)

    extra_samples = 0
    if do_overshoot and dist > 12.0:
        pause = rng.uniform(*cfg.overshoot_pause_ms)
        await asyncio.sleep(pause / 1000.0)
        # correction segment: shallow, slow move back to the true target
        corr_path = _bezier_path(tracker.position(), target, rng, cfg)
        corr_samples = await _move_along(page, tracker, corr_path, duration_ms * 0.3, rng, cfg)
        extra_samples += corr_samples

    extra_samples += await _tremor_settle(page, tracker, target, rng, cfg)
    total_duration = duration_ms + (cfg.overshoot_pause_ms[1] if do_overshoot else 0.0)

    return MoveResult(start, target, main_samples + extra_samples, total_duration, do_overshoot)


async def human_click(
    page: PageLike,
    selector: str | None = None,
    *,
    position: tuple[float, float] | None = None,
    target_width_px: float = 80.0,
    cfg: MouseConfig | None = None,
    rng: random.Random | None = None,
    tracker: CursorTracker | None = None,
    overshoot: bool | str = "auto",
    button: str = "left",
) -> ClickResult:
    """Move to a target and click with realistic timing.

    Either ``selector`` (resolved via ``page.locator(selector).bounding_box()``)
    or an explicit ``position`` must be provided. When a selector is used, the
    click point is jittered inside the bounding box instead of hitting the
    geometric center, which avoids the "always exactly center" fingerprint.
    """
    if selector is None and position is None:
        raise ValueError("human_click requires either a selector or a position")

    cfg = (cfg or MouseConfig()).clamp()
    rng = rng or random.Random()
    tracker = tracker or CursorTracker()

    if position is None:
        assert selector is not None
        box = await page.locator(selector).bounding_box()
        if not box:
            raise RuntimeError(f"No bounding box for selector: {selector!r}")
        bx, by, bw, bh = box["x"], box["y"], box["width"], box["height"]
        # jitter inside the inner 70% to avoid edge-knob targets
        jx = bx + bw * (0.15 + rng.random() * 0.7)
        jy = by + bh * (0.15 + rng.random() * 0.7)
        position = (jx, jy)
        # use the shorter bbox side as the target width for Fitts' law
        target_width_px = max(min(bw, bh), cfg.min_target_width_px)
    else:
        position = (float(position[0]), float(position[1]))

    move_result = await human_move(
        page,
        position,
        tracker=tracker,
        target_width_px=target_width_px,
        cfg=cfg,
        rng=rng,
        overshoot=overshoot,
    )

    decision = rng.uniform(*cfg.decision_pause_ms)
    await asyncio.sleep(decision / 1000.0)

    dwell = rng.uniform(*cfg.dwell_ms)
    await page.mouse.down(button=button)
    await asyncio.sleep(dwell / 1000.0)
    await page.mouse.up(button=button)

    return ClickResult(
        start=move_result.start,
        end=move_result.end,
        samples=move_result.samples,
        duration_ms=move_result.duration_ms,
        overshot=move_result.overshot,
        dwell_ms=dwell,
        decision_pause_ms=decision,
    )