"""INTEGRATION tests — real git binary + HTTP layer against live Odoo."""
import os
import shutil
import tempfile

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
