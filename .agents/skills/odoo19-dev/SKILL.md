---
name: odoo19-dev
description: Odoo 19 module development rules for THIS project (dw_git). Use when writing or editing XML views (form, list, kanban, search), Python models, controllers, manifests, Owl components, field widgets, browser tours or tests in dw_git/, or when Odoo throws view validation errors, "Missing 'card' template", "Forbidden owl directive", "Unknown field/action", "Invalid props for component", "widget don't support the type", CSS bundle errors, InFailedSqlTransaction, or when a browser tour fails or is skipped. Encodes every Odoo 17->19 breaking change and every silent-failure mode hit in this repo.
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

## Audit views by definition, not by clicking

Screenshots find instances; the view XML finds classes. This script found
every remaining display bug in one pass — run it after any view work:

```python
# models with a list but no form -> Odoo autogenerates an ugly fallback
# actions with no <field name="help"> -> empty lists show lorem sample rows
# string="X" one-character headers    -> render as empty cells
# widget="..." not in the registry    -> silently ignored
```

Concretely, in this repo it turned up: `git.pr.file` had **no form view at
all** (the dialog users saw was Odoo's autogenerated fallback, which is why
it looked broken), **all 13 actions lacked `help`** so every empty list fell
back to lorem-ipsum sample rows, and four `+`/`-` column headers rendered as
blank cells with a stray tooltip over the neighbouring column.

An `ir.actions.act_window` without `help` is a bug, not a default. Add:

```xml
<field name="help" type="html">
    <p class="o_view_nocontent_smiling_face">Create your first X</p>
    <p>One sentence on what an X is and why you would make one.</p>
</field>
```

## Assets fail silently — check they exist

A missing file in an `assets` bundle is **not** a build error. Odoo logs
`Could not get content for <path>` to the browser console and renders the
page unstyled. Install succeeds, tests pass, CI is green.

`git mv odoogit dw_git` renamed the directory; the SCSS inside it kept its
old filename while the manifest was rewritten to the new one. Result: an
entire backend bundle pointing at a file that did not exist.

Gate it — `make assets`, and in CI:

```python
import ast, glob, os, sys
missing = []
for mf in glob.glob('*/__manifest__.py'):
    src = open(mf).read()
    man = ast.literal_eval(src[src.index('{'):])
    for paths in man.get('assets', {}).values():
        for e in paths:
            p = e[0] if isinstance(e, (list, tuple)) else e
            if '*' not in p and not os.path.isfile(p):
                missing.append(p)
sys.exit('assets declared but absent: ' + ', '.join(missing)) if missing else None
```

Globs cannot be checked this way and are the reason
`static/src/components/**/*` sat in the manifest for months pointing at a
directory that never existed. Prefer explicit paths.

**Also check the stylesheet targets something.** This module shipped 45
selectors for a file browser, diff viewer and commit graph that were never
built, and **zero** for the `o_kanban_git_*` classes its views actually
render. Compare the two sets before believing a stylesheet works:

```bash
grep -rhoE 'class="[^"]+"' dw_git/views/*.xml | tr ' ' '\n' | sort -u   # used
grep -oE '^\.[a-zA-Z0-9_-]+' dw_git/static/src/scss/*.scss | sort -u    # styled
```

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

## Owl 2 in Odoo 19 (audit round 5 — the UI layer, tested for the first time)

Every rule below fixed a bug that shipped and was invisible to a green suite.

- **`t-out` ESCAPES a plain string.** Returning raw HTML from a getter renders
  visible `<span class="hljs-keyword">` tags. Wrap in `markup()` from
  `@odoo/owl`. There is no warning.
- **Never mutate DOM that Owl owns.** `hljs.highlightElement(el)` replaces the
  element's children, destroying the text node Owl created for `t-esc`. Owl
  keeps writing into the now-detached node, so the pane freezes on the first
  value forever while the rest of the UI updates. Compute the markup and let
  Owl render it.
- **Client actions receive more props than `action`.** Odoo passes `actionId`,
  `updateActionState` and `className` too. Declaring only `action` raises
  `Invalid props for component 'X': unknown key 'actionId'` — but ONLY in dev
  and test mode, because Owl skips prop validation in production. Use
  `static props = ["*"]`.
- **`.o_field_widget { display: inline-block }`** applies to the wrapper Odoo
  generates for a custom widget (`o_field_<name>`). Inline-block shrinks to
  content, so a widget renders as narrow as its longest line. Style the
  wrapper, not just its insides.

## Field widgets: supportedTypes and options are both enforced silently

- `badge` supports **selection, many2one, char** only. On an Integer it logs
  "The widget: badge don't support the type integer" to the browser console
  and falls back — no failure, so it survived 23 times here.
- `badge` has **no `classes` option**. Its only supported option is
  `color_field`; colour comes from `decoration-*` attributes. Elaborate
  `options="{'classes': {...}}"` maps are read by nothing and every badge
  renders default grey, looking exactly as it would if it worked.
- To widen a widget, extend it: spread the exported descriptor and add types.
  See `dw_git/static/src/components/badge/git_badge_field.js`.
