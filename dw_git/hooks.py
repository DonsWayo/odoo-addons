import logging

_logger = logging.getLogger(__name__)

DEFAULT_PARAMS = {
    'dw_git.repo_base_path': '/var/lib/odoo/git/repos',
    'dw_git.ssh_host': 'git.example.com',
}


def _post_init_hook(env):
    """Seed configuration, without overwriting what the operator has set.

    This hook runs on every `-u dw_git` upgrade too. It used to call
    set_param() unconditionally, so each upgrade silently reset the
    repository storage path back to the default and orphaned every repo
    on disk.
    """
    ICP = env['ir.config_parameter'].sudo()
    for key, default in DEFAULT_PARAMS.items():
        if not ICP.get_param(key):
            ICP.set_param(key, default)

    _backfill_git_user_group(env)
    _logger.info("Git Hosting installed; configuration parameters verified")


def _backfill_git_user_group(env):
    """Put existing employees into group_git_user.

    Every ir.rule in this module is scoped to dw_git.group_git_user, and a
    record rule bound to a group simply does not apply to non-members — who
    then match no rule at all and are restricted by nothing. The module
    declares `base.group_user.implied_ids += group_git_user`, but on an
    already-populated database that implication is not retroactive, so every
    pre-existing employee stayed outside the group and outside the rules.
    """
    git_user = env.ref('dw_git.group_git_user', raise_if_not_found=False)
    base_user = env.ref('base.group_user', raise_if_not_found=False)
    if not git_user or not base_user:
        return
    missing = env['res.users'].sudo().search([
        ('group_ids', 'in', base_user.ids),
        ('group_ids', 'not in', git_user.ids),
        ('share', '=', False),
    ])
    if missing:
        git_user.sudo().write({'user_ids': [(4, u.id) for u in missing]})
        _logger.info("Git Hosting: added %s existing user(s) to Git User",
                     len(missing))


def _uninstall_hook(env):
    """Remove the scheduled mirror sync."""
    env['ir.cron'].search(
        [('code', '=', 'model._cron_sync_mirrors()')]).unlink()
    _logger.info("Git Hosting uninstalled")
