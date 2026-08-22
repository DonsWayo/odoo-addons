# -*- coding: utf-8 -*-
import os
import tempfile
import shutil
from unittest.mock import patch, MagicMock

from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError, UserError


@tagged('post_install', '-at_install')
class TestGitRepository(TransactionCase):

    def setUp(self):
        super().setUp()
        self.user = self.env['res.users'].create({
            'name': 'Test User',
            'login': 'testuser',
            'email': 'test@example.com',
        })
        self.other_user = self.env['res.users'].create({
            'name': 'Other User',
            'login': 'otheruser',
            'email': 'other@example.com',
        })

    def test_repo_creation(self):
        repo = self.env['git.repository'].create({
            'name': 'test-repo',
            'owner_id': self.user.id,
            'visibility': 'private',
        })
        self.assertEqual(repo.name, 'test-repo')
        self.assertEqual(repo.default_branch, 'main')
        self.assertEqual(repo.owner_id, self.user)
        self.assertEqual(repo.visibility, 'private')

    def test_repo_name_validation(self):
        """Test repository name format validation"""
        with self.assertRaises(ValidationError):
            self.env['git.repository'].create({
                'name': 'invalid name',  # spaces not allowed
                'owner_id': self.user.id,
            })

        with self.assertRaises(ValidationError):
            self.env['git.repository'].create({
                'name': 'Test',  # uppercase not allowed at start
                'owner_id': self.user.id,
            })

        # Valid names
        for name in ['test-repo', 'test_repo', 'test.repo', 'testrepo', 't']:
            repo = self.env['git.repository'].create({
                'name': name,
                'owner_id': self.user.id,
            })
            self.assertEqual(repo.name, name)
            repo.unlink()

    def test_repo_name_unique_per_company(self):
        """Test unique constraint per company"""
        self.env['git.repository'].create({
            'name': 'test-repo',
            'owner_id': self.user.id,
        })
        with self.assertRaises(ValidationError):
            self.env['git.repository'].create({
                'name': 'test-repo',
                'owner_id': self.user.id,
            })

    def test_clone_urls(self):
        repo = self.env['git.repository'].create({
            'name': 'test-repo',
            'owner_id': self.user.id,
        })
        self.assertIn('testuser/test-repo.git', repo.clone_url_http)
        self.assertIn('git@', repo.clone_url_ssh)

    def test_star_toggle(self):
        repo = self.env['git.repository'].create({
            'name': 'test-repo',
            'owner_id': self.user.id,
        })
        self.assertFalse(repo.is_starred)
        self.assertEqual(repo.star_count, 0)

        repo.with_user(self.user).action_toggle_star()
        self.assertTrue(repo.is_starred)
        self.assertEqual(repo.star_count, 1)

        repo.with_user(self.user).action_toggle_star()
        self.assertFalse(repo.is_starred)
        self.assertEqual(repo.star_count, 0)

    def test_access_check(self):
        repo = self.env['git.repository'].create({
            'name': 'test-repo',
            'owner_id': self.user.id,
            'visibility': 'private',
        })
        # Owner has access
        self.assertTrue(repo._check_access(self.user, 'read'))
        self.assertTrue(repo._check_access(self.user, 'write'))

        # Other user no access
        self.assertFalse(repo._check_access(self.other_user, 'read'))

        # Add as member
        repo.member_ids = [(4, self.other_user.id)]
        self.assertTrue(repo._check_access(self.other_user, 'read'))
        self.assertTrue(repo._check_access(self.other_user, 'write'))

    def test_internal_visibility(self):
        repo = self.env['git.repository'].create({
            'name': 'test-repo',
            'owner_id': self.user.id,
            'visibility': 'internal',
        })
        # Internal user has read access
        self.assertTrue(repo._check_access(self.other_user, 'read'))
        self.assertFalse(repo._check_access(self.other_user, 'write'))

    def test_counters(self):
        repo = self.env['git.repository'].create({
            'name': 'test-repo',
            'owner_id': self.user.id,
        })
        self.assertEqual(repo.commit_count, 0)
        self.assertEqual(repo.branch_count, 0)
        self.assertEqual(repo.open_pr_count, 0)


