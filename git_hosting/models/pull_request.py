# -*- coding: utf-8 -*-
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class GitPullRequest(models.Model):
    _name = 'git.pull_request'
    _description = 'Pull Request'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _order = 'create_date desc'

    number = fields.Integer(
        string='PR Number',
        readonly=True,
        copy=False,
        default=lambda self: self.env['ir.sequence'].next_by_code('git.pull.request') or 1
    )
    name = fields.Char(compute='_compute_name', store=True)

    title = fields.Char(required=True, tracking=True)
    description = fields.Html()
    state = fields.Selection([
        ('draft', 'Draft'),
        ('open', 'Open'),
        ('merged', 'Merged'),
        ('closed', 'Closed'),
    ], default='draft', tracking=True, index=True)

    # === Branches ===
    repository_id = fields.Many2one(
        'git.repository',
        required=True,
        ondelete='cascade',
        index=True
    )
    source_branch_id = fields.Many2one(
        'git.branch',
        string='Source Branch',
        required=True,
        domain="[('repository_id', '=', repository_id)]"
    )
    target_branch_id = fields.Many2one(
        'git.branch',
        string='Target Branch',
        required=True,
        domain="[('repository_id', '=', repository_id)]"
    )

    # === People ===
    author_id = fields.Many2one(
        'res.users',
        string='Author',
        required=True,
        default=lambda self: self.env.user,
        tracking=True
    )
    assignee_ids = fields.Many2many('res.users', string='Assignees')
    reviewer_ids = fields.Many2many('res.users', string='Reviewers')
    merged_by_id = fields.Many2one('res.users', string='Merged By')

    # === Commits & Changes ===
    commit_ids = fields.One2many('git.commit', 'pull_request_id', string='Commits')
    commit_count = fields.Integer(compute='_compute_commit_count')
    file_ids = fields.One2many('git.pr.file', 'pull_request_id', string='Changed Files')
    additions = fields.Integer(compute='_compute_stats')
    deletions = fields.Integer(compute='_compute_stats')
    changed_files = fields.Integer(compute='_compute_stats')

    # === Merge Info ===
    merge_method = fields.Selection([
        ('merge', 'Merge commit'),
        ('squash', 'Squash and merge'),
        ('rebase', 'Rebase and merge'),
    ], default='merge')
    merge_commit_sha = fields.Char()
    is_mergeable = fields.Boolean(compute='_compute_mergeable', store=True)
    has_conflicts = fields.Boolean(compute='_compute_mergeable', store=True)

    # === Reviews ===
    review_ids = fields.One2many('git.pr.review', 'pull_request_id', string='Reviews')
    approval_count = fields.Integer(compute='_compute_review_status')
    changes_requested = fields.Boolean(compute='_compute_review_status')

    # === CI/CD Checks ===
    check_run_ids = fields.One2many('git.check_run', 'pull_request_id', string='Check Runs')
    all_checks_passed = fields.Boolean(compute='_compute_checks')
    required_checks_passed = fields.Boolean(compute='_compute_checks')

    # === Dates ===
    merged_at = fields.Datetime()
    closed_at = fields.Datetime()

    @api.depends('number', 'title')
    def _compute_name(self):
        for pr in self:
            pr.name = f"#{pr.number}: {pr.title}" if pr.number else pr.title

    @api.depends('commit_ids')
    def _compute_commit_count(self):
        for pr in self:
            pr.commit_count = len(pr.commit_ids)

    @api.depends('file_ids.additions', 'file_ids.deletions')
    def _compute_stats(self):
        for pr in self:
            pr.additions = sum(pr.file_ids.mapped('additions'))
            pr.deletions = sum(pr.file_ids.mapped('deletions'))
            pr.changed_files = len(pr.file_ids)

    def _compute_mergeable(self):
        """Check if PR can be merged (no conflicts, target branch not protected, etc.)"""
        for pr in self:
            pr.has_conflicts = pr._check_conflicts()
            target = pr.target_branch_id
            can_merge = True
            if target.is_protected:
                if target.require_pr_reviews:
                    if pr.approval_count < target.required_approving_reviews:
                        can_merge = False
                if target.require_status_checks:
                    if not pr.required_checks_passed:
                        can_merge = False
            pr.is_mergeable = can_merge and not pr.has_conflicts

    def _check_conflicts(self):
        """Check for merge conflicts using git"""
        try:
            import git
            repo = git.Repo(self.repository_id._get_repo_path())
            repo.git.merge_tree(self.target_branch_id.commit_sha, self.source_branch_id.commit_sha)
            return False
        except Exception:
            return True

    @api.depends('review_ids.state')
    def _compute_review_status(self):
        for pr in self:
            approvals = pr.review_ids.filtered(lambda r: r.state == 'approve')
            changes = pr.review_ids.filtered(lambda r: r.state == 'request_changes')
            pr.approval_count = len(approvals)
            pr.changes_requested = bool(changes)

    @api.depends('check_run_ids.conclusion')
    def _compute_checks(self):
        for pr in self:
            required = pr.target_branch_id.required_status_check_contexts.splitlines() if pr.target_branch_id.required_status_check_contexts else []
            runs = pr.check_run_ids.filtered(lambda c: c.name in required) if required else pr.check_run_ids
            pr.all_checks_passed = all(r.conclusion == 'success' for r in runs) if runs else True
            pr.required_checks_passed = pr.all_checks_passed

    def action_merge(self, method=None):
        """Merge the pull request"""
        self.ensure_one()
        if self.state != 'open':
            raise UserError(_("Only open pull requests can be merged."))
        if not self.is_mergeable:
            raise UserError(_("This pull request cannot be merged due to conflicts or failed checks."))

        method = method or self.merge_method
        merge_commit = self._perform_git_merge(method)

        self.write({
            'state': 'merged',
            'merged_at': fields.Datetime.now(),
            'merged_by_id': self.env.user.id,
            'merge_commit_sha': merge_commit.hexsha,
        })

        self.target_branch_id.write({
            'commit_sha': merge_commit.hexsha,
        })

        if self.repository_id.auto_delete_head_branch and not self.source_branch_id.is_default:
            self.source_branch_id.unlink()

        return True

    def _perform_git_merge(self, method):
        import git
        repo = git.Repo(self.repository_id._get_repo_path())

        if method == 'squash':
            index = repo.index
            index.merge_tree(repo.commit(self.source_branch_id.commit_sha))
            commit = index.commit(
                f"Merge PR #{self.number}: {self.title}",
                parent_commits=(repo.commit(self.target_branch_id.commit_sha),),
                author=self.env.user.partner_id.name,
                committer=self.env.user.partner_id.name,
            )
        elif method == 'rebase':
            repo.git.rebase(self.target_branch_id.name, self.source_branch_id.name)
            commit = repo.commit(self.source_branch_id.name)
            repo.git.checkout(self.target_branch_id.name)
            repo.git.merge('--ff-only', self.source_branch_id.name)
        else:
            repo.git.checkout(self.target_branch_id.name)
            repo.git.merge(self.source_branch_id.name, '--no-ff', '-m',
                          f"Merge PR #{self.number}: {self.title}")
            commit = repo.head.commit

        return commit

    def action_close(self):
        self.write({'state': 'closed', 'closed_at': fields.Datetime.now()})

    def action_reopen(self):
        self.write({'state': 'open', 'closed_at': False})


