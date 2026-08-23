# -*- coding: utf-8 -*-
import os
import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class GitBranch(models.Model):
    _name = 'git.branch'
    _description = 'Git Branch'
    _order = 'is_default desc, name'
    _name_repo_uniq = models.Constraint(
        'unique(name, repository_id)',
        'Branch name must be unique per repository!',
    )

    name = fields.Char(required=True, index=True)
    repository_id = fields.Many2one(
        'git.repository',
        required=True,
        ondelete='cascade',
        index=True
    )
    commit_sha = fields.Char(
        string='HEAD Commit SHA',
        required=True,
        size=40,
        help="Full SHA of the commit this branch points to"
    )
    target_branch = fields.Char(string='Source Branch')

    # === Protection Rules ===
    is_protected = fields.Boolean(
        default=False,
        help="Prevent force pushes and deletions"
    )
    require_pr_reviews = fields.Boolean(
        string='Require Pull Request Reviews',
        default=False
    )
    required_approving_reviews = fields.Integer(
        default=1,
        help="Number of required approving reviews"
    )
    dismiss_stale_reviews = fields.Boolean(
        default=True,
        help="Dismiss stale reviews when new commits are pushed"
    )
    require_linear_history = fields.Boolean(
        default=False,
        help="Require linear history (no merge commits)"
    )
    require_status_checks = fields.Boolean(
        default=False,
        help="Require status checks to pass before merging"
    )
    required_status_check_contexts = fields.Text(
        help="Required status check contexts (one per line)"
    )
    allow_force_push = fields.Boolean(default=False)
    allow_deletions = fields.Boolean(default=False)

    # === Access Control ===
    restricted_push_user_ids = fields.Many2many(
        'res.users',
        'git_branch_push_user_rel',
        'branch_id', 'user_id',
        string='Users Allowed to Push',
        domain="[('share', '=', False)]"
    )
    restricted_merge_user_ids = fields.Many2many(
        'res.users',
        'git_branch_merge_user_rel',
        'branch_id', 'user_id',
        string='Users Allowed to Merge',
        domain="[('share', '=', False)]"
    )
    restricted_push_group_ids = fields.Many2many(
        'res.groups',
        'git_branch_push_group_rel',
        'branch_id', 'group_id',
        string='Groups Allowed to Push'
    )

    # === Computed ===
    is_default = fields.Boolean(compute='_compute_is_default', store=True)
    ahead_commits = fields.Integer(compute='_compute_ahead_behind')
    behind_commits = fields.Integer(compute='_compute_ahead_behind')
    last_commit_date = fields.Datetime(related='commit_id.committed_date')
    commit_id = fields.Many2one('git.commit', string='HEAD Commit', compute='_compute_commit_id', store=True)

    @api.depends('repository_id.default_branch')
    def _compute_is_default(self):
        for branch in self:
            branch.is_default = branch.name == branch.repository_id.default_branch

    @api.depends('commit_sha')
    def _compute_commit_id(self):
        for branch in self:
            if branch.commit_sha:
                branch.commit_id = self.env['git.commit'].search([
                    ('sha', '=', branch.commit_sha),
                    ('repository_id', '=', branch.repository_id.id)
                ], limit=1)
            else:
                branch.commit_id = False

    def _compute_ahead_behind(self):
        """Compute ahead/behind relative to default branch"""
        for branch in self:
            if branch.is_default:
                branch.ahead_commits = 0
                branch.behind_commits = 0
            else:
                try:
                    import git
                    repo = git.Repo(branch.repository_id._get_repo_path())
                    default_branch = branch.repository_id.default_branch
                    branch.ahead_commits = len(list(repo.iter_commits(
                        f'{default_branch}..{branch.name}')))
                    branch.behind_commits = len(list(repo.iter_commits(
                        f'{branch.name}..{default_branch}')))
                except Exception:
                    branch.ahead_commits = 0
                    branch.behind_commits = 0

    def can_user_push(self, user=None):
        """Check if user can push to this branch"""
        user = user or self.env.user
        if not self.is_protected:
            return True
        if user in self.restricted_push_user_ids:
            return True
        if user.has_group('odoogit.group_git_manager'):
            return True
        return False

    def can_user_merge(self, user=None):
        """Check if user can merge to this branch"""
        user = user or self.env.user
        if not self.is_protected:
            return True
        if user in self.restricted_merge_user_ids:
            return True
        if user.has_group('odoogit.group_git_manager'):
            return True
        return False

    @api.constrains('name', 'repository_id')
    def _check_branch_unique(self):
        for rec in self:
            dup = self.search([
                ('name', '=', rec.name),
                ('repository_id', '=', rec.repository_id.id),
                ('id', '!=', rec.id),
            ], limit=1)
            if dup:
                raise ValidationError(_(
                    "Branch '%s' already exists in this repository.",
                    rec.name))

    def action_create_pr(self, target_branch_id=None):
        """Create pull request from this branch"""
        self.ensure_one()
        if not target_branch_id:
            target_branch = self.repository_id.branch_ids.filtered(
                lambda b: b.is_default
            )[:1]
        else:
            target_branch = self.env['git.branch'].browse(target_branch_id)

        return {
            'type': 'ir.actions.act_window',
            'name': 'New Pull Request',
            'res_model': 'git.pull_request',
            'view_mode': 'form',
            'context': {
                'default_repository_id': self.repository_id.id,
                'default_source_branch_id': self.id,
                'default_target_branch_id': target_branch.id,
            },
        }