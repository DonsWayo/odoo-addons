# -*- coding: utf-8 -*-
import json

from odoo import http
from odoo.http import request


class GitAPIController(http.Controller):

    @http.route('/api/git/repositories', type='json', auth='user', methods=['GET'])
    def api_list_repositories(self, **kwargs):
        """List repositories for current user"""
        domain = [
            '|', '|',
            ('owner_id', '=', request.env.user.id),
            ('member_ids', 'in', request.env.user.id),
            ('group_ids', 'in', request.env.user.group_ids.ids)
        ]
        if kwargs.get('visibility'):
            domain.append(('visibility', '=', kwargs['visibility']))

        repos = request.env['git.repository'].search(domain, limit=kwargs.get('limit', 50))
        return [{
            'id': r.id,
            'name': r.name,
            'full_name': f"{r.owner_id.login}/{r.name}",
            'description': r.description,
            'visibility': r.visibility,
            'default_branch': r.default_branch,
            'star_count': r.star_count,
            'fork_count': 0,
            'updated_at': r.write_date.isoformat() if r.write_date else None,
        } for r in repos]

    @http.route('/api/git/repositories/<int:repo_id>', type='json', auth='user', methods=['GET'])
    def api_get_repository(self, repo_id, **kwargs):
        """Get single repository details"""
        repo = request.env['git.repository'].browse(repo_id)
        if not repo.exists() or not repo._check_access(request.env.user):
            return {'error': 'Not found'}, 404

        return {
            'id': repo.id,
            'name': repo.name,
            'full_name': f"{repo.owner_id.login}/{repo.name}",
            'description': repo.description,
            'visibility': repo.visibility,
            'default_branch': repo.default_branch,
            'clone_url_http': repo.clone_url_http,
            'clone_url_ssh': repo.clone_url_ssh,
            'stats': {
                'commits': repo.commit_count,
                'branches': repo.branch_count,
                'pull_requests': repo.open_pr_count,
                'issues': repo.open_issue_count,
                'stars': repo.star_count,
                'forks': 0,
            },
            'permissions': repo._get_user_permissions(request.env.user),
        }

    @http.route('/api/git/repositories', type='json', auth='user', methods=['POST'], csrf=False)
    def api_create_repository(self, **kwargs):
        """Create new repository via API"""
        data = json.loads(request.httprequest.data)

        repo = request.env['git.repository'].create({
            'name': data['name'],
            'description': data.get('description', ''),
            'visibility': data.get('visibility', 'private'),
            'has_wiki': data.get('has_wiki', True),
            'has_issues': data.get('has_issues', True),
            'has_pull_requests': data.get('has_pull_requests', True),
            'default_branch': data.get('default_branch', 'main'),
        })

        # Initialize empty repository on disk
        repo._init_git_repo()

        return {
            'id': repo.id,
            'name': repo.name,
            'clone_url_http': repo.clone_url_http,
            'clone_url_ssh': repo.clone_url_ssh,
        }

    @http.route('/api/git/repositories/<int:repo_id>/branches', type='json', auth='user', methods=['GET'])
    def api_list_branches(self, repo_id, **kwargs):
        """List branches for repository"""
        repo = request.env['git.repository'].browse(repo_id)
        if not repo.exists() or not repo._check_access(request.env.user):
            return {'error': 'Not found'}, 404

        branches = repo.branch_ids
        return [{
            'name': b.name,
            'commit_sha': b.commit_sha,
            'is_protected': b.is_protected,
            'is_default': b.is_default,
            'ahead_commits': b.ahead_commits,
            'behind_commits': b.behind_commits,
            'last_commit_date': b.last_commit_date.isoformat() if b.last_commit_date else None,
        } for b in branches]

    @http.route('/api/git/repositories/<int:repo_id>/commits', type='json', auth='user', methods=['GET'])
    def api_list_commits(self, repo_id, **kwargs):
        """List commits for repository"""
        repo = request.env['git.repository'].browse(repo_id)
        if not repo.exists() or not repo._check_access(request.env.user):
            return {'error': 'Not found'}, 404

        branch = kwargs.get('branch', repo.default_branch)
        limit = kwargs.get('limit', 50)

        commits = repo.commit_ids.filtered(lambda c: branch in c.branch_ids.mapped('name'))[:limit]
        return [{
            'sha': c.sha,
            'short_sha': c.short_sha,
            'message': c.message_short,
            'author': {
                'name': c.author_name,
                'email': c.author_email,
            },
            'date': c.committed_date.isoformat() if c.committed_date else None,
            'additions': c.additions,
            'deletions': c.deletions,
        } for c in commits]

    @http.route('/api/git/repositories/<int:repo_id>/tree', type='json', auth='user', methods=['GET'])
    def api_get_tree(self, repo_id, **kwargs):
        """Get file tree for repository at path"""
        repo = request.env['git.repository'].browse(repo_id)
        if not repo.exists() or not repo._check_access(request.env.user):
            return {'error': 'Not found'}, 404

        # This would use git to get the tree
        # For now return empty
        return {'tree': []}

    @http.route('/api/git/pull_requests/<int:pr_id>', type='json', auth='user', methods=['GET'])
    def api_get_pr(self, pr_id, **kwargs):
        """Get pull request details"""
        pr = request.env['git.pull_request'].browse(pr_id)
        if not pr.exists() or not pr._check_access(request.env.user):
            return {'error': 'Not found'}, 404

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

    @http.route('/api/git/pull_requests/<int:pr_id>/files', type='json', auth='user', methods=['GET'])
    def api_get_pr_files(self, pr_id, **kwargs):
        """Get PR changed files"""
        pr = request.env['git.pull_request'].browse(pr_id)
        if not pr.exists() or not pr._check_access(request.env.user):
            return {'error': 'Not found'}, 404

        return [{
            'filename': f.filename,
            'status': f.status,
            'additions': f.additions,
            'deletions': f.deletions,
            'patch': f.patch,
        } for f in pr.file_ids]

    @http.route('/api/git/pull_requests/<int:pr_id>/review', type='json', auth='user', methods=['POST'], csrf=False)
    def api_create_review(self, pr_id, **kwargs):
        """Create PR review"""
        pr = request.env['git.pull_request'].browse(pr_id)
        if not pr.exists() or not pr._check_access(request.env.user):
            return {'error': 'Not found'}, 404

        data = json.loads(request.httprequest.data)
        review = request.env['git.pr.review'].create({
            'pull_request_id': pr_id,
            'reviewer_id': request.env.user.id,
            'state': data.get('state', 'comment'),
            'body': data.get('body', ''),
        })

        return {
            'id': review.id,
            'state': review.state,
            'body': review.body,
        }