class GitPRFile(models.Model):
    _name = 'git.pr.file'
    _description = 'Pull Request File Change'

    pull_request_id = fields.Many2one('git.pull_request', required=True, ondelete='cascade')
    filename = fields.Char(required=True)
    status = fields.Selection([
        ('added', 'Added'),
        ('modified', 'Modified'),
        ('removed', 'Removed'),
        ('renamed', 'Renamed'),
    ], required=True)
    additions = fields.Integer(default=0)
    deletions = fields.Integer(default=0)
    patch = fields.Text()


class GitPRReview(models.Model):
    _name = 'git.pr.review'
    _description = 'Pull Request Review'
    _order = 'create_date desc'

    pull_request_id = fields.Many2one('git.pull_request', required=True, ondelete='cascade')
    reviewer_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('comment', 'Comment'),
        ('approve', 'Approve'),
        ('request_changes', 'Request Changes'),
    ], default='pending', required=True)
    body = fields.Html()
    commit_id = fields.Many2one('git.commit', string='Reviewed Commit')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('state') in ('approve', 'request_changes'):
                pr = self.env['git.pull_request'].browse(vals['pull_request_id'])
                vals['commit_id'] = pr.source_branch_id.commit_id.id if pr.source_branch_id.commit_id else False
        return super().create(vals_list)