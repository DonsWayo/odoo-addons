# OdooGit QA — Reusable Browser Test Flows

Declarative YAML test flows executed via [agent-browser](https://agent-browser.dev)
(same pattern as Maestro YAML flows for mobile, but for web).

## Layout

```
qa/
├── run.py            # dependency-free YAML flow runner (python3)
├── flows/            # test flows (YAML)
│   ├── 01_login.yaml
│   ├── 02_repositories_list.yaml
│   ├── 03_repository_form.yaml
│   ├── 04_pull_requests.yaml
│   ├── 05_assets_clean.yaml
│   └── 06_console_clean.yaml
└── output/           # screenshots + report (gitignored)
```

## Quick start

```bash
# default: http://localhost:8069, admin/admin
python3 qa/run.py

# custom target / credentials
QA_BASE_URL=http://staging:8069 QA_USER=admin QA_PASS=admin python3 qa/run.py

# single flow
python3 qa/run.py qa/flows/04_pull_requests.yaml
```

## Flow schema

```yaml
name: Flow display name
session: qa-odoo            # agent-browser session id (isolated browser)
steps:
  - open: /web/login        # path appended to $QA_BASE_URL, or full URL
  - wait: 2000              # ms
  - wait_text: "Repositories"
  - fill_label: "Email"     # find by label
    value: admin
  - press: Enter
  - assert_url: "**/odoo**" # glob match
  - assert_text: "Git"
  - assert_no_text: "Traceback"
  - click_text: "New"
  - snapshot: true          # fail if page has no interactive elements
  - console_clean: true     # fail on new console errors since flow start
  - screenshot: 02_list.png # saved to qa/output/
  - eval: "document.title"  # JS; combine with assert_eval
  - assert_eval: "document.readyState === 'complete'"
```

Any step may include `optional: true` to warn instead of fail.

## CI usage

Exit code is `0` only when every step of every flow passes. Screenshots of
failures are written to `qa/output/` for artifact upload.

```yaml
# GitHub Actions example
- run: docker compose up -d --wait
- run: python3 qa/run.py
- uses: actions/upload-artifact@v4
  if: always()
  with: { name: qa-screenshots, path: qa/output/ }
```

## Session isolation

Each flow declares its own agent-browser `session`, giving an isolated browser
(own cookies/storage/history). Sessions are closed by the runner on exit.
See https://agent-browser.dev/sessions and https://agent-browser.dev/snapshots.
