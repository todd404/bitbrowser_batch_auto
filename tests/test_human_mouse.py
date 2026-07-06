"""Tests for the human-like mouse helpers and declarative ``human_click``."""

from __future__ import annotations

import asyncio
import math
import random
import unittest

from bitbrowser_auto.human import (
    CursorTracker,
    MouseConfig,
    human_click,
    human_move,
)
from bitbrowser_auto.human.mouse import (
    _bezier_path,
    _fitts_ms,
    _min_jerk,
    _point_at_length,
)
from bitbrowser_auto.runner.declarative import DeclarativeRunner


class _FakeMouse:
    def __init__(self) -> None:
        self.moves: list[tuple[float, float]] = []
        self.down_count = 0
        self.up_count = 0
        self.slept: list[float] = []

    async def move(self, x: float, y: float, steps: int = 1) -> None:
        self.moves.append((float(x), float(y)))

    async def down(self, button: str = "left") -> None:
        self.down_count += 1

    async def up(self, button: str = "left") -> None:
        self.up_count += 1


class _FakeLocator:
    def __init__(self, box: dict | None) -> None:
        self._box = box

    async def bounding_box(self) -> dict | None:
        return self._box


class _SleepPage:
    """Async page stand-in that records moves/clicks and respects sleeps.

    ``asyncio.sleep`` is patched via a per-test clock so tests are fast and
    deterministic.
    """

    def __init__(self, box: dict | None = None) -> None:
        self.mouse = _FakeMouse()
        self._locator = _FakeLocator(box)
        self._sleeps: list[float] = []

    def locator(self, selector: str) -> _FakeLocator:
        return self._locator


def _run(coro):
    return asyncio.run(coro)


class GeometryTest(unittest.TestCase):
    def test_min_jerk_endpoints_and_monotonic(self) -> None:
        self.assertEqual(_min_jerk(0.0), 0.0)
        self.assertEqual(_min_jerk(1.0), 1.0)
        # monotonically non-decreasing on a dense grid
        prev = 0.0
        for i in range(1, 21):
            v = _min_jerk(i / 20)
            self.assertGreaterEqual(v, prev - 1e-9)
            prev = v

    def test_bezier_path_starts_and_ends_at_endpoints(self) -> None:
        rng = random.Random(7)
        path = _bezier_path((0.0, 0.0), (500.0, 200.0), rng, MouseConfig())
        self.assertEqual(path[0], (0.0, 0.0))
        self.assertEqual(path[-1], (500.0, 200.0))
        self.assertGreater(len(path), 2)
        # control points never collapse onto the start/end
        for p in path[1:-1]:
            self.assertNotEqual(p, (0.0, 0.0))

    def test_bezier_path_degenerate_for_short_distance(self) -> None:
        path = _bezier_path((10.0, 10.0), (10.5, 10.5), random.Random(1), MouseConfig())
        self.assertEqual(path, [(10.0, 10.0), (10.5, 10.5)])

    def test_point_at_length_endpoints(self) -> None:
        path = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)]
        self.assertEqual(_point_at_length(path, 0.0), (0.0, 0.0))
        self.assertEqual(_point_at_length(path, 1.0), (100.0, 100.0))
        mid = _point_at_length(path, 0.5)
        # half path length lands at the corner
        self.assertAlmostEqual(mid[0], 100.0)
        self.assertAlmostEqual(mid[1], 0.0)

    def test_fitts_grows_with_distance_shrinks_with_width(self) -> None:
        cfg = MouseConfig()
        near = _fitts_ms(50.0, 80.0, cfg)
        far = _fitts_ms(800.0, 80.0, cfg)
        self.assertGreater(far, near)
        small_target = _fitts_ms(800.0, 16.0, cfg)
        self.assertGreater(small_target, far)


