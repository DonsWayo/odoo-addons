from odoo import http
from odoo.http import request


class GitPortalController(http.Controller):

    @http.route(['/my/repositories', '/my/repositories/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_repositories(self, page=1, **kwargs):
        """Portal view for user's repositories"""
        user = request.env.user
        domain = [
            '|', '|',
            ('owner_id', '=', user.id),
            ('member_ids', 'in', user.id),
            ('group_ids', 'in', user.group_ids.ids)
        ]

        Repository = request.env['git.repository']
        repositories = Repository.search(domain, limit=12, offset=(page-1)*12)
        total = Repository.search_count(domain)

        return request.render('odoogit.portal_my_repositories', {
            'repositories': repositories,
            'page': page,
            'total': total,
        })

    @http.route('/git/<string:owner>/<string:repo>', type='http', auth='public', website=True)
    def portal_repository_home(self, owner, repo, **kwargs):
        """Public/portal repository home page"""
        repository = request.env['git.repository'].sudo().search([
            ('name', '=', repo),
            ('owner_id.login', '=', owner),
        ], limit=1)

        if not repository:
            return request.not_found()

        # Check access
        if not repository._check_portal_access(request.env.user):
            return request.render('odoogit.portal_repository_private', {'repo': repository})

        return request.render('odoogit.portal_repository_home', {
            'repository': repository,
            'branches': repository.branch_ids,
            'recent_commits': repository.commit_ids[:10],
            'open_prs': repository.pull_request_ids.filtered(lambda p: p.state == 'open')[:5],
        })

    @http.route('/git/<string:owner>/<string:repo>/commit/<string:sha>', type='http', auth='public', website=True)
    def portal_commit(self, owner, repo, sha, **kwargs):
        """Portal commit view"""
        repository = request.env['git.repository'].sudo().search([
            ('name', '=', repo),
            ('owner_id.login', '=', owner),
        ], limit=1)

        if not repository or not repository._check_portal_access(request.env.user):
            return request.not_found()

        commit = repository.commit_ids.filtered(lambda c: c.sha == sha)[:1]
        if not commit:
            return request.not_found()

        return request.render('odoogit.portal_commit', {
            'repository': repository,
            'commit': commit,
        })
