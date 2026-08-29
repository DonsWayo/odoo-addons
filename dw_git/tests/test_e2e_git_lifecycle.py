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

    def test_merge_deletes_head_ref_without_poisoning_the_transaction(self):
        """Regression: auto_delete_head_branch broke the merge notification.

        The cleanup called `source_branch_id.unlink()`. That branch is
        pinned by this very PR's `source_branch_id`, which is
        `required=True` and therefore `ondelete='restrict'`, so the DELETE
        always failed. It was wrapped in `except Exception: pass`, but in
        PostgreSQL a failed statement aborts the transaction — swallowing
        the Python exception does not revive it. The very next statement,
        `env.ref()` for the merge mail template, then died on a plain
        SELECT with InFailedSqlTransaction.

        Observable result: merge reports success, no branch is deleted, no
        mail is sent, and only a log line records it.

        Asserted here: the ref is gone from the bare repo, the branch
        record survives (the PR's history points at it), and the cursor is
        still usable afterwards — the last being the part that regressed.
        """
        self.assertTrue(self.repo.auto_delete_head_branch,
                        'precondition: the setting defaults on')

        clone = os.path.join(self.work, 'delhead-clone')
        self._git_http('clone', '-q', self._remote(), clone)
        self._write_commit(clone, 'base.py', 'x = 1\n', 'base')
        self._git_http('push', '-q', 'origin', 'HEAD:refs/heads/main',
                       cwd=clone)
        self._git('checkout', '-q', '-b', 'doomed', cwd=clone)
        self._write_commit(clone, 'f.txt', 'y\n', 'feature')
        self._git_http('push', '-q', 'origin', 'HEAD:refs/heads/doomed',
                       cwd=clone)

        self.env.invalidate_all()
        Branch = self.env['git.branch']
        main = Branch.search([('repository_id', '=', self.repo.id),
                              ('name', '=', 'main')])
        doomed = Branch.search([('repository_id', '=', self.repo.id),
                                ('name', '=', 'doomed')])
        self.assertTrue(main and doomed)
        self.assertIn('doomed', self._bare().heads,
                      'precondition: the ref exists before the merge')

        pr = self.env['git.pull_request'].create({
            'title': 'Delete my head branch',
            'repository_id': self.repo.id,
            'source_branch_id': doomed.id,
            'target_branch_id': main.id,
            'author_id': self.dev.id,
            'state': 'open',
        })
        pr.with_user(self.dev).action_merge()
        self.assertEqual(pr.state, 'merged')

        # 1. the ref is actually gone from disk — the cleanup that was
        #    advertised and never once happened
        self.assertNotIn(
            'doomed', [h.name for h in self._bare().heads],
            'auto_delete_head_branch did not remove the ref')

        # 2. the record survives: the merged PR still refers to it
        self.assertTrue(doomed.exists(),
                        'the branch record backs the PR history')
        self.assertEqual(pr.source_branch_id, doomed)

        # 3. the transaction is still usable. Under the old code this
        #    raised InFailedSqlTransaction, which is what silently killed
        #    the merge notification.
        self.env.cr.execute('SELECT 1')
        self.assertEqual(self.env.cr.fetchone()[0], 1)
        self.assertTrue(
            self.env.ref('dw_git.mail_template_git_pr_merged',
                         raise_if_not_found=False),
            'the merge mail template must still be resolvable')

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


