<h1 align="center">OdooGit</h1>

<p align="center">
  <strong>Git repository hosting inside Odoo 19.</strong><br>
  Self-hosted repositories as first-class Odoo records — real bare repos on
  disk, served over Git Smart HTTP, with pull requests, reviews, access tokens
  and webhooks wired into Odoo's own users, groups and record rules.<br>
  <code>git clone</code>, <code>git push</code> and <code>git fetch</code> talk
  straight to them through <code>git http-backend</code>.
</p>

<p align="center">
  <a href="https://github.com/DonsWayo/odoogit/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/DonsWayo/odoogit/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/DonsWayo/odoogit/releases/latest"><img alt="Release" src="https://img.shields.io/github/v/release/DonsWayo/odoogit"></a>
  <a href="LICENSE"><img alt="License: LGPL-3.0" src="https://img.shields.io/badge/license-LGPL--3.0-blue"></a>
  <img alt="Odoo 19.0" src="https://img.shields.io/badge/odoo-19.0-714B67">
  <img alt="105 tests" src="https://img.shields.io/badge/tests-105%20passing-brightgreen">
</p>

<p align="center">
  <a href="#what-it-does">Features</a> ·
  <a href="#install-docker">Install</a> ·
  <a href="#cloning-and-pushing">Clone &amp; push</a> ·
  <a href="#permissions">Permissions</a> ·
  <a href="#testing">Testing</a> ·
  <a href="docs/LIMITATIONS.md">Limitations</a> ·
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

---

> **Status:** working, self-hosted, single-node. Read
> [docs/LIMITATIONS.md](docs/LIMITATIONS.md) before deploying — notably
> **webhooks are recorded but never delivered**, there is **no SSH
> transport**, and branch protection is enforced on Odoo-side merges only, not
> on `git push`.

## What it does

| Area | Supported |
|---|---|
| **Repositories** | `private` (members only) and `internal` (all employees) visibility, owner + member + group access, stars, per-owner namespacing (`<owner>/<name>.git`) |
| **Git transport** | Smart HTTP clone / fetch / push via `git http-backend`, Basic-auth with Personal Access Tokens, proper `401 WWW-Authenticate` challenges |
| **Branches** | synced from the bare repo on every push, ahead/behind counters, protection settings (see limitations), default-branch tracking |
| **Commits** | last 50 per branch mirrored into Odoo on push — SHA, author, message, date |
| **Pull requests** | draft → open → merged/closed, merge / squash / rebase, conflict detection, merges performed with `merge-tree` + `commit-tree` so they work on bare repos |
| **Reviews** | approve / request changes / comment, approval counting against the target branch's required count; a "request changes" blocks the merge |
| **Tokens** | PATs and deploy keys stored **only** as SHA-256 hashes, with scopes and expiry; the raw secret is shown once and never persisted |
| **Webhooks** | payload construction and HMAC-SHA256 signing, delivery records — **not delivered**, see limitations |
| **Portal** | customer-facing repository and commit pages |
| **JSON-RPC API** | repositories, branches, commits, tree, pull requests, reviews |

Not included: issues, wiki, labels, forks, SSH, file browser UI.

## Install (Docker)

```bash
git clone https://github.com/DonsWayo/odoogit.git
cd odoogit
docker compose build && docker compose up -d
docker compose exec odoo odoo -d odoo -i odoogit --stop-after-init \
  --db_host=postgres --db_user=odoo --db_password=odoo --workers=0
```

Log in at http://localhost:8069 — `admin` / `admin`.

The module source is baked into the image, so **code changes need
`docker compose build odoo && docker compose up -d --force-recreate odoo`**.
To iterate without rebuilding, enable the bind mount:

```bash
cp docker-compose.override.yml.example docker-compose.override.yml
docker compose up -d --force-recreate odoo
```

## Install (existing Odoo 19)

Copy `odoogit/` into your addons path, update the apps list, install
**OdooGit**. Requires the `git` binary on the server and
`pip install GitPython`.

Then set **Settings → Technical → System Parameters**:

| Key | Meaning | Default |
|---|---|---|
| `odoogit.repo_base_path` | where bare repos live | `/var/lib/odoo/git/repos` |
| `odoogit.ssh_host` | host shown in the (non-functional) SSH clone URL | `git.example.com` |

The Odoo process must own `repo_base_path` — it creates
`<base>/<owner-login>/<repo-name>.git` and runs `git http-backend` there.

## Cloning and pushing

Create a Personal Access Token under **Git → Configuration → Access Tokens**.
The token is displayed once, on the form that creates it; it is stored only as
a hash and cannot be recovered afterwards.

```bash
git clone https://<login>:<token>@your-odoo-host/git/<owner>/<repo>.git
cd repo && git push origin main
```

A push syncs branches and the last 50 commits per branch back into Odoo.

## Permissions

Access is decided in two independent places, and both must allow an action:

- **Record rules** (`security/record_rules.xml`) govern the ORM and the UI.
  Every rule is scoped to `odoogit.group_git_user`, which
  `base.group_user` implies — so every internal employee is a Git User.
- **`git.repository._check_repo_access()`** governs the controllers (Smart
  HTTP, JSON-RPC, portal), which run `sudo()` searches and must decide access
  themselves.

A token never grants more than its owner already has: a PAT is resolved to its
owning user, and that user's access to the repository is what gets checked.

## Testing

```bash
# 105 Python tests: unit, integration against a real git binary, HTTP, regression
docker compose exec odoo odoo -d odoo --test-enable --test-tags /odoogit \
  --stop-after-init --http-port=8070 \
  --db_host=postgres --db_user=odoo --db_password=odoo --workers=0

# browser QA: 6 deterministic YAML flows (needs the stack up)
python3 qa/run.py
```

`odoogit/tests/test_regressions.py` holds one test per defect found in the
August 2026 audit — see [docs/AUDIT-2026-08.md](docs/AUDIT-2026-08.md).

## Documentation

| | |
|---|---|
| [docs/LIMITATIONS.md](docs/LIMITATIONS.md) | What is deliberately absent, and why — **read before deploying** |
| [docs/AUDIT-2026-08.md](docs/AUDIT-2026-08.md) | August 2026 audit: every finding, its evidence, and the test that now covers it |
| [docs/RELEASING.md](docs/RELEASING.md) | Versioning, pre-release checks, upgrade notes |
| [CHANGELOG.md](CHANGELOG.md) | What changed, per release |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Dev loop and the testing rules this project holds to |
| [SECURITY.md](SECURITY.md) | Reporting vulnerabilities; past advisories |
| [AGENTS.md](AGENTS.md) · [odoo19-dev skill](.agents/skills/odoo19-dev/SKILL.md) | Every Odoo 17→19 breaking change this module hit, for coding agents |

## Contributing

Issues and pull requests welcome — start with
[CONTRIBUTING.md](CONTRIBUTING.md). The short version: a new route needs an
HTTP test, a new x2many needs a test that populates it, and a permission
change needs a test acting as a second user. This project learned why the hard
way.

## Security

Report vulnerabilities privately via
[GitHub Security Advisories](https://github.com/DonsWayo/odoogit/security/advisories/new),
not public issues. See [SECURITY.md](SECURITY.md) — **if you ever ran
19.0.1.0.0, rotate every access token and deploy key.**

## License

[LGPL-3](LICENSE), same as Odoo.