@tagged('post_install', '-at_install')
class TestGitBranch(TransactionCase):

    def setUp(self):
        super().setUp()
        self.user = self.env['res.users'].create({
            'name': 'Test User',
            'login': 'testuser',
            'email': 'test@example.com',
        })
        self.repo = self.env['git.repository'].create({
            'name': 'test-repo',
            'owner_id': self.user.id,
        })

    def test_branch_creation(self):
        branch = self.env['git.branch'].create({
            'name': 'main',
            'repository_id': self.repo.id,
            'commit_sha': 'a' * 40,
        })
        self.assertEqual(branch.name, 'main')
        self.assertTrue(branch.is_default)

    def test_branch_unique_per_repo(self):
        self.env['git.branch'].create({
            'name': 'main',
            'repository_id': self.repo.id,
            'commit_sha': 'a' * 40,
        })
        with self.assertRaises(ValidationError):
            self.env['git.branch'].create({
                'name': 'main',
                'repository_id': self.repo.id,
                'commit_sha': 'b' * 40,
            })

    def test_branch_protection_push_check(self):
        branch = self.env['git.branch'].create({
            'name': 'protected',
            'repository_id': self.repo.id,
            'commit_sha': 'a' * 40,
            'is_protected': True,
        })
        # Protected branch - user cannot push
        self.assertFalse(branch.can_user_push(self.user))

        # Add user to allowed list
        branch.restricted_push_user_ids = [(4, self.user.id)]
        self.assertTrue(branch.can_user_push(self.user))

    def test_branch_protection_manager_bypass(self):
        branch = self.env['git.branch'].create({
            'name': 'protected',
            'repository_id': self.repo.id,
            'commit_sha': 'a' * 40,
            'is_protected': True,
        })
        # Manager can push
        manager = self.env['res.users'].create({
            'name': 'Manager',
            'login': 'manager',
            'email': 'manager@example.com',
            'groups_id': [(4, self.env.ref('git_hosting.group_git_manager').id)],
        })
        self.assertTrue(branch.can_user_push(manager))

    def test_branch_ahead_behind(self):
        branch = self.env['git.branch'].create({
            'name': 'feature',
            'repository_id': self.repo.id,
            'commit_sha': 'a' * 40,
        })
        # Without git repo, should be 0
        self.assertEqual(branch.ahead_commits, 0)
        self.assertEqual(branch.behind_commits, 0)


@tagged('post_install', '-at_install')
class TestGitCommit(TransactionCase):

    def setUp(self):
        super().setUp()
        self.user = self.env['res.users'].create({
            'name': 'Test User',
            'login': 'testuser',
            'email': 'test@example.com',
        })
        self.repo = self.env['git.repository'].create({
            'name': 'test-repo',
            'owner_id': self.user.id,
        })

    def test_commit_creation(self):
        commit = self.env['git.commit'].create({
            'sha': 'a' * 40,
            'message': 'Initial commit\n\nBody',
            'repository_id': self.repo.id,
        })
        self.assertEqual(commit.short_sha, 'a' * 8)
        self.assertEqual(commit.message_short, 'Initial commit')


@tagged('post_install', '-at_install')
class TestGitPullRequest(TransactionCase):

    def setUp(self):
        super().setUp()
        self.user = self.env['res.users'].create({
            'name': 'Test User',
            'login': 'testuser',
            'email': 'test@example.com',
        })
        self.repo = self.env['git.repository'].create({
            'name': 'test-repo',
            'owner_id': self.user.id,
        })
        self.main_branch = self.env['git.branch'].create({
            'name': 'main',
            'repository_id': self.repo.id,
            'commit_sha': 'a' * 40,
        })
        self.feature_branch = self.env['git.branch'].create({
            'name': 'feature',
            'repository_id': self.repo.id,
            'commit_sha': 'b' * 40,
        })

    def test_pr_creation(self):
        pr = self.env['git.pull_request'].create({
            'title': 'Add feature',
            'repository_id': self.repo.id,
            'source_branch_id': self.feature_branch.id,
            'target_branch_id': self.main_branch.id,
        })
        self.assertEqual(pr.title, 'Add feature')
        self.assertEqual(pr.state, 'draft')
        self.assertEqual(pr.number, 1)
        self.assertTrue(pr.name.startswith('#1:'))

    def test_pr_mergeable_no_conflicts(self):
        pr = self.env['git.pull_request'].create({
            'title': 'Add feature',
            'repository_id': self.repo.id,
            'source_branch_id': self.feature_branch.id,
            'target_branch_id': self.main_branch.id,
        })
        # Without actual git repo, _check_conflicts returns True (has conflicts)
        # But is_mergeable also checks target branch protection
        self.assertFalse(pr.is_mergeable)

    def test_pr_review_status(self):
        pr = self.env['git.pull_request'].create({
            'title': 'Add feature',
            'repository_id': self.repo.id,
            'source_branch_id': self.feature_branch.id,
            'target_branch_id': self.main_branch.id,
        })
        self.assertEqual(pr.approval_count, 0)
        self.assertFalse(pr.changes_requested)

        # Add approval
        self.env['git.pr.review'].create({
            'pull_request_id': pr.id,
            'reviewer_id': self.user.id,
            'state': 'approve',
        })
        self.assertEqual(pr.approval_count, 1)

        # Add changes requested
        self.env['git.pr.review'].create({
            'pull_request_id': pr.id,
            'reviewer_id': self.user.id,
            'state': 'request_changes',
        })
        self.assertTrue(pr.changes_requested)


