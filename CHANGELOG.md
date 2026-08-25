# Changelog

All notable changes to OdooGit are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Versions use Odoo's addon scheme: `<odoo-series>.<major>.<minor>.<patch>`.
`19.0.1.1.0` is the second feature release of OdooGit for Odoo 19.0.

## [Unreleased]

## [19.0.1.4.0] - 2026-08-25

### Fixed

- **Four icons rendered as blank space throughout the UI.** Odoo ships Font
  Awesome 4.7; the views used the Font Awesome 5/6 names `fa-code-branch`,
  `fa-git-pull-request`, `fa-commit` and `fa-webhook`, which produce an empty
  `<i>` with no console error and no view-validation failure. Replaced with
  `fa-code-fork`, `fa-share-alt`, `fa-history` and `fa-plug` across five view
  files, each verified to resolve to a real glyph in the browser.
- **The repository kanban card was unreadable.** The visibility badge butted
  straight against the repository name, and the counter row was three
  unlabelled digits - two of which had no icon because of the bug above. The
  head is now a spaced flex row and the counters are four labelled figures
  (branches, commits, open pull requests, stars).

### Changed

- Apps Store description rewritten from ~450 to ~890 words with a structure
  benchmarked against the most-downloaded 19.0 module: why the module exists,
  what it is, screenshots per capability, access model, an explicit "read this
  before you install" section, and the test story. Seven screenshots, up from
  three.
- Added kanban and commit-history screenshots to the listing.

### Added

- `.agents/skills/odoo19-dev/SKILL.md` gains four sections of findings from
  this round: the Font Awesome 4.7 trap with a browser snippet that reports
  dead icon classes, list/kanban view defaults (`optional="hide"`,
  `sample="1"`), how to drive an external process against Odoo's test HTTP
  server, and the Apps Store rules learned by publishing.

### Added

- `odoogit/doc/index.rst` — the Apps Store loads a module's documentation tab
  from this path and requires pure, valid RST.
- A `19.0` branch tracking `main`. The Apps Store requires the registered
  branch to be named after the Odoo series, so this is the branch it scans;
  `docs/RELEASING.md` now pushes it as part of every release.

### Fixed

- **Em-dashes rendered as `â€` on the published Apps Store listing.** The
  store does not decode `static/description/index.html` as UTF-8, so the file
  is now pure ASCII with `&mdash;` entities.
- **The Apps Store cover and large screenshot were the same branding image.**
  Odoo blows up the first `images` entry whose name ends in `_screenshot`, and
  intends that slot for "a full demo page and not your company logo larger".
  The banner is now `cover.png` (thumbnail) and the large image is
  `repositories_screenshot.png`, a real screenshot of the UI — matching the
  shape of Odoo's own `theme_enark`, which also confirmed that
  `static/description/` is the right home for these files.
- `docs/PUBLISHING.md` gave the wrong registration URL. The Apps Store
  normalises every repository to the SSH URI scheme
  (`ssh://git@github.com/DonsWayo/odoogit#main`) and rejects an `https://`
  URL as badly formatted — and the branch must be the series name (`19.0`),
  not the default branch, with a `.git` suffix. It also listed authorising
  `online-odoo` as a
  required step; that applies to **private** repositories only, and this one
  is public. Added the store's author rules, the licence compatibility
  constraints for LGPL-3, and why the GitHub social preview cannot be uploaded
  by automation.

## [19.0.1.3.0] — 2026-08-25

### Fixed

- **A repository owner could not merge their own pull request.**
  `action_merge()` advances the target branch and may delete the merged head
  branch, but `ir.model.access` gave employees read-only on `git.branch` — so
  every merge raised `AccessError` and only a Git Manager could complete a
  pull request. Found by the new end-to-end test, not by any unit test.
- **Branches and commits of an `internal` repository are now readable by
  employees.** Their record rules only matched owners, members and groups, so
  a repository visible to everyone had branches visible to nobody. Read and
  write are now separate rules, mirroring `git.repository`.
- **The pull-request browser tour asserted nothing.** Its setup created the
  fixture as `git.pull.request` — the model is `git.pull_request` — and the
  resulting `KeyError` was swallowed by a bare `except`, so the tour had been
  running against a repository with no pull requests since it was written.

