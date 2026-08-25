# AGENTS.md — odoogit (Odoo 19 Git hosting module)

Guidance for AI coding agents (Claude Code, opencode, Cursor, Codex, …).

## Project

Odoo 19 module `odoogit` — self-hosted git repository manager (repos, branches,
commits, PRs, reviews, PATs, deploy keys, webhooks, portal). Runs in Docker
(odoo:19 + postgres:16) with GitPython.

## Before you touch views/models

READ the project skill first — it encodes every Odoo 19 breaking change that
has already broken this repo:

- `.agents/skills/odoo19-dev/SKILL.md`

## Commands

```bash
docker compose build odoo && docker compose up -d          # rebuild stack
docker compose exec odoo odoo -d odoo -i odoogit --stop-after-init \
  --db_host=postgres --db_user=odoo --db_password=odoo --workers=0   # install (-u to upgrade)
python3 qa/run.py                                          # browser QA (must stay green)
docker compose exec odoo odoo -d odoo --test-enable --test-tags /odoogit \
  --stop-after-init --http-port=8070 --db_host=postgres --db_user=odoo \
  --db_password=odoo --workers=0                           # tests (105)
```

Login: http://localhost:8069 — admin/admin.

## Audit trail

`docs/AUDIT-2026-08.md` lists every defect found in the August 2026 audit and
the regression test that now covers it. `docs/LIMITATIONS.md` lists what is
deliberately absent — check it before "fixing" webhooks or SSH.

## Non-negotiables

1. Validate all XML parses BEFORE building (see skill).
2. Kanban templates: `t-name="card"`, `record.x.value`/`.raw_value`.
3. Form views: no `t-out`/`t-if`/`t-att-*` outside nested kanban.
4. Every button action and field in a view must exist on the model.
5. Run `python3 qa/run.py` after any view change; keep it green.
6. New controller route ⇒ new HTTP test. New field on an x2many ⇒ a test that
   populates it. New permission path ⇒ a test acting as a second user.
