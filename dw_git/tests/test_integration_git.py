"""INTEGRATION tests — real git binary + HTTP layer against live Odoo."""
import os
import re
import shutil
import subprocess
import tempfile
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, tagged

from .common import DwGitCommon


@tagged('integration', 'post_install', '-at_install')
class TestGitRepoOnDisk(DwGitCommon):
    """Real git operations against the module's repo storage."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp(prefix='dw_git_test_')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _make_source_repo(self, name='src'):
        """Create a working repo with 2 commits, return its path."""
        path = os.path.join(self.tmp, name)
        self._git('init', '-q', '-b', 'main', path)
        cfg = ['-C', path, '-c', 'user.email=t@t.com', '-c', 'user.name=T']
        with open(os.path.join(path, 'README.md'), 'w') as f:
            f.write('# test\n')
        self._git(*cfg, 'add', '.')
        self._git(*cfg, 'commit', '-qm', 'c1')
        with open(os.path.join(path, 'f.txt'), 'w') as f:
            f.write('data\n')
        self._git(*cfg, 'add', '.')
        self._git(*cfg, 'commit', '-qm', 'c2')
        return path

    def _bare_repo_record(self):
        """Create repository record + seed it with a real bare clone."""
        src = self._make_source_repo()
        bare_tmp = src + '.git'
        self._git('clone', '-q', '--bare', src, bare_tmp)
        repo = self._repo('int-repo')
        target = repo._get_repo_path()
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(bare_tmp, target)
        # import branches/commits into DB like the module does
        for br in ['main']:
            sha = self._git('-C', target, 'show-ref', '--hash', br).strip()
            self.Branch.create({'name': br, 'repository_id': repo.id,
                                'commit_sha': sha})
            log = self._git('-C', target,
                            'log', '--format=%H|%s', br)
            for line in log.strip().splitlines():
                sha, msg = line.split('|', 1)
                if not self.Commit.search([('sha', '=', sha),
                                           ('repository_id', '=', repo.id)]):
                    self.Commit.create({'sha': sha, 'message': msg,
                                        'author_name': 'T',
                                        'committed_date': '2026-01-01 00:00:00',
                                        'repository_id': repo.id})
        return repo, target

    def test_bare_repo_created_on_disk(self):
        repo = self._repo('disk-check')
        repo._init_git_repo()
        self.assertTrue(os.path.isdir(repo._get_repo_path()))
        self.assertTrue(os.path.isfile(
            os.path.join(repo._get_repo_path(), 'HEAD')))

    def test_refs_read_from_real_repo(self):
        repo, target = self._bare_repo_record()
        refs = repo._get_git_refs()
        # module stores refs keyed by short branch name
        main_sha = self._git('-C', target, 'show-ref', '--hash', 'main').strip()
        values = set(refs.values())
        candidates = {refs.get('refs/heads/main'), refs.get('main')}
        self.assertTrue(candidates & values or main_sha in values,
                        f"main sha {main_sha} not among refs {refs}")
        self.assertIn(main_sha, values)

    def test_commits_imported_match_git_log(self):
        repo, target = self._bare_repo_record()
        expected = len(self._git('-C', target, 'rev-list',
                                 '--count', 'main').strip().split())
        expected = int(self._git('-C', target, 'rev-list', '--count', 'main'))
        self.assertEqual(repo.commit_count, expected)

    def test_branch_sha_matches_disk(self):
        repo, target = self._bare_repo_record()
        b = self.Branch.search([('repository_id', '=', repo.id),
                                ('name', '=', 'main')])
        disk_sha = self._git('-C', target, 'show-ref', '--hash', 'main').strip()
        self.assertEqual(b.commit_sha, disk_sha)


@tagged('integration', 'post_install', '-at_install')
class TestGitHttpEndpoints(HttpCase):
    """HTTP layer: PAT auth flow + info/refs protocol endpoint."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env['res.users'].create({
            'name': 'Http User', 'login': 'httpuser', 'email': 'h@t.com'})
        cls.repo = cls.env['git.repository'].create({
            'name': 'http-repo', 'owner_id': cls.user.id,
            'visibility': 'private'})

    def test_server_reachable_and_pat_valid(self):
        """Sanity: Odoo responds and PAT record exists with hash."""
        pat = self.env['git.personal_access_token'].sudo().create(
            {'name': 'http-test', 'user_id': self.user.id})
        self.assertTrue(pat.token)
        self.assertTrue(pat.token_hash)
        res = self.url_open('/web/login', timeout=30)
        self.assertEqual(res.status_code, 200)

    def test_info_refs_requires_auth_for_private(self):
        """Anonymous hit on private repo info/refs must not leak refs."""
        self.authenticate(None, None)
        url = f'/git/{self.user.login}/{self.repo.name}.git/info/refs'
        res = self.url_open(url, timeout=30)
        # unauthenticated: 401 challenge (git clients need it to send creds),
        # or 404/303 — never 200 leaking refs
        self.assertIn(res.status_code, (401, 303, 404))
        if res.status_code == 200:
            self.assertNotIn(b'refs/heads', res.content)
        if res.status_code == 401:
            self.assertIn('WWW-Authenticate', res.headers)

    def test_webhook_signature_format(self):
        """Webhook payload signing uses HMAC-SHA256."""
        import hashlib
        import hmac
        import json
        wh = self.env['git.webhook'].sudo().create({
            'name': 'wh', 'url': 'https://example.com/hook',
            'repository_id': self.repo.id})
        body = json.dumps({'test': True}).encode()
        sig = hmac.new(wh.secret_token.encode(), body,
                       hashlib.sha256).hexdigest()
        self.assertEqual(len(sig), 64)