- `make assets` runs `qa/check_widgets.py`, which fails on a widget used
  against a type it does not support. Console warnings do not fail builds.

## Browser tours — the traps that cost a full day

- **A tour that declares `url:` navigates there on start**, discarding the
  `startUrl` the test passed. Every record-based tour then tests the LIST.
  If the test supplies the URL, the tour must not declare one.
- **Tours only trigger on VISIBLE elements.** `select option` can never match:
  an `<option>` has no layout box. Assert on the `<select>` and inspect its
  options in `run()`.
- **List records open from the CELL**, not the `<tr>`. Clicking the row fires
  no request at all and the dialog never opens.
- **A readonly field is a `<span>`, not a `<textarea>`.** `textarea:value(...)`
  cannot match one; textareas exist only in edit mode.
- **Odoo puts the field name on the wrapper div**, not the input:
  `[name='x'] input`, never `input[name='x']`.
- **Target buttons by class, not text.** Odoo renders duplicate control-panel
  buttons per viewport and the hidden one can match first. Use
  `.o_list_button_add` for New. Text matching passed under Chromium 131
  locally and hung under Chrome 152 in CI.
- **A step with no `run` only WAITS** — it never clicks.
- **`search_default_*` in an action's context filters your fixture away.**
  `action_git_repository` sets `search_default_my_repos`
  (`[('owner_id','=',uid)]`), so a fixture owned by anyone other than the
  login the tour uses is invisible. Own fixtures as the user that logs in.
- Odoo logs success as **`TOUR <name> SUCCEEDED`** — uppercase. A
  case-sensitive grep for "succeeded" matches nothing, which is how the CI
  guard failed the build on the first genuinely green run.

## Tours skip themselves, silently

Odoo SKIPS every tour when Chrome or `websocket-client` is missing and still
reports **"0 failed"**. Google ships no arm64 Linux Chrome and Ubuntu's
`chromium` is a snap stub, so on Apple Silicon there is no browser at all and
the entire UI layer goes untested while every run looks green.

The Dockerfile installs Playwright's Chromium wherever `google-chrome` is
absent; Odoo finds it via `find_in_path` or `ODOO_BROWSER_BIN`. Both
`make test` and CI fail when a tour is skipped, and CI pins the count against
the number of tours registered under `static/src/tours`. `> 0` would still
pass if six of seven quietly stopped running.

**Green is often the absence of a test, not the presence of a pass.**

## Test isolation: what rolls back and what does not

- **The filesystem does not roll back.** Odoo rolls the database back between
  tests; nothing rolls back `refs/heads`. A bare repo built in `setUpClass`
  carries state across every test in the class, and tests run alphabetically —
  so a test asserting "the bare repo is empty" passes or fails on execution
  ORDER. Assert on movement (snapshot before, compare after), not on absence.
- Writing identical bytes in two tests that share a bare repo leaves nothing
  staged and `git commit` exits 1. Make fixture content unique per test.
- **Mail template validation is data-dependent.** `_check_can_be_rendered`
  renders over `search([], limit=1)` and **returns early when the table is
  empty**. A test asserting a bad template is refused passes on a seeded
  database and fails on a fresh one. Create a record first.
- Data created in `setUp` AND `setUpClass` IS visible to HTTP requests through
  the shared test cursor — verified with a probe. Do not go looking there
  first; it cost hours.

## PostgreSQL: a swallowed exception still poisons the transaction

`except Exception: pass` around an ORM write does NOT contain the failure. In
PostgreSQL a failed statement aborts the WHOLE transaction; catching the
Python exception does not revive it, and every later query raises
`InFailedSqlTransaction`. Here a failed branch `unlink()` during merge killed
the merge notification that ran three lines later — merge reported success,
no branch deleted, no mail sent, one log line.

Use `with self.env.cr.savepoint():` around anything allowed to fail.

Related: a `required=True` Many2one gets `ondelete='restrict'`. A record
pinned by its own parent can never be unlinked, so "delete the child on
merge" style cleanup silently never works.

## Do not swallow exceptions into a plausible empty result

`api_get_tree`/`api_get_blob` wrapped their body in `except Exception` and
returned an empty listing. A missing repository, an unknown ref, a mistyped
path and a genuine bug were indistinguishable from an empty directory. Report
the reason (`no_repository`, `unknown_ref`, `not_found`, …) and let unexpected
exceptions propagate. A bug that looks like an empty directory is a bug nobody
reports.

## Never key a filesystem path on a mutable field

Bare repos lived at `<base>/<owner.login>/<name>.git`. `res.users.login` is
mutable, so renaming a user orphaned every repository they owned — records
pointing at a directory that no longer existed, clone 404, data intact on disk
under the old name. A `write()` override chased the repository rename and made
it look handled; nothing hooked `res.users.write`. Key on the record id and the
class of bug disappears rather than needing a second hook.

## Measure coverage, do not grep for it

Grepping test files for method names calls `upload_pack` untested when every
clone test drives it, and calls a method covered when a test only names it in
a docstring. `make coverage` runs the suite under coverage.py. Note what it
still cannot see: **executed is not asserted** — every line of the mail
templates ran while they rendered their own source to nobody.
