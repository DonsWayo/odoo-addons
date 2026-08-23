# -*- coding: utf-8 -*-
import secrets
import hashlib

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class GitPersonalAccessToken(models.Model):
    _name = 'git.personal_access_token'
    _description = 'Personal Access Token (for git clone/push via HTTPS)'
    _order = 'create_date desc'

    name = fields.Char(required=True, help="Token identifier (e.g., 'CI token', 'Laptop token')")
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
        help="SHA256 hash of the token for verification"
    )
    scopes = fields.Selection([
        ('read', 'Read (clone, fetch)'),
        ('write', 'Read/Write (clone, fetch, push)'),
    ], default='write', required=True)

    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, ondelete='cascade')
    repository_ids = fields.Many2many(
        'git.repository',
        'git_pat_repo_rel',
        'pat_id', 'repo_id',
        string='Allowed Repositories',
        help="Empty = all accessible repositories"
    )

    last_used = fields.Datetime()
    expires_at = fields.Date()
    is_active = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('token'):
                raw_token = secrets.token_urlsafe(32)
                vals['token'] = raw_token
                vals['token_hash'] = hashlib.sha256(raw_token.encode()).hexdigest()
        return super().create(vals_list)

    def _verify_token(self, raw_token):
        """Verify a raw token against stored hash"""
        return self.token_hash == hashlib.sha256(raw_token.encode()).hexdigest()

    @api.model
    def find_by_token(self, raw_token):
        """Find and verify PAT by raw token"""
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        pat = self.search([('token_hash', '=', token_hash), ('is_active', '=', True)], limit=1)
        if pat and (not pat.expires_at or pat.expires_at >= fields.Date.today()):
            pat.write({'last_used': fields.Datetime.now()})
            return pat
        return False

    def action_revoke(self):
        self.write({'is_active': False})

    def action_regenerate(self):
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
                'message': _('Token regenerated. New token: %s') % raw_token,
            }
        }