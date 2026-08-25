---
name: odoo19-dev
description: Odoo 19 module development rules for THIS project (dw_git). Use when writing or editing XML views (form, list, kanban, search), Python models, controllers, or manifests in dw_git/, or when Odoo throws view validation errors, "Missing 'card' template", "Forbidden owl directive", "Unknown field/action", or CSS bundle errors. Encodes every Odoo 17→19 breaking change hit in this repo.
always-apply: false
---

# Odoo 19 rules for dw_git (project-scoped)

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
python3 -c "from xml.etree import ElementTree as ET; import glob; [ET.parse(f) for f in glob.glob('dw_git/views/*.xml') + glob.glob('dw_git/wizards/*.xml')]; print('XML OK')"
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
| `res.groups.users` | `user_ids` (`all_user_ids` for the implied closure) |
| `t-call="portal.layout"` | `t-call="portal.portal_layout"` |

## Field parameter hygiene

Unknown field params log `unknown parameter 'inverse_name'` warnings —
remove them or override `_valid_field_parameter` on the model.

## Build & verify loop

```bash
docker compose build odoo && docker compose up -d
docker compose exec odoo odoo -d odoo -i dw_git --stop-after-init \
  --db_host=postgres --db_user=odoo --db_password=odoo --workers=0   # install
# use -u dw_git for upgrades after view changes
python3 qa/run.py                     # browser QA (6 flows, must stay green)
```

Unit tests: `--test-enable --test-tags /dw_git --http-port=8070` (130 tests).

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
- More than one database on the server ⇒ Odoo serves
  `/web/database/selector` instead of `/web/login`, and EVERY qa/run.py flow
  fails at `fill_label 'Password': element never appeared`. Drop the scratch
  databases (`odoo_clean`, `release_check`, …) before blaming your change.

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


## Security model traps (audit round 3)

- **A record rule bound to a group does not restrict non-members.** Odoo ANDs
  the rules that apply to *you*; if no rule applies, you are unrestricted.
  So `<field name="groups" eval="[(4, ref('group_git_manager'))]"/>` on a
  model whose ACL grants `base.group_user` means every non-manager employee
  reads everything. Scope restrictive rules to the group that everyone is in
  (`group_git_user`), and add a separate permissive `[(1,'=',1)]` rule for
  managers.
- **Every model needs its own rule.** `git.pr.file`, `git.pr.review` and
  `git.webhook.delivery` inherit nothing from `git.pull_request` — sub-records
  of a private repo are public until you write their rule.
- **`implied_ids` is not retroactive.** Adding
  `base.group_user.implied_ids += your_group` in a data file grants the group
  to users created *after* that point. On a populated database the existing
  employees stay outside it — and every rule scoped to that group silently
  stops applying. Backfill in `post_init_hook`:
  `grp.write({'user_ids': [(4, u.id) for u in stale_users]})`.
- **Verify group membership on a FRESH database.** An upgraded dev DB can
  report `has_group(...) == False` for a group that works fine on install;
  debugging rules on a stale DB sends you chasing the wrong bug.

## Controllers

- `type='json'` → `type='jsonrpc'` (19 deprecates the alias). JSON-RPC is
  **POST-only**: leaving `methods=['GET']` makes every call answer **405**,
  with no error in the log.
- A jsonrpc route receives its arguments as keyword args from `params`. Do not
  `json.loads(request.httprequest.data)` — the body is the JSON-RPC envelope,
  so `data['name']` raises `KeyError: 'name'`.
- Two jsonrpc routes cannot share a path (both are POST). `GET /x` + `POST /x`
  must become `/x` + `/x/create`.
- Returning `{'error': ...}, 404` from a json route serialises the *tuple* as
  a successful result. Raise `AccessError`/`UserError` instead.
- Methods defined on one model are not available on another: calling
  `pr._check_repo_access(...)` when it lives on `git.repository` is an
  `AttributeError` at request time, invisible until something calls the route.

## Fields

- **`@api.depends_context` values are hashed into the field cache key**, so
  they must be hashable. Passing a dict raises `TypeError` on every read of
  the field. Use a tuple of pairs and `dict(...)` it inside the compute.
- Pattern for a write-once secret: non-stored `compute=` field reading from
  `depends_context`, with `create()` returning
  `records.with_context(key=tuple(zip(records.ids, secrets)))`. The value is
  readable on the recordset that produced it and nowhere else — no column,
  nothing to leak.
- Non-stored computes still need `@api.depends` to refresh in a form view
  when their sources change (e.g. clone URLs vs `owner_id`/`name`).

## Test-suite blind spots this repo actually had

A green suite proves nothing about code it never calls. Before trusting it:

