---
name: odoo19-dev
description: Odoo 19 module development rules for THIS project (odoogit). Use when writing or editing XML views (form, list, kanban, search), Python models, controllers, or manifests in odoogit/, or when Odoo throws view validation errors, "Missing 'card' template", "Forbidden owl directive", "Unknown field/action", or CSS bundle errors. Encodes every Odoo 17→19 breaking change hit in this repo.
always-apply: false
---

# Odoo 19 rules for odoogit (project-scoped)

Battle-tested against Odoo 19.0.post20260817 (docker: `odoo:19`). Every rule
here fixed a REAL failure in this repo. Apply before building the image.

## Kanban views (19 breaking change)

- Template MUST be `<t t-name="card">` — `kanban-box` throws
  `Error: Missing 'card' template` at render (form x2many nested kanban AND
  main kanban views). Applies to nested kanban inside one2many fields too.
- Field access: `record.field.value` = formatted display, `record.field.raw_value`
  = raw (for `t-if` logic). Bare `record.field` renders garbage.
- `t-if` / `t-att-class` / `t-attf-class` work (Owl templates).
- Prefer inline `<field name="x"/>` — renders with its widget (badge, avatar…).
- No `oe_kanban_global_click` needed — cards are clickable by default.
- No dict-literal indexing `t-att-class="{...}[record.x]"`; use ternary chains
  or `t-attf-class="bg-#{'x' if cond else 'y'}"`.
- Declare every field used by the template at `<kanban>` root.

## Form views are server-rendered (no Owl)

- FORBIDDEN in form arch: `t-out`, `t-esc`, `t-if`, `t-att-*` — raises
  `Forbidden owl directive used in arch`. Exception: nested `<kanban>`
  templates inside one2many (client-side Owl, allowed).
- Conditional display: `invisible="python_expr"` on the element.
- Decorative headers: use `<field name="x" class="..."/>`, not `t-out`.
- Datetime fields need `widget="datetime"` (`widget="date"` logs console
  warnings). `fields.Date` keeps `widget="date"`.

## XML escaping (build-breaking)

Inside attribute values: `&` → `&amp;`, `<` → `&lt;` (e.g. button strings
"Squash &amp; Merge", domains `expires_at &lt; context_today()`). Validate
every view file parses BEFORE `docker compose build`:

```bash
python3 -c "from xml.etree import ElementTree as ET; import glob; [ET.parse(f) for f in glob.glob('odoogit/views/*.xml') + glob.glob('odoogit/wizards/*.xml')]; print('XML OK')"
```

Docker COPY layers cache aggressively: a bad build sticks until files change.

## View ↔ model contract (install-time validator)

- Every `type="object" button name="X"` must be a real method on the model.
- Every `<field name="Y">` must exist on the model (x2many inline sub-views
  use the COMPOSING model's fields).
- No clipboard-copy via `type="object"` — remove such buttons.
- x2many inverse: if the view needs `child_ids` on parent, add
  `fields.One2many('child', 'parent_id')`.
- Search views: fields inside `<group>` must exist; `t-*` forbidden too.

## Other 17→19 renames hit in this repo

| old | new |
|---|---|
| `attrs="{'invisible': [...]}"` | `invisible="expr"` |
| `states={...}` on buttons | `invisible="state != 'x'"` |
| `view_mode` `tree` | `list` |
| `_sql_constraints` | `models.Constraint('unique(...)', 'msg')` in class body |
| kanban `record.value` | `record.field.value` / `.raw_value` |
| `groups_id` (res.users) | `group_ids` |
| `@api.constrains` dup-checks | keep, but pair with Constraint for DB-level |
| `type='json'` route | `type='jsonrpc'` (check controllers/) |
| `odoo.osv.expression` | `odoo.fields.Domain` |
| `group_operator` field param | `aggregator` |

## Field parameter hygiene

Unknown field params log `unknown parameter 'inverse_name'` warnings —
remove them or override `_valid_field_parameter` on the model.

## Build & verify loop

```bash
docker compose build odoo && docker compose up -d
docker compose exec odoo odoo -d odoo -i odoogit --stop-after-init \
  --db_host=postgres --db_user=odoo --db_password=odoo --workers=0   # install
# use -u odoogit for upgrades after view changes
python3 qa/run.py                     # browser QA (6 flows, must stay green)
```

Unit tests: `--test-enable --test-tags /odoogit --http-port=8070` (54 tests).

## Known environment traps

- `odoo shell` does NOT auto-commit — call `env.cr.commit()`.
- After `agent-browser close`, sleep ~2s before `open` (relaunch race).
- Snapshot refs print `[ref=eN]`; click via `@eN`. `find text X click` does
  NOT open list records — snapshot + ref click (`click_row` in qa/run.py).
- CSS error placeholder "A css error occured, using an old style to render
  this page" = a bundle member failed to load (missing SCSS file). Check
  `__manifest__.py` assets paths match real files.
- Stale browser tabs hold old bundles after upgrades — hard-refresh before
  trusting a JS error report.

## Dogfood findings (round 2 — every button, multi-user, real git)

- `t-attf-class="x-#{'a' if cond else 'b'}"` breaks the Owl template
  compiler (`Missing } in template expression`). Use `t-att-class` with
  ternary chains.
- Granting groups is not enough: `implied_ids` on `base.group_system`
  applies to NEW users only on install; existing DBs need the group added
  per user (odoo shell) after upgrading.
- Record rules: a global rule (no `groups`) is ALWAYS ANDed — group rules
  can never bypass it. Restrictive rules must be group rules; make every
  internal employee a member of the base module group via
  `base.group_user.implied_ids`.
- Git smart HTTP: clients only send credentials AFTER a 401 with
  `WWW-Authenticate: Basic`. A 404 on `/info/refs` makes clone/push fail
  silently. Denials must be 401 (auth) / 403 (forbidden) — never 200 with
  an error payload.
- Token auth must propagate the identity: return `(repository, user)` and
  run branch-protection/webhook logic as that user, or member pushes fail.
- GitPython on bare repos: `repo.refs[].name` is `main`, NOT
  `refs/heads/main`; `checkout` fails ("must be run in a work tree") —
  merge via `merge-tree --write-tree` + `commit-tree` + `update-ref`;
  rebase via temp `worktree add`.
- Stored computed fields WITHOUT `@api.depends` never compute on create
  (silently NULL).
- Deleting an x2many-referenced record raises the constraint AFTER your
  transaction already did the important work — guard deletions.
- `repo.git.execute([...])` bypasses `custom_environment`; use mapped
  calls (`repo.git.commit_tree(...)`) inside the context manager.
- Migrating file-backed records when a path key changes (owner/name):
  implement in `write()` or the storage diverges from the DB.