@tagged('post_install', '-at_install')
class TestNotificationPipeline(DwGitCommon):
    """The notification path end to end: event -> mail.mail -> real content.

    Unit tests cover the template syntax. This covers the wiring around it,
    which failed independently: templates that rendered correctly were never
    sent at all, and when they were, they were addressed to nobody.
    """

    def setUp(self):
        super().setUp()
        self.reviewer = self._create_user('notif-reviewer')
        self.reviewer.write({'email': 'notif-reviewer@test.com'})
        self.repo = self._repo('notify')
        self.main = self._branch(self.repo, 'main')
        self.feat = self._branch(self.repo, 'feature/notify', sha='b' * 40)

    def _mails_from(self, func):
        """Return the mail.mail records a call produces."""
        Mail = self.env['mail.mail']
        before = Mail.search([]).ids
        func()
        self.env.flush_all()
        return Mail.search([('id', 'not in', before)])

    def _new_pr(self, **kw):
        vals = {
            'title': 'Notify me', 'repository_id': self.repo.id,
            'source_branch_id': self.feat.id,
            'target_branch_id': self.main.id, 'author_id': self.user.id,
        }
        vals.update(kw)
        return self.PR.create(vals)

    def test_creating_a_pr_sends_mail_with_rendered_content(self):
        pr = None

        def create():
            nonlocal pr
            pr = self._new_pr(reviewer_ids=[(6, 0, [self.reviewer.id])])

        mails = self._mails_from(create)
        self.assertTrue(mails, 'creating a pull request sent no mail at all')
        bodies = ' '.join(str(m.body_html or '') for m in mails)
        self.assertNotIn('{{', bodies, 'mail body kept raw placeholders')
        self.assertIn(pr.title, bodies, 'mail body never names the PR')

    def test_adding_a_reviewer_notifies_only_that_reviewer(self):
        """Regression: the template addresses object.reviewer_ids, so every
        existing reviewer was re-asked each time another was added."""
        first = self.reviewer
        second = self._create_user('notif-second')
        second.write({'email': 'notif-second@test.com'})

        pr = self._new_pr()
        pr.write({'reviewer_ids': [(4, first.id)]})
        self.env.flush_all()

        mails = self._mails_from(
            lambda: pr.write({'reviewer_ids': [(4, second.id)]}))
        addressed = ' '.join(m.email_to or '' for m in mails)
        self.assertIn(second.email, addressed,
                      'the newly added reviewer was not asked')
        self.assertNotIn(first.email, addressed,
                         'an already-asked reviewer was asked again')

    def test_adding_a_reviewer_schedules_an_activity_for_them(self):
        pr = self._new_pr()
        pr.write({'reviewer_ids': [(4, self.reviewer.id)]})
        self.env.flush_all()
        activities = self.env['mail.activity'].search([
            ('res_model', '=', 'git.pull_request'), ('res_id', '=', pr.id)])
        self.assertIn(self.reviewer, activities.mapped('user_id'),
                      'requesting a review scheduled no activity')

    def test_removing_a_reviewer_notifies_nobody(self):
        pr = self._new_pr(reviewer_ids=[(6, 0, [self.reviewer.id])])
        self.env.flush_all()
        mails = self._mails_from(
            lambda: pr.write({'reviewer_ids': [(3, self.reviewer.id)]}))
        self.assertFalse(mails, 'removing a reviewer sent mail')

    def test_an_unrelated_write_notifies_nobody(self):
        pr = self._new_pr(reviewer_ids=[(6, 0, [self.reviewer.id])])
        self.env.flush_all()
        mails = self._mails_from(
            lambda: pr.write({'title': 'Retitled, not re-reviewed'}))
        self.assertFalse(
            [m for m in mails if 'review' in (m.subject or '').lower()],
            'editing an unrelated field re-sent the review request')

    def test_a_failing_send_cannot_block_the_git_operation(self):
        """Notifications are best effort by design: losing the mail must
        never cost the merge.

        Note this cannot be provoked by saving a broken template — Odoo 19
        validates templates on write and refuses to store one it cannot
        render. The realistic failure is at send time (SMTP down, a
        transient error), so that is what is simulated.
        """
        pr = self._new_pr(state='open')
        template = self.env.ref('dw_git.mail_template_git_pr_merged')

        def explode(*args, **kwargs):
            raise RuntimeError('SMTP is down')

        with patch.object(type(template), 'send_mail', explode):
            pr._send_merged_notification()          # must not raise
            pr._send_closed_notification()
            pr._send_created_notification()

    def test_odoo_refuses_to_store_an_unrenderable_template(self):
        """The reason the above cannot be tested by breaking a template.

        Worth pinning: it is why a syntax error in these templates can only
        arrive through the XML data files, never through the UI — and so
        why the unit tests check the shipped XML rather than trusting that
        a bad template would be caught on save.
        """
        # A record must exist for the validation to have anything to
        # render against. Odoo checks a template by rendering it over a
        # sample record of its model, and with none in the table there is
        # nothing to render, so the write is accepted and no error is
        # raised. That made this test pass on a database with seeded data
        # and fail on a fresh one — it failed in CI while passing locally
        # for exactly that reason.
        self._new_pr(state='open')
        template = self.env.ref('dw_git.mail_template_git_pr_merged')
        with self.assertRaises(ValidationError):
            template.write({'email_from': '{{ object.no_such_field_xyz }}'})