### Added

- **End-to-end tests for the loop the product exists for**
  (`test_e2e_git_lifecycle.py`): clone over HTTP with a real Personal Access
  Token, commit, push, watch branches and commits appear in Odoo, open a pull
  request, merge it, and verify the bare repository on disk agrees. Covers
  merge, squash and rebase-adjacent paths, plus the transport refusing a
  stranger's token and an anonymous clone.
  Odoo's in-test HTTP server answers 400 to any request without its
  test-cursor cookie, so these forward it through `git -c http.extraHeader`
  inside `allow_requests()` — without that the authorisation assertions would
  have passed for the wrong reason.
- Screenshots and a social-preview banner under `docs/images/`, regenerable
  from `docs/images/social-preview.src.html`.
- An Odoo Apps Store listing page (`static/description/index.html`) plus the
  manifest `images` and `support` keys.
- A redrawn app icon at 256×256, and `docs/PUBLISHING.md` — the store
  checklist, the rules `index.html` must follow (only PNG/GIF/JPEG from
  `static/description`, external links stripped), and where it is worth
  telling people about the module.

### Changed

- **The repository and pull-request list views were nearly empty.** Every
  useful column — owner, default branch, counters, last activity, stars;
  source and target branch, author, approvals, mergeable — shipped as
  `optional="hide"`, leaving two columns visible by default. They are now
  shown.
- Removed `open_issue_count` and `wiki_page_count`, which computed a constant
  0 for models deleted in `9bc27d3`, and the dead "Open Issues" column.

## [19.0.1.2.0] — 2026-08-25

### Added

- **Repository import actually imports.** `git.import.wizard` had a required
  `source_url` that nothing read: it created an empty record and told the user
  import "is not yet implemented". It now initialises the bare repo and
  fetches the source's branches through a new
  `git.repository._fetch_refs_from()`, shared with mirroring so the import
  path gets the same URL allowlist — `ext::` is a shell command to git, and
  `file://` a local path.
- `Makefile` with the full task set (`make help`). The documented commands
  were 120-character `docker compose exec` invocations repeated in four files;
  they are now `make install`, `make test`, `make check`, `make qa`,
  `make release-check`, `make versions`.
- Ruff lint, wired into CI as a gate rather than advice. F821 (undefined name)
  would have caught the `NameError` that shipped in 19.0.1.0.0.
- `.editorconfig`.

### Changed

- **PostgreSQL 16 → 18.** Verified, not assumed: clean install, upgrade path,
  115 tests and the browser flows all pass on 18.6. PostgreSQL 18 also
  relocated its recommended mount point, so the compose volume moved from
  `/var/lib/postgresql/data` to `/var/lib/postgresql`.
  **This needs a fresh volume — run `make clean` before `make up`**, or
  Postgres refuses to start on a version-16 data directory.
- GitPython 3.1.44 → 3.1.59.
- GitHub Actions bumped to `checkout@v7`, `setup-python@v7`,
  `upload-artifact@v7`.
- `zip()` over record ids and freshly generated secrets is now `strict=True`.
  A length mismatch there would have silently handed somebody another user's
  token instead of raising.

### Removed

- `websocket-client` from the image: nothing in the module imported it. It was
  left over from the `bus` dependency dropped in 19.0.1.1.0.
- Nine unused imports, two unused locals, and the redundant
  `# -*- coding: utf-8 -*-` lines (Python 3 is UTF-8 by default).

### Fixed

- `_init_git_repo()` re-raises with `from e`, so the original OSError survives
  in the traceback instead of being masked by the `UserError`.

## [19.0.1.1.0] — 2026-08-25

Audit release. Full findings and evidence in
[docs/AUDIT-2026-08.md](docs/AUDIT-2026-08.md).

### Security

- **Personal Access Tokens no longer unlock repositories their owner cannot
  access.** The Smart HTTP layer discarded the Basic-auth username, resolved
  the password to a PAT globally, and granted access without checking the
  token owner's permissions. Since `repository_ids` defaults to empty, any
  employee's token could clone *and push to* any private repository. Tokens
  are now resolved to their owner and that owner's access is what is checked.
