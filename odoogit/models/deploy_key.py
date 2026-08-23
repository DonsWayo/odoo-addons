# -*- coding: utf-8 -*-
import hashlib

from odoo import models, fields, api, _


class GitDeployKey(models.Model):
    _name = 'git.deploy_key'
    _description = 'Repository Deploy Key (for CI/CD access via HTTPS)'
    _order = 'create_date desc'

    name = fields.Char(required=True, help="Key identifier (e.g., 'GitHub Actions', 'GitLab CI')")
    token = fields.Char(
        string='Token',
        readonly=True,
        copy=False,
        help="The actual token (shown only once on creation)"
    )
    token_hash = fields.Char(
        string='Token Hash',
        readonly=True,
        copy=False,
    )
    can_push = fields.Boolean(default=False, help="Allow push access (not just read)")

    repository_id = fields.Many2one('git.repository', required=True, ondelete='cascade')
    last_used = fields.Datetime()
    is_active = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('token'):
                import secrets
                raw_token = secrets.token_urlsafe(32)
                vals['token'] = raw_token
                vals['token_hash'] = hashlib.sha256(raw_token.encode()).hexdigest()
        return super().create(vals_list)

    @api.model
    def find_by_token(self, raw_token):
        """Find and verify deploy key by raw token"""
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        key = self.search([('token_hash', '=', token_hash), ('is_active', '=', True)], limit=1)
        if key:
            key.write({'last_used': fields.Datetime.now()})
            return key
        return False

    def action_revoke(self):
        self.write({'is_active': False})

    def action_regenerate(self):
        import secrets
        raw_token = secrets.token_urlsafe(32)
        self.write({
            'token': raw_token,
            'token_hash': hashlib.sha256(raw_token.encode()).hexdigest(),
            'last_used': False,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('Deploy key regenerated. New token: %s') % raw_token,
            }
        }