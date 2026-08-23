# -*- coding: utf-8 -*-
from odoo import models, fields, _


class GitMirrorWizard(models.TransientModel):
    _name = 'git.mirror.wizard'
    _description = 'Setup Mirror Wizard'

    repository_id = fields.Many2one('git.repository', required=True, readonly=True)
    mirror_url = fields.Char(string='Upstream Mirror URL', required=True)
    mirror_interval = fields.Selection([
        ('hourly', 'Hourly'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
    ], default='daily', required=True)

    def action_setup(self):
        self.ensure_one()
        self.repository_id.write({
            'is_mirror': True,
            'mirror_url': self.mirror_url,
            'mirror_interval': self.mirror_interval,
            'mirror_active': True,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('Mirror configured. Will sync on next cron run.'),
            }
        }