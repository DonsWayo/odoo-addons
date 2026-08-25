---
name: odoo-browser-qa
description: Reusable browser QA for Odoo modules using agent-browser with YAML flows. Use when asked to "QA the Odoo UI", "run browser tests", "verify the web client", "check styles render", or before releasing an Odoo module change. Executes the deterministic flows in qa/flows/ and reports pass/fail with screenshots.
allowed-tools: Bash(agent-browser:*), Bash(docker compose:*), Bash(python3 qa/*), Bash(./qa/*)
---

# Odoo Browser QA (agent-browser + YAML flows)

Deterministic, CI-reusable browser tests for the Git Hosting module. The flows live
in `qa/flows/*.yaml` and run via the dependency-free runner `qa/run.py`
(Maestro-style YAML, but for web through [agent-browser](https://agent-browser.dev)).

## Quick reference

```bash
# everything: seed data (idempotent) + all flows
python3 qa/run.py

# single flow
python3 qa/run.py qa/flows/04_pull_requests.yaml

# custom target/creds (e.g. staging)
QA_BASE_URL=http://staging:8069 QA_USER=admin QA_PASS=admin python3 qa/run.py
```

Results: exit 0 = green. Screenshots (incl. `*__FAIL_*.png` on failure) land in
`qa/output/`. Upload as CI artifacts.

## Environment prerequisites

1. Stack up: `docker compose up -d` (odoo + postgres), wait for health.
2. Module installed: `docker compose exec odoo odoo -d odoo -i dw_git --stop-after-init ...`
   (use `-u` to upgrade after view changes).
3. Seeding is handled by `qa/run.py` via `qa/seed.py` (real bare git repo,
   2 branches, 4 commits, 1 open PR; skips if present; **commits via
   `env.cr.commit()`** — odoo shell does NOT auto-commit).

## Flow authoring rules (learned the hard way)

- **Login form renders via Owl AFTER networkidle** — runner auto-retries
  `fill_label`/`click_*` for ~10s; still add `wait: 3000` after `press: Enter`.
- **After `close`, sleep 2s before `open`** or the relaunch races and you land
  on `about:blank` (runner does this for you).
- **Snapshot refs print as `[ref=eN]`**, clicks use `@eN`. Use the `click_row`
  step — it snapshots, finds the row containing your text, clicks its ref.
  Raw `find text X click` does NOT open Odoo list records.
- **`eval --json` returns `data.result`** — the runner's `assert_eval` uses it;
  plain `eval` output mixes in `[agent-browser] launched browser` noise.
- **XML escaping in Odoo view files**: inside attribute values escape
  `&` -> `&amp;`, `<` -> `&lt;`. Validate every file with
  `python3 -c "from xml.etree import ElementTree as ET; ET.parse('<file>')"`
  BEFORE rebuilding the image (Docker COPY caches make bad builds sticky).
- **Form views are server-rendered**: no `t-out`/`t-if`/`t-att-*` (Owl
  directives) outside nested `<kanban>` templates. Use
  `invisible="expr"`, `widget="badge"`, `<field/>`.
- **Every button `type="object" name="X"` must exist** as a method on the
  model; every `<field name="Y">` must exist on the model. Odoo's install-time
  validator enforces both — audit before building:
  `python3 qa/audit_views.py` (see below).
- **`widget="date"` on Datetime fields** logs console warnings; use
  `widget="datetime"` (Date fields keep `date`).

## Auditing views before a build (optional but recommended)

```bash
python3 - <<'EOF'
from xml.etree import ElementTree as ET
import os
for f in sorted(os.listdir('dw_git/views')):
    if f.endswith('.xml'):
        ET.parse(f'dw_git/views/{f}'); print('ok:', f)
EOF
```

## Debugging a failing flow

1. Open `qa/output/<flow>__FAIL_<nn>.png` — shows the exact failing page.
2. Re-run just that flow with `python3 qa/run.py qa/flows/<flow>.yaml`.
3. Probe interactively with a scratch session:
   ```bash
   agent-browser --session probe open http://localhost:8069/web/login
   agent-browser --session probe snapshot -i -c
   agent-browser --session probe console   # JS errors
   ```
4. Server-side errors: `docker compose logs odoo --tail 50`.

## Sessions

Each flow declares an isolated agent-browser `session` (own cookies/storage).
Runner closes sessions on flow start/end. See
https://agent-browser.dev/sessions and https://agent-browser.dev/snapshots.
