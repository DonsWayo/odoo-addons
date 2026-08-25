"""UNIT tests — pure model logic. No HTTP, no filesystem git."""
import hashlib
from datetime import date, timedelta

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import DwGitCommon


@tagged('unit', 'post_install', '-at_install')
class TestRepositoryUnit(DwGitCommon):

    def _repo(self, name='unit-repo', **kw):
        return super()._repo(name=name, **kw)

    # -- creation & constraints --
    def test_create_defaults(self):
        r = self._repo()
        self.assertEqual(r.default_branch, 'main')
        self.assertEqual(r.visibility, 'private')

    def test_name_unique_per_owner(self):
        r = self._repo()
        fixed = r.name
        with self.assertRaises(Exception) as ctx:
            self.Repo.create({'name': fixed, 'owner_id': self.user.id})
            self.env.flush_all()
        self.assertTrue(isinstance(ctx.exception, ValidationError)
                        or 'unique' in str(ctx.exception).lower()
                        or 'duplicate' in str(ctx.exception).lower())

    def test_same_name_allowed_for_different_owners(self):
        """alice/web and bob/web live in different directories on disk and
        must be allowed to coexist (was blocked by company-wide uniqueness)."""
        r = self._repo()
        twin = self.Repo.create({'name': r.name, 'owner_id': self.other.id})
        self.env.flush_all()
        self.assertNotEqual(r._get_repo_path(), twin._get_repo_path())

    def test_invalid_names_rejected(self):
        with self.assertRaises(ValidationError):
            self._repo(name='has space')

    def test_valid_names_accepted(self):
        for ok in ('abc', 'a-b_c.d', 'x'):
            self.assertIn(ok, self._repo(name=ok).name)

    # -- access matrix --
    def test_owner_full_access(self):
        r = self._repo(visibility='private')
        self.assertTrue(r._check_repo_access(self.user, 'read'))
        self.assertTrue(r._check_repo_access(self.user, 'write'))

    def test_private_blocks_others(self):
        r = self._repo(visibility='private')
        self.assertFalse(r._check_repo_access(self.other, 'read'))
        self.assertFalse(r._check_repo_access(self.other, 'write'))

    def test_member_gets_rw(self):
        r = self._repo(visibility='private')
        r.member_ids = [(4, self.other.id)]
        self.assertTrue(r._check_repo_access(self.other, 'read'))
        self.assertTrue(r._check_repo_access(self.other, 'write'))

    def test_internal_readonly_for_employees(self):
        r = self._repo(visibility='internal')
        self.assertTrue(r._check_repo_access(self.other, 'read'))
        self.assertFalse(r._check_repo_access(self.other, 'write'))

    def test_manager_bypasses(self):
        mgr = self._create_user('mgr', groups=['dw_git.group_git_manager'])
        r = self._repo(visibility='private')
        self.assertTrue(r._check_repo_access(mgr, 'read'))
        self.assertTrue(r._check_repo_access(mgr, 'write'))

    def test_permissions_matrix_shape(self):
        r = self._repo(visibility='internal')
        self.assertEqual(r._get_user_permissions(self.other),
                         {'read': True, 'write': False, 'admin': False})
        self.assertTrue(all(r._get_user_permissions(self.user).values()))

    def test_portal_access_delegates_read(self):
        r = self._repo(visibility='private')
        self.assertFalse(r._check_portal_access(self.other))
        r.member_ids = [(4, self.other.id)]
        self.assertTrue(r._check_portal_access(self.other))

    # -- stars / counters / urls --
    def test_star_toggle_cycle(self):
        r = self._repo()
        # act as the (active) owner: env.user must be an active user,
        # __system__/uid-1 is inactive and gets filtered from m2m reads
        ru = r.with_user(self.user)
        ru.action_toggle_star()
        ru.invalidate_recordset(['is_starred', 'star_count'])
        self.assertEqual((ru.is_starred, ru.star_count), (True, 1))
        ru.action_toggle_star()
        ru.invalidate_recordset(['is_starred', 'star_count'])
        self.assertEqual((ru.is_starred, ru.star_count), (False, 0))

    def test_counters_zero_when_empty(self):
        r = self._repo()
        self.assertEqual((r.commit_count, r.branch_count, r.open_pr_count), (0, 0, 0))

    def test_clone_urls_computed(self):
        r = self._repo()
        r._compute_clone_urls()
        expected_path = f"/git/{self.user.login}/{r.name}.git"
        self.assertIn(expected_path, r.clone_url_http)
        self.assertIn(f"{self.user.login}/{r.name}.git", r.clone_url_ssh)


