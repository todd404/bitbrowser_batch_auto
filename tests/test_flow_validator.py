from __future__ import annotations

import unittest

from bitbrowser_auto.runner.flow_validator import FlowValidator


class FlowValidatorTest(unittest.TestCase):
    def test_valid_core_flow(self) -> None:
        flow = {
            "name": "demo",
            "inputs": {"url": {"type": "string", "required": True}},
            "steps": [{"action": "goto", "url": "{{ inputs.url }}"}],
        }

        result = FlowValidator().validate(flow)

        self.assertTrue(result.ok)
        self.assertEqual(result.errors, [])

    def test_rejects_unknown_action(self) -> None:
        flow = {"steps": [{"action": "evaluate", "script": "1 + 1"}]}

        result = FlowValidator().validate(flow)

        self.assertFalse(result.ok)
        self.assertIn("steps[0].action 'evaluate' is not supported", result.errors)

    def test_rejects_unknown_template_variable(self) -> None:
        flow = {"steps": [{"action": "goto", "url": "{{ secrets.password }}"}]}

        result = FlowValidator().validate(flow)

        self.assertFalse(result.ok)
        self.assertIn("steps[0].url contains unsupported template variable 'secrets.password'", result.errors)

    def test_rejects_disallowed_playwright_method(self) -> None:
        flow = {"steps": [{"action": "playwright", "target": "page", "method": "evaluate"}]}

        result = FlowValidator().validate(flow)

        self.assertFalse(result.ok)
        self.assertIn("steps[0].method 'evaluate' is not allowed for target 'page'", result.errors)


if __name__ == "__main__":
    unittest.main()

