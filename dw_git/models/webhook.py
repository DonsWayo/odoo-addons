import hashlib
import hmac
import json
import secrets

from odoo import _, fields, models
from odoo.exceptions import UserError


class GitWebhook(models.Model):
    _name = 'git.webhook'
    _description = 'Repository Webhook'
    _order = 'create_date desc'

    name = fields.Char(required=True)
    url = fields.Char(required=True, help="Target URL for webhook payload")
    secret_token = fields.Char(
        required=True,
        default=lambda self: secrets.token_urlsafe(32),
        copy=False,
        help="Secret for signing payloads"
    )

    repository_id = fields.Many2one('git.repository', required=True, ondelete='cascade')

    # Events
    event_push = fields.Boolean(default=True)
    event_pull_request = fields.Boolean(default=True)
    event_pull_request_review = fields.Boolean(default=True)
    event_branch = fields.Boolean(default=False)
    event_tag = fields.Boolean(default=False)

    # Config
    content_type = fields.Selection([
        ('json', 'application/json'),
        ('form', 'application/x-www-form-urlencoded'),
    ], default='json')
    ssl_verify = fields.Boolean(default=True)
    is_active = fields.Boolean(default=True)

    # Stats
    last_delivery = fields.Datetime()
    last_status = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed'),
    ])
    failure_count = fields.Integer(default=0)
    delivery_ids = fields.One2many('git.webhook.delivery', 'webhook_id', string='Recent Deliveries')

    def _process_event(self, event_type, payload):
        """Queue webhook delivery"""
        if not self.is_active:
            return

        event_map = {
            'push': self.event_push,
            'pull_request': self.event_pull_request,
            'pull_request_review': self.event_pull_request_review,
            'create': self.event_branch,
            'delete': self.event_branch,
        }

        if not event_map.get(event_type, False):
            return

        # Add signature
        body = json.dumps(payload).encode()
        signature = hmac.new(
            self.secret_token.encode(),
            body,
            hashlib.sha256
        ).hexdigest()

        # Create delivery record
        self.env['git.webhook.delivery'].sudo().create({
            'webhook_id': self.id,
            'event_type': event_type,
            'payload': body,
            'signature': f'sha256={signature}',
        })

    def action_test_delivery(self):
        """Send a test payload"""
        self._process_event('ping', {'zen': 'Test webhook from Odoo Git Hosting'})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('Test webhook sent!'),
            }
        }


class GitWebhookDelivery(models.Model):
    _name = 'git.webhook.delivery'
    _description = 'Webhook Delivery'
    _order = 'create_date desc'

    webhook_id = fields.Many2one('git.webhook', required=True, ondelete='cascade')
    event_type = fields.Char(required=True)
    payload = fields.Text(required=True)
    signature = fields.Char(required=True)

    response_code = fields.Integer()
    response_body = fields.Text()
    duration = fields.Float(help="Response time in seconds")

    status = fields.Selection([
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ], default='pending')
    error_message = fields.Text()

    def action_retry(self):
        """Retry failed delivery"""
        self.ensure_one()
        if self.status != 'failed':
            raise UserError(_("Only failed deliveries can be retried."))
        # Re-queue
        self.write({'status': 'pending'})
        # Actual sending would be done by a cron job
        return True
