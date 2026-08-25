import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class GitCommit(models.Model):
    _name = 'git.commit'
    _description = 'Git Commit'
    _order = 'committed_date desc'
    _rec_name = 'short_sha'

    sha = fields.Char(required=True, size=40, index=True)
    short_sha = fields.Char(compute='_compute_short_sha', store=True, size=8)
    message = fields.Text()
    message_short = fields.Char(compute='_compute_message_short')

    # Author/Committer
    author_name = fields.Char()
    author_email = fields.Char()
    author_date = fields.Datetime()
    committer_name = fields.Char()
    committer_email = fields.Char()
    committed_date = fields.Datetime(index=True)

    # Relations
    repository_id = fields.Many2one('git.repository', required=True, ondelete='cascade', index=True)
    branch_ids = fields.Many2many('git.branch', 'git_commit_branch_rel', 'commit_id', 'branch_id', string='Branches')
    pull_request_id = fields.Many2one('git.pull_request', string='Pull Request')
    parent_ids = fields.Many2many('git.commit', 'git_commit_parent_rel', 'commit_id', 'parent_id', string='Parents')

    # Stats
    additions = fields.Integer()
    deletions = fields.Integer()
    files_changed = fields.Integer()

    # GPG Signature
    is_signed = fields.Boolean(default=False)
    signature = fields.Text()
    signature_verification = fields.Selection([
        ('none', 'No signature'),
        ('valid', 'Valid signature'),
        ('invalid', 'Invalid signature'),
        ('unknown', 'Unknown key'),
    ], default='none')

    @api.depends('sha')
    def _compute_short_sha(self):
        for commit in self:
            commit.short_sha = commit.sha[:8] if commit.sha else ''

    @api.depends('message')
    def _compute_message_short(self):
        for commit in self:
            commit.message_short = commit.message.split('\n')[0][:80] if commit.message else ''

    def _get_history(self, limit=50):
        """Get commit history for graph"""
        try:
            import git
            repo = git.Repo(self.repository_id._get_repo_path())
            commits = list(repo.iter_commits(self.sha, max_count=limit))
            return commits
        except Exception:
            return []

    def _get_diff(self, parent_sha=None):
        """Get diff against parent"""
        try:
            import git
            repo = git.Repo(self.repository_id._get_repo_path())
            parent = repo.commit(parent_sha) if parent_sha else (self.parent_ids[:1] and repo.commit(self.parent_ids[0].sha))
            if parent:
                return repo.git.diff(parent.sha, self.sha)
            return ''
        except Exception:
            return ''