class MoveTest(unittest.TestCase):
    def test_human_move_emits_progression_to_target(self) -> None:
        page = _SleepPage()
        tracker = CursorTracker(start=(10.0, 10.0))
        rng = random.Random(123)
        result = _run(
            human_move(page, (420.0, 320.0), tracker=tracker, rng=rng, target_width_px=80.0)
        )
        self.assertGreater(result.samples, 4)
        # last emitted position must be very close to the target
        last_x, last_y = page.mouse.moves[-1]
        self.assertAlmostEqual(last_x, 420.0, delta=1.0)
        self.assertAlmostEqual(last_y, 320.0, delta=1.0)
        self.assertEqual(tracker.position(), (420.0, 320.0))

    def test_human_move_no_overshoot_when_forced_off(self) -> None:
        page = _SleepPage()
        tracker = CursorTracker(start=(0.0, 0.0))
        rng = random.Random(5)
        result = _run(
            human_move(page, (500.0, 400.0), tracker=tracker, rng=rng, overshoot=False)
        )
        self.assertFalse(result.overshot)
        # no emitted point should be substantially past the target on the axis
        for x, y in page.mouse.moves[:-1]:
            self.assertLess(x, 510.0)
            self.assertLess(y, 410.0)

    def test_human_move_tracked_from_previous_position(self) -> None:
        page = _SleepPage()
        tracker = CursorTracker(start=(120.0, 120.0))
        rng = random.Random(1)
        _ = _run(human_move(page, (300.0, 300.0), tracker=tracker, rng=rng))
        first_x, first_y = page.mouse.moves[0]
        # first sample should be close to the previously tracked start
        self.assertLess(math.hypot(first_x - 120.0, first_y - 120.0), 30.0)


class ClickTest(unittest.TestCase):
    BOX = {"x": 400.0, "y": 300.0, "width": 80.0, "height": 40.0}

    def test_human_click_requires_selector_or_position(self) -> None:
        page = _SleepPage()
        with self.assertRaises(ValueError):
            _run(human_click(page))

    def test_human_click_jitters_inside_bbox_and_clicks(self) -> None:
        page = _SleepPage(box=self.BOX)
        rng = random.Random(99)
        result = _run(human_click(page, "button", rng=rng))
        self.assertEqual(page.mouse.down_count, 1)
        self.assertEqual(page.mouse.up_count, 1)
        self.assertGreater(result.dwell_ms, 0.0)
        self.assertGreater(result.decision_pause_ms, 0.0)
        # final click position is inside the bbox interior
        last_x, last_y = page.mouse.moves[-1]
        self.assertGreater(last_x, self.BOX["x"])
        self.assertLess(last_x, self.BOX["x"] + self.BOX["width"])
        self.assertGreater(last_y, self.BOX["y"])
        self.assertLess(last_y, self.BOX["y"] + self.BOX["height"])

    def test_human_click_with_position_does_not_need_locator(self) -> None:
        page = _SleepPage(box=None)
        _run(human_click(page, position=(250.0, 250.0), rng=random.Random(2)))
        self.assertEqual(page.mouse.up_count, 1)


class DeclarativeHumanClickTest(unittest.IsolatedAsyncioTestCase):
    """Smoke test that the runner wires human_click end-to-end."""

    BOX = {"x": 20.0, "y": 20.0, "width": 60.0, "height": 30.0}

    def _build(self):
        from types import SimpleNamespace

        mouse = _FakeMouse()
        locator = _FakeLocator(self.BOX)

        class _Page:
            url = "https://example.test/"

            def __init__(self, mouse, locator):
                self.mouse = mouse
                self._locator = locator

            def locator(self, selector: str):
                return self._locator

        page = _Page(mouse, locator)
        ctx = SimpleNamespace(page=page, context=None, inputs={})
        return ctx, mouse

    async def test_declarative_human_click_runs(self) -> None:
        runner = DeclarativeRunner()
        flow = {
            "steps": [
                {"action": "human_click", "selector": "button", "speed_factor": 1.1, "overshoot": False}
            ]
        }
        ctx, mouse = self._build()
        result = await runner.run(ctx, flow)
        self.assertEqual(mouse.down_count, 1)
        self.assertEqual(mouse.up_count, 1)
        tr = runner.trace_steps[0]
        self.assertEqual(tr["action"], "human_click")
        self.assertIn("samples", tr["result"])


if __name__ == "__main__":
    unittest.main()