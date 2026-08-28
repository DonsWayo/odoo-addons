"""Move bare repositories from <base>/<owner.login>/<name>.git to <base>/<id>.git.

The old layout keyed the on-disk path on res.users.login, which is
mutable: renaming a user orphaned every repository they owned (#9). Paths
are now keyed on the repository id, which never changes.

Best effort by design. A repository whose directory is already missing, or
whose destination already exists, is left alone and logged rather than
raising — an upgrade that aborts halfway through moving git data is worse
than one that reports what it could not move.
"""
import logging
import os
import shutil

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    cr.execute("""
        SELECT r.id, r.name, u.login
          FROM git_repository r
          JOIN res_users u ON u.id = r.owner_id
    """)
    rows = cr.fetchall()
    if not rows:
        return

    cr.execute("""
        SELECT value FROM ir_config_parameter
         WHERE key = 'dw_git.repo_base_path'
    """)
    found = cr.fetchone()
    base = found[0] if found else '/var/lib/odoo/git/repos'

    moved = skipped = missing = 0
    for repo_id, name, login in rows:
        old = os.path.join(base, login, f'{name}.git')
        new = os.path.join(base, f'{repo_id}.git')
        if os.path.isdir(new):
            skipped += 1
            continue
        if not os.path.isdir(old):
            missing += 1
            _logger.warning(
                "dw_git: repository %s (%s/%s) has no directory at %s; "
                "nothing to move", repo_id, login, name, old)
            continue
        os.makedirs(base, exist_ok=True)
        shutil.move(old, new)
        moved += 1

    # the per-owner directories are empty once their contents have moved
    for _repo_id, _name, login in {(r[0], r[1], r[2]) for r in rows}:
        owner_dir = os.path.join(base, login)
        if os.path.isdir(owner_dir) and not os.listdir(owner_dir):
            os.rmdir(owner_dir)

    _logger.info(
        "dw_git: repository layout migrated to id-keyed paths — "
        "%s moved, %s already present, %s missing", moved, skipped, missing)

    _renumber_pull_requests(cr)


def _renumber_pull_requests(cr):
    """Renumber pull requests per repository, oldest first (#8).

    Numbers came from a single global ir.sequence, so the first pull
    request in a new repository could be #795. They are now per
    repository, and existing data has to be brought into that shape or the
    unique constraint on (repository_id, number) cannot hold.

    Ordered by id, which is creation order, so the sequence within each
    repository still reflects the order they were opened.
    """
    cr.execute("""
        SELECT id, repository_id FROM git_pull_request
         WHERE repository_id IS NOT NULL
         ORDER BY repository_id, id
    """)
    seen = {}
    for pr_id, repo_id in cr.fetchall():
        seen[repo_id] = seen.get(repo_id, 0) + 1
        cr.execute("UPDATE git_pull_request SET number = %s WHERE id = %s",
                   (seen[repo_id], pr_id))
    if seen:
        _logger.info(
            "dw_git: renumbered pull requests per repository across %s "
            "repositories", len(seen))