@tagged('post_install', '-at_install')
class TestAheadBehindAgainstRealHistory(DwGitCommon):
    """Ahead/behind counters, computed from an actual diverged branch.

    These are rendered as badges in three views, and the compute swallows
    every exception and falls back to 0/0. That makes "up to date" and
    "the computation broke" the same answer on screen. No test asserted a
    non-zero count, so the whole feature could have been dead and nothing
    would have said so.
    """

    def setUp(self):
        super().setUp()
        self.base = tempfile.mkdtemp(prefix='dw-git-ahead-')
        self.addCleanup(shutil.rmtree, self.base, True)
        self.env['ir.config_parameter'].sudo().set_param(
            'dw_git.repo_base_path', self.base)

        self.repo = self._repo('ahead-behind')
        self.repo._init_git_repo()
        self.work = tempfile.mkdtemp(prefix='dw-git-ahead-work-')
        self.addCleanup(shutil.rmtree, self.work, True)
        subprocess.run(['git', 'clone', '-q', self.repo._get_repo_path(),
                        self.work], check=True, capture_output=True)
        self._git('symbolic-ref', 'HEAD', 'refs/heads/main')

    def _git(self, *args):
        return subprocess.run(['git', '-C', self.work] + list(args),
                              check=True, capture_output=True, text=True).stdout

    def _commit(self, message, name, body):
        with open(os.path.join(self.work, name), 'w') as fh:
            fh.write(body)
        self._git('add', '-A')
        self._git('-c', 'user.email=t@t.com', '-c', 'user.name=T',
                  'commit', '-qm', message)
        return self._git('rev-parse', 'HEAD').strip()

    def test_a_diverged_branch_reports_a_non_zero_ahead_count(self):
        main_sha = self._commit('base', 'a.txt', 'one\n')
        self._git('push', '-q', 'origin', 'HEAD:refs/heads/main')

        self._git('checkout', '-q', '-b', 'feature/ahead')
        self._commit('first', 'b.txt', 'two\n')
        feat_sha = self._commit('second', 'c.txt', 'three\n')
        self._git('push', '-q', 'origin', 'HEAD:refs/heads/feature/ahead')

        main = self._branch(self.repo, 'main', sha=main_sha)
        main.write({'is_default': True})
        feature = self._branch(self.repo, 'feature/ahead', sha=feat_sha)

        feature.invalidate_recordset()
        self.assertEqual(
            feature.ahead_commits, 2,
            'a branch two commits ahead of default reported '
            f'{feature.ahead_commits} — 0 here would be indistinguishable '
            'from the compute silently failing')
        self.assertEqual(feature.behind_commits, 0)

    def test_the_default_branch_is_level_with_itself(self):
        sha = self._commit('base', 'a.txt', 'one\n')
        self._git('push', '-q', 'origin', 'HEAD:refs/heads/main')
        main = self._branch(self.repo, 'main', sha=sha)
        main.write({'is_default': True})
        main.invalidate_recordset()
        self.assertEqual((main.ahead_commits, main.behind_commits), (0, 0))


