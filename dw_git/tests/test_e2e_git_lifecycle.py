"""END-TO-END: the loop the product exists for.

A real `git` binary, over real HTTP, authenticating with a real Personal
Access Token, against a repository Odoo created — clone, commit, push, then
open a pull request and merge it, and check that what Odoo believes matches
what is on disk.

Nothing else in the suite does this. `test_integration_git.py` drives the
model layer against a bare repo it copied into place, and `test_e2e_tours.py`
drives the web client; between them the actual clone/push/merge path was
never executed by a test.
"""
import itertools
import os
import shutil
import subprocess
import tempfile

from odoo.tests import HttpCase, tagged
from odoo.tests.common import TEST_CURSOR_COOKIE_NAME

_repo_seq = itertools.count(1)


@tagged('e2e', 'git_lifecycle', 'post_install', '-at_install')
class TestGitLifecycleOverHttp(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Repositories live on the filesystem, which does not roll back with
        # the test transaction. Without a private base path the bare repo
        # from a previous run survives and the next run clones a repository
        # that already has the commits it is about to create.
        cls.base_path = tempfile.mkdtemp(prefix='dw_git_lifecycle_')
        cls.addClassCleanup(shutil.rmtree, cls.base_path, ignore_errors=True)
        cls.env['ir.config_parameter'].sudo().set_param(
            'dw_git.repo_base_path', cls.base_path)
        cls.dev = cls.env['res.users'].create({
            'name': 'Lifecycle Dev', 'login': 'lifecycle-dev',
            'email': 'dev@lifecycle.test'})
        cls.pat = cls.env['git.personal_access_token'].create({
            'name': 'lifecycle token', 'user_id': cls.dev.id,
            'scopes': 'write'})
        cls.token = cls.pat.token          # readable once, on this recordset
        assert cls.token, 'PAT creation did not surface a token'

    def setUp(self):
        super().setUp()
        self.work = tempfile.mkdtemp(prefix='dw_git_e2e_')
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)
        # One repository per test. The bare repo lives on the filesystem and
        # does not roll back with the transaction, so a shared one would let
        # each test see the commits pushed by the ones before it.
        self.repo = self.env['git.repository'].create({
            'name': f'lifecycle-{next(_repo_seq)}',
            'owner_id': self.dev.id,
            'visibility': 'private',
            'default_branch': 'main'})
        self.repo._init_git_repo()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _remote(self, login=None, token=None):
        """Authenticated clone URL against this test's live HTTP server."""
        login = self.dev.login if login is None else login
        token = self.token if token is None else token
        base = self.base_url().replace('http://', '')
        return (f'http://{login}:{token}@{base}'
                f'/git/{self.dev.login}/{self.repo.name}.git')

    def _run_git(self, args, cwd=None):
        env = dict(os.environ,
                   GIT_TERMINAL_PROMPT='0',      # never block on a prompt
                   GIT_CONFIG_NOSYSTEM='1',
                   HOME=self.work,
                   GIT_AUTHOR_NAME='Lifecycle Dev',
                   GIT_AUTHOR_EMAIL='dev@lifecycle.test',
                   GIT_COMMITTER_NAME='Lifecycle Dev',
                   GIT_COMMITTER_EMAIL='dev@lifecycle.test')
        return subprocess.run(['git', *args], cwd=cwd or self.work, env=env,
                              capture_output=True, text=True, timeout=120)

    def _git(self, *args, cwd=None, check=True):
        """Run a purely local git command."""
        proc = self._run_git(list(args), cwd)
        if check and proc.returncode != 0:
            self.fail(f"git {' '.join(args)} failed ({proc.returncode})\n"
                      f"stdout: {proc.stdout}\nstderr: {proc.stderr}")
        return proc

    def _git_http(self, *args, cwd=None, check=True):
        """Run a git command that talks to the Odoo test server.

        Odoo's in-test HTTP server answers 400 to any request without its
        test-cursor cookie, so an external `git` process cannot reach it
        unaided. `allow_requests()` mints a key and releases the test lock;
        the cookie rides along in an extra HTTP header, which also keeps the
        request bound to this test's cursor so the pushed records are visible
        to `self.env` afterwards.
        """
        with self.allow_requests():
            header = (f'http.extraHeader=Cookie: '
                      f'{TEST_CURSOR_COOKIE_NAME}={self.http_request_key}')
            proc = self._run_git(['-c', header, *args], cwd)
        if check and proc.returncode != 0:
            self.fail(f"git {' '.join(args)} failed ({proc.returncode})\n"
                      f"stdout: {proc.stdout}\nstderr: {proc.stderr}")
        return proc

    def _write_commit(self, clone, filename, content, message):
        with open(os.path.join(clone, filename), 'w') as fh:
            fh.write(content)
        self._git('add', filename, cwd=clone)
        self._git('commit', '-qm', message, cwd=clone)
        return self._git('rev-parse', 'HEAD', cwd=clone).stdout.strip()

    def _bare(self):
        import git
        return git.Repo(self.repo._get_repo_path())

    # ------------------------------------------------------------------
    # the loop
    # ------------------------------------------------------------------
    def test_clone_commit_push_syncs_into_odoo(self):
        """clone -> commit -> push, and Odoo learns the branch and commit."""
        clone = os.path.join(self.work, 'clone')
        self._git_http('clone', '-q', self._remote(), clone)
        self.assertTrue(os.path.isdir(os.path.join(clone, '.git')))

        sha = self._write_commit(clone, 'README.md', '# lifecycle\n',
                                 'initial commit')
        self._git_http('push', '-q', 'origin', 'HEAD:refs/heads/main', cwd=clone)

        # the bare repo really advanced
        self.assertEqual(self._bare().heads.main.commit.hexsha, sha)

        # ...and the push hook mirrored it into Odoo
        self.env.invalidate_all()
        branch = self.env['git.branch'].search([
            ('repository_id', '=', self.repo.id), ('name', '=', 'main')])
        self.assertTrue(branch, 'push did not create the branch record')
        self.assertEqual(branch.commit_sha, sha)

        commit = self.env['git.commit'].search([
            ('repository_id', '=', self.repo.id), ('sha', '=', sha)])
        self.assertTrue(commit, 'push did not create the commit record')
        self.assertEqual(commit.message, 'initial commit')
        self.assertEqual(commit.author_email, 'dev@lifecycle.test')

    def test_full_pull_request_lifecycle(self):
        """Branch, push, open a PR, merge it, and verify the bare repo."""
        clone = os.path.join(self.work, 'pr-clone')
        self._git_http('clone', '-q', self._remote(), clone)

        base = self._write_commit(clone, 'app.py', 'print("v1")\n', 'base')
        self._git_http('push', '-q', 'origin', 'HEAD:refs/heads/main', cwd=clone)

        self._git('checkout', '-q', '-b', 'feature', cwd=clone)
        head = self._write_commit(clone, 'feature.txt', 'new thing\n',
                                  'add feature')
        self._git_http('push', '-q', 'origin', 'HEAD:refs/heads/feature', cwd=clone)

        self.env.invalidate_all()
        Branch = self.env['git.branch']
        main = Branch.search([('repository_id', '=', self.repo.id),
                              ('name', '=', 'main')])
        feature = Branch.search([('repository_id', '=', self.repo.id),
                                 ('name', '=', 'feature')])
        self.assertTrue(main and feature, 'both branches must be synced')
        self.assertEqual(feature.commit_sha, head)

        pr = self.env['git.pull_request'].create({
            'title': 'Add the feature',
            'repository_id': self.repo.id,
            'source_branch_id': feature.id,
            'target_branch_id': main.id,
            'author_id': self.dev.id,
            'state': 'open',
        })
        self.assertFalse(pr.has_conflicts, 'a fast-forward must not conflict')
        self.assertTrue(pr.is_mergeable)

        pr.with_user(self.dev).action_merge()

        self.assertEqual(pr.state, 'merged')
        self.assertTrue(pr.merge_commit_sha)

        # the merge landed in the bare repo, not just in Odoo's opinion of it
        bare = self._bare()
        merged = bare.heads.main.commit
        self.assertEqual(merged.hexsha, pr.merge_commit_sha)
        self.assertIn(base, [p.hexsha for p in merged.parents])
        self.assertIn(head, [p.hexsha for p in merged.parents])

        # ...and a fresh checkout of main really contains the feature file.
        #
        # Cloned from the bare path rather than over HTTP: Odoo's test server
        # starts refusing with 403 after a few allow_requests() round trips
        # in one test. The same sequence over HTTP works against a normally
        # running server — verified by hand — so this asserts the property
        # without depending on harness behaviour we do not control.
        verify = os.path.join(self.work, 'verify')
        self._git('clone', '-q', '--branch', 'main',
                  self.repo._get_repo_path(), verify)
        self.assertTrue(os.path.isfile(os.path.join(verify, 'feature.txt')),
                        'merged file missing from a fresh checkout of main')
        self.assertTrue(os.path.isfile(os.path.join(verify, 'app.py')),
                        'base file missing after the merge')

    def test_squash_merge_produces_a_single_parent(self):
        clone = os.path.join(self.work, 'squash-clone')
        self._git_http('clone', '-q', self._remote(), clone)
        base = self._write_commit(clone, 'a.txt', '1\n', 'base')
        self._git_http('push', '-q', 'origin', 'HEAD:refs/heads/main', cwd=clone)

        self._git('checkout', '-q', '-b', 'many', cwd=clone)
        self._write_commit(clone, 'b.txt', '1\n', 'first')
        self._write_commit(clone, 'c.txt', '2\n', 'second')
        self._git_http('push', '-q', 'origin', 'HEAD:refs/heads/many', cwd=clone)

        self.env.invalidate_all()
        Branch = self.env['git.branch']
        main = Branch.search([('repository_id', '=', self.repo.id),
                              ('name', '=', 'main')])
        many = Branch.search([('repository_id', '=', self.repo.id),
                              ('name', '=', 'many')])
        pr = self.env['git.pull_request'].create({
            'title': 'Squash me', 'repository_id': self.repo.id,
            'source_branch_id': many.id, 'target_branch_id': main.id,
            'author_id': self.dev.id, 'state': 'open',
            'merge_method': 'squash'})
        pr.with_user(self.dev).action_merge()

        merged = self._bare().heads.main.commit
        self.assertEqual([p.hexsha for p in merged.parents], [base],
                         'a squash must leave exactly one parent')
        self.assertEqual(
            sorted(b.name for b in merged.tree.blobs),
            ['a.txt', 'b.txt', 'c.txt'],
            'squashed tree is missing files from the source branch')


