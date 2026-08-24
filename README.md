# OdooGit — Git Repository Manager for Odoo 19

Self-hosted Git repository management inside Odoo 19: repositories, branches,
commits, pull requests with reviews and merge strategies, personal access
tokens, deploy keys, webhooks, and a customer portal.

Powered by [GitPython](https://github.com/gitpython-developers/GitPython) —
every repository is a real bare Git repository on disk.

## Features

| Area | Highlights |
|---|---|
| **Repositories** | public/internal/private visibility, members & groups, stars, clone URLs (HTTP/SSH), per-repo settings |
| **Branches** | real Git branches, ahead/behind counters, branch protection (required reviews, linear history, status checks, push/merge restrictions) |
| **Commits** | synced from Git (SHA, author, stats), GPG signature info, parents, branch membership |
| **Pull Requests** | draft → open → merged/closed lifecycle, merge / squash / rebase strategies, conflict detection, changed files with +/- stats |
| **Reviews** | approve / request changes / comment, approval counting, reviewed-commit pinning, branch-protection enforcement |
| **Tokens & Keys** | SHA-256-hashed personal access tokens with scopes & expiry; scoped deploy keys (push/PR/review) |
| **Webhooks** | push/PR/review/branch/tag events, HMAC signatures, delivery history with retry, failure tracking |
| **Portal** | customer-facing repository & commit pages with access rules |

## Install (Docker, recommended)

```bash
git clone https://github.com/DonsWayo/odoogit.git
cd odoogit
docker compose build && docker compose up -d
# create the DB and install the module
docker compose exec odoo odoo -d odoo -i odoogit --stop-after-init \
  --db_host=postgres --db_user=odoo --db_password=odoo --workers=0
```

Login at http://localhost:8069 — `admin` / `admin`.

## Install (existing Odoo 19)

Copy `odoogit/` into your addons path, update the apps list, install
**OdooGit**. Requires `GitPython` (`pip3 install GitPython`) and the `git`
binary on the server.

Set the repository storage path under *Git → Configuration → Repository Base
Path* (default `/var/lib/odoo/git/repos`).

## Browser QA

Deterministic YAML test flows driven by [agent-browser](https://agent-browser.dev)
— see [`qa/README.md`](qa/README.md):

```bash
python3 qa/run.py        # seeds demo data (idempotent) + runs 6 flows
```

## Agent notes

Coding agents: read [`AGENTS.md`](AGENTS.md) and the project skill
[`.agents/skills/odoo19-dev/SKILL.md`](.agents/skills/odoo19-dev/SKILL.md) —
it documents every Odoo 17→19 breaking change this module survived.

## License

LGPL-3 — same as Odoo.