@tagged('e2e', 'post_install', '-at_install')
class TestDeactivatedUsersLoseTransportAccess(HttpCase):
    """A deactivated user must not be able to clone or push.

    _check_repo_access is documented as the only gate on every path that
    runs under sudo() — the git transport, PAT and deploy-key
    authentication, and the portal. It checked ownership, membership,
    groups and company, and never checked whether the user was still
    ACTIVE. Deactivating someone removes their session and their record
    access, but their personal access token kept working over Smart HTTP,
    which is precisely the layer that bypasses record rules.

    The store listing says "Deactivate the user and it is gone." These
    tests are what make that sentence true.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.base_path = tempfile.mkdtemp(prefix='dw_git_deactivated_')
        cls.addClassCleanup(shutil.rmtree, cls.base_path, ignore_errors=True)
        cls.env['ir.config_parameter'].sudo().set_param(
            'dw_git.repo_base_path', cls.base_path)

        cls.user = cls.env['res.users'].create({
            'name': 'Soon Gone', 'login': 'soon-gone',
            'email': 'sg@lc.test'})
        cls.pat = cls.env['git.personal_access_token'].create({
            'name': 'sg token', 'user_id': cls.user.id, 'scopes': 'write'})
        cls.token = cls.pat.token
        cls.repo = cls.env['git.repository'].create({
            'name': 'deact-repo', 'owner_id': cls.user.id,
            'visibility': 'private', 'default_branch': 'main'})
        cls.repo._init_git_repo()

    def setUp(self):
        super().setUp()
        self.work = tempfile.mkdtemp(prefix='dw_git_deact_work_')
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)

    def _clone(self, target):
        base = self.base_url().replace('http://', '')
        url = (f'http://{self.user.login}:{self.token}@{base}'
               f'/git/{self.user.login}/{self.repo.name}.git')
        env = dict(os.environ, GIT_TERMINAL_PROMPT='0',
                   GIT_CONFIG_NOSYSTEM='1', HOME=self.work)
        with self.allow_requests():
            header = (f'http.extraHeader=Cookie: '
                      f'{TEST_CURSOR_COOKIE_NAME}={self.http_request_key}')
            return subprocess.run(
                ['git', '-c', header, 'clone', '-q', url,
                 os.path.join(self.work, target)],
                env=env, capture_output=True, text=True, timeout=120)

    def test_an_active_user_can_clone(self):
        proc = self._clone('active-clone')
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_a_deactivated_user_cannot_clone(self):
        self.user.write({'active': False})
        self.env.flush_all()
        proc = self._clone('inactive-clone')
        self.assertNotEqual(
            proc.returncode, 0,
            "a deactivated user's PAT still cloned over Smart HTTP")

    def test_check_repo_access_refuses_a_deactivated_user(self):
        self.assertTrue(self.repo._check_repo_access(self.user, 'read'))
        self.user.write({'active': False})
        self.env.flush_all()
        self.assertFalse(
            self.repo._check_repo_access(self.user, 'read'),
            'the only gate on the sudo() paths must refuse inactive users')

    def test_find_by_token_refuses_a_deactivated_users_token(self):
        self.user.write({'active': False})
        self.env.flush_all()
        found = self.env['git.personal_access_token'].sudo().find_by_token(
            self.token)
        self.assertFalse(
            found, "a deactivated user's token must not resolve")


@tagged('e2e', 'git_lifecycle', 'post_install', '-at_install')
class TestDeployKeyTransportAuthorisation(HttpCase):
    """`_identity_for_token()` resolves a deploy key to `repository.owner_id`
    — a HIGHER-privilege identity than the key itself, gated on
    `deploy_key.can_push`. That code path had never been driven through a
    real `git clone` / `git push` HTTP round trip; only the model-level
    lookup (`find_by_token`) and record rules had coverage. Proven here the
    same way `TestGitTransportAuthorisation` proves the PAT path: with a
    real `git` binary against the live test server.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.base_path = tempfile.mkdtemp(prefix='dw_git_deploykey_')
        cls.addClassCleanup(shutil.rmtree, cls.base_path, ignore_errors=True)
        cls.env['ir.config_parameter'].sudo().set_param(
            'dw_git.repo_base_path', cls.base_path)

        cls.owner = cls.env['res.users'].create({
            'name': 'DK Owner', 'login': 'dk-owner', 'email': 'dko@lc.test'})
        cls.repo_a = cls.env['git.repository'].create({
            'name': 'dk-repo-a', 'owner_id': cls.owner.id,
            'visibility': 'private'})
        cls.repo_a._init_git_repo()

        cls.other_owner = cls.env['res.users'].create({
            'name': 'DK Other Owner', 'login': 'dk-other-owner',
            'email': 'dko2@lc.test'})
        cls.repo_b = cls.env['git.repository'].create({
            'name': 'dk-repo-b', 'owner_id': cls.other_owner.id,
            'visibility': 'private'})
        cls.repo_b._init_git_repo()

        cls.readonly_key = cls.env['git.deploy_key'].create({
            'name': 'ci readonly', 'repository_id': cls.repo_a.id,
            'can_push': False}).token
        cls.push_key = cls.env['git.deploy_key'].create({
            'name': 'ci push', 'repository_id': cls.repo_a.id,
            'can_push': True}).token
        assert cls.readonly_key and cls.push_key, \
            'deploy key creation did not surface a raw token'

    def setUp(self):
        super().setUp()
        self.work = tempfile.mkdtemp(prefix='dw_git_deploykey_work_')
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)

    # ------------------------------------------------------------------
    # helpers — same pattern as TestGitTransportAuthorisation._clone /
    # TestGitLifecycleOverHttp._git_http, adapted for deploy-key Basic auth
    # (the username half is ignored server-side; only the password/secret
    # after ':' is looked up as a token).
    # ------------------------------------------------------------------
    def _url(self, secret, owner_login, repo_name):
        base = self.base_url().replace('http://', '')
        return (f'http://deploy-key:{secret}@{base}'
                f'/git/{owner_login}/{repo_name}.git')

    def _run_git(self, args, cwd=None):
        env = dict(os.environ, GIT_TERMINAL_PROMPT='0',
                    GIT_CONFIG_NOSYSTEM='1', HOME=self.work,
                    GIT_AUTHOR_NAME='CI Deploy Key',
                    GIT_AUTHOR_EMAIL='ci@deploykey.test',
                    GIT_COMMITTER_NAME='CI Deploy Key',
                    GIT_COMMITTER_EMAIL='ci@deploykey.test')
        return subprocess.run(['git', *args], cwd=cwd or self.work,
                              env=env, capture_output=True, text=True,
                              timeout=120)

    def _git_http(self, *args, cwd=None):
        """Run a git command against the live test server, cookie attached
        so the request is not refused for the wrong reason (see the sibling
        classes in this file for why this cookie is required)."""
        with self.allow_requests():
            header = (f'http.extraHeader=Cookie: '
                      f'{TEST_CURSOR_COOKIE_NAME}={self.http_request_key}')
            return self._run_git(['-c', header, *args], cwd)

    def _git(self, *args, cwd=None):
        proc = self._run_git(list(args), cwd)
        if proc.returncode != 0:
            self.fail(f"git {' '.join(args)} failed ({proc.returncode})\n"
                      f"stdout: {proc.stdout}\nstderr: {proc.stderr}")
        return proc

    def _write_commit(self, clone, filename, content, message):
        with open(os.path.join(clone, filename), 'w') as fh:
            fh.write(content)
        self._git('add', filename, cwd=clone)
        self._git('commit', '-qm', message, cwd=clone)
        return self._git('rev-parse', 'HEAD', cwd=clone).stdout.strip()

    def _bare(self, repository):
        import git
        return git.Repo(repository._get_repo_path())

    # ------------------------------------------------------------------
    # 1. read-only deploy key can clone its own repository
    # ------------------------------------------------------------------
    def test_readonly_deploy_key_can_clone_its_own_repo(self):
        proc = self._git_http(
            'clone', '-q', self._url(
                self.readonly_key, self.owner.login, self.repo_a.name),
            os.path.join(self.work, 'ro-clone'))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(os.path.isdir(
            os.path.join(self.work, 'ro-clone', '.git')))

    # ------------------------------------------------------------------
    # 2. read-only deploy key is refused on push
    # ------------------------------------------------------------------
    def test_readonly_deploy_key_cannot_push(self):
        clone = os.path.join(self.work, 'ro-push-clone')
        self._git_http(
            'clone', '-q',
            self._url(self.readonly_key, self.owner.login, self.repo_a.name),
            clone)
        self._write_commit(clone, 'nope.txt', 'x\n', 'should not land')

        # Snapshot the refs BEFORE pushing rather than asserting the bare
        # repo is empty afterwards. The bare repo is created once in
        # setUpClass and lives on the filesystem: Odoo rolls the database
        # back between tests, but nothing rolls back refs/heads. The
        # sibling test that legitimately pushes sorts earlier
        # alphabetically, so by the time this runs `main` already exists
        # through no fault of this push. Only movement proves a leak.
        before = {h.name: h.commit.hexsha for h in self._bare(self.repo_a).heads}

        proc = self._git_http(
            'push', '-q', 'origin', 'HEAD:refs/heads/main', cwd=clone)
        self.assertNotEqual(
            proc.returncode, 0,
            "a read-only deploy key (can_push=False) was able to push")
        # refused by Git Hosting, not by the test server's cookie gate
        self.assertNotIn('400', proc.stderr, proc.stderr)

        # the bare repo on disk never advanced
        after = {h.name: h.commit.hexsha for h in self._bare(self.repo_a).heads}
        self.assertEqual(
            before, after,
            'a read-only deploy key moved a ref in the bare repository')

    # ------------------------------------------------------------------
    # 3. push-capable deploy key can push, and it lands in Odoo
    # ------------------------------------------------------------------
    def test_push_deploy_key_can_push_and_syncs_into_odoo(self):
        clone = os.path.join(self.work, 'push-clone')
        self._git_http(
            'clone', '-q',
            self._url(self.push_key, self.owner.login, self.repo_a.name),
            clone)

        sha = self._write_commit(clone, 'README.md', '# ci\n',
                                 'deploy key push')
        self._git_http(
            'push', '-q', 'origin', 'HEAD:refs/heads/main', cwd=clone)

        # the bare repo really advanced
        self.assertEqual(self._bare(self.repo_a).heads.main.commit.hexsha,
                         sha)

        # ...and the push hook mirrored it into Odoo
        self.env.invalidate_all()
        branch = self.env['git.branch'].search([
            ('repository_id', '=', self.repo_a.id), ('name', '=', 'main')])
        self.assertTrue(branch, 'branch pushed via deploy key was not synced')
        self.assertEqual(branch.commit_sha, sha)

    # ------------------------------------------------------------------
    # 4. a deploy key scoped to repo A cannot clone or push repo B, even
    #    though the identity it would resolve to is a HIGHER-privilege one
    #    (the repository owner) than the key holder should ever obtain.
    # ------------------------------------------------------------------
    def test_deploy_key_cannot_clone_a_different_repository(self):
        proc = self._git_http(
            'clone', '-q',
            self._url(self.readonly_key, self.other_owner.login,
                      self.repo_b.name),
            os.path.join(self.work, 'wrong-repo-clone'))
        self.assertNotEqual(
            proc.returncode, 0,
            "a deploy key scoped to repo A cloned repo B")
        self.assertNotIn('400', proc.stderr, proc.stderr)

    def test_deploy_key_cannot_push_a_different_repository(self):
        # clone repo B legitimately first (as its own owner would, over the
        # session), so there is a local clone to attempt the push from.
        legit_clone = os.path.join(self.work, 'repo-b-legit')
        self._git(
            'clone', '-q', self.repo_b._get_repo_path(), legit_clone)
        self._write_commit(legit_clone, 'intrusion.txt', 'x\n',
                           'pushed with repo A\'s deploy key')

        self._git('remote', 'set-url', 'origin',
                  self._url(self.push_key, self.other_owner.login,
                            self.repo_b.name), cwd=legit_clone)
        proc = self._git_http(
            'push', '-q', 'origin', 'HEAD:refs/heads/main', cwd=legit_clone)
        self.assertNotEqual(
            proc.returncode, 0,
            "a deploy key scoped to repo A pushed to repo B, using the "
            "identity it resolved to (repo B's own owner)")

        bare_b = self._bare(self.repo_b)
        self.assertNotIn(
            'main', [h.name for h in bare_b.heads],
            "the foreign deploy key's push landed in repo B")


