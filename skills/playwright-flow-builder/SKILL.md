---
name: playwright-flow-builder
description: Turn a user's natural-language browser workflow into a reusable BitBrowser/Playwright flow in this repository. Use when Codex, Claude Code, or another coding agent needs to drive Playwright interactively, handle login/manual checkpoints, discover stable selectors, and save or validate a declarative YAML flow or Python flow under flows/.
---

# Playwright Flow Builder

Use this skill to explore a live website with Playwright, complete the user's described browser task, and solidify the working procedure as a reusable project flow.

Work from the repository root so bundled scripts can import `src/bitbrowser_auto` and write to the existing `flows/` and `artifacts/` directories.

## First Moves

1. Clarify only the missing essentials: target URL, desired outcome, flow name, success signal, required inputs, and BitBrowser `browser_id` if BitBrowser must be used.
2. Read `references/flow-authoring.md` before authoring or materializing a flow.
3. Inspect existing examples in `flows/declarative/` and `flows/py/`, plus `src/bitbrowser_auto/runner/declarative.py` when action support is uncertain.
4. Prefer a declarative YAML flow for linear tasks. Use a Python flow for loops, pagination, dynamic branching, complex extraction, or external API calls.

## Explore With Playwright

Use any reliable browser-control surface available to the agent. If no native browser tool is available, use the bundled probe:

```bash
python skills/playwright-flow-builder/scripts/playwright_probe.py \
  --browser-id <browser-id> \
  --url <start-url> \
  --artifact-dir artifacts/flow-authoring/<flow-name>
```

If BitBrowser is not required, launch a normal headed Chromium session:

```bash
python skills/playwright-flow-builder/scripts/playwright_probe.py \
  --url <start-url> \
  --artifact-dir artifacts/flow-authoring/<flow-name>
```

Inside the probe, send one JSON command per line:

```json
{"action":"observe","limit":25}
{"action":"click","selector":"button:has-text('Search')"}
{"action":"human_click","selector":"button:has-text('立即签到')","speed_factor":1.0,"overshoot":"auto"}
{"action":"fill","selector":"input[name='q']","value":"{{ inputs.keyword }}"}
{"action":"screenshot","name":"after-search"}
```

Use exploration to learn stable selectors, required waits, page transitions, failure modes, and final success evidence. Save screenshots at meaningful checkpoints.

## Login And Manual Checkpoints

Never ask the user to paste passwords, recovery codes, cookies, or 2FA tokens into chat.

When login, captcha, passkey, or 2FA is required:

1. Keep the visible browser open.
2. Tell the user exactly what to do in the browser.
3. Pause automation until the user confirms completion.
4. Continue from the authenticated page and treat the browser profile/session as the credential store.

With the probe, use:

```json
{"action":"pause","message":"Please complete login in the visible browser, then press Enter here."}
{"action":"observe","limit":20}
```

Only generate credential-filling steps when the user explicitly wants reusable credential inputs. In that case use flow inputs such as `{{ inputs.username }}` and `{{ inputs.password }}`; never hard-code secrets.

## Human-Like Cursor (Anti-Bot)

When a page does behavior fingerprinting (滑块拼图, reCAPTCHA, hCaptcha, Cloudflare Turnstile, fingerprint SDKs), use `human_click` instead of `click`. It drives `page.mouse` along a randomized Bézier path with minimum-jerk velocity, Fitts'-law duration, overshoot + correction, terminal tremor, and a realistic click dwell. See `docs/human-mouse-simulation.md` for the model and defaults, and `references/flow-authoring.md` for the action schema and Python-flow usage.

- Prefer `human_click` over `click` on verification/login pages.
- Do not mix `human_click` with raw `playwright` `mouse.move` on the same page — the cursor-position tracker would drift.
- For 滑块 drag-puzzle verification (hold + drag), general `human_click` is not enough; plan it as a dedicated step and leave the drag primitive for a follow-up task until `human_drag` is implemented.

## Solidify The Flow

After the task succeeds manually:

1. Remove exploratory noise and keep the minimal stable procedure.
2. Replace user-specific values with `inputs`.
3. Add waits around navigation, async results, modals, and post-login state.
4. Add at least one final screenshot or extraction/assertion that proves success.
5. Materialize the flow with the bundled helper or by editing files directly.

Declarative materialization example:

```bash
python skills/playwright-flow-builder/scripts/materialize_flow.py --spec - --overwrite <<'JSON'
{
  "flow_type": "declarative",
  "name": "search_example",
  "display_name": "Search example",
  "description": "Open a site, search a keyword, and capture results.",
  "category": "web",
  "inputs": {
    "url": {"type": "string", "required": true, "default": "https://example.com"},
    "keyword": {"type": "string", "required": true}
  },
  "steps": [
    {"action": "goto", "url": "{{ inputs.url }}"},
    {"action": "fill", "selector": "input[name='q']", "value": "{{ inputs.keyword }}"},
    {"action": "press", "selector": "input[name='q']", "key": "Enter"},
    {"action": "wait_for", "selector": ".result", "timeout_ms": 30000},
    {"action": "screenshot", "name": "final", "full_page": true}
  ]
}
JSON
```

Python materialization example:

```bash
python skills/playwright-flow-builder/scripts/materialize_flow.py --spec python-flow-spec.json --overwrite
```

## Validate And Run

For declarative flows:

```bash
python -m bitbrowser_auto validate-flow <flow-name>
```

For Python flows:

```bash
python -m py_compile flows/py/<flow-name>.py
```

When a safe browser/account is available, do one end-to-end run:

```bash
python -m bitbrowser_auto run-one \
  --browser-id <browser-id> \
  --flow-type declarative \
  --flow <flow-name> \
  --url <start-url>
```

Use `--flow-type python` for Python flows. Keep the BitBrowser window open unless the user explicitly asks to close it.

## Delivery

Report the flow file path, the generated inputs, validation commands/results, any manual-login requirement, and the artifact directory with screenshots or probe logs. If a full run was skipped, state the missing prerequisite clearly.