- **Deploy keys and webhooks are no longer readable by every employee.** Their
  only record rule named `group_git_manager`; a rule bound to a group does not
  apply to non-members, who therefore matched no rule at all. Both models
  stored a plaintext credential. Rules are now scoped to `group_git_user`,
  with separate manager rules.
- **Added the missing record rules for `git.pr.file`, `git.pr.review` and
  `git.webhook.delivery`** — review bodies, diff patches and delivery payloads
  of private repositories were readable by any internal user.
- **Raw tokens are no longer stored.** `git.personal_access_token.token` and
  `git.deploy_key.token` are now non-stored computed fields, surfaced only on
  the recordset returned by `create()` / `action_regenerate()`. The database
  keeps the SHA-256 hash and nothing else. Token comparison uses
  `hmac.compare_digest`.
- **Branch merge restrictions are enforced.** `action_merge()` now calls
  `git.branch.can_user_merge()`, which existed but was called from nowhere.
- A review in `request_changes` now blocks the merge.
- **Posting a review requires write access, not read access.**
  `POST /api/git/pull_requests/<id>/review` checked read permission. On an
  `internal` repository every employee is a read-only viewer, so any employee
  could post an `approve` — which counts towards a protected branch's
  required-approval threshold and unblocks the merge.
- **Mirror URLs are validated against an allowlist.** `_sync_mirror()` was a
  no-op before this release; implementing it introduced a command-execution
  path, caught in review. `git fetch` treats `ext::sh -c '...'` as a shell
  command and `file://` as a local path, `mirror_url` is a plain field that
  `ir.model.access` lets every employee write, and the mirror cron runs
  hourly as the Odoo system user. Only `https://`, `http://`, `git://`,
  `ssh://` and `user@host:path` are accepted now — enforced by an
  `@api.constrains` and re-checked at fetch time, with
  `GIT_ALLOW_PROTOCOL` pinned as a second layer.

### Fixed

- `_init_git_repo()` raised `NameError` on every call — the module imported
  `os as _os` and the method called `os.makedirs`. No repository was ever
  created on disk through this path.
- The JSON API was entirely unreachable: routes declared `type='json'` with
  `methods=['GET']`, but JSON-RPC is POST, so every GET route answered `405`.
  All routes are now `type='jsonrpc'` and take their arguments from `params`
  rather than re-parsing the request body.
- `POST /api/git/repositories` wrote `has_wiki` / `has_issues`, fields deleted
  with the wiki and issue models, and crashed on every call. The route moved to
  `/api/git/repositories/create` (list and create can no longer share a path
  now that both are POST) and initialises the bare repo on disk.
- The three pull-request API endpoints called `_check_repo_access()` — a
  `git.repository` method — on a `git.pull_request` record, raising
  `AttributeError` every time.
- Every portal page returned HTTP 500: `/git/<owner>/<repo>` read the deleted
  `repository.issue_ids`, and all three templates called `portal.layout`,
  which Odoo 19 renamed to `portal.portal_layout`.
- The hourly mirror cron raised `Invalid field git.repository.is_mirror` on
  every run. The mirror fields (`is_mirror`, `mirror_url`, `mirror_active`,
  `mirror_interval`, `mirror_last_sync`) now exist, and `_sync_mirror()`
  performs a real `git fetch` instead of `pass`.
- Installing with demo data failed — `demo_data.xml` set `has_wiki` /
  `has_issues`.
- `collaborator_count` raised for any repository shared with an `res.groups`:
  it read `group.users`, which Odoo 19 renamed to `user_ids`.
- Added `ir.model.access` rows for the four wizard models, which shipped with
  none.
- `_post_init_hook` reset `odoogit.repo_base_path` and `odoogit.ssh_host` on
  **every** `-u odoogit` upgrade, orphaning existing repositories behind the
  old path. It now seeds only unset parameters.
- Upgrades now backfill `group_git_user` membership. Every record rule in the
  module is scoped to that group, granted through
  `base.group_user.implied_ids` — which is not retroactive, so on an existing
  database the module's record rules applied to nobody.
