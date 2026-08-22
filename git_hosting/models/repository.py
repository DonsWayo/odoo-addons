# -*- coding: utf-8 -*-
import os
import secrets
import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class GitRepository(models.Model):
    _name = 'git.repository'
    _description = 'Git Repository'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    _order = 'name'
    _check_company_auto = True

    # === Basic Fields ===
    name = fields.Char(
        required=True,
        index='trigram',
        tracking=True,
        help="Repository name (alphanumeric, hyphens, underscores, dots)"
    )
    description = fields.Html()

    # === Visibility & Access ===
    visibility = fields.Selection([
        ('private', 'Private (members only)'),
        ('internal', 'Internal (all employees)'),
    ], default='private', required=True, tracking=True)

    # === Git Configuration ===
    default_branch = fields.Char(
        default='main',
        required=True,
        help="Default branch name"
    )

    # === Ownership & Members ===
    owner_id = fields.Many2one(
        'res.users',
        string='Owner',
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
        index=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        required=True
    )
    member_ids = fields.Many2many(
        'res.users',
        'git_repo_member_rel',
        'repo_id', 'user_id',
        string='Members',
        domain="[('share', '=', False)]"
    )
    group_ids = fields.Many2many(
        'res.groups',
        'git_repo_group_rel',
        'repo_id', 'group_id',
        string='Groups'
    )

    # === Project Integration ===
    project_id = fields.Many2one(
        'project.project',
        string='Linked Project',
        domain="[('company_id', 'in', [company_id, False])]",
        help="Link to project for task integration"
    )

    # === One2many Relations ===
    branch_ids = fields.One2many('git.branch', 'repository_id', string='Branches')
    commit_ids = fields.One2many('git.commit', 'repository_id', string='Commits')
    pull_request_ids = fields.One2many('git.pull_request', 'repository_id', string='Pull Requests')
    issue_ids = fields.One2many('git.issue', 'repository_id', string='Issues')
    wiki_page_ids = fields.One2many('git.wiki.page', 'repository_id', string='Wiki Pages')
    pat_ids = fields.One2many('git.personal_access_token', 'repository_id', string='Personal Access Tokens')
    deploy_key_ids = fields.One2many('git.deploy_key', 'repository_id', string='Deploy Keys')
    webhook_ids = fields.One2many('git.webhook', 'repository_id', string='Webhooks')

    # === Computed Counters ===
    commit_count = fields.Integer(compute='_compute_counters')
    branch_count = fields.Integer(compute='_compute_counters')
    open_pr_count = fields.Integer(compute='_compute_counters')
    open_issue_count = fields.Integer(compute='_compute_counters')
    wiki_page_count = fields.Integer(compute='_compute_counters')
    collaborator_count = fields.Integer(compute='_compute_collaborator_count')

    # === Last Activity ===
    last_activity_date = fields.Datetime(
        compute='_compute_last_activity',
        store=True,
        index=True
    )

    # === Stars ===
    star_ids = fields.Many2many(
        'res.users',
        'git_repo_star_rel',
        'repo_id', 'user_id',
        string='Stars'
    )
    star_count = fields.Integer(compute='_compute_star_count')
    is_starred = fields.Boolean(compute='_compute_is_starred')

    # === Settings ===
    has_issues = fields.Boolean(default=True)
    has_wiki = fields.Boolean(default=True)
    has_pull_requests = fields.Boolean(default=True)
    has_projects = fields.Boolean(default=False)
    require_signed_commits = fields.Boolean(default=False)
    max_file_size = fields.Integer(default=100, help="Max file size in MB")
    auto_delete_head_branch = fields.Boolean(default=True)

    # === Constraints ===
    _sql_constraints = [
        ('name_company_uniq', 'unique(name, company_id)',
         'Repository name must be unique per company!'),
        ('name_format',
         "CHECK(name ~ '^[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]$')",
         'Invalid repository name format'),
    ]

    @api.depends('branch_ids', 'commit_ids', 'pull_request_ids', 'issue_ids', 'wiki_page_ids')
    def _compute_counters(self):
        for repo in self:
            repo.commit_count = len(repo.commit_ids)
            repo.branch_count = len(repo.branch_ids)
            repo.open_pr_count = len(repo.pull_request_ids.filtered(lambda pr: pr.state == 'open'))
            repo.open_issue_count = len(repo.issue_ids.filtered(lambda i: i.state == 'open'))
            repo.wiki_page_count = len(repo.wiki_page_ids)

    @api.depends('member_ids', 'group_ids')
    def _compute_collaborator_count(self):
        for repo in self:
            users = repo.member_ids
            for group in repo.group_ids:
                users |= group.users
            repo.collaborator_count = len(users)

    @api.depends('commit_ids.create_date', 'pull_request_ids.create_date', 'issue_ids.create_date')
    def _compute_last_activity(self):
        for repo in self:
            dates = []
            if repo.commit_ids:
                dates.append(max(repo.commit_ids.mapped('create_date')))
            if repo.pull_request_ids:
                dates.append(max(repo.pull_request_ids.mapped('create_date')))
            if repo.issue_ids:
                dates.append(max(repo.issue_ids.mapped('create_date')))
            repo.last_activity_date = max(dates) if dates else False

    @api.depends('star_ids')
    def _compute_star_count(self):
        for repo in self:
            repo.star_count = len(repo.star_ids)

    @api.depends('star_ids')
    def _compute_is_starred(self):
        user = self.env.user
        for repo in self:
            repo.is_starred = user in repo.star_ids

    def action_toggle_star(self):
        self.ensure_one()
        if self.env.user in self.star_ids:
            self.star_ids = [(3, self.env.user.id)]
        else:
            self.star_ids = [(4, self.env.user.id)]
        return True

    def _get_repo_path(self):
        """Get absolute path for repository"""
        base_path = self.env['ir.config_parameter'].sudo().get_param(
            'git_hosting.repo_base_path',
            '/var/lib/odoo/git/repos'
        )
        return os.path.join(base_path, self.owner_id.login, f"{self.name}.git")

    def _init_git_repo(self):
        """Initialize bare Git repository on filesystem"""
        self.ensure_one()
        repo_path = self._get_repo_path()
        if not os.path.exists(repo_path):
            os.makedirs(repo_path, exist_ok=True)
            try:
                import git
                repo = git.Repo.init(repo_path, bare=True)
                # Create initial empty commit for default branch
                if self.default_branch != 'main':
                    pass  # Will create on first push
            except Exception as e:
                _logger.error(f"Failed to init git repo: {e}")
                raise UserError(_("Failed to initialize Git repository: %s") % str(e))
        return True

    def _get_git_refs(self):
        """Get all refs for Git Smart HTTP advertisement"""
        self.ensure_one()
        repo_path = self._get_repo_path()
        if not os.path.exists(repo_path):
            return {}
        try:
            import git
            repo = git.Repo(repo_path)
            refs = {}
            for ref in repo.refs:
                refs[ref.name] = ref.commit.hexsha
            return refs
        except Exception:
            return {}

    def action_open_branches(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Branches',
            'res_model': 'git.branch',
            'view_mode': 'list,form',
            'domain': [('repository_id', '=', self.id)],
            'context': {'default_repository_id': self.id},
        }

    def action_open_commits(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Commits',
            'res_model': 'git.commit',
            'view_mode': 'list,form',
            'domain': [('repository_id', '=', self.id)],
            'context': {'default_repository_id': self.id},
        }

    def action_open_pull_requests(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Pull Requests',
            'res_model': 'git.pull_request',
            'view_mode': 'list,form',
            'domain': [('repository_id', '=', self.id)],
            'context': {'default_repository_id': self.id},
        }

    def action_open_issues(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Issues',
            'res_model': 'git.issue',
            'view_mode': 'list,form',
            'domain': [('repository_id', '=', self.id)],
            'context': {'default_repository_id': self.id},
        }

    def _check_access(self, user, operation='read'):
        """Check if user has access to repository"""
        if user.has_group('git_hosting.group_git_manager'):
            return True
        if user == self.owner_id:
            return True
        if user in self.member_ids:
            return True
        if self.group_ids & user.groups_id:
            return True
        if operation == 'read' and self.visibility == 'internal' and not user.share:
            return True
        return False