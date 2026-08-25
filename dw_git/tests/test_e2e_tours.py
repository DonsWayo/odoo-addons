"""E2E tests — full browser tours through the real web client."""
import itertools

from odoo.tests import HttpCase, tagged

_e2e_counter = itertools.count(1)


@tagged('e2e', 'at_install', '-post_install')
class TestDwGitUiE2E(HttpCase):
    """Browser-driven flows: login -> app menu -> repo CRUD -> views render."""

    def setUp(self):
        super().setUp()
        n = next(_e2e_counter)
        self.user = self.env['res.users'].create({
            'name': f'E2E User {n}', 'login': f'e2euser{n}', 'email': f'e2e{n}@t.com'})
        self.repo = self.env['git.repository'].create({
            'name': f'e2e-repo-{n}',
            'owner_id': self.user.id,
            'visibility': 'internal',
            'description': '<p>E2E demo repository</p>'})
        main = self.env['git.branch'].create({
            'name': 'main', 'repository_id': self.repo.id, 'commit_sha': 'a' * 40})
        feat = self.env['git.branch'].create({
            'name': 'feat', 'repository_id': self.repo.id, 'commit_sha': 'b' * 40})
        # the model is git.pull_request; this said git.pull.request and the
        # KeyError was swallowed, so the PR tour ran against a repo with no
        # pull requests and asserted nothing
        self.pr = self.env['git.pull_request'].create({
            'title': 'E2E PR', 'repository_id': self.repo.id,
            'source_branch_id': feat.id, 'target_branch_id': main.id,
            'state': 'open'})

    def test_01_repository_list_renders(self):
        """Action loads, list view renders with our repo row."""
        self.start_tour('/odoo/action-dw_git.action_git_repository',
                        'dw_git_repository_list', login='admin')

    def test_02_create_repo_via_ui(self):
        """Create a repository through the form view."""
        self.start_tour('/odoo/action-dw_git.action_git_repository',
                        'dw_git_create_repo', login='admin')

    def test_03_branches_tab_shows_records(self):
        """Open repo form, switch to Branches tab, see seeded branch."""
        self.start_tour(f'/odoo/action-dw_git.action_git_repository/{self.repo.id}',
                        'dw_git_branches_tab', login='admin')

    def test_04_pr_list_and_kanban_render(self):
        self.start_tour('/odoo/action-dw_git.action_git_pull_request',
                        'dw_git_pr_list', login='admin')

    def test_05_pat_lifecycle_via_ui(self):
        """PAT list renders and revoke button works."""
        self.env['git.personal_access_token'].create({
            'name': 'e2e-token', 'user_id': self.env.ref('base.user_admin').id})
        self.start_tour('/odoo/action-dw_git.action_git_personal_access_token',
                        'dw_git_pat_list', login='admin')