@tagged('post_install', '-at_install')
class TestGitPAT(TransactionCase):

    def setUp(self):
        super().setUp()
        self.user = self.env['res.users'].create({
            'name': 'Test User',
            'login': 'testuser',
            'email': 'test@example.com',
        })
        self.repo = self.env['git.repository'].create({
            'name': 'test-repo',
            'owner_id': self.user.id,
        })

    def test_pat_creation_generates_token(self):
        pat = self.env['git.personal_access_token'].create({
            'name': 'Test Token',
            'user_id': self.user.id,
        })
        self.assertTrue(pat.token)
        self.assertEqual(len(pat.token), 43)  # token_urlsafe(32) = 43 chars
        self.assertTrue(pat.token_hash)

    def test_pat_verification(self):
        pat = self.env['git.personal_access_token'].create({
            'name': 'Test Token',
            'user_id': self.user.id,
        })
        raw_token = pat.token
        self.assertTrue(pat._verify_token(raw_token))
        self.assertFalse(pat._verify_token('wrong-token'))

    def test_pat_find_by_token(self):
        pat = self.env['git.personal_access_token'].create({
            'name': 'Test Token',
            'user_id': self.user.id,
        })
        found = self.env['git.personal_access_token'].find_by_token(pat.token)
        self.assertEqual(found, pat)

        # Wrong token
        found = self.env['git.personal_access_token'].find_by_token('wrong')
        self.assertFalse(found)

    def test_pat_expired(self):
        from datetime import date, timedelta
        pat = self.env['git.personal_access_token'].create({
            'name': 'Test Token',
            'user_id': self.user.id,
            'expires_at': date.today() - timedelta(days=1),
        })
        found = self.env['git.personal_access_token'].find_by_token(pat.token)
        self.assertFalse(found)


@tagged('post_install', '-at_install')
class TestGitDeployKey(TransactionCase):

    def setUp(self):
        super().setUp()
        self.user = self.env['res.users'].create({
            'name': 'Test User',
            'login': 'testuser',
            'email': 'test@example.com',
        })
        self.repo = self.env['git.repository'].create({
            'name': 'test-repo',
            'owner_id': self.user.id,
        })

    def test_deploy_key_creation(self):
        key = self.env['git.deploy_key'].create({
            'name': 'CI Key',
            'repository_id': self.repo.id,
            'can_push': True,
        })
        self.assertTrue(key.token)
        self.assertTrue(key.token_hash)
        self.assertTrue(key.can_push)

    def test_deploy_key_find_by_token(self):
        key = self.env['git.deploy_key'].create({
            'name': 'CI Key',
            'repository_id': self.repo.id,
        })
        found = self.env['git.deploy_key'].find_by_token(key.token)
        self.assertEqual(found, key)


@tagged('post_install', '-at_install')
class TestGitWebhook(TransactionCase):

    def setUp(self):
        super().setUp()
        self.user = self.env['res.users'].create({
            'name': 'Test User',
            'login': 'testuser',
            'email': 'test@example.com',
        })
        self.repo = self.env['git.repository'].create({
            'name': 'test-repo',
            'owner_id': self.user.id,
        })

    def test_webhook_creation(self):
        webhook = self.env['git.webhook'].create({
            'name': 'Test Webhook',
            'url': 'https://example.com/webhook',
            'repository_id': self.repo.id,
        })
        self.assertTrue(webhook.secret_token)
        self.assertTrue(webhook.event_push)
        self.assertTrue(webhook.event_pull_request)