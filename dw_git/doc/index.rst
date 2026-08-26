===========
Git Hosting
===========

Git repository hosting inside Odoo 19. Repositories are real bare Git
repositories on disk, served over Git Smart HTTP, with pull requests,
reviews, access tokens and webhooks stored as ordinary Odoo records.

Installation
============

Requirements:

* Odoo 19.0
* The ``git`` binary on the server
* GitPython (``pip install GitPython``)
* A storage path owned by the Odoo system user

Copy ``dw_git`` into your addons path, update the apps list, and install
**Git Hosting**.

Configuration
=============

Set these under *Settings -> Technical -> System Parameters*:

``dw_git.repo_base_path``
    Directory holding the bare repositories. Defaults to
    ``/var/lib/odoo/git/repos``. The Odoo process creates
    ``<base>/<owner-login>/<repo-name>.git`` and runs ``git http-backend``
    there, so it must own the path.

``dw_git.ssh_host``
    Host shown in the SSH clone URL. This module ships no SSH server; the
    value is informational.

Usage
=====

Create a repository under *Git -> Repositories*. Generate a Personal Access
Token under *Git -> Configuration -> Access Tokens*; it is displayed once and
stored only as a SHA-256 hash.

Clone and push over HTTPS::

    git clone https://<login>:<token>@your-odoo-host/git/<owner>/<repo>.git

A push synchronises branches and the most recent commits per branch back into
Odoo.

Reviewing code
==============

**Browse Files** on a repository opens a read-only browser: pick a branch,
walk the tree one directory at a time, and read any file at that ref with
syntax highlighting. Binary files and files over 2 MB are not rendered.

A pull request's **Changes** tab lists every changed file with its additions
and deletions. Opening one shows the diff computed against the merge base,
rendered in colour, with the raw unified patch on a second tab. **Refresh
Changes** recomputes it from the repository.

Notifications
=============

Mail goes out when a pull request is created, a review is requested, and when
it is merged or closed. Requesting a review also schedules a to-do activity on
the reviewer, so it lands in their Odoo inbox alongside their other work.
Only newly added reviewers are notified.

Links in those mails resolve per recipient: an internal user is taken to the
backend record, a portal user to the portal page.

Access control
==============

Two independent layers must both allow an operation:

* Record rules govern the ORM and the backend UI. Every rule is scoped to the
  *Git User* group, which *Internal User* implies.
* ``git.repository._check_repo_access()`` governs the controllers, which run
  privileged searches and decide access themselves.

A token never grants more than its owner already has: it is resolved to the
owning user, and that user's access to the repository is what is checked.

Known limitations
=================

These are deliberate, and documented so nobody is surprised by them:

* Webhook payloads are built and signed, but **not delivered**. There is no
  delivery worker; adding one requires an SSRF policy for the user-supplied
  target URL.
* There is **no SSH transport**. Only Git Smart HTTP works.
* Branch protection is enforced on merges performed through Odoo, **not** on
  ``git push``.
* ``require_signed_commits``, ``require_linear_history`` and
  ``require_status_checks`` are stored but never enforced.
* Commit synchronisation mirrors the most recent commits per branch, not the
  entire history.

Support
=======

Issues and questions: https://github.com/DonsWayo/odoo-addons/issues

License
=======

LGPL-3, the same licence as Odoo.
