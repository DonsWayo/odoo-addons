import logging
import os
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

NAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]$')

# Remote URLs accepted for mirroring. This is an allowlist on purpose.
#
# `git fetch` treats several URL forms as instructions rather than locations:
#   ext::sh -c '...'   runs a shell command  (remote code execution)
#   file:///etc/...    reads the local filesystem
#   -upload-pack=...   is parsed as a git option, not a URL
# `mirror_url` is a plain field on git.repository, which ir.model.access
# grants every employee write on — so it is attacker-controlled input that
# the hourly mirror cron feeds to git as the Odoo system user.
MIRROR_URL_RE = re.compile(
    r"""^(?:
          (?:https?|git|ssh)://[^\s'"\\]+      # scheme form
        | [A-Za-z0-9._-]+@[A-Za-z0-9.-]+:[^\s'"\\]+   # scp form: user@host:path
    )$""",
    re.VERBOSE,
)
# Protocols git may use for a mirror fetch, as GIT_ALLOW_PROTOCOL expects them.
MIRROR_ALLOWED_PROTOCOLS = 'http:https:git:ssh'



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
    clone_url_http = fields.Char(compute='_compute_clone_urls', string='Clone URL (HTTPS)')
    clone_url_ssh = fields.Char(compute='_compute_clone_urls', string='Clone URL (SSH)')

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
    pat_ids = fields.Many2many(
        'git.personal_access_token',
        'git_pat_repo_rel',
        'repo_id', 'pat_id',
        string='Personal Access Tokens',
    )
    deploy_key_ids = fields.One2many('git.deploy_key', 'repository_id', string='Deploy Keys')
    webhook_ids = fields.One2many('git.webhook', 'repository_id', string='Webhooks')

    # === Computed Counters ===
    commit_count = fields.Integer(compute='_compute_counters')
    branch_count = fields.Integer(compute='_compute_counters')
    open_pr_count = fields.Integer(compute='_compute_counters')
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
    has_pull_requests = fields.Boolean(default=True)
    protected_branch_ids = fields.Many2many(
        'git.branch',
        'git_repo_protected_branch_rel',
        'repo_id', 'branch_id',
        string='Protected Branches'
    )
    has_projects = fields.Boolean(default=False)

    # === Mirroring ===
    is_mirror = fields.Boolean(
        default=False,
        help="This repository tracks an upstream remote")
    mirror_url = fields.Char(help="Upstream URL fetched by the mirror cron")
    mirror_active = fields.Boolean(
        default=False,
        help="Include this mirror in the scheduled sync")
    mirror_interval = fields.Selection([
        ('hourly', 'Hourly'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
    ], default='daily',
        help="Desired sync cadence. The cron runs hourly and skips mirrors "
             "whose interval has not elapsed since mirror_last_sync.")
    mirror_last_sync = fields.Datetime(readonly=True)
    require_signed_commits = fields.Boolean(default=False)
    max_file_size = fields.Integer(default=100, help="Max file size in MB")
    auto_delete_head_branch = fields.Boolean(default=True)

    # === Constraints ===
# Name validation handled by api.constrains below (ORM-level,
    # raises ValidationError before DB flush)

    @api.depends('branch_ids', 'commit_ids', 'pull_request_ids')
    def _compute_counters(self):
        for repo in self:
            repo.commit_count = len(repo.commit_ids)
            repo.branch_count = len(repo.branch_ids)
            repo.open_pr_count = len(repo.pull_request_ids.filtered(lambda pr: pr.state == 'open'))

    @api.depends('member_ids', 'group_ids')
    def _compute_collaborator_count(self):
        for repo in self:
            users = repo.member_ids
            for group in repo.group_ids:
                users |= group.user_ids
            repo.collaborator_count = len(users)

    @api.depends('commit_ids.create_date', 'pull_request_ids.create_date')
    def _compute_last_activity(self):
        for repo in self:
            dates = []
            if repo.commit_ids:
                dates.append(max(repo.commit_ids.mapped('create_date')))
            if repo.pull_request_ids:
                dates.append(max(repo.pull_request_ids.mapped('create_date')))
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

    @api.depends('owner_id', 'name')
    def _compute_clone_urls(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', 'http://localhost:8069')
        ssh_host = self.env['ir.config_parameter'].sudo().get_param('dw_git.ssh_host', 'git.example.com')
        for repo in self:
            if repo.owner_id and repo.name:
                repo.clone_url_http = f"{base_url}/git/{repo.owner_id.login}/{repo.name}.git"
                repo.clone_url_ssh = f"git@{ssh_host}:{repo.owner_id.login}/{repo.name}.git"
            else:
                repo.clone_url_http = False
                repo.clone_url_ssh = False

    def _get_repo_path(self):
        """Get absolute path for repository"""
        base_path = self.env['ir.config_parameter'].sudo().get_param(
            'dw_git.repo_base_path',
            '/var/lib/odoo/git/repos'
        )
        return os.path.join(base_path, self.owner_id.login, f"{self.name}.git")

    def _init_git_repo(self):
        """Create the bare Git repository on disk. Idempotent."""
        self.ensure_one()
        repo_path = self._get_repo_path()
        if os.path.exists(repo_path):
            return True
        try:
            import git
            os.makedirs(repo_path, exist_ok=True)
            git.Repo.init(repo_path, bare=True,
                          initial_branch=self.default_branch or 'main')
        except Exception as e:
            _logger.error("Failed to init git repo at %s: %s", repo_path, e)
            raise UserError(
                _("Failed to initialize Git repository: %s", e)) from e
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

    @api.constrains('name')
    def _check_name_validity(self):
        for rec in self:
            if rec.name and not NAME_RE.match(rec.name):
                raise ValidationError(_(
                    "Invalid repository name: %s. Use letters, digits, "
                    "dots, hyphens or underscores.", rec.name))

    @api.constrains('mirror_url')
    def _check_mirror_url(self):
        """Reject remote URLs that git would treat as a command or a path."""
        for rec in self:
            if rec.mirror_url and not MIRROR_URL_RE.match(rec.mirror_url.strip()):
                raise ValidationError(_(
                    "Invalid mirror URL: %(url)s\n\n"
                    "Use https://, http://, git://, ssh:// or "
                    "user@host:path. Other forms — notably ext:// and "
                    "file:// — let git run commands or read local files.",
                    url=rec.mirror_url))

    @api.constrains('name', 'owner_id')
    def _check_name_owner_unique(self):
        """One name per owner — matches the on-disk <owner>/<name>.git layout.

        Company-wide uniqueness (the previous rule) made alice/web and bob/web
        collide even though they occupy different directories.
        """
        for rec in self:
            dup = self.search([
                ('name', '=', rec.name),
                ('owner_id', '=', rec.owner_id.id),
                ('id', '!=', rec.id),
            ], limit=1)
            if dup:
                raise ValidationError(_(
                    "%(owner)s already owns a repository named '%(name)s'.",
                    owner=rec.owner_id.name, name=rec.name))

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

    def _sync_from_git(self):
        """Sync branches and commits from the on-disk git repo into Odoo."""
        self.ensure_one()
        import os

        import git as git_lib
        path = self._get_repo_path()
        if not os.path.isdir(path):
            return
        repo = git_lib.Repo(path)
        Branch = self.env['git.branch'].sudo()
        Commit = self.env['git.commit'].sudo()
        from datetime import datetime
        for head in repo.heads:
            sha = head.commit.hexsha
            branch = Branch.search([
                ('name', '=', head.name),
                ('repository_id', '=', self.id),
            ], limit=1)
            if branch:
                branch.write({'commit_sha': sha})
            else:
                Branch.create({
                    'name': head.name,
                    'repository_id': self.id,
                    'commit_sha': sha,
                })
            for gc in repo.iter_commits(head, max_count=50):
                if Commit.search_count([('sha', '=', gc.hexsha),
                                        ('repository_id', '=', self.id)]):
                    continue
                Commit.create({
                    'sha': gc.hexsha,
                    'message': (gc.message or '').strip(),
                    'author_name': gc.author.name if gc.author else '',
                    'author_email': gc.author.email if gc.author else '',
                    'committed_date': datetime.fromtimestamp(gc.committed_date),
                    'repository_id': self.id,
                })
        # A push arrives over HTTP; commit so the synced refs survive even if a
        # later step of the request fails. Never commit under the test cursor —
        # it would leak fixtures across tests.
        if not self.env.registry.in_test_mode():
            self.env.cr.commit()

    def write(self, vals):
        """Migrate the bare repo on disk when owner/name changes the path."""
        import shutil
        result = True
        for repo in self:
            old_path = repo._get_repo_path()
            res = super(GitRepository, repo).write(vals)
            new_path = repo._get_repo_path()
            if old_path != new_path and os.path.isdir(old_path):
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                if not os.path.exists(new_path):
                    shutil.move(old_path, new_path)
            result = result and res
        return result

    def _check_repo_access(self, user, operation='read'):
        """Check if user has access to repository"""
        if user.has_group('dw_git.group_git_manager'):
            return True
        if user == self.owner_id:
            return True
        if user in self.member_ids:
            return True
        if self.group_ids & user.group_ids:
            return True
        return bool(operation == 'read' and self.visibility == 'internal'
                    and not user.share)

    def _check_portal_access(self, user):
        """Check if user has portal access to repository"""
        return self._check_repo_access(user, 'read')

    def _get_user_permissions(self, user):
        """Get user permissions for repository"""
        perms = {
            'read': False,
            'write': False,
            'admin': False,
        }
        if user.has_group('dw_git.group_git_manager') or user == self.owner_id:
            perms = {'read': True, 'write': True, 'admin': True}
        elif user in self.member_ids or self.group_ids & user.group_ids:
            perms = {'read': True, 'write': True, 'admin': False}
        elif self.visibility == 'internal' and not user.share:
            perms = {'read': True, 'write': False, 'admin': False}
        return perms

    @api.model
    def _cron_sync_mirrors(self):
        """Scheduled action to sync mirrored repositories"""
        repos = self.search([('is_mirror', '=', True), ('mirror_active', '=', True)])
        for repo in repos:
            try:
                repo._sync_mirror()
            except Exception as e:
                _logger.error(f"Failed to sync mirror for {repo.name}: {e}")
                repo.message_post(body=_("Mirror sync failed: %s") % str(e))

    def _sync_mirror(self):
        """Fetch all refs from the configured upstream into the bare repo."""
        self.ensure_one()
        if not self.mirror_url:
            return False
        self._fetch_refs_from(self.mirror_url)
        self.mirror_last_sync = fields.Datetime.now()
        return True

    def _fetch_refs_from(self, url):
        """Fetch every branch from `url` into this repository's bare repo.

        Shared by mirroring and one-shot import. The URL is re-validated
        here and not only in the field constraint, because this runs against
        whatever is in the database — including rows written before the
        constraint existed, or through raw SQL.
        """
        self.ensure_one()
        url = (url or '').strip()
        if not MIRROR_URL_RE.match(url):
            raise UserError(_(
                "Refusing to fetch from an unsupported remote URL: %(url)s",
                url=url))
        import git
        path = self._get_repo_path()
        if not os.path.isdir(path):
            self._init_git_repo()
        repo = git.Repo(path)
        if 'origin' in [r.name for r in repo.remotes]:
            repo.remotes.origin.set_url(url)
        else:
            repo.create_remote('origin', url)
        # Belt and braces: even if a URL slipped past the allowlist, git
        # itself refuses any transport outside this set.
        with repo.git.custom_environment(
                GIT_ALLOW_PROTOCOL=MIRROR_ALLOWED_PROTOCOLS,
                GIT_TERMINAL_PROMPT='0'):
            repo.git.fetch('--prune', 'origin', '+refs/heads/*:refs/heads/*')
        self._sync_from_git()
        return True