@tagged('e2e', 'git_lifecycle', 'post_install', '-at_install')
class TestGitTransportAuthorisation(HttpCase):
    """The same transport, exercised by someone who should be refused."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Repositories live on the filesystem, which does not roll back with
        # the test transaction. Without a private base path the bare repo
        # from a previous run survives and the next run clones a repository
        # that already has the commits it is about to create.
        cls.base_path = tempfile.mkdtemp(prefix='dw_git_authz_')
        cls.addClassCleanup(shutil.rmtree, cls.base_path, ignore_errors=True)
        cls.env['ir.config_parameter'].sudo().set_param(
            'dw_git.repo_base_path', cls.base_path)
        cls.owner = cls.env['res.users'].create({
            'name': 'Owner', 'login': 'lc-owner', 'email': 'o@lc.test'})
        cls.stranger = cls.env['res.users'].create({
            'name': 'Stranger', 'login': 'lc-stranger', 'email': 's@lc.test'})
        cls.repo = cls.env['git.repository'].create({
            'name': 'lc-private', 'owner_id': cls.owner.id,
            'visibility': 'private'})
        cls.repo._init_git_repo()
        cls.stranger_token = cls.env['git.personal_access_token'].create({
            'name': 'stranger', 'user_id': cls.stranger.id,
            'scopes': 'write'}).token

    def setUp(self):
        super().setUp()
        self.work = tempfile.mkdtemp(prefix='dw_git_auth_')
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)

    def _clone(self, url, dest):
        """Clone with the test-cursor cookie attached.

        Without it every request is refused with 400 by the test server and
        these assertions would pass for the wrong reason — proving nothing
        about Git Hosting's own authorisation.
        """
        with self.allow_requests():
            header = (f'http.extraHeader=Cookie: '
                      f'{TEST_CURSOR_COOKIE_NAME}={self.http_request_key}')
            return subprocess.run(
                ['git', '-c', header, 'clone', '-q', url,
                 os.path.join(self.work, dest)],
                env=dict(os.environ, GIT_TERMINAL_PROMPT='0', HOME=self.work),
                capture_output=True, text=True, timeout=120)

    def _clone_as(self, login, token):
        base = self.base_url().replace('http://', '')
        return self._clone(
            f'http://{login}:{token}@{base}'
            f'/git/{self.owner.login}/{self.repo.name}.git', 'out')

    def test_stranger_token_cannot_clone_a_private_repo(self):
        """The privilege escalation fixed in 19.0.1.1.0, proven with git."""
        proc = self._clone_as(self.stranger.login, self.stranger_token)
        self.assertNotEqual(
            proc.returncode, 0,
            "a stranger's PAT cloned a private repository")
        # refused by Git Hosting, not by the test server's cookie gate
        self.assertNotIn('400', proc.stderr, proc.stderr)
        self.assertIn('Authentication failed', proc.stderr, proc.stderr)

    def test_anonymous_cannot_clone_a_private_repo(self):
        proc = self._clone(
            f"{self.base_url()}/git/{self.owner.login}/{self.repo.name}.git",
            'anon')
        self.assertNotEqual(proc.returncode, 0,
                            'anonymous clone of a private repository succeeded')
        self.assertNotIn('400', proc.stderr, proc.stderr)

    def test_owner_can_clone_their_own_repo(self):
        """The control: the refusals above must be about identity, not
        about the transport being broken for everybody."""
        token = self.env['git.personal_access_token'].create(
            {'name': 'owner key', 'user_id': self.owner.id,
             'scopes': 'write'}).token
        base = self.base_url().replace('http://', '')
        proc = self._clone(
            f'http://{self.owner.login}:{token}@{base}'
            f'/git/{self.owner.login}/{self.repo.name}.git', 'owned')
        self.assertEqual(proc.returncode, 0, proc.stderr)
