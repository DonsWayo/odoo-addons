"""UNIT tests for the notification templates.

These exist because every bug this file guards against was invisible to a
passing suite: the templates rendered without raising, they simply produced
nothing usable. Two separate rendering engines are involved and they do not
share a syntax, which is exactly the kind of thing a human reads past.

    subject / email_to / email_from   inline_template   {{ expr }}
    body_html                         qweb              <t t-out="expr"/>

Writing `{{ }}` in a body is not an error. QWeb emits it as literal text,
so the mail goes out reading "{{ object.title }}" to a real person.
"""
import re

from odoo.tests import TransactionCase, tagged

#: every template the module ships, with the record it renders against
TEMPLATES = [
    'mail_template_git_pr_created',
    'mail_template_git_pr_review_request',
    'mail_template_git_pr_merged',
    'mail_template_git_pr_closed',
]


@tagged('post_install', '-at_install')
class TestMailTemplateSyntax(TransactionCase):
    """Static checks: catch the wrong engine's syntax before it is sent."""

    def _template(self, xmlid):
        return self.env.ref(f'dw_git.{xmlid}', raise_if_not_found=False)

    def test_bodies_use_qweb_not_inline_template(self):
        """body_html is rendered by QWeb, where {{ }} is literal text.

        Regression: all five bodies were written with {{ object.title }}.
        Nothing raised — recipients simply received the placeholder text.
        """
        for xmlid in TEMPLATES:
            template = self._template(xmlid)
            self.assertTrue(template, f'{xmlid} is missing')
            body = str(template.body_html or '')
            self.assertNotIn(
                '{{', body,
                f'{xmlid}: body_html is QWeb — use <t t-out="..."/>, '
                'not {{ }}, which QWeb emits as literal text')

    def test_addressing_fields_use_inline_template_not_qweb(self):
        """The mirror image: subject/email_to are NOT QWeb.

        Regression: these were written with ${...}, the jinja form Odoo
        dropped in 14, so email_to rendered empty and email_from rendered
        as its own source text. Guard against both wrong syntaxes.
        """
        for xmlid in TEMPLATES:
            template = self._template(xmlid)
            for fname in ('subject', 'email_to', 'email_from'):
                value = template[fname] or ''
                self.assertNotIn(
                    '${', value,
                    f'{xmlid}.{fname}: ${{...}} was removed in Odoo 14')
                self.assertNotIn(
                    't-out', value,
                    f'{xmlid}.{fname} is an inline template — use {{{{ }}}}, '
                    'not QWeb directives')

    def test_every_template_addresses_someone(self):
        """A template with no recipient field sends to nobody."""
        for xmlid in TEMPLATES:
            template = self._template(xmlid)
            self.assertTrue(
                (template.email_to or template.partner_to
                 or template.email_from),
                f'{xmlid} has no recipient field set at all')


@tagged('post_install', '-at_install')
class TestMailTemplateRendering(TransactionCase):
    """Render against a real record — the only proof that counts."""

    def setUp(self):
        super().setUp()
        owner = self.env['res.users'].create({
            'name': 'Tmpl Owner', 'login': 'tmpl-owner',
            'email': 'tmpl-owner@test.com',
        })
        repo = self.env['git.repository'].create({
            'name': 'tmpl-repo', 'owner_id': owner.id,
        })
        main = self.env['git.branch'].create({
            'name': 'main', 'repository_id': repo.id, 'commit_sha': 'a' * 40})
        feat = self.env['git.branch'].create({
            'name': 'feature/x', 'repository_id': repo.id,
            'commit_sha': 'b' * 40})
        self.pr = self.env['git.pull_request'].create({
            'title': 'A distinctive title worth finding',
            'repository_id': repo.id,
            'source_branch_id': feat.id,
            'target_branch_id': main.id,
            'author_id': owner.id,
        })

    def test_rendered_bodies_contain_record_data_not_placeholders(self):
        for xmlid in TEMPLATES:
            template = self.env.ref(f'dw_git.{xmlid}')
            values = template._generate_template(
                [self.pr.id], ('subject', 'body_html'))[self.pr.id]
            body = str(values.get('body_html') or '')

            self.assertNotIn('{{', body,
                             f'{xmlid}: unrendered placeholder in the body')
            self.assertNotIn('t-out', body,
                             f'{xmlid}: unrendered QWeb directive in the body')
            self.assertIn(self.pr.title, body,
                          f'{xmlid}: the body never mentions the record')
            self.assertIn(self.pr.title, values.get('subject') or '',
                          f'{xmlid}: the subject never mentions the record')

    def test_links_are_real_urls(self):
        """The body links through _notify_get_action_link, so every href
        must come out as a URL rather than an unrendered expression."""
        for xmlid in TEMPLATES:
            template = self.env.ref(f'dw_git.{xmlid}')
            body = str(template._generate_template(
                [self.pr.id], ('body_html',))[self.pr.id].get('body_html') or '')
            for href in re.findall(r'href="([^"]*)"', body):
                self.assertNotIn('object.', href,
                                 f'{xmlid}: href kept a raw expression')
                self.assertTrue(
                    href.startswith('http') or href.startswith('/'),
                    f'{xmlid}: href {href!r} is not a URL')