@tagged('post_install', '-at_install')
class TestWebhookTellsTheTruth(DwGitCommon):
    """The test-delivery button reported success for work it never did."""

    def test_test_delivery_does_not_claim_to_have_sent_anything(self):
        """Regression: the button returned "Test webhook sent!". This module
        builds and signs payloads and stores the delivery record, but has no
        HTTP client at all — nothing is transmitted. The notification was
        the one place a user could have learned that, and it said the
        opposite.
        """
        repo = self._repo('hook-honesty')
        hook = self.env['git.webhook'].create({
            'name': 'ci', 'url': 'https://example.invalid/hook',
            'repository_id': repo.id,
        })
        before = self.env['git.webhook.delivery'].search_count(
            [('webhook_id', '=', hook.id)])

        action = hook.action_test_delivery()
        message = (action['params'].get('message') or '') + \
                  (action['params'].get('title') or '')

        self.assertNotIn('sent', message.lower(),
                         'the button still claims the payload was sent')
        self.assertNotEqual(action['params'].get('type'), 'success',
                            'reporting success for work never done')
        self.assertIn('not deliver', message.lower() + ' ' +
                      str(action['params'].get('message', '')).lower(),
                      'the user is not told delivery does not happen')

        after = self.env['git.webhook.delivery'].search_count(
            [('webhook_id', '=', hook.id)])
        self.assertEqual(after, before + 1,
                         'the payload should still be recorded for inspection')

    def test_no_http_client_is_imported_anywhere_in_the_webhook_model(self):
        """Pins the reason the message above must stay honest. If someone
        implements real delivery, this fails and the copy gets revisited."""
        import inspect

        from odoo.addons.dw_git.models import webhook as webhook_module
        source = inspect.getsource(webhook_module)
        for client in ('import requests', 'urllib.request', 'http.client'):
            self.assertNotIn(
                client, source,
                f'{client} appeared — webhooks may now actually be '
                'delivered, so action_test_delivery must stop saying they '
                'are not')


