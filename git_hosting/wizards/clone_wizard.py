# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class GitCloneWizard(models.TransientModel):
    _name = 'git.clone.wizard'
    _description = 'Clone Repository Wizard'

    repository_id = fields.Many2one('git.repository', required=True, readonly=True)
    clone_url_http = fields.Char(string='HTTPS Clone URL', readonly=True)
    clone_url_ssh = fields.Char(string='SSH Clone URL', readonly=True)
    token_help = fields.Text(
        string='Authentication',
        default="For HTTPS, use your Personal Access Token as password.\n"
                "Example: git clone https://<username>:<pat_token>@host/git/user/repo.git",
        readonly=True
    )

    def action_copy_http(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('HTTPS clone URL copied to clipboard!'),
            }
        }