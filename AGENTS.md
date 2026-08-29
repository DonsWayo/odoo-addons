# AGENTS.md — dw_git (Odoo 19 Git hosting module)

Guidance for AI coding agents (Claude Code, opencode, Cursor, Codex, …).

## Project

Odoo 19 module `dw_git` — self-hosted git repository manager (repos, branches,
commits, PRs, reviews, PATs, deploy keys, webhooks, portal). Runs in Docker
(odoo:19 + postgres:16) with GitPython.

## Before you touch views/models

READ the project skill first — it encodes every Odoo 19 breaking change and
every silent-failure mode that has already broken this repo:

- `.agents/skills/odoo19-dev/SKILL.md`

This is not optional and not a formality. The skill already documented
`_sql_constraints` -> `models.Constraint` (Odoo 19 ignores the old list
silently) and it was used anyway, in this repo, months later — the constraint
was simply never created and the test that should have caught it passed. If
you are touching views, Owl components, field widgets, tours or tests, read
the matching section before writing, not after the failure.

## Commands

```bash
make build up install   # first run
make check              # xml + lint + upgrade + tests — do this before pushing
make ci                 # the CI gates, locally: throwaway DB + every guard
make test               # full suite, INCLUDING browser tours
make coverage           # measured line coverage, not grepped
make assets             # every asset exists; every widget matches its field type
make seed               # demo data + a real mirrored GitHub repository
make qa                 # browser QA (must stay green)
make help               # everything else
```

`make ci` is the one to trust before pushing. It installs into a THROWAWAY
database, so it cannot pass because your dev database happens to be
healthy — `make test` once reported "0 failed, 0 error(s) of 0 tests" and
exited 0 because dw_git was uninstalled there, and a suite with nothing in
it looks exactly like a suite that passed. It also greps the install log
and pins the browser-tour count to the tours registered on disk.

`make test` FAILS if a browser tour was skipped. Odoo skips tours when Chrome
is missing and still prints "0 failed" — that is how this module's entire UI
layer went untested for its whole life while every run looked green.

`make lint` is a gate, not advice: ruff's F821 would have caught the
`NameError` that shipped in 19.0.1.0.0.

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
7. Assert BEHAVIOUR, not structure. A tour asserting `.d2h-ins` exists passed
   for the whole life of the feature while nothing on the page had any colour.
8. Never `except Exception: pass` around an ORM write. In PostgreSQL the
   transaction stays aborted and the NEXT statement dies —
   `with self.env.cr.savepoint():` or let it raise.
9. Never key a filesystem path, URL slug or cache key on a mutable field.
   `res.users.login` is mutable and it orphaned every repository a renamed
   user owned.
10. Check CI before merging. Six PRs went into an already-red `main` on the
    strength of a local `make test` that was silently skipping the UI layer.
