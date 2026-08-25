# -*- coding: utf-8 -*-
import hashlib
import hmac
import secrets

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class GitPersonalAccessToken(models.Model):
    _name = 'git.personal_access_token'
    _description = 'Personal Access Token (for git clone/push via HTTPS)'
    _order = 'create_date desc'

    name = fields.Char(required=True, help="Token identifier (e.g., 'CI token', 'Laptop token')")
    token = fields.Char(
        string='Token',
        compute='_compute_token',
        readonly=True,
        copy=False,
        help="The generated token. Not stored: it is readable only on the "
             "recordset returned by create()/action_regenerate(), which is "
             "what the form view renders once."
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

    @api.depends_context('git_fresh_tokens')
    def _compute_token(self):
        """Surface the raw token only for the request that generated it.

        The secret lives in the context of the recordset returned by create()
        or action_regenerate() and is never written to a database column, so
        it cannot be recovered later — by an admin, a backup, or an attacker
        with read access to the table.
        """
        # tuple of (id, secret) pairs — context values are hashed into the
        # field cache key, so a dict here raises TypeError on every read
        fresh = dict(self.env.context.get('git_fresh_tokens') or ())
        for rec in self:
            rec.token = fresh.get(rec.id) or False

    @api.model_create_multi
    def create(self, vals_list):
        raw_tokens = []
        for vals in vals_list:
            raw_token = vals.pop('token', None) or secrets.token_urlsafe(32)
            vals['token_hash'] = hashlib.sha256(raw_token.encode()).hexdigest()
            raw_tokens.append(raw_token)
        records = super().create(vals_list)
        return records.with_context(
            git_fresh_tokens=tuple(zip(records.ids, raw_tokens)))

    def _verify_token(self, raw_token):
        """Constant-time comparison of a raw token against the stored hash."""
        self.ensure_one()
        if not self.token_hash:
            return False
        return hmac.compare_digest(
            self.token_hash, hashlib.sha256(raw_token.encode()).hexdigest())

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
        self.ensure_one()
        raw_token = secrets.token_urlsafe(32)
        self.write({
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