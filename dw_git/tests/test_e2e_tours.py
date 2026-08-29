"""E2E tests — full browser tours through the real web client."""
import itertools

from odoo.tests import HttpCase, tagged

_e2e_counter = itertools.count(1)


# post_install, not at_install. Odoo warns "HttpCase test should be in
# post_install only" and it is right: at_install runs before the JS asset
# bundles are generated, so this module's own widgets — the git_diff_viewer
# field and the file-browser client action — are not in web.assets_backend
# yet. Any view using them fails to render, and the tour times out waiting
# for .o_form_view on a form that never mounted. Every tour here was
# skipped for lack of Chrome, so the mis-tagging was never observable.
@tagged('e2e', 'post_install', '-at_install')
class TestDwGitUiE2E(HttpCase):
    """Browser-driven flows: login -> app menu -> repo CRUD -> views render."""

    def setUp(self):
        super().setUp()
        n = next(_e2e_counter)
        self.user = self.env['res.users'].create({
            'name': f'E2E User {n}', 'login': f'e2euser{n}', 'email': f'e2e{n}@t.com'})
        # Owned by the user the tour LOGS IN AS. The repositories action
        # sets context {'search_default_my_repos': 1}, and that filter is
        # [('owner_id', '=', uid)] — so a repository owned by anyone else is
        # filtered out of the list the moment it opens, and the tour asserted
        # against an empty list ("e2e-repo not in list"). The extra user is
        # kept as a member so the fixture still exercises membership.
        self.repo = self.env['git.repository'].create({
            'name': f'e2e-repo-{n}',
            'owner_id': self.env.ref('base.user_admin').id,
            'member_ids': [(4, self.user.id)],
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

        # The browser runs its HTTP requests through the same test cursor,
        # but reads the DATABASE, not this test's ORM cache. Records created
        # above live only in the cache until something flushes them, so the
        # webclient fetched an empty list and the form failed with
        # "records with IDs 1 cannot be found". Every tour here was skipped
        # for lack of Chrome, so this was never once observed.
        self.env.flush_all()

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


# post_install, not at_install. Odoo warns "HttpCase test should be in
# post_install only" and it is right: at_install runs before the JS asset
# bundles are generated, so this module's own widgets — the git_diff_viewer
# field and the file-browser client action — are not in web.assets_backend
# yet. Any view using them fails to render, and the tour times out waiting
# for .o_form_view on a form that never mounted. Every tour here was
# skipped for lack of Chrome, so the mis-tagging was never observable.
@tagged('e2e', 'post_install', '-at_install')
class TestDwGitDiffAndBrowserE2E(HttpCase):
    """Tours over the two views that render code.

    These need a repository with real git history behind them — a record
    with no bare repo produces an empty tree and an empty diff, which is
    precisely the state that made the UI look broken to a user. Building
    the repo for real is the point: the tour then proves the whole chain,
    from `git push` through the tree/blob routes to the rendered markup.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import os
        import shutil
        import subprocess
        import tempfile

        cls.base = tempfile.mkdtemp(prefix='dw-git-e2e-view-')
        cls.addClassCleanup(shutil.rmtree, cls.base, True)
        cls.env['ir.config_parameter'].sudo().set_param(
            'dw_git.repo_base_path', cls.base)

        owner = cls.env.ref('base.user_admin')
        cls.repo = cls.env['git.repository'].create({
            'name': 'e2e-viewer', 'owner_id': owner.id,
            'visibility': 'internal'})
        cls.repo._init_git_repo()

        work = tempfile.mkdtemp(prefix='dw-git-e2e-work-')
        cls.addClassCleanup(shutil.rmtree, work, True)
        bare = cls.repo._get_repo_path()

        def git(*args, cwd=work):
            subprocess.run(['git'] + list(args), cwd=cwd, check=True,
                           capture_output=True)

        def commit(msg, path, content):
            with open(os.path.join(work, path), 'w') as fh:
                fh.write(content)
            git('add', '-A')
            git('-c', 'user.email=e2e@t.com', '-c', 'user.name=E2E',
                'commit', '-qm', msg)

        subprocess.run(['git', 'clone', '-q', bare, work], check=True,
                       capture_output=True)
        git('symbolic-ref', 'HEAD', 'refs/heads/main')
        commit('Add greeter', 'greet.py',
               'def greet(name):\n    return f"Hello, {name}!"\n')
        git('push', '-q', 'origin', 'HEAD:refs/heads/main')
        main_sha = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=work,
                                  capture_output=True, text=True).stdout.strip()

        git('checkout', '-q', '-b', 'feature/validate')
        commit('Validate the name', 'greet.py',
               'def greet(name):\n'
               '    if not name:\n'
               '        raise ValueError("name is required")\n'
               '    return f"Hello, {name}!"\n')
        git('push', '-q', 'origin', 'HEAD:refs/heads/feature/validate')
        feat_sha = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=work,
                                  capture_output=True, text=True).stdout.strip()

        Branch = cls.env['git.branch']
        main_b = Branch.create({'name': 'main', 'repository_id': cls.repo.id,
                                'commit_sha': main_sha})
        feat_b = Branch.create({'name': 'feature/validate',
                                'repository_id': cls.repo.id,
                                'commit_sha': feat_sha})
        cls.pr = cls.env['git.pull_request'].create({
            'title': 'Validate the name', 'repository_id': cls.repo.id,
            'source_branch_id': feat_b.id, 'target_branch_id': main_b.id,
            'state': 'open', 'author_id': owner.id})
        cls.pr.action_refresh_changes()
        cls.env.flush_all()

    def test_06_pr_diff_renders(self):
        """The diff dialog shows coloured, readable diff markup."""
        self.assertTrue(
            self.pr.file_ids.filtered('patch'),
            'precondition: the PR must have a real patch to render')
        self.start_tour(
            f'/odoo/action-dw_git.action_git_pull_request/{self.pr.id}',
            'dw_git_pr_diff', login='admin')

    def test_09_pr_review_flow(self):
        """Pull request Reviews tab renders review rows and approval count."""
        # Create a review on the PR
        self.env['git.pr.review'].create({
            'pull_request_id': self.pr.id,
            'reviewer_id': self.env.ref('base.user_admin').id,
            'state': 'approve'
        })
        self.env.flush_all()
        # Open the PR form and tour through the Reviews tab
        self.start_tour(
            f'/odoo/action-dw_git.action_git_pull_request/{self.pr.id}',
            'dw_git_pr_review', login='admin')

    def test_08_commit_shows_its_changes(self):
        """A commit page shows real stats and a real diff."""
        # The class fixture pushes to the bare repo and creates the branch
        # records by hand; it never imports commits. Drive the real sync
        # here rather than manufacturing a git.commit record, so this also
        # exercises the path that populates the stats.
        self.repo._sync_from_git()
        self.env.flush_all()
        commit = self.env['git.commit'].search(
            [('repository_id', '=', self.repo.id)],
            order='committed_date desc', limit=1)
        self.assertTrue(commit, 'the sync must have imported a commit')
        self.assertTrue(
            commit.patch,
            'precondition: the commit must have a diff to render')
        self.assertTrue(
            commit.files_changed,
            'precondition: stats must be populated at sync')
        self.start_tour(
            f'/odoo/action-dw_git.action_git_commit/{commit.id}',
            'dw_git_commit_diff', login='admin')

    def test_07_file_browser_renders_highlighted_source(self):
        """Browse Files loads the tree and highlights a file."""
        self.start_tour(
            f'/odoo/action-dw_git.action_git_repository/{self.repo.id}',
            'dw_git_file_browser', login='admin')
