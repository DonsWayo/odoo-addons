# Known limitations

What Git Hosting does not do yet. Everything here is deliberate and tested to be
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

`clone_url_ssh` is computed from the `dw_git.ssh_host` parameter and shown in
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

## File browsing and diffs are read-only

Both now exist. `Browse Files` on a repository opens a branch selector, a
directory-at-a-time tree and syntax-highlighted file contents, backed by
`GET /api/git/repositories/<id>/tree` and `.../blob`. Pull request diffs are
computed against the merge base and rendered in colour, with the raw unified
patch on its own tab.

What they are not: there is no editing, no staging, no commenting on a line,
and no blame or history view for a single file. Files over 2 MB and binary
files are not rendered.

## Commit sync is bounded

`_sync_from_git()` mirrors the **last 50 commits per branch** on each push.
Older history stays on disk and is reachable by `git`, but has no
`git.commit` record and so does not appear in Odoo.

## Mirrors reach arbitrary hosts, by design

A mirror fetches from whatever `mirror_url` names, so an operator who
configures one causes the Odoo server to make an outbound request to that
host. On an internal network that includes hosts a user could not otherwise
reach — cloud metadata endpoints among them.

The URL is validated against an allowlist (`https`, `http`, `git`, `ssh`, and
`user@host:path`) which rejects the forms git would execute rather than
fetch — `ext::` runs a shell command, `file://` reads the local filesystem,
and a leading `-` is parsed as a git option. `GIT_ALLOW_PROTOCOL` pins the
transport set as a second layer.

What is *not* restricted is which host you may point it at. There is no
address allow/deny list, no DNS-rebinding protection and no egress policy. If
that matters in your deployment, restrict it at the network layer and keep
`git.repository` write access narrow.

## Mirrors are pull-only and unconditional

`_cron_sync_mirrors` runs hourly and fetches every active mirror.
`mirror_interval` ("hourly"/"daily"/"weekly") is stored and displayed but is
not yet used to skip a mirror that synced recently.