@tagged('e2e', 'post_install', '-at_install')
class TestPortalCollaboratorsCannotReachTheTransport(HttpCase):
    """Portal access must stop at the portal (#21).

    A portal collaborator is an external person — a customer looking at a
    pull request. `_check_repo_access` is the gate on the git transport,
    the JSON-RPC API, and PAT and deploy-key authentication, and every one
    of those callers asks it the same question with operation='read'. So
    putting portal collaborators into THAT method would have handed them
    `git clone` over Smart HTTP and the whole API along with the web page.

    portal_member_ids is therefore consulted only by _check_portal_access.
    These tests are what hold the two apart.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.base_path = tempfile.mkdtemp(prefix='dw_git_portal_')
        cls.addClassCleanup(shutil.rmtree, cls.base_path, ignore_errors=True)
        cls.env['ir.config_parameter'].sudo().set_param(
            'dw_git.repo_base_path', cls.base_path)

        cls.owner = cls.env['res.users'].create({
            'name': 'Portal Repo Owner', 'login': 'portal-owner',
            'email': 'po@lc.test'})
        cls.customer = cls.env['res.users'].create({
            'name': 'A Customer', 'login': 'portal-customer',
            'email': 'pc@lc.test',
            'group_ids': [(6, 0, [cls.env.ref('base.group_portal').id])]})
        cls.repo = cls.env['git.repository'].create({
            'name': 'portal-repo', 'owner_id': cls.owner.id,
            'visibility': 'private', 'default_branch': 'main',
            'portal_member_ids': [(4, cls.customer.id)]})
        cls.repo._init_git_repo()
        cls.pat = cls.env['git.personal_access_token'].create({
            'name': 'customer token', 'user_id': cls.customer.id,
            'scopes': 'read'})
        cls.token = cls.pat.token

    def setUp(self):
        super().setUp()
        self.work = tempfile.mkdtemp(prefix='dw_git_portal_work_')
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)

    def test_the_customer_is_really_a_portal_user(self):
        self.assertTrue(
            self.customer.share,
            'precondition: the fixture must be a portal user, not an employee')

    def test_a_portal_collaborator_may_read_the_portal_page(self):
        self.assertTrue(
            self.repo._check_portal_access(self.customer),
            'the whole point of #21 is that this now works')

    def test_a_portal_collaborator_is_refused_by_the_transport_gate(self):
        self.assertFalse(
            self.repo._check_repo_access(self.customer, 'read'),
            'portal_member_ids must not be visible to _check_repo_access — '
            'that gate gates git clone and the JSON-RPC API')
        self.assertFalse(
            self.repo._check_repo_access(self.customer, 'write'))

    def test_a_portal_collaborator_cannot_clone_over_smart_http(self):
        base = self.base_url().replace('http://', '')
        url = (f'http://{self.customer.login}:{self.token}@{base}'
               f'/git/{self.owner.login}/{self.repo.name}.git')
        env = dict(os.environ, GIT_TERMINAL_PROMPT='0',
                   GIT_CONFIG_NOSYSTEM='1', HOME=self.work)
        with self.allow_requests():
            header = (f'http.extraHeader=Cookie: '
                      f'{TEST_CURSOR_COOKIE_NAME}={self.http_request_key}')
            proc = subprocess.run(
                ['git', '-c', header, 'clone', '-q', url,
                 os.path.join(self.work, 'stolen')],
                env=env, capture_output=True, text=True, timeout=120)
        self.assertNotEqual(
            proc.returncode, 0,
            'a portal collaborator cloned the source tree over Smart HTTP')
        self.assertFalse(
            os.path.isdir(os.path.join(self.work, 'stolen', '.git')))

    def test_a_portal_user_who_is_not_a_collaborator_gets_nothing(self):
        stranger = self.env['res.users'].create({
            'name': 'Other Customer', 'login': 'portal-stranger',
            'email': 'ps@lc.test',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])]})
        self.assertFalse(self.repo._check_portal_access(stranger))
        self.assertFalse(self.repo._check_repo_access(stranger, 'read'))

    def test_a_deactivated_portal_collaborator_loses_the_portal_too(self):
        self.customer.write({'active': False})
        self.env.flush_all()
        self.assertFalse(
            self.repo._check_portal_access(self.customer),
            'deactivation must revoke portal access as well')
