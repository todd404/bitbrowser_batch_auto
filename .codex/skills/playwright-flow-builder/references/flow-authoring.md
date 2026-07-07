# Flow Authoring Reference

Use this reference after triggering `$playwright-flow-builder` when turning a browser task into a reusable flow.
Run project commands from the repository root with `.venv/bin/python` so the skill uses the project's virtualenv instead of a system `python`.

## Flow Choice

Use declarative YAML when the workflow is mostly linear:

- Navigate to one or more fixed pages.
- Click, fill, press, wait, extract, assert, or screenshot.
- Use simple `if_visible` or `if_text` branches.
- Use allowlisted Playwright passthrough for a small missing operation.

Use Python when the workflow needs:

- Loops, pagination, retries, or variable-length lists.
- Complex branching based on page data.
- Data cleaning or external API calls.
- Helper functions shared across steps.

## Declarative Flow Shape

Write declarative flows under `flows/declarative/<name>.yaml`.

```yaml
name: "search_example"
display_name: "Search example"
description: "Search a keyword and save the result page."
category: "web"
version: 1
inputs:
  url:
    type: string
    required: true
    default: "https://example.com"
  keyword:
    type: string
    required: true
steps:
  - action: goto
    url: "{{ inputs.url }}"
  - action: fill
    selector: "input[name='q']"
    value: "{{ inputs.keyword }}"
  - action: press
    selector: "input[name='q']"
    key: "Enter"
  - action: wait_for
    selector: ".result"
    timeout_ms: 30000
  - action: screenshot
    name: "final"
    full_page: true
```

Supported core actions are defined in `src/bitbrowser_auto/runner/declarative.py`:

- `goto`: `url`, optional `wait_until`, `timeout_ms`
- `click`: `selector`, optional `timeout_ms`
- `fill`: `selector`, `value`, optional `timeout_ms`
- `press`: `selector`, `key`, optional `timeout_ms`
- `wait_for`: `selector`, optional `state`, `timeout_ms`
- `wait_for_url`: `url`, optional `timeout_ms`
- `extract_text`: `selector`, `save_as`, optional `timeout_ms`
- `extract_attr`: `selector`, `attr`, `save_as`, optional `timeout_ms`
- `screenshot`: optional `name`, `full_page`
- `assert_text`: `selector`, `text`, optional `timeout_ms`
- `if_visible`: `selector`, `then`
- `if_text`: `selector`, `text`, `then`
- `playwright`: allowlisted passthrough

Template variables currently supported by the runner:

- `{{ inputs.<key> }}`
- `{{ outputs.<key> }}`
- `{{ task.id }}`

## Playwright Passthrough

Use passthrough only when core actions are insufficient. The runner allowlist includes common methods on `page`, `context`, `locator`, `keyboard`, and `mouse`.

Example:

```yaml
- action: playwright
  target: page
  method: locator
  args:
    - "button:has-text('Submit')"
  chain:
    - method: click
      kwargs:
        timeout: 30000
```

Validate passthrough flows with:

```bash
.venv/bin/python -m bitbrowser_auto validate-flow <flow-name>
```

## Python Flow Shape

Write Python flows under `flows/py/<name>.py`.

```python
async def run(ctx):
    page = ctx.page
    inputs = ctx.inputs

    await page.goto(inputs["url"], wait_until="domcontentloaded")
    await page.locator("input[name='q']").fill(inputs["keyword"])
    await page.locator("input[name='q']").press("Enter")
    await page.locator(".result").wait_for(timeout=30000)
    screenshot = await ctx.artifacts.screenshot(page, "final", full_page=True)
    return {"url": page.url, "screenshot": screenshot}
```

Available context:

- `ctx.page`
- `ctx.context`
- `ctx.browser`
- `ctx.task`
- `ctx.inputs`
- `ctx.artifacts`
- `ctx.bitbrowser`
- `ctx.logger`

For UI metadata, add `flows/py/<name>.meta.yaml`:

```yaml
display_name: "Search example"
description: "Search a keyword and save the result page."
category: "web"
inputs:
  url:
    type: string
    required: true
  keyword:
    type: string
    required: true
```

## Login UX

Prefer profile-based login:

1. Open the target site in the visible browser.
2. Pause and let the user log in manually.
3. Continue from the authenticated page.
4. Save the flow as requiring an already logged-in BitBrowser profile.

Use credential inputs only when explicitly requested. If generated, use placeholders and avoid logging secrets:

```yaml
inputs:
  username:
    type: string
    required: true
  password:
    type: password
    required: true
steps:
  - action: fill
    selector: "input[name='username']"
    value: "{{ inputs.username }}"
  - action: fill
    selector: "input[name='password']"
    value: "{{ inputs.password }}"
```

## Materialize Spec Schema

`scripts/materialize_flow.py` accepts JSON or YAML from a file or stdin.

Declarative spec:

```json
{
  "flow_type": "declarative",
  "name": "flow_name",
  "display_name": "Human title",
  "description": "What this flow does.",
  "category": "web",
  "version": 1,
  "inputs": {},
  "steps": []
}
```

Python spec:

```json
{
  "flow_type": "python",
  "name": "flow_name",
  "display_name": "Human title",
  "description": "What this flow does.",
  "category": "web",
  "inputs": {},
  "python": "async def run(ctx):\n    return {\"ok\": True}\n"
}
```

Useful commands:

```bash
.venv/bin/python skills/playwright-flow-builder/scripts/materialize_flow.py --spec spec.json
.venv/bin/python skills/playwright-flow-builder/scripts/materialize_flow.py --spec - --overwrite
```

## Probe Commands

`scripts/playwright_probe.py` accepts one JSON command per line.

Common commands:

- `{"action":"observe","limit":25}`
- `{"action":"goto","url":"https://example.com"}`
- `{"action":"click","selector":"text=Login"}`
- `{"action":"fill","selector":"input[name='q']","value":"hello"}`
- `{"action":"press","selector":"input[name='q']","key":"Enter"}`
- `{"action":"wait_for","selector":".result","state":"visible","timeout_ms":30000}`
- `{"action":"wait_for_url","url":"**/done","timeout_ms":30000}`
- `{"action":"text","selector":".result"}`
- `{"action":"attr","selector":"a.next","attr":"href"}`
- `{"action":"screenshot","name":"checkpoint"}`
- `{"action":"pause","message":"Complete login in the browser, then press Enter."}`
- `{"action":"note","text":"The modal appears only on first visit."}`
- `{"action":"exit"}`

The probe writes:

- `commands.jsonl`: command log with redacted password fills.
- screenshots requested by `screenshot` or captured after errors.
- JSON observations printed to stdout for the agent to use.

## Quality Checklist

Before delivering:

- Selectors prefer roles, labels, placeholders, stable attributes, or semantic text over brittle DOM paths.
- Steps include waits for async UI and navigation.
- Secrets are not written to files, logs, or chat.
- Flow inputs cover values the user will change.
- Final step proves success with screenshot, extraction, or assertion.
- Declarative flows pass `.venv/bin/python -m bitbrowser_auto validate-flow <name>`.
- Python flows pass `.venv/bin/python -m py_compile flows/py/<name>.py`.
