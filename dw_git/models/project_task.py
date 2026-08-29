"""project.task, extended to see the code that touched it."""
from odoo import api, fields, models


class ProjectTask(models.Model):
    _inherit = 'project.task'

    git_commit_ids = fields.Many2many(
        'git.commit', 'git_commit_task_rel', 'task_id', 'commit_id',
        string='Git Commits', readonly=True)
    git_pr_ids = fields.Many2many(
        'git.pull_request', 'git_pr_task_rel', 'task_id', 'pr_id',
        string='Git Pull Requests', readonly=True)

    git_commit_count = fields.Integer(compute='_compute_git_counts')
    git_pr_count = fields.Integer(compute='_compute_git_counts')

    @api.depends('git_commit_ids', 'git_pr_ids')
    def _compute_git_counts(self):
        # Counted through the current user's own access, not sudo(): a
        # count is information, and a task should not reveal that work
        # exists in a repository the reader cannot open.
        for task in self:
            task.git_commit_count = len(task.git_commit_ids)
            task.git_pr_count = len(task.git_pr_ids)
