"""Commits and pull requests linked to project tasks (#7).

git.repository.project_id existed, was filterable, and nothing read it —
the whole `project` dependency was carried for one dead field. These tests
cover the integration it was there for.
"""
from odoo.tests import tagged

from .common import DwGitCommon


@tagged('post_install', '-at_install')
class TestTaskReferenceParsing(DwGitCommon):
    """The reference syntax, in isolation."""

    def setUp(self):
        super().setUp()
        self.parser = self.env['git.commit']

    def _refs(self, text):
        return self.parser._extract_task_refs(text)

    def test_plain_reference(self):
        self.assertEqual(self._refs('fix the thing task-42'), {42: False})

    def test_hash_and_space_forms(self):
        for text in ('task#42', 'task 42', '#task-42', 'TASK-42'):
            self.assertIn(42, self._refs(text), text)

    def test_closing_keywords(self):
        for word in ('closes', 'closed', 'close', 'fixes', 'fixed', 'fix',
                     'resolves', 'resolved', 'resolve'):
            self.assertEqual(
                self._refs(f'{word} task-7'), {7: True},
                f'{word} should mark the reference as closing')

    def test_a_bare_number_is_not_a_task_reference(self):
        # Pull requests are numbered per repository and shown as "#5". A
        # bare number would mean "pull request 5" to a reader and "task 5"
        # to us, in the same sentence.
        self.assertEqual(self._refs('see #5 and 42'), {})

    def test_closing_wins_over_a_bare_mention_of_the_same_task(self):
        self.assertEqual(
            self._refs('touches task-9\n\nfixes task-9'), {9: True})

    def test_html_tags_do_not_split_a_reference(self):
        self.assertEqual(
            self._refs('<p>fixes <strong>task-3</strong></p>'), {3: True})

    def test_several_tasks_in_one_message(self):
        self.assertEqual(
            self._refs('task-1, fixes task-2'), {1: False, 2: True})


@tagged('post_install', '-at_install')
class TestCommitsLinkTasks(DwGitCommon):

    def setUp(self):
        super().setUp()
        self.repo = self._repo('task-link')
        self.project = self.env['project.project'].create({'name': 'P'})
        self.task = self.env['project.task'].create({
            'name': 'Do the thing', 'project_id': self.project.id})

    def _commit(self, message, sha='a' * 40):
        return self.env['git.commit'].create({
            'sha': sha, 'message': message, 'repository_id': self.repo.id,
            'author_name': 'A', 'author_email': 'a@b.c'})

    def test_a_commit_links_the_task_it_names(self):
        commit = self._commit(f'work on task-{self.task.id}')
        self.assertIn(self.task, commit.task_ids)

    def test_the_task_is_told_about_it(self):
        before = len(self.task.message_ids)
        self._commit(f'work on task-{self.task.id}')
        self.assertGreater(
            len(self.task.message_ids), before,
            'the point of the link is that someone reading the TASK sees '
            'the code, so it must be posted there')

    def test_an_unknown_task_id_is_ignored(self):
        commit = self._commit('fixes task-99999999')
        self.assertFalse(commit.task_ids)

    def test_a_commit_with_no_reference_links_nothing(self):
        self.assertFalse(self._commit('routine tidy-up').task_ids)

    def test_the_task_can_see_the_commit_back(self):
        commit = self._commit(f'task-{self.task.id}')
        self.assertIn(commit, self.task.git_commit_ids)
        self.assertEqual(self.task.git_commit_count, 1)


@tagged('post_install', '-at_install')
class TestPullRequestsLinkAndCloseTasks(DwGitCommon):

    def setUp(self):
        super().setUp()
        self.repo = self._repo('pr-task-link')
        self.project = self.env['project.project'].create({'name': 'PP'})
        self.done = self.env['project.task.type'].create({
            'name': 'Done', 'fold': True,
            'project_ids': [(4, self.project.id)]})
        self.task = self.env['project.task'].create({
            'name': 'Ship it', 'project_id': self.project.id})
        self.main = self.Branch.create({
            'name': 'main', 'repository_id': self.repo.id,
            'commit_sha': 'a' * 40})
        self.feature = self.Branch.create({
            'name': 'feature', 'repository_id': self.repo.id,
            'commit_sha': 'b' * 40})

    def _pr(self, title='change', description=False):
        return self.PR.create({
            'title': title, 'description': description,
            'repository_id': self.repo.id,
            'source_branch_id': self.feature.id,
            'target_branch_id': self.main.id, 'state': 'open'})

    def test_a_title_reference_links_the_task(self):
        pr = self._pr(title=f'Rework auth (task-{self.task.id})')
        self.assertIn(self.task, pr.task_ids)

    def test_a_description_reference_links_the_task(self):
        pr = self._pr(description=f'<p>fixes task-{self.task.id}</p>')
        self.assertIn(self.task, pr.task_ids)

    def test_editing_the_description_later_links_the_task(self):
        pr = self._pr()
        self.assertFalse(pr.task_ids)
        pr.write({'description': f'<p>fixes task-{self.task.id}</p>'})
        self.assertIn(
            self.task, pr.task_ids,
            'the feature must not depend on getting the wording right '
            'the first time')

    def test_the_task_can_see_the_pull_request_back(self):
        pr = self._pr(title=f'task-{self.task.id}')
        self.assertIn(pr, self.task.git_pr_ids)
        self.assertEqual(self.task.git_pr_count, 1)

    def test_a_closing_reference_closes_the_task_on_merge(self):
        pr = self._pr(title=f'fixes task-{self.task.id}')
        pr._close_referenced_tasks()
        self.assertEqual(
            self.task.stage_id, self.done,
            'a pull request saying it fixes a task should close it')

    def test_a_bare_reference_does_not_close_the_task(self):
        pr = self._pr(title=f'touches task-{self.task.id}')
        before = self.task.stage_id
        pr._close_referenced_tasks()
        self.assertEqual(
            self.task.stage_id, before,
            'mentioning a task is not the same as finishing it')

    def test_a_project_with_no_closing_stage_leaves_the_task_alone(self):
        other = self.env['project.project'].create({'name': 'No Done'})
        self.env['project.task.type'].search([
            ('project_ids', 'in', other.id), ('fold', '=', True)]).write(
                {'project_ids': [(3, other.id)]})
        task = self.env['project.task'].create({
            'name': 'orphan', 'project_id': other.id})
        pr = self._pr(title=f'fixes task-{task.id}')
        before = task.stage_id
        messages = len(task.message_ids)
        pr._close_referenced_tasks()
        self.assertEqual(
            task.stage_id, before,
            'better to leave the task where it is than park it in the '
            'wrong column')
        self.assertGreater(
            len(task.message_ids), messages,
            'and to say so, rather than do nothing silently')
