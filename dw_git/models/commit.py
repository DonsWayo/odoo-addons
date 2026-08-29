import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class GitCommit(models.Model):
    _name = 'git.commit'
    _inherit = ['git.task.link.mixin']
    _description = 'Git Commit'
    _order = 'committed_date desc'
    _rec_name = 'short_sha'

    sha = fields.Char(required=True, size=40, index=True)
    task_ids = fields.Many2many(
        'project.task', 'git_commit_task_rel', 'commit_id', 'task_id',
        string='Tasks', readonly=True,
        help="Tasks referenced by this commit's message, e.g. 'task-42'.")
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

    patch = fields.Text(
        compute='_compute_patch',
        help="Unified diff of this commit against its first parent.")

    def _compute_patch(self):
        """Read the commit's diff from the repository, on demand.

        Not stored: the text can be large, it never changes once the commit
        exists, and storing it would duplicate the object database for no
        gain. Computed rather than eager so that listing commits does not
        run one diff per row.

        _get_diff() has existed on this model since the beginning and
        nothing ever called it — the ability to show a commit's changes was
        written and never wired to anything, so every commit page showed a
        message and no code.
        """
        for commit in self:
            commit.patch = commit._get_diff() or ''


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

    #: git's canonical empty tree. Diffing a root commit against it is how
    #: git itself shows the first commit in a repository.
    EMPTY_TREE_SHA = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'

    def _get_diff(self, parent_sha=None):
        """Unified diff of this commit against its first parent.

        Parents come from GIT, not from parent_ids. That relation is an
        Odoo many2many which _sync_from_git never populates, so the
        previous implementation resolved no parent for any commit and
        returned an empty string every time — which is why the diff was
        empty rather than merely unused.

        A root commit has no parent and is diffed against the empty tree,
        the same way git shows the first commit in a repository.
        """
        self.ensure_one()
        try:
            import git
            repo = git.Repo(self.repository_id._get_repo_path())
            commit = repo.commit(self.sha)
            if parent_sha:
                base = parent_sha
            elif commit.parents:
                base = commit.parents[0].hexsha
            else:
                base = self.EMPTY_TREE_SHA
            return repo.git.diff(base, self.sha)
        except Exception:
            # a repository that is not on disk, or a sha that is not in it
            return ''

    @api.model_create_multi
    def create(self, vals_list):
        commits = super().create(vals_list)
        commits._link_referenced_tasks()
        return commits

    def _link_referenced_tasks(self):
        """Attach tasks named in the commit message, and say so on the task.

        Linking silently would make this an invisible feature: the value is
        that someone reading the task sees the code that touched it, so the
        link is posted to the task's chatter as well as stored.
        """
        for commit in self:
            refs = commit._extract_task_refs(commit.message)
            tasks = commit._resolve_tasks(refs)
            if not tasks:
                continue
            commit.task_ids = [(6, 0, tasks.ids)]
            for task in tasks:
                task.message_post(body=_(
                    "Referenced in commit %(sha)s of %(repo)s: %(message)s",
                    sha=commit.sha[:8],
                    repo=commit.repository_id.name,
                    message=commit.message.splitlines()[0] if commit.message else ''))
