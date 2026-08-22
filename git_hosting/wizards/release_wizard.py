# -*- coding: utf-8 -*-
from odoo import models, fields, _


class GitReleaseWizard(models.TransientModel):
    _name = 'git.release.wizard'
    _description = 'Create Release Wizard'

    repository_id = fields.Many2one('git.repository', required=True, readonly=True)
    tag_name = fields.Char(string='Tag Name', required=True, help="e.g., v1.0.0")
    target_branch = fields.Char(string='Target Branch', default='main')
    title = fields.Char(string='Release Title')
    description = fields.Html(string='Release Notes')
    is_prerelease = fields.Boolean(string='Pre-release')
    is_draft = fields.Boolean(string='Draft')

    def action_create_release(self):
        self.ensure_one()
        # TODO: Create git tag and release record
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('Release creation not yet implemented.'),
            }
        }