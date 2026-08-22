# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def _post_init_hook(env):
    """Post-installation setup"""
    # Create default labels
    labels = [
        {'name': 'bug', 'color': '#d73a4a', 'description': "Something isn't working"},
        {'name': 'enhancement', 'color': '#a2eeef', 'description': 'New feature or request'},
        {'name': 'documentation', 'color': '#0075ca', 'description': 'Documentation improvements'},
        {'name': 'good first issue', 'color': '#7057ff', 'description': 'Good for newcomers'},
        {'name': 'help wanted', 'color': '#008672', 'description': 'Extra attention needed'},
    ]
    for label in labels:
        try:
            env['git.label'].create(label)
        except Exception:
            pass  # Model might not exist yet

    # Create system parameters
    env['ir.config_parameter'].sudo().set_param(
        'git_hosting.repo_base_path',
        '/var/lib/odoo/git/repos'
    )
    env['ir.config_parameter'].sudo().set_param(
        'git_hosting.ssh_host',
        'git.example.com'
    )

    _logger.info("Git Hosting module installed successfully")


def _uninstall_hook(env):
    """Cleanup on uninstall"""
    # Remove cron
    cron = env['ir.cron'].search([('code', '=', 'model._cron_sync_mirrors()')])
    cron.unlink()

    _logger.info("Git Hosting module uninstalled")