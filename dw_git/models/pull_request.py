import logging

from odoo import _, api, fields, models
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
        index=True,
        help="Per-repository, starting at 1 — the number users read as "
             "'the Nth pull request in THIS repository'.",
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
    assignee_ids = fields.Many2many('res.users', 'git_pr_assignee_rel', 'pr_id', 'user_id', string='Assignees')
    reviewer_ids = fields.Many2many('res.users', 'git_pr_reviewer_rel', 'pr_id', 'user_id', string='Reviewers')
    merged_by_id = fields.Many2one('res.users', string='Merged By')

    # === Commits & Changes ===
    commit_ids = fields.One2many('git.commit', 'pull_request_id', string='Commits')
    commit_count = fields.Integer(compute='_compute_commit_count')
    file_ids = fields.One2many('git.pr.file', 'pull_request_id', string='Changed Files')
    additions = fields.Integer(compute='_compute_stats')
    deletions = fields.Integer(compute='_compute_stats')
    changed_files = fields.Integer(
        string='Changed File Count', compute='_compute_stats')

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

    # === Dates ===
    merged_at = fields.Datetime()
    closed_at = fields.Datetime()

    @api.depends('number', 'title')
    def _compute_name(self):
        for pr in self:
            title = pr.title or ''
            pr.name = f"#{pr.number}: {title}" if pr.number else title

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

    @api.depends('state', 'source_branch_id.commit_sha', 'target_branch_id.commit_sha',
                 'target_branch_id.is_protected', 'target_branch_id.require_pr_reviews',
                 'target_branch_id.required_approving_reviews', 'approval_count',
                 'changes_requested')
    def _compute_mergeable(self):
        """Whether the PR satisfies the target branch's merge requirements."""
        for pr in self:
            pr.has_conflicts = pr._check_conflicts()
            target = pr.target_branch_id
            can_merge = True
            if pr.changes_requested:
                can_merge = False
            if target.is_protected and target.require_pr_reviews:
                if pr.approval_count < target.required_approving_reviews:
                    can_merge = False
            pr.is_mergeable = can_merge and not pr.has_conflicts

    def _check_conflicts(self):
        """True when merging source into target would conflict.

        `git merge-tree` exits non-zero on conflict, which GitPython raises.
        Any other failure (missing repo, unknown sha) is reported as a
        conflict too — refusing to merge is the safe default — but is logged
        so it can be told apart from a real conflict.
        """
        import os
        if not (self.source_branch_id.commit_sha
                and self.target_branch_id.commit_sha):
            return True
        path = self.repository_id._get_repo_path()
        if not os.path.isdir(path):
            _logger.warning("PR %s: no bare repo at %s", self.id, path)
            return True
        try:
            import git
            repo = git.Repo(path)
            repo.git.merge_tree('--write-tree',
                                self.target_branch_id.commit_sha,
                                self.source_branch_id.commit_sha)
            return False
        except Exception as exc:
            _logger.info("PR %s not mergeable: %s", self.id, exc)
            return True

    @api.depends('review_ids.state')
    def _compute_review_status(self):
        for pr in self:
            approvals = pr.review_ids.filtered(lambda r: r.state == 'approve')
            changes = pr.review_ids.filtered(lambda r: r.state == 'request_changes')
            pr.approval_count = len(approvals)
            pr.changes_requested = bool(changes)

    @api.depends('repository_id.owner_id', 'repository_id.name', 'number')
    def _compute_access_url(self):
        """Compute the portal access URL for the pull request.

        portal.mixin provides a default access_url='#'; we override it here
        to point to the actual pull request portal page. Users can share this
        link to give portal access to the pull request.
        """
        super()._compute_access_url()
        for pr in self:
            if pr.repository_id.owner_id and pr.repository_id.name and pr.number:
                owner_login = pr.repository_id.owner_id.login
                repo_name = pr.repository_id.name
                pr.access_url = f'/git/{owner_login}/{repo_name}/pr/{pr.number}'
            else:
                pr.access_url = '#'

    # models.Constraint, not the old _sql_constraints list: Odoo 19
    # replaced that API and silently ignores the list, so the constraint
    # was never created and a duplicate number was accepted.
    _number_per_repository_uniq = models.Constraint(
        'unique(repository_id, number)',
        'A pull request with this number already exists in this repository.',
    )

    def _next_number(self, repository_id):
        """The next free pull request number within one repository.

        Numbers used to come from a single global ir.sequence, so the first
        pull request in a brand new repository could be #795. Every Git
        host numbers per repository, and users read the number as "the Nth
        pull request in THIS repo" — a number that counts every PR on the
        server is not the number they think they are reading.

        The row lock is the point. Two clients opening a pull request
        against the same repository at the same moment would otherwise
        both read the same MAX and both take it; SELECT ... FOR UPDATE on
        the repository row serialises them. The unique constraint above is
        the backstop if anything ever reaches this by another path.
        """
        self.env.cr.execute(
            "SELECT id FROM git_repository WHERE id = %s FOR UPDATE",
            (repository_id,))
        self.env.cr.execute(
            "SELECT COALESCE(MAX(number), 0) FROM git_pull_request "
            "WHERE repository_id = %s",
            (repository_id,))
        return self.env.cr.fetchone()[0] + 1

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('number') and vals.get('repository_id'):
                vals['number'] = self._next_number(vals['repository_id'])
        records = super().create(vals_list)
        for pr in records:
            # best effort: a PR can legitimately exist before its bare repo
            # has the commits (fixtures, imports), so never block creation
            try:
                pr._sync_changed_files()
            except Exception as exc:      # noqa: BLE001 - diagnostic only
                _logger.info("PR %s: initial diff skipped: %s", pr.id, exc)

            # Send PR created notification to reviewers
            pr._send_created_notification()

            # Schedule initial review activities for reviewers
            pr._schedule_review_activities(pr.reviewer_ids)
        return records

    def write(self, vals):
        """Handle updates to PR, including reviewer additions.

        When reviewers are added to a pull request, we send a review request
        notification and schedule an activity on each newly-added reviewer.
        """
        # Track which reviewers are newly added for each PR
        reviewer_changes = {}
        if 'reviewer_ids' in vals and vals['reviewer_ids']:
            # Parse the M2M command to detect added reviewers
            # vals['reviewer_ids'] is a list of (cmd, id, values) tuples
            for pr in self:
                old_reviewer_ids = set(pr.reviewer_ids.ids)
                reviewer_changes[pr.id] = old_reviewer_ids

        result = super().write(vals)

        # After write completes, check for newly added reviewers and notify them
        if 'reviewer_ids' in vals and vals['reviewer_ids']:
            for pr in self:
                old_ids = reviewer_changes.get(pr.id, set())
                new_ids = set(pr.reviewer_ids.ids)
                newly_added = self.env['res.users'].browse(new_ids - old_ids)
                if newly_added:
                    pr._send_review_request_notification(newly_added)
                    pr._schedule_review_activities(newly_added)

        return result

    def action_merge(self, method=None):
        """Merge the pull request"""
        self.ensure_one()
        if self.state != 'open':
            raise UserError(_("Only open pull requests can be merged."))
        if not self.is_mergeable:
            raise UserError(_(
                "This pull request cannot be merged: it has conflicts, "
                "unresolved change requests, or too few approvals."))
        if not self.target_branch_id.can_user_merge(self.env.user):
            raise UserError(_(
                "Branch '%s' is protected and you are not allowed to merge "
                "into it.", self.target_branch_id.name))

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

        if (self.repository_id.auto_delete_head_branch
                and not self.source_branch_id.is_default):
            self._delete_head_branch()

        # Send merge notification — best effort; a mail failure should not
        # block the merge from succeeding
        try:
            self._send_merged_notification()
        except Exception as exc:
            _logger.exception("Failed to send PR merge notification for PR %s: %s", self.id, exc)

        return True

    def _delete_head_branch(self):
        """Delete the merged head branch's git ref, keeping its record.

        This used to call `source_branch_id.unlink()` inside a bare
        `except Exception: pass`, which was wrong twice over.

        It could never succeed: `source_branch_id` is `required=True`, so
        Odoo gives it `ondelete='restrict'`, and *this* pull request — the
        one just merged — still points at the branch. The guard excluded
        `self` from the "still referenced" search, but self is precisely
        the reference that blocks the delete. The feature has therefore
        never once deleted a branch.

        Worse, the failure was not harmless. In PostgreSQL a failed
        statement aborts the whole transaction; catching the Python
        exception does not undo that, so every subsequent query raised
        InFailedSqlTransaction. The next thing action_merge does is send
        the merge notification, which died on a plain SELECT for the mail
        template. A merge would report success, delete nothing, and send
        no mail, leaving only a log line.

        So: delete the ref on disk, which is the cleanup actually wanted,
        and keep the Odoo record because the PR's history refers to it —
        the same thing GitHub does. The savepoint means a git failure
        cannot poison the caller's transaction.
        """
        self.ensure_one()
        branch = self.source_branch_id
        try:
            with self.env.cr.savepoint():
                import git
                repo = git.Repo(self.repository_id._get_repo_path())
                if branch.name in repo.heads:
                    git.Head.delete(repo, branch.name, force=True)
        except Exception:
            _logger.warning(
                "Could not delete head branch %r of PR %s on disk",
                branch.name, self.id, exc_info=True)
            return False
        return True

    def _perform_git_merge(self, method):
        """Merge using plumbing commands — works on bare repos (no work tree)."""
        import git

        repo = git.Repo(self.repository_id._get_repo_path())
        target = self.target_branch_id.name
        source = self.source_branch_id.name
        ref = f'refs/heads/{target}'
        msg = f"Merge PR #{self.number}: {self.title}"
        author = self.env.user.partner_id

        env = {
            'GIT_AUTHOR_NAME': author.name or 'Git Hosting',
            'GIT_AUTHOR_EMAIL': author.email or 'dw_git@localhost',
            'GIT_COMMITTER_NAME': author.name or 'Git Hosting',
            'GIT_COMMITTER_EMAIL': author.email or 'dw_git@localhost',
        }

        if method == 'rebase':
            # linear history: fast-forward when possible, else rebase in a
            # temporary work tree (bare repos have none of their own)
            if repo.is_ancestor(target, source):
                sha = repo.commit(source).hexsha
                repo.git.update_ref(ref, sha)
                return repo.commit(sha)
            import tempfile
            with tempfile.TemporaryDirectory() as td:
                repo.git.worktree('add', '--detach', td, source)
                try:
                    wt = git.Repo(td)
                    wt.git.rebase(target)
                    sha = wt.head.commit.hexsha
                    repo.git.update_ref(ref, sha)
                    return repo.commit(sha)
                finally:
                    repo.git.worktree('remove', '--force', td)

        # merge / squash: build the merged tree, then commit it explicitly
        tree = repo.git.merge_tree('--write-tree', target, source).strip()
        cmd = ['-m', msg, '-p', target]
        if method != 'squash':
            cmd += ['-p', source]
        with repo.git.custom_environment(**env):
            sha = repo.git.commit_tree(tree, *cmd).strip()
        repo.git.update_ref(ref, sha)
        return repo.commit(sha)

    def action_refresh_changes(self):
        """Recompute the changed-file list and patches from the repository."""
        import os
        for pr in self:
            if pr._sync_changed_files():
                continue
            # _sync_changed_files already returns False when it cannot read
            # the repository; throwing that away reported success and left
            # the user pressing a button that could never work, against an
            # empty diff that told them to press it.
            path = pr.repository_id._get_repo_path()
            if not os.path.isdir(path):
                raise UserError(_(
                    "There is no git repository on disk for '%(repo)s'.\n\n"
                    "It was expected at %(path)s. Either nothing has been "
                    "pushed to this repository yet, or its files were moved "
                    "or removed from the server.",
                    repo=pr.repository_id.name, path=path))
            raise UserError(_(
                "Could not read a diff for '%(src)s' into '%(tgt)s'.\n\n"
                "Both branches exist in Odoo, but their commits are not in "
                "the repository on disk. This happens when records were "
                "imported or seeded without the matching git history.",
                src=pr.source_branch_id.name or '?',
                tgt=pr.target_branch_id.name or '?'))
        return True

    def _sync_changed_files(self):
        """Replace git.pr.file rows with the real diff from the bare repo.

        Nothing populated these before: the Changed Files tab listed whatever
        had been inserted by hand, and every patch was empty. The diff is
        taken against the merge base, not the target tip, so it shows what
        this branch changes rather than everything that happened on the
        target since it forked.
        """
        self.ensure_one()
        import os
        Files = self.env['git.pr.file']
        path = self.repository_id._get_repo_path()
        source = self.source_branch_id.commit_sha
        target = self.target_branch_id.commit_sha
        if not (os.path.isdir(path) and source and target):
            return False
        try:
            import git as git_lib
            repo = git_lib.Repo(path)
            bases = repo.merge_base(target, source)
            base = bases[0] if bases else repo.commit(target)
            diffs = base.diff(repo.commit(source), create_patch=True,
                              unified=3)
        except Exception as exc:
            _logger.warning("PR %s: cannot diff %s..%s: %s",
                            self.id, target[:8], source[:8], exc)
            return False

        self.file_ids.unlink()
        rows = []
        for d in diffs:
            if d.new_file:
                status = 'added'
            elif d.deleted_file:
                status = 'removed'
            elif d.renamed_file:
                status = 'renamed'
            else:
                status = 'modified'
            hunk = (d.diff or b'')
            if isinstance(hunk, bytes):
                hunk = hunk.decode('utf-8', errors='replace')
            added = sum(1 for ln in hunk.splitlines()
                        if ln.startswith('+') and not ln.startswith('+++'))
            removed = sum(1 for ln in hunk.splitlines()
                          if ln.startswith('-') and not ln.startswith('---'))
            # d.diff is only the hunk body (GitPython strips the file
            # header), so it's neither a valid `git apply` input nor
            # something a diff-rendering library can attribute to a file.
            # Rebuild the header GitPython omits, including the
            # "new/deleted file mode" and "index" lines real git writes —
            # without them a diff renderer can't tell an added file from a
            # rename (both show as "a/<path> b/<path>" on the first line).
            git_path_a = d.a_path or d.b_path
            git_path_b = d.b_path or d.a_path
            header_lines = [f"diff --git a/{git_path_a} b/{git_path_b}"]
            a_sha = d.a_blob.hexsha[:7] if d.a_blob else '0' * 7
            b_sha = d.b_blob.hexsha[:7] if d.b_blob else '0' * 7
            mode = d.b_mode or d.a_mode or 0o100644
            if d.renamed_file:
                header_lines.append("similarity index 100%")
                header_lines.append(f"rename from {d.rename_from}")
                header_lines.append(f"rename to {d.rename_to}")
            elif d.new_file:
                header_lines.append(f"new file mode {mode:o}")
                header_lines.append(f"index 0000000..{b_sha}")
            elif d.deleted_file:
                header_lines.append(f"deleted file mode {mode:o}")
                header_lines.append(f"index {a_sha}..0000000")
            else:
                header_lines.append(f"index {a_sha}..{b_sha} {mode:o}")
            if hunk:
                old_label = '/dev/null' if d.new_file else f'a/{git_path_a}'
                new_label = '/dev/null' if d.deleted_file else f'b/{git_path_b}'
                header_lines.append(f"--- {old_label}")
                header_lines.append(f"+++ {new_label}")
            header = '\n'.join(header_lines) + '\n'
            patch = header + hunk if hunk else header
            rows.append({
                'pull_request_id': self.id,
                'filename': d.b_path or d.a_path,
                'status': status,
                'additions': added,
                'deletions': removed,
                'patch': patch,
            })
        if rows:
            Files.create(rows)
        return True

    def action_close(self):
        """Close a pull request and send notification"""
        self.write({'state': 'closed', 'closed_at': fields.Datetime.now()})
        # Send close notification — best effort; a mail failure should not
        # block the close from succeeding
        try:
            self._send_closed_notification()
        except Exception as exc:
            _logger.exception("Failed to send PR close notification for PR %s: %s", self.id, exc)

    def action_reopen(self):
        self.write({'state': 'open', 'closed_at': False})

    def _send_created_notification(self):
        """Send PR created notification to reviewers.

        Uses the mail_template_git_pr_created template. Failures are logged
        and do not block PR creation.
        """
        self.ensure_one()
        template = self.env.ref('dw_git.mail_template_git_pr_created', raise_if_not_found=False)
        if not template:
            return
        try:
            template.send_mail(self.id, force_send=False)
        except Exception as exc:
            _logger.warning("Failed to send PR created email for PR %s: %s", self.id, exc)

    def _send_review_request_notification(self, reviewers):
        """Ask `reviewers` — and only them — for a review.

        The template addresses object.reviewer_ids, i.e. everyone currently
        on the PR. Left to itself it would re-ask every existing reviewer
        each time one more is added, so the recipient list is overridden
        here with the reviewers actually being asked.

        Failures are logged and never block the reviewer assignment.
        """
        self.ensure_one()
        recipients = reviewers.filtered('email_formatted')
        if not recipients:
            return
        template = self.env.ref('dw_git.mail_template_git_pr_review_request', raise_if_not_found=False)
        if not template:
            return
        try:
            template.send_mail(self.id, force_send=False, email_values={
                'email_to': ','.join(recipients.mapped('email_formatted')),
            })
        except Exception as exc:
            _logger.warning("Failed to send PR review request email for PR %s: %s", self.id, exc)

    def _send_merged_notification(self):
        """Send PR merged notification to author.

        Uses the mail_template_git_pr_merged template. Failures are logged.
        """
        self.ensure_one()
        template = self.env.ref('dw_git.mail_template_git_pr_merged', raise_if_not_found=False)
        if not template:
            return
        try:
            template.send_mail(self.id, force_send=False)
        except Exception as exc:
            _logger.warning("Failed to send PR merged email for PR %s: %s", self.id, exc)

    def _send_closed_notification(self):
        """Send PR closed notification to author.

        Uses the mail_template_git_pr_closed template. Failures are logged.
        """
        self.ensure_one()
        template = self.env.ref('dw_git.mail_template_git_pr_closed', raise_if_not_found=False)
        if not template:
            return
        try:
            template.send_mail(self.id, force_send=False)
        except Exception as exc:
            _logger.warning("Failed to send PR closed email for PR %s: %s", self.id, exc)

    def _schedule_review_activities(self, reviewers):
        """Schedule review activities for the given reviewers.

        Creates a 'To Do' activity on each reviewer to review this PR.
        Failures are logged and do not block the PR creation/update.
        """
        self.ensure_one()
        if not reviewers:
            return
        try:
            activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
            if not activity_type:
                return
            for reviewer in reviewers:
                self.activity_schedule(
                    activity_type_id=activity_type.id,
                    user_id=reviewer.id,
                    summary=_("Review PR #%d: %s") % (self.number, self.title),
                )
        except Exception as exc:
            _logger.warning("Failed to schedule review activities for PR %s: %s", self.id, exc)


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