- Smart HTTP truncated LF-delimited CGI responses: the parser found a 2-byte
  `\n\n` separator and then skipped 4 bytes, eating the first two bytes of
  every such body.
- Post-merge branch cleanup tested the wrong branch in its "still referenced"
  guard, blocking cleanup arbitrarily.
- `_check_conflicts()` reported missing repositories and unknown SHAs as merge
  conflicts, indistinguishably and silently; failures are now logged and
  preconditions checked explicitly.
- Push webhook payloads reported a hardcoded `refs/heads/main`.
- `_sync_from_git()` no longer calls `cr.commit()` under the test cursor.
- `git.repository.write()` returned a bare `True` instead of `super()`'s
  result.

### Changed

- **Repository names are now unique per owner, not per company.** The on-disk
  layout is `<base>/<owner>/<name>.git`, so `alice/web` and `bob/web` never
  collide — but the old constraint rejected the second one. Existing
  single-owner databases are unaffected.
- `_check_branch_protection()` renamed to `_check_push_permission()`, which is
  what it actually does. Per-branch enforcement on push is documented as
  absent in [docs/LIMITATIONS.md](docs/LIMITATIONS.md).
- Manifest: real author and website, and `bus`, `auth_oauth`, `base_setup` and
  `hr` dropped from `depends` — none were referenced anywhere.

### Removed

- Dead `git.label` seeding from `_post_init_hook` (the model was deleted).
- Dead module-level `_check_portal_access` in `controllers/portal.py`, marked
  "will be monkey-patched"; nothing ever patched it.
- Unreferenced `static/src/scss/git_hosting.scss` and the two asset glob roots
  (`static/src/components/**`, `static/src/services/**`) that match no files.
- Unknown `inverse_name=` parameter on `git.repository.pat_ids`, logged as a
  warning on every boot.

### Testing

- Test suite grew from **54 to 105** tests. The pre-audit suite passed 54/54
  while twelve public entry points crashed on first call — it seeded
  repositories with `shutil.copytree()` instead of `_init_git_repo()`, never
  issued an HTTP request to the API or portal, never attached a group to a
  repository, and never authenticated as one user against another's repo.
- New `odoogit/tests/test_regressions.py`: one test per defect above.
- Added `docker-compose.override.yml.example` for a bind-mounted dev loop.

### Project

- GitHub Actions CI: static checks (XML, Python, manifest, declared data
  files), clean install with demo data, and the full suite. The install step
  fails the build on `Invalid field`, `Template not found`,
  `have no access rules` or `unknown parameter` — four audit findings
  announced themselves as exactly one of those lines while the suite stayed
  green.
- Release workflow: tag `v19.0.*` verifies the tag matches the manifest
  version, extracts the matching `CHANGELOG.md` section as release notes, and
  attaches a packaged addon zip.
- `CONTRIBUTING.md`, `SECURITY.md` (with the 19.0.1.0.0 advisory and the
  required token rotation), issue and pull-request templates, `CODEOWNERS`,
  and Dependabot for Actions and Docker.

## [19.0.1.0.0] — 2026-08-24

First working release: repositories, branches, commits, pull requests with
reviews and merge strategies, personal access tokens, deploy keys, webhooks,
portal pages, and Git Smart HTTP transport.

[Unreleased]: https://github.com/DonsWayo/odoogit/compare/v19.0.1.4.0...HEAD
[19.0.1.4.0]: https://github.com/DonsWayo/odoogit/compare/v19.0.1.3.0...v19.0.1.4.0
[19.0.1.3.0]: https://github.com/DonsWayo/odoogit/compare/v19.0.1.2.0...v19.0.1.3.0
[19.0.1.2.0]: https://github.com/DonsWayo/odoogit/compare/v19.0.1.1.0...v19.0.1.2.0
[19.0.1.1.0]: https://github.com/DonsWayo/odoogit/compare/v19.0.1.0.0...v19.0.1.1.0
[19.0.1.0.0]: https://github.com/DonsWayo/odoogit/releases/tag/v19.0.1.0.0
