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

        self._record_delivery(event_type, payload)

    def _record_delivery(self, event_type, payload):
        """Sign a payload and store it as a delivery record.

        Split out of _process_event because that method drops any event the
        webhook is not subscribed to, which is right for real events and
        wrong for a manual test: 'ping' is in no subscription list, so the
        test button fell straight through the event filter and did nothing
        whatsoever — while reporting success.
        """
        self.ensure_one()
        body = json.dumps(payload).encode()
        signature = hmac.new(
            self.secret_token.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        return self.env['git.webhook.delivery'].sudo().create({
            'webhook_id': self.id,
            'event_type': event_type,
            'payload': body,
            'signature': f'sha256={signature}',
        })

    def action_test_delivery(self):
        """Build and record a signed test payload.

        It is not sent. This module builds and signs webhook payloads and
        stores the delivery record, but ships no HTTP client — there is no
        `requests` call anywhere in this file. The limitation is documented,
        but the button used to report "Test webhook sent!", which is the one
        place a user would ever find out, and it said the opposite of the
        truth. Say what actually happened instead.
        """
        self._record_delivery('ping', {'zen': 'Test webhook from Odoo Git Hosting'})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'warning',
                'title': _('Payload recorded, not delivered'),
                'message': _(
                    'A signed test payload was built and stored under '
                    'Deliveries, where you can inspect its body and '
                    'signature. Git Hosting does not send webhooks over the '
                    'network yet — nothing was transmitted to the endpoint.'),
                'sticky': True,
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