@tagged('unit', 'post_install', '-at_install')
class TestBranchUnit(DwGitCommon):

    def setUp(self):
        super().setUp()
        self.repo = self._repo('branch-unit')

    def test_main_is_default_flag(self):
        self.assertTrue(self._branch(self.repo, 'main').is_default)

    def test_duplicate_branch_rejected(self):
        self._branch(self.repo, 'dev')
        with self.assertRaises(Exception) as ctx:
            self._branch(self.repo, 'dev', sha='b' * 40)
            self.env.flush_all()
        self.assertTrue('unique' in str(ctx.exception).lower()
                        or 'duplicate' in str(ctx.exception).lower())

    def test_protected_branch_blocks_push(self):
        b = self._branch(self.repo, 'protected', is_protected=True)
        self.assertFalse(b.can_user_push(self.user))
        b.restricted_push_user_ids = [(4, self.user.id)]
        self.assertTrue(b.can_user_push(self.user))

    def test_unprotected_allows_all(self):
        b = self._branch(self.repo, 'open')
        self.assertTrue(b.can_user_push(self.user))
        self.assertTrue(b.can_user_merge(self.user))


@tagged('unit', 'post_install', '-at_install')
class TestTokenUnit(DwGitCommon):

    def test_pat_hash_roundtrip(self):
        pat = self.PAT.create({'name': 'ci', 'user_id': self.user.id})
        self.assertEqual(pat.token_hash,
                         hashlib.sha256(pat.token.encode()).hexdigest())

    def test_pat_find_by_token(self):
        pat = self.PAT.create({'name': 'ci', 'user_id': self.user.id})
        self.assertEqual(self.PAT.find_by_token(pat.token).id, pat.id)
        self.assertFalse(self.PAT.find_by_token('garbage'))

    def test_pat_revoked_rejected(self):
        pat = self.PAT.create({'name': 'ci', 'user_id': self.user.id})
        pat.action_revoke()
        self.assertFalse(self.PAT.find_by_token(pat.token))

    def test_pat_expired_rejected(self):
        pat = self.PAT.create({'name': 'ci', 'user_id': self.user.id,
                               'expires_at': date.today() - timedelta(days=1)})
        self.assertFalse(self.PAT.find_by_token(pat.token))

    def test_deploy_key_scoped_to_repo(self):
        repo = self._repo('dk-repo')
        key = self.DeployKey.create({'name': 'ci', 'repository_id': repo.id})
        found = self.DeployKey.find_by_token(key.token)
        self.assertEqual(found.repository_id.id, repo.id)


@tagged('unit', 'post_install', '-at_install')
class TestPullRequestUnit(DwGitCommon):

    def setUp(self):
        super().setUp()
        self.repo = self._repo('pr-unit')
        self.main = self._branch(self.repo, 'main')
        self.feat = self._branch(self.repo, 'feature', sha='b' * 40)

    def _pr(self, **kw):
        vals = {'title': 'T', 'repository_id': self.repo.id,
                'source_branch_id': self.feat.id,
                'target_branch_id': self.main.id}
        vals.update(kw)
        return self.PR.create(vals)

    def test_number_and_display_name(self):
        pr = self._pr(title='My change')
        self.assertTrue(pr.number >= 1)
        self.assertIn(str(pr.number), pr.name)

    def test_review_counts(self):
        pr = self._pr()
        Review = self.env['git.pr.review']
        Review.create({'pull_request_id': pr.id, 'state': 'approve'})
        Review.create({'pull_request_id': pr.id, 'state': 'comment'})
        self.assertEqual(pr.approval_count, 1)
        self.assertFalse(pr.changes_requested)
        Review.create({'pull_request_id': pr.id, 'state': 'request_changes'})
        self.assertTrue(pr.changes_requested)

    def test_close_reopen_lifecycle(self):
        pr = self._pr(state='open')
        pr.action_close()
        self.assertEqual(pr.state, 'closed')
        self.assertTrue(pr.closed_at)
        pr.action_reopen()
        self.assertEqual(pr.state, 'open')
        self.assertFalse(pr.closed_at)

    def test_merge_rejected_on_closed_pr(self):
        from odoo.exceptions import UserError
        pr = self._pr(state='closed')
        with self.assertRaises(UserError):
            pr.action_merge()

    def test_review_records_commit_sha(self):
        # seed the HEAD commit so the branch's stored compute can resolve it
        self.env['git.commit'].create({
            'sha': self.feat.commit_sha, 'message': 'head',
            'repository_id': self.repo.id})
        pr = self._pr()
        review = self.env['git.pr.review'].create({
            'pull_request_id': pr.id, 'state': 'approve'})
        self.assertEqual(review.commit_id.sha, self.feat.commit_sha)