- Do the tests build fixtures by calling **production** setup code, or by
  reproducing it? Seeding repos with `shutil.copytree()` meant `_init_git_repo`
  had never run — it raised `NameError` on line 1.
- Is there **one HTTP request** per controller route? Eight endpoints returned
  405/500 on first call while the suite was 54/54 green.
- Does any test exercise the **x2many/m2m paths** (a repo with `group_ids`
  set)? That one omission hid a renamed field.
- Does any test act as **a second user** against the first user's data? That
  is the only way authorisation bugs surface.


## Font Awesome is 4.7 — FA5/6 names render as NOTHING (audit round 4)

Odoo ships Font Awesome **4.7**. An FA5/6 class produces an empty `<i>`: no
icon, no console error, no view-validation failure. It looks like a spacing
bug. This repo shipped four of them across five view files.

| used (FA5/6, blank) | use instead (FA4.7) |
|---|---|
| `fa-code-branch` | `fa-code-fork` |
| `fa-git-pull-request` | `fa-share-alt` (node-graph glyph) |
| `fa-commit` | `fa-history` |
| `fa-webhook` | `fa-plug` |

Verify every icon before shipping — paste into `agent-browser eval` against a
running Odoo, and it prints exactly which classes are dead:

```js
(() => {
  const names = "code-fork history share-alt plug star".split(' ');
  const missing = [];
  for (const n of names) {
    const i = document.createElement('i');
    i.className = 'fa fa-' + n;
    document.body.appendChild(i);
    const c = getComputedStyle(i, '::before').content;
    if (!c || c === 'none' || c === '""') missing.push('fa-' + n);
    i.remove();
  }
  return {missing};
})()
```

Collect the module's icons first:
`grep -rhoE 'fa fa-[a-z0-9-]+' dw_git/views/ | sed 's/fa fa-//' | sort -u`

## List/kanban views ship the defaults you set, not the fields you declared

- **`optional="hide"` is a default, not a toggle hint.** `git.repository`
  declared owner, counters, activity and stars — all `optional="hide"` — so
  the list rendered with **two** columns and looked empty. Only hide what is
  genuinely secondary.
- **`sample="1"` renders greyed Lorem-ipsum rows when the model is empty.**
  Fine in-product, but never screenshot it for a store listing or README: it
  looks like broken data.
- Kanban card heads need explicit spacing. `<span name/><span badge/>` with no
  `d-flex … gap-2` butts the badge against the name.
- Bare counters (`3  6  0`) are unreadable. Give each an icon **and** a
  `title` attribute.

## Driving an external process against the test HTTP server

Odoo's in-test server answers **400 "Request ignored during test as it does
not contain the required cookie"** to anything without its test-cursor cookie.
An external `git`, `curl` or CLI therefore cannot reach it — and a *negative*
test will pass for the wrong reason, proving nothing.

```python
from odoo.tests.common import TEST_CURSOR_COOKIE_NAME

with self.allow_requests():                       # mints a key, releases the lock
    header = f'http.extraHeader=Cookie: {TEST_CURSOR_COOKIE_NAME}={self.http_request_key}'
    subprocess.run(['git', '-c', header, 'clone', url, dest], ...)
```

Two more traps in the same tests:

- The server starts refusing with **403** after a few `allow_requests()` round
  trips in one test method. Verify late steps against the bare repo on disk
  instead of a further HTTP call.
- **The filesystem does not roll back with the transaction.** Point
  `dw_git.repo_base_path` at a `tempfile.mkdtemp()` per test class and create
  a fresh repository per test, or run N sees the commits run N-1 pushed.

## Odoo Apps Store (learned by publishing this module)

- Register the **SSH URI** with a `.git` suffix and the **series** as branch:
  `ssh://git@github.com/DonsWayo/odoo-addons.git#19.0`. An `https://` URL is
  rejected; `#main` does not map to a series. Keep that branch pushed or the
  store serves stale code silently.
- `static/description/index.html` is **not decoded as UTF-8**. A literal `—`
  publishes as `â€`. Keep the file pure ASCII and use `&mdash;`. Check:
  `python3 -c "s=open(F,encoding='utf-8').read(); print(sorted({c for c in s if ord(c)>127}) or 'ASCII')"`
- `images` in the manifest: **first entry = thumbnail**, first entry whose name
  ends `_screenshot` = the enlarged image, which Odoo intends for "a full demo
  page and not your company logo larger". Put a real UI screenshot there, not
  the banner. Paths live under `static/description/` (confirmed against
  `odoo/design-themes` `theme_enark`).
- `doc/index.rst` becomes the Documentation tab and must be pure valid RST.
- The dashboard's `Scan` **checkbox** is `auto_scan` (a setting); the `Scan`
  **link** is the trigger. A scan completes in about a minute.