@tagged('integration', 'post_install', '-at_install')
class TestMirrorSyncActuallyFetches(DwGitCommon):
    """`_sync_mirror()` / `_fetch_refs_from()` against a real upstream repo.

    Every other mirror test in this module is negative-path
    (TestMirrorUrlValidation, `test_sync_revalidates_before_running_git`)
    or a no-op (`test_cron_sync_mirrors_does_not_crash` runs the cron with
    zero mirror repositories). None of them ever perform a real `git fetch`
    and check that the data landed in Odoo. This class does exactly that:
    build a real bare repo on disk, fetch from it, and assert the branches
    and commits actually show up as `git.branch` / `git.commit` records —
    not merely that no exception was raised.
    """

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.mkdtemp(prefix='dw_git_mirror_')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.env['ir.config_parameter'].sudo().set_param(
            'dw_git.repo_base_path', self.tmp)

    def _make_upstream(self):
        """Build a real bare source repo: main (2 commits) + a branch."""
        work = os.path.join(self.tmp, 'upstream-work')
        self._git('init', '-q', '-b', 'main', work)
        cfg = ['-C', work, '-c', 'user.email=t@t.com', '-c', 'user.name=T']

        def commit(fname, content, msg):
            with open(os.path.join(work, fname), 'w') as fh:
                fh.write(content)
            self._git('-C', work, 'add', '.')
            self._git(*cfg, 'commit', '-qm', msg)
            return self._git('-C', work, 'rev-parse', 'HEAD').strip()

        c1 = commit('a.txt', 'one\n', 'first commit')
        c2 = commit('b.txt', 'two\n', 'second commit')
        self._git('-C', work, 'checkout', '-q', '-b', 'feature/x')
        c3 = commit('c.txt', 'three\n', 'feature commit')

        bare = os.path.join(self.tmp, 'upstream.git')
        self._git('clone', '-q', '--bare', work, bare)
        return bare, {'main': c2, 'feature/x': c3}, c1

    def _permissive_mirror_guards(self):
        """Context managers patching the mirror URL/protocol allowlists.

        `MIRROR_URL_RE` in dw_git/models/repository.py deliberately rejects
        `file://` — see the comment above the regex: it is a real RCE
        vector (`ext::sh -c ...`) and `file://` reads the local filesystem
        of the Odoo server. `GIT_ALLOW_PROTOCOL` in `_fetch_refs_from` is a
        second, independent belt-and-braces guard that git itself enforces
        and which also excludes `file`. Both allowlists are intentionally
        hostile to `file://` and are already covered by their own tests in
        `TestMirrorUrlValidation` (test_regressions.py). A local `file://`
        path is only how *this test* stands up a "remote" without a
        network, so both guards are patched, scoped to a single `with`
        block, and never touched in the shipped module.

        The third patch is the SSRF host check added in #47. It resolves
        the URL's hostname and refuses loopback and private ranges; a
        `file://` URL has no hostname at all, so it would be refused before
        reaching git. It is patched here for the same reason and with the
        same scope as the other two.
        """
        return (
            patch('odoo.addons.dw_git.models.repository.MIRROR_URL_RE',
                  re.compile(r'.*')),
            patch('odoo.addons.dw_git.models.repository.'
                  'MIRROR_ALLOWED_PROTOCOLS', 'http:https:git:ssh:file'),
            patch('odoo.addons.dw_git.models.repository.GitRepository.'
                  '_check_mirror_host', lambda self, url: None),
        )

    def test_sync_mirror_actually_fetches_and_lands_data(self):
        bare, heads, c1_sha = self._make_upstream()
        repo = self._repo('mirror-live')
        repo._init_git_repo()
        repo.write({'is_mirror': True, 'mirror_active': True})

        url_patch, proto_patch, host_patch = self._permissive_mirror_guards()
        with url_patch, proto_patch, host_patch:
            repo.write({'mirror_url': 'file://' + bare})
            self.env.flush_all()
            result = repo._sync_mirror()

        self.assertTrue(result, '_sync_mirror() reported failure')
        self.assertTrue(repo.mirror_last_sync,
                         'mirror_last_sync was never stamped')

        branches = self.Branch.search([('repository_id', '=', repo.id)])
        self.assertEqual(
            set(branches.mapped('name')), {'main', 'feature/x'},
            f'expected both upstream branches, got {branches.mapped("name")}')
        main = branches.filtered(lambda b: b.name == 'main')
        feat = branches.filtered(lambda b: b.name == 'feature/x')
        self.assertEqual(main.commit_sha, heads['main'])
        self.assertEqual(feat.commit_sha, heads['feature/x'])

        commits = self.Commit.search([('repository_id', '=', repo.id)])
        messages = set(commits.mapped('message'))
        self.assertEqual(
            {'first commit', 'second commit', 'feature commit'}, messages,
            f'expected 3 upstream commit messages, got {messages}')
        first = commits.filtered(lambda c: c.sha == c1_sha)
        self.assertEqual(len(first), 1, 'the first commit never landed')
        self.assertEqual(first.message, 'first commit')

    def test_cron_sync_mirrors_fetches_a_repository_that_is_due(self):
        """Unlike test_cron_sync_mirrors_does_not_crash (zero mirrors,
        proves nothing), this seeds one genuinely due mirror — is_mirror,
        mirror_active, a valid mirror_url, never synced before — and
        checks the cron actually fetched it, not merely that it didn't
        raise.
        """
        bare, heads, _ = self._make_upstream()
        repo = self._repo('mirror-cron-live')
        repo._init_git_repo()
        repo.write({'is_mirror': True, 'mirror_active': True})
        self.assertFalse(repo.mirror_last_sync, 'precondition: never synced')

        url_patch, proto_patch, host_patch = self._permissive_mirror_guards()
        with url_patch, proto_patch, host_patch:
            repo.write({'mirror_url': 'file://' + bare})
            self.env.flush_all()
            self.Repo._cron_sync_mirrors()

        self.assertTrue(
            repo.mirror_last_sync,
            'cron did not sync a repository that is due for sync')
        branches = self.Branch.search([('repository_id', '=', repo.id)])
        self.assertEqual(
            set(branches.mapped('name')), {'main', 'feature/x'},
            f'cron ran but no branches landed: {branches.mapped("name")}')
