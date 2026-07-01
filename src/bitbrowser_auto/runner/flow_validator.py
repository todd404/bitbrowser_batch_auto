from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .declarative import (
    ALLOWED_PLAYWRIGHT_METHODS,
    ALLOWED_PLAYWRIGHT_TARGETS,
    CORE_ACTION_REQUIRED_FIELDS,
    TEMPLATE_PATTERN,
)


@dataclass
class FlowValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class FlowValidator:
    def validate(self, flow: dict[str, Any]) -> FlowValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if not isinstance(flow, dict):
            return FlowValidationResult(ok=False, errors=["flow must be a mapping"])

        declared_inputs = _declared_inputs(flow)
        steps = flow.get("steps")
        if not isinstance(steps, list) or not steps:
            errors.append("flow.steps must be a non-empty list")
        else:
            self._validate_steps(steps, errors, warnings, declared_inputs, path="steps")

        return FlowValidationResult(ok=not errors, errors=errors, warnings=warnings)

    def _validate_steps(
        self,
        steps: list[Any],
        errors: list[str],
        warnings: list[str],
        declared_inputs: set[str],
        *,
        path: str,
    ) -> None:
        for index, step in enumerate(steps):
            step_path = f"{path}[{index}]"
            if not isinstance(step, dict):
                errors.append(f"{step_path} must be a mapping")
                continue

            action = step.get("action")
            if not isinstance(action, str) or not action:
                errors.append(f"{step_path}.action is required")
                continue

            if action == "playwright":
                self._validate_playwright_step(step, errors, step_path)
            elif action in CORE_ACTION_REQUIRED_FIELDS:
                for field in CORE_ACTION_REQUIRED_FIELDS[action]:
                    if field not in step:
                        errors.append(f"{step_path}.{field} is required for action {action!r}")
            else:
                errors.append(f"{step_path}.action {action!r} is not supported")

            self._validate_templates(step, errors, warnings, declared_inputs, step_path)

            if action == "if_visible":
                then_steps = step.get("then")
                if not isinstance(then_steps, list) or not then_steps:
                    errors.append(f"{step_path}.then must be a non-empty list")
                else:
                    self._validate_steps(
                        then_steps,
                        errors,
                        warnings,
                        declared_inputs,
                        path=f"{step_path}.then",
                    )

    def _validate_playwright_step(self, step: dict[str, Any], errors: list[str], step_path: str) -> None:
        target = step.get("target")
        method = step.get("method")
        if target not in ALLOWED_PLAYWRIGHT_TARGETS:
            errors.append(f"{step_path}.target {target!r} is not allowed")
            return
        if target == "locator" and "selector" not in step:
            errors.append(f"{step_path}.selector is required for target 'locator'")
        if not _method_allowed(str(target), method):
            errors.append(f"{step_path}.method {method!r} is not allowed for target {target!r}")

        chain = step.get("chain", [])
        if chain is None:
            return
        if not isinstance(chain, list):
            errors.append(f"{step_path}.chain must be a list")
            return

        current_target = _next_target(str(target), str(method))
        for index, link in enumerate(chain):
            link_path = f"{step_path}.chain[{index}]"
            if not isinstance(link, dict):
                errors.append(f"{link_path} must be a mapping")
                continue
            link_method = link.get("method")
            if not current_target:
                errors.append(f"{link_path} cannot be chained after method {method!r}")
                continue
            if not _method_allowed(current_target, link_method):
                errors.append(f"{link_path}.method {link_method!r} is not allowed for target {current_target!r}")
                continue
            current_target = _next_target(current_target, str(link_method))

    def _validate_templates(
        self,
        value: Any,
        errors: list[str],
        warnings: list[str],
        declared_inputs: set[str],
        path: str,
    ) -> None:
        if isinstance(value, str):
            for match in TEMPLATE_PATTERN.finditer(value):
                expr = match.group(1).strip()
                if expr.startswith("inputs."):
                    key = expr.removeprefix("inputs.")
                    if declared_inputs and key not in declared_inputs:
                        warnings.append(f"{path} references undeclared input {expr!r}")
                elif expr.startswith("outputs.") or expr == "task.id":
                    continue
                else:
                    errors.append(f"{path} contains unsupported template variable {expr!r}")
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                self._validate_templates(item, errors, warnings, declared_inputs, f"{path}[{index}]")
            return
        if isinstance(value, dict):
            for key, item in value.items():
                self._validate_templates(item, errors, warnings, declared_inputs, f"{path}.{key}")


def _declared_inputs(flow: dict[str, Any]) -> set[str]:
    inputs = flow.get("inputs") or {}
    if isinstance(inputs, dict):
        return {str(key) for key in inputs}
    return set()


def _method_allowed(target: str, method: Any) -> bool:
    if not isinstance(method, str):
        return False
    return method in ALLOWED_PLAYWRIGHT_METHODS.get(target, set())


def _next_target(target: str, method: str) -> str | None:
    if target == "page" and method == "locator":
        return "locator"
    if target == "context" and method == "new_page":
        return "page"
    if target == "locator" and method in {"first", "last", "nth"}:
        return "locator"
    return None
