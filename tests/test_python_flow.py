from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from bitbrowser_auto.observability import ArtifactManager
from bitbrowser_auto.runner.python_flow import PythonRunner, load_python_flow_run, resolve_python_flow_path
from bitbrowser_auto.runner.task import Task


class FakePage:
    url = "about:blank"

    async def goto(self, url: str, **_: object) -> None:
        self.url = url

    async def title(self) -> str:
        return "Fake Title"

    async def screenshot(self, path: str, **_: object) -> None:
        Path(path).write_bytes(b"fake image")


class PythonFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_python_runner_executes_async_flow_and_records_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flow_dir = Path(tmp) / "flows"
            flow_dir.mkdir()
            (flow_dir / "demo.py").write_text(
                "\n".join(
                    [
                        "async def run(ctx):",
                        "    await ctx.page.goto(ctx.inputs['url'])",
                        "    return {'url': ctx.page.url}",
                    ]
                ),
                encoding="utf-8",
            )
            ctx = SimpleNamespace(
                page=FakePage(),
                inputs={"url": "https://example.com"},
                artifacts=ArtifactManager(Path(tmp) / "artifacts", "task-001"),
                task=Task(id="task-001", browser_id="browser-001", flow_type="python", flow="demo"),
            )

            runner = PythonRunner(flow_dir=flow_dir, screenshot_policy="every_step")
            outputs = await runner.run(ctx, "demo")

            self.assertEqual(outputs["url"], "https://example.com")
            self.assertEqual(len(runner.trace_steps), 1)
            self.assertTrue(runner.trace_steps[0]["ok"])
            self.assertIn("screenshot", runner.trace_steps[0])

    async def test_python_runner_records_failed_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flow_dir = Path(tmp) / "flows"
            flow_dir.mkdir()
            (flow_dir / "bad.py").write_text(
                "\n".join(["async def run(ctx):", "    raise RuntimeError('boom')"]),
                encoding="utf-8",
            )
            ctx = SimpleNamespace(
                page=FakePage(),
                inputs={},
                artifacts=ArtifactManager(Path(tmp) / "artifacts", "task-001"),
                task=Task(id="task-001", browser_id="browser-001", flow_type="python", flow="bad"),
            )

            runner = PythonRunner(flow_dir=flow_dir, screenshot_policy="on_error")
            with self.assertRaises(RuntimeError):
                await runner.run(ctx, "bad")

            self.assertEqual(runner.trace_steps[0]["error"], "boom")
            self.assertIn("screenshot", runner.trace_steps[0])

    def test_rejects_sync_python_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sync_flow.py"
            path.write_text("def run(ctx):\n    return {}\n", encoding="utf-8")

            with self.assertRaises(TypeError):
                load_python_flow_run(path)

    def test_resolves_named_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flow_dir = Path(tmp)
            path = flow_dir / "demo.py"
            path.write_text("async def run(ctx):\n    return {}\n", encoding="utf-8")

            self.assertEqual(resolve_python_flow_path(flow_dir, "demo"), path)


if __name__ == "__main__":
    unittest.main()

