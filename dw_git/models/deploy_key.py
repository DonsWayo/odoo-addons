import hashlib
import hmac
import secrets

from odoo import _, api, fields, models


class GitDeployKey(models.Model):
    _name = 'git.deploy_key'
    _description = 'Repository Deploy Key (for CI/CD access via HTTPS)'
    _order = 'create_date desc'

    name = fields.Char(required=True, help="Key identifier (e.g., 'GitHub Actions', 'GitLab CI')")
    token = fields.Char(
        string='Token',
        compute='_compute_token',
        readonly=True,
        copy=False,
        help="The generated token. Not stored: readable only on the recordset "
             "returned by create()/action_regenerate()."
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

    @api.depends_context('git_fresh_tokens')
    def _compute_token(self):
        """See git.personal_access_token._compute_token — same contract."""
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
            git_fresh_tokens=tuple(zip(records.ids, raw_tokens, strict=True)))

    def _verify_token(self, raw_token):
        """Constant-time comparison against the stored hash."""
        self.ensure_one()
        if not self.token_hash:
            return False
        return hmac.compare_digest(
            self.token_hash, hashlib.sha256(raw_token.encode()).hexdigest())

    @api.model
    def find_by_token(self, raw_token):
        """Find and verify deploy key by raw token"""
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        # A deploy key resolves to repository.owner_id, so an inactive
        # owner must not be reachable through it either.
        key = self.search([('token_hash', '=', token_hash),
                           ('is_active', '=', True),
                           ('repository_id.owner_id.active', '=', True)],
                          limit=1)
        if key:
            key.write({'last_used': fields.Datetime.now()})
            return key
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
                'message': _('Deploy key regenerated. New token: %s') % raw_token,
            }
        }
