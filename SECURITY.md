# Security policy

## Reporting a vulnerability

**Do not open a public issue.** Use GitHub's private reporting:

➡️ **[Report a vulnerability](https://github.com/DonsWayo/odoo-addons/security/advisories/new)**

Please include the Git Hosting and Odoo versions, whether the issue is reachable
from the Git Smart HTTP endpoints, the JSON-RPC API, the portal or the backend
UI, and the smallest reproduction you have. If it involves access control, say
which user reached which record.

Expect an acknowledgement within 5 working days. This is a small project with
no paid maintainers, so please allow reasonable time before disclosing.

## Supported versions

| Version | Supported |
|---|---|
| 19.0.1.1.x | ✅ |
| 19.0.1.0.x | ❌ — see the advisory below |
| < 19.0 | ❌ |

## Known past vulnerabilities

### 19.0.1.0.0 - 19.0.1.7.0 - cross-company repository disclosure

Fixed in **19.0.1.7.1**. Only affects databases running **more than one
company**. Single-company installs were never exposed by this.

If you ran any version up to and including `19.0.1.7.0` with multiple
companies, treat the following as having happened:

**Any employee of any company could read every `internal`-visibility
repository in the database, regardless of which company owned it** — its
branches, commits and pull requests in the backend and the JSON-RPC API, and
its complete source history by `git clone` over Smart HTTP using their own
personal access token.

Two independent gates were both missing the check:

1. **No record rule referenced `company_id`.** `git.repository` has a
   required `company_id` and sets `_check_company_auto = True`, but the
   repository rule's `visibility == 'internal'` branch was an unqualified
   `OR`, and no rule in the module scoped by company.
2. **`_check_repo_access()` never looked at company either.** This is the
   only gate on the git transport, on PAT and deploy-key authentication and
   on the portal, because those paths run under `sudo()` where record rules
   do not apply. Fixing the rules alone would have left `git clone` working
   exactly as before.

A Git Manager in one company also had full access to every other company's
repositories.

**Required action after upgrading:**

- **Review access logs for clones you cannot account for**, particularly
  `GET /git/<owner>/<repo>.git/info/refs` and `git-upload-pack` requests from
  users outside the owning company.
- Treat the contents of any multi-company `internal` repository as having
  been readable by every employee in the database. Rotate any credential that
  was committed to one.
- No token rotation is required for this issue specifically: tokens were
  never disclosed, they were simply honoured too widely. Rotation is still
  wise if a clone you cannot account for appears in the logs.

### 19.0.1.0.0 — token authorisation and credential exposure

Fixed in **19.0.1.1.0**. Full detail in
[docs/AUDIT-2026-08.md](docs/AUDIT-2026-08.md).

If you ever ran `19.0.1.0.0`, treat the following as having happened:

1. **Any Personal Access Token unlocked any repository.** The Git Smart HTTP
   layer resolved the Basic-auth password to a PAT without checking whether
   that token's owner could access the repository. A write-scoped token from
   any employee could clone *and push to* every private repository on the
   server.
2. **Every internal employee could read every deploy key and webhook**,
   including their plaintext credentials and HMAC secrets, plus every pull
   request review body, diff patch and webhook delivery payload.
3. **Raw tokens were stored in the database** next to their SHA-256 hash, so a
   database dump, backup or read-only SQL access disclosed every usable
   credential.

**Required action after upgrading:**

- **Rotate every Personal Access Token and every deploy key.** The upgrade
  drops the plaintext columns, but any secret that existed before it should be
  considered disclosed.
- **Rotate every webhook secret** (`git.webhook.secret_token`).
- Review your repositories' commit history for pushes you cannot account for.

## Scope

In scope: command execution or local file access through a user-supplied
value (repository names, mirror URLs, refs); authentication and authorisation
on the Git Smart HTTP endpoints,
the `/api/git/*` JSON-RPC routes and the portal; record rules and ACLs;
credential storage and handling; anything letting a user reach a repository
they are not a member of.

Out of scope — these are documented, intentional gaps, not vulnerabilities.
See [docs/LIMITATIONS.md](docs/LIMITATIONS.md):

- Branch protection is not enforced on `git push`; anyone with repository
  write access can push to a protected branch over HTTPS.
- Webhooks are never delivered, so webhook-side SSRF is not currently
  reachable. Building delivery requires an SSRF policy first.
- There is no SSH transport; `clone_url_ssh` is decorative.
- A mirror reaches whatever host its URL names. The URL form is restricted to
  transports git will not execute, but the destination is not filtered —
  restrict egress at the network layer if that matters to you.
- `require_signed_commits`, `require_linear_history` and
  `require_status_checks` are stored but never enforced.

## Deployment notes

Git Hosting runs `git http-backend` as the Odoo system user against directories it
owns under `dw_git.repo_base_path`. Give that path to the Odoo user alone,
put Odoo behind TLS — Personal Access Tokens travel as HTTP Basic credentials
— and remember that Git Manager is effectively repository-wide superuser.
