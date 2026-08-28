# Roadmap

Findings from reading the module defect-by-defect. Everything here is
verified against the code and against a running server, not inferred.

Last revised 2026-08-28, against 19.0.1.8.0.

---

## The failure mode that keeps recurring

Worth stating first, because it explains most of what follows and most of
what has been fixed.

> A capability is claimed, nothing verifies it against a running system,
> and it fails **silently** — no exception, no failing test, at most a log
> line.

Confirmed instances, all found by using the product rather than by the
suite:

| What was claimed | What happened |
|---|---|
| `git push` records commits | `Registry.in_test_mode()` was removed in Odoo 19; the hook swallowed the `AttributeError` and recorded nothing |
| Five mail templates notify people | `${...}` has been dead since Odoo 14; `email_to` rendered empty, bodies emitted their own source |
| Diffs are syntax-highlighted | diff2html's *slim* bundle carries no highlight.js; it was never fetched |
| "Test webhook sent!" | `ping` is in no subscription list, so the button fell through the event filter and did nothing |
| Multi-company isolation | record rules protected the ORM; `git clone` still worked, because the controller runs `sudo()` |
| Deploy keys are narrower than their owner | the deploy-key branch never called `_check_repo_access`, so it outlived company scoping ([#30]) |
| `auto_delete_head_branch` cleans up | the `unlink()` could never succeed, and its failure aborted the transaction, killing the merge email ([#32]) |
| Browser tours pass | Odoo silently skips tours with no Chrome or `websocket-client`, reporting "0 failed" |

**Guards now in place**, each one closing the specific hole that let an
instance through:

- `make assets` — checks manifest bundles *and* paths hardcoded in JS and
  fetched at runtime with `loadJS`/`loadCSS`. A manifest-only check
  reported "OK" while highlight.js was never fetched.
- `make coverage` — measured line coverage. Grepping test files for method
  names calls `upload_pack` untested when every clone test drives it.
- `make test` depends on `upgrade`, not `build`. Rebuilding reloads Python
  but not **data**: without `-u`, security rules, views and mail templates
  keep whatever the database last loaded. A correct company-scoping fix
  looked broken for an hour because of this.
- CI fails on skipped tours; Chrome and `websocket-client` are in the image.
- `make seed` builds **real** bare repositories with real commits, so a
  diff that does not render locally is a bug, not a gap in the fixture.
- mailpit in the stack, so notification mail can actually be read.

The lesson generalises: **a test that asserts structure is not a test that
asserts behaviour.** A tour asserting `.d2h-ins` exists passed happily
while nothing on the page had any colour.

---

## Closed since the first revision

| # | Finding | Resolution |
|---|---|---|
| 1 | Five mail templates exist, none is ever sent | Wired into `action_merge`, `action_close`, PR creation and review requests. Both render engines now covered by tests — `subject`/`email_to` are `inline_template` (`{{ }}`), `body_html` is QWeb (`<t t-out/>`) |
| 2 | `mail.activity.mixin` inherited and never used | `activity_schedule()` on each newly requested reviewer |
| 3 | `portal.mixin` contract unmet, `access_url` was `'#'` | `_compute_access_url` on both models: `/git/{owner}/{repo}` and `…/pr/{number}` |
| 7 | Multi-company is unguarded | 19 record rules scoped on `company_ids`, **and** a company check inside `_check_repo_access`, which is the only gate on the `sudo()` paths |
| 8 | No translations | `dw_git/i18n/dw_git.pot`, `make i18n` |

Note that #7 needed **two** fixes. The record rules alone looked complete
and were not: the git transport runs under `sudo()`, which bypasses
`ir.rule` entirely, so `git clone` still succeeded across companies. A
subagent review caught that; it was right and the first fix was not.

---

## Open

### #9 — Repository paths are keyed on `res.users.login` — *highest risk*

Bare repos live at `<base>/<owner.login>/<name>.git`. `login` is mutable.
Renaming a user orphans every repository they own: the records point at a
directory that no longer exists, and clone returns 404 with the data
sitting untouched on disk under the old name.

There is now a migration in `_sync_from_git` for the rename case, but the
underlying design is still wrong. Paths should be keyed on an immutable
id. This is the one item that can lose access to real customer data.

### #8 — Pull request numbers are global, not per repository

`number` comes from a single `ir.sequence`, so the first PR in a new
repository might be `#795`. Every Git host numbers per repository, and
users read the number as "the 795th PR **here**". Fixing it after release
means renumbering existing data or living with a discontinuity.

### #31 — `api_get_tree` / `api_get_blob` swallow every exception

Both wrap their body in `except Exception` and return an empty result. A
missing repository, a bad ref and a genuine bug are indistinguishable from
an empty directory. The JSON-RPC caller cannot tell absence from failure.
Same shape as the webhook button.

### #21 — Portal is advertised but unreachable

Both models implement portal URLs and the pages render, but `member_ids`
is restricted to internal users and no portal ACLs ship, so no portal user
can legitimately be given a repository. The decision is binary: grant
portal access properly, or drop the portal and stop advertising it.

### #7 — `project_id` is a field nobody reads

`git.repository.project_id` exists and is filterable, and nothing else in
the module mentions it. The entire `project` dependency exists to support
one dead field. Either implement the integration below or drop both.

### #19 — `widget="badge"` on Integer fields

Warns in Odoo 19 and forces enumerated colour maps. Cosmetic.

---

## Not yet built, in order of value

1. **`project` — commits and PRs linked to tasks.** Parse task references
   out of commit messages and PR titles. This is the reason to host Git
   inside an ERP at all, and the one thing no standalone Git host can do
   as naturally. It also gives `project_id` (#7) a purpose.
2. **Webhook delivery.** Payloads are built and signed correctly; there is
   no HTTP client anywhere in `webhook.py`. The button now says so
   plainly, which is honest but not a feature. Needs a queue and retry,
   not just a `requests.post`.
3. **Per-repository PR numbering** (#8) — cheaper now than later.
4. **`website`** — public repository pages, if public visibility is added.
5. **`bus`** — live PR status. Nice, not necessary; costs a dependency.

---

## Coverage

Run `make coverage` for current numbers; do not quote figures from memory.

Two things the number does not capture, and which have both hidden real
bugs here:

- **Executed is not asserted.** Every line of the mail templates was
  executed while they rendered their own source to nobody.
- **Filesystem state is not transactional.** Odoo rolls the database back
  between tests; nothing rolls back `refs/heads`. A test asserting a bare
  repo was empty passed or failed on alphabetical execution order — see
  the note in `TestDeployKeyTransportAuthorisation`.

---

## Repository shape

The monorepo split is done: `MODULES` in the `Makefile` drives install,
upgrade, test and lint, so adding a module means editing one list. The
`Dockerfile` copies every addon directory at the repo root, `entrypoint.sh`
materialises them all and prunes stale ones, and CI reads the same list.

Remaining single-module assumptions live only in prose — `README.md`,
`CHANGELOG.md` and `docs/` still describe one module — and in
`ruff.toml`'s explicit `dw_git/` path.
