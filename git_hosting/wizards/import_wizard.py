# -*- coding: utf-8 -*-
from odoo import models, fields, _


class GitImportWizard(models.TransientModel):
    _name = 'git.import.wizard'
    _description = 'Import Repository Wizard'

    name = fields.Char(string='Repository Name', required=True)
    source_url = fields.Char(string='Source URL (bare repo)', required=True)
    visibility = fields.Selection([
        ('private', 'Private'),
        ('internal', 'Internal'),
    ], default='private', required=True)

    def action_import(self):
        self.ensure_one()
        repo = self.env['git.repository'].create({
            'name': self.name,
            'visibility': self.visibility,
            'owner_id': self.env.user.id,
        })
        # TODO: Implement actual import from source_url
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('Repository created. Import from URL not yet implemented.'),
            }
        }