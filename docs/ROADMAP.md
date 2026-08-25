# What needs a rethink

Findings from reading the module as a whole rather than defect-by-defect.
Everything here is verified against the code, not inferred.

## Dead integrations — declared, wired to nothing

These make the module look more integrated than it is. Each is a few hours of
work, and together they are most of what separates OdooGit from "a Git server
that happens to live in Odoo".

### 1. Five mail templates exist. None is ever sent.

`views/mail_templates.xml` defines `mail_template_git_pr_created`,
`_pr_review_request`, `_pr_merged`, `_pr_closed` and `_webhook_failed`. The
only `message_post` in the entire module is a failure notice in the mirror
cron.

**Nobody is notified of anything.** A pull request opens in silence; a review
request never reaches the reviewer; a merge tells no one. For a collaboration
tool this is the largest functional hole after webhook delivery — and unlike
webhooks it needs no new design, only wiring the templates that already exist
into `action_merge`, `action_close` and `git.pr.review.create`.

### 2. `mail.activity.mixin` is inherited and never used

No `activity_schedule()` anywhere. Requesting a review should create an
activity on the reviewer, which is how every other Odoo app tells a person
they owe someone something. Right now `reviewer_ids` is a list nobody is told
about.

### 3. `portal.mixin` is inherited but its contract is unmet

Both `git.repository` and `git.pull_request` inherit `portal.mixin` and never
override `_compute_access_url`, so the mixin's default applies and
`access_url` is literally `'#'`. Every portal share link points nowhere.

### 4. `project_id` is a field nobody reads

`git.repository.project_id` exists, and a search filter groups by it. Nothing
else in the module mentions it — the whole `project` dependency exists to
support one dead field.

The obvious integration is the one every developer expects: parse commit
messages and PR titles for task references, link them, and optionally close
the task on merge. Until that exists, either build it or drop `project` from
`depends`.

## Design decisions worth revisiting

### 5. Pull request numbers are global, not per repository

`number` draws from one `ir.sequence`. The screenshots show it: three open
PRs across three repositories numbered **61, 62 and 17**. GitHub, GitLab and
Gitea all number per repository, and users will read `#61` as "the 61st PR in
this repo".

This is cheap to fix now and expensive later — changing it after people have
linked to PR numbers means renumbering live data.

### 6. Repository paths are keyed on `res.users.login`

`_get_repo_path()` returns `<base>/<owner.login>/<name>.git`, and the clone
URL and every controller route use `owner_id.login` too.

Two consequences:

- **Renaming a user orphans every repository they own.** `write()` migrates
  the directory when `owner_id` or `name` changes, but nothing watches
  `res.users.login`. There is no `res.users` override in the module.
- **Logins are usually email addresses**, so real paths become
  `/var/lib/odoo/git/repos/alice@example.com/web.git` and clone URLs carry an
  `@` before the host.

A stable, immutable slug on the repository — or on the owner — would remove
both problems. That is a schema change, so it is better decided early.

### 7. Multi-company is unguarded

`git.repository` has a required `company_id` and sets
`_check_company_auto = True`, but **no record rule mentions `company_id`**.
In a multi-company database, an `internal` repository belonging to company A
is readable by every employee of company B.

Either add the company clause to the rules or drop `company_id` and say the
module is single-company.

### 8. No translations

There is no `i18n/` directory and no `.pot` template, so the module is
English-only on the Apps Store regardless of the user's language.

## Integrations worth building, in order of value

| | Integration | Why |
|---|---|---|
| 1 | **mail** — send the templates that exist | Silence is the single most surprising thing about using it today |
| 2 | **mail.activity** — review requests as activities | Puts reviews in the reviewer's Odoo inbox, where their other work is |
| 3 | **project** — commits and PRs linked to tasks | The reason to host Git in an ERP at all; nobody else can do this as naturally |
| 4 | **portal** — implement `_compute_access_url` | Makes sharing a repository or PR with a customer actually work |
| 5 | **website** | Public repository pages, if public visibility is ever added |
| 6 | **bus** — live PR and CI status | Nice, not necessary; costs a dependency that was just removed |

## Repository shape: growing past one module

The repository is **already the right shape for a monorepo.** The Apps Store
requires "one folder per App at the root", and `odoogit/` is exactly that.
Adding `odoo_cicd/` or `odoo_containers/` beside it needs **no change to the
Apps Store registration** — the scan walks the registered branch and picks up
every module folder it finds.

What is single-module today is the *tooling*, not the layout:

| File | Assumption to remove |
|---|---|
| `Dockerfile` | `COPY odoogit /opt/odoogit` |
| `entrypoint.sh` | copies one directory |
| `Makefile` | `MODULE := odoogit` |
| `.github/workflows/ci.yml` | installs and tests one module |
| `ruff.toml` | lints `odoogit/` |
| `README.md`, `CHANGELOG.md`, `docs/` | describe one module |

### Naming

**Do not call it `DonsWayo/odoo`.** It reads as a fork of `odoo/odoo`, which
is what people will assume from the URL alone, and it leans on the Odoo
trademark for a repository that is not Odoo. `DonsWayo/odoo-addons` is the
convention most vendors use and says exactly what it holds.

The GitHub rename itself is safe — GitHub redirects the old URL for git
operations — but update the Apps Store registration afterwards from *My
Repos* rather than relying on the redirect.

### Versioning across modules

Odoo versions each module independently in its own manifest, so a single
repository-wide tag stops making sense. Prefix the tag with the module:
`odoogit-v19.0.1.4.0`. Keep `CHANGELOG.md` per module, inside the module
folder, and let the root README be an index.

### Sequencing

Do not restructure ahead of need. The cheap move now is to make the tooling
take a **list** of modules instead of one name, so that adding module two is
a one-line change rather than a refactor. Rename the repository when there is
actually a second module to put in it.
