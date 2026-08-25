"""JSON-RPC API for Git Hosting.

All routes are `type='jsonrpc'` (Odoo 19 renamed `type='json'`), which means
they are POST endpoints taking a JSON-RPC envelope. Arguments arrive as
keyword arguments in `params` — do not read `request.httprequest.data`
directly, the body is the envelope, not your payload.
"""
from odoo import _, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request


class GitAPIController(http.Controller):

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _repo_or_raise(self, repo_id, operation='read'):
        """Fetch a repository the caller may access, or raise AccessError.

        Raising (rather than returning `{'error': ...}, 404`) matters: the old
        code returned a tuple from a JSON route, which serialised the tuple as
        a successful result instead of signalling failure.
        """
        repo = request.env['git.repository'].browse(repo_id).exists()
        if not repo or not repo._check_repo_access(request.env.user, operation):
            raise AccessError(_("Repository not found or not accessible."))
        return repo

    def _pr_or_raise(self, pr_id, operation='read'):
        """Access to a PR is access to the repository that contains it."""
        pr = request.env['git.pull_request'].browse(pr_id).exists()
        if not pr or not pr.repository_id._check_repo_access(
                request.env.user, operation):
            raise AccessError(_("Pull request not found or not accessible."))
        return pr

    @staticmethod
    def _repo_json(repo):
        return {
            'id': repo.id,
            'name': repo.name,
            'full_name': f"{repo.owner_id.login}/{repo.name}",
            'description': repo.description,
            'visibility': repo.visibility,
            'default_branch': repo.default_branch,
            'star_count': repo.star_count,
            'updated_at': repo.write_date.isoformat() if repo.write_date else None,
        }

    # ------------------------------------------------------------------
    # repositories
    # ------------------------------------------------------------------
    @http.route('/api/git/repositories', type='jsonrpc', auth='user')
    def api_list_repositories(self, visibility=None, limit=50, **kwargs):
        """List repositories visible to the current user."""
        user = request.env.user
        domain = [
            '|', '|', '|',
            ('owner_id', '=', user.id),
            ('member_ids', 'in', user.id),
            ('group_ids', 'in', user.group_ids.ids),
            ('visibility', '=', 'internal'),
        ]
        if visibility:
            domain = ['&'] + domain + [('visibility', '=', visibility)]
        repos = request.env['git.repository'].search(domain, limit=limit)
        return [self._repo_json(r) for r in repos]

    @http.route('/api/git/repositories/<int:repo_id>', type='jsonrpc',
                auth='user')
    def api_get_repository(self, repo_id, **kwargs):
        """Get a single repository, with the caller's effective permissions."""
        repo = self._repo_or_raise(repo_id)
        payload = self._repo_json(repo)
        payload.update({
            'clone_url_http': repo.clone_url_http,
            'clone_url_ssh': repo.clone_url_ssh,
            'stats': {
                'commits': repo.commit_count,
                'branches': repo.branch_count,
                'pull_requests': repo.open_pr_count,
                'stars': repo.star_count,
            },
            'permissions': repo._get_user_permissions(request.env.user),
        })
        return payload

    @http.route('/api/git/repositories/create', type='jsonrpc', auth='user')
    def api_create_repository(self, name=None, description='',
                              visibility='private', default_branch='main',
                              has_pull_requests=True, **kwargs):
        """Create a repository and initialise its bare repo on disk."""
        if not name:
            raise UserError(_("A repository name is required."))
        repo = request.env['git.repository'].create({
            'name': name,
            'description': description,
            'visibility': visibility,
            'has_pull_requests': has_pull_requests,
            'default_branch': default_branch,
        })
        repo._init_git_repo()
        return {
            'id': repo.id,
            'name': repo.name,
            'clone_url_http': repo.clone_url_http,
            'clone_url_ssh': repo.clone_url_ssh,
        }

    @http.route('/api/git/repositories/<int:repo_id>/branches',
                type='jsonrpc', auth='user')
    def api_list_branches(self, repo_id, **kwargs):
        repo = self._repo_or_raise(repo_id)
        return [{
            'name': b.name,
            'commit_sha': b.commit_sha,
            'is_protected': b.is_protected,
            'is_default': b.is_default,
            'ahead_commits': b.ahead_commits,
            'behind_commits': b.behind_commits,
            'last_commit_date': b.last_commit_date.isoformat() if b.last_commit_date else None,
        } for b in repo.branch_ids]

    @http.route('/api/git/repositories/<int:repo_id>/commits',
                type='jsonrpc', auth='user')
    def api_list_commits(self, repo_id, branch=None, limit=50, **kwargs):
        repo = self._repo_or_raise(repo_id)
        commits = repo.commit_ids
        if branch:
            commits = commits.filtered(
                lambda c: branch in c.branch_ids.mapped('name'))
        return [{
            'sha': c.sha,
            'short_sha': c.short_sha,
            'message': c.message_short,
            'author': {'name': c.author_name, 'email': c.author_email},
            'date': c.committed_date.isoformat() if c.committed_date else None,
            'additions': c.additions,
            'deletions': c.deletions,
        } for c in commits[:limit]]

    @http.route('/api/git/repositories/<int:repo_id>/tree',
                type='jsonrpc', auth='user')
    def api_get_tree(self, repo_id, ref=None, path='', **kwargs):
        """List one directory level of the repository tree at `ref`."""
        repo = self._repo_or_raise(repo_id)
        import os
        if not os.path.isdir(repo._get_repo_path()):
            return {'ref': ref or repo.default_branch, 'path': path,
                    'tree': []}
        try:
            import git
            git_repo = git.Repo(repo._get_repo_path())
            commit = git_repo.commit(ref or repo.default_branch)
            tree = commit.tree / path if path else commit.tree
            return {
                'ref': ref or repo.default_branch,
                'path': path,
                'tree': [{
                    'name': item.name,
                    'path': item.path,
                    'type': 'tree' if item.type == 'tree' else 'blob',
                    'size': getattr(item, 'size', 0),
                } for item in tree],
            }
        except Exception:
            # empty repo, unknown ref, or unknown path
            return {'ref': ref or repo.default_branch, 'path': path,
                    'tree': []}

    # ------------------------------------------------------------------
    # pull requests
    # ------------------------------------------------------------------
    @http.route('/api/git/pull_requests/<int:pr_id>', type='jsonrpc',
                auth='user')
    def api_get_pr(self, pr_id, **kwargs):
        pr = self._pr_or_raise(pr_id)
        return {
            'id': pr.id,
            'number': pr.number,
            'title': pr.title,
            'description': pr.description,
            'state': pr.state,
            'source_branch': pr.source_branch_id.name,
            'target_branch': pr.target_branch_id.name,
            'author': pr.author_id.name,
            'mergeable': pr.is_mergeable,
            'approval_count': pr.approval_count,
            'changes_requested': pr.changes_requested,
        }

    @http.route('/api/git/pull_requests/<int:pr_id>/files', type='jsonrpc',
                auth='user')
    def api_get_pr_files(self, pr_id, **kwargs):
        pr = self._pr_or_raise(pr_id)
        return [{
            'filename': f.filename,
            'status': f.status,
            'additions': f.additions,
            'deletions': f.deletions,
            'patch': f.patch,
        } for f in pr.file_ids]

    @http.route('/api/git/pull_requests/<int:pr_id>/review', type='jsonrpc',
                auth='user')
    def api_create_review(self, pr_id, state='comment', body='', **kwargs):
        # A review is a write, and an 'approve' counts towards the target
        # branch's required approvals — so it must not be gated by a read
        # check. On an `internal` repository every employee can read, but
        # only owners, members and group members may write.
        pr = self._pr_or_raise(pr_id, 'write')
        review = request.env['git.pr.review'].create({
            'pull_request_id': pr.id,
            'reviewer_id': request.env.user.id,
            'state': state,
            'body': body,
        })
        return {'id': review.id, 'state': review.state, 'body': review.body}
