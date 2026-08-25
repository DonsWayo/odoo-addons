# Known limitations

What OdooGit does not do yet. Everything here is deliberate and tested to be
absent — none of it is a bug report.

## Webhooks are recorded, not delivered

`git.webhook._process_event()` builds the payload, computes the
HMAC-SHA256 signature and writes a `git.webhook.delivery` row with
`status='pending'`. **Nothing sends it.** There is no delivery cron, no
queue, and no HTTP client in the module.

The delivery history, retry button and failure counters in the UI all operate
on rows that never left the server.

Implementing delivery is not a one-line change: the target URL is supplied by
the user, so an outbound HTTP client here is an SSRF surface and needs an
explicit policy (address allow/deny lists, timeouts, redirect handling,
retry/backoff, and a bound on concurrent deliveries). That decision is left to
whoever deploys this.

## There is no SSH transport

`clone_url_ssh` is computed from the `odoogit.ssh_host` parameter and shown in
the UI, but the module ships no SSH server and no `authorized_keys`
management. **Only Git Smart HTTP works.**

`git.deploy_key` stores a bearer token used over HTTPS — it is not an SSH
public key, despite the name.

Use the HTTPS URL with a Personal Access Token as the password:

```bash
git clone https://<user>:<pat>@your-odoo/git/<owner>/<repo>.git
```

## Branch protection is not enforced on push

`git.branch` carries `is_protected`, `restricted_push_user_ids`,
`restricted_merge_user_ids` and friends. These are enforced when a merge
happens **through Odoo** (`action_merge`).

They are *not* enforced by `git-receive-pack`. The controller checks that the
authenticated identity has write access to the repository, then hands the pack
to `git http-backend`. Deciding per-branch rules would mean parsing the ref
updates out of the pack — which this controller does not do — or installing a
real `pre-receive` hook in each bare repository.

Anyone with repository write access can push to a protected branch over HTTPS.

## Settings that are stored but never read

These fields exist on the models and render in the UI. Nothing consumes them:

| Model | Field |
|---|---|
| `git.repository` | `require_signed_commits`, `max_file_size`, `has_projects` |
| `git.branch` | `require_linear_history`, `require_status_checks`, `required_status_check_contexts`, `dismiss_stale_reviews`, `allow_force_push`, `allow_deletions` |

`git.commit.signature_verification` is likewise stored but never computed from
an actual GPG check.

## No file browser or diff viewer

`GET /api/git/repositories/<id>/tree` lists one directory level from the bare
repository. There is no backend UI for browsing files, and no rendered diff
view — `git.pr.file.patch` holds raw patch text, populated only if something
external writes it.

## Commit sync is bounded

`_sync_from_git()` mirrors the **last 50 commits per branch** on each push.
Older history stays on disk and is reachable by `git`, but has no
`git.commit` record and so does not appear in Odoo.

## Mirrors are pull-only and unconditional

`_cron_sync_mirrors` runs hourly and fetches every active mirror.
`mirror_interval` ("hourly"/"daily"/"weekly") is stored and displayed but is
not yet used to skip a mirror that synced recently.
