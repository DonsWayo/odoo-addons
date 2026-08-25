{
    'name': 'OdooGit - Git Hosting',
    'version': '19.0.1.4.0',
    'category': 'Tools/Development',
    'summary': 'Self-hosted Git repository hosting and code review inside Odoo: '
               'clone and push over HTTPS, pull requests, branch protection, '
               'access tokens, deploy keys and webhooks. A real Git server, '
               'no external service to run.',
    'description': """
Self-hosted Git repository management inside Odoo 19:

- Private/internal repositories served over Git Smart HTTP
- Branches with protection settings, pull requests, code reviews
- Commit history synced from the bare repositories on disk
- Personal Access Tokens for git clone/push over HTTPS
- Deploy keys for CI/CD
- Webhooks with HMAC-SHA256 signatures and delivery history
- Portal pages for repositories and commits
- mail.thread integration on repositories and pull requests

See README.md for the supported feature set and docs/LIMITATIONS.md for
what is deliberately not implemented yet.
""",
    'author': 'Juan Jose Carracedo',
    'website': 'https://github.com/DonsWayo/odoo-addons',
    'license': 'LGPL-3',
    # Apps Store listing. The first entry is the cover/thumbnail; the first
    # whose name ends in _screenshot is blown up as the large image, which
    # Odoo intends for "a full demo page and not your company logo larger" —
    # so that slot is a real screenshot of the UI, not the banner.
    'images': [
        'static/description/cover.png',
        'static/description/repositories_screenshot.png',
        'static/description/kanban.png',
        'static/description/pull_requests.png',
        'static/description/commits.png',
        'static/description/repository_form.png',
    ],
    'support': 'https://github.com/DonsWayo/odoo-addons/issues',
    'depends': [
        'base',
        'mail',
        'portal',
        'web',
        'project',
    ],
    'data': [
        'security/git_security.xml',
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        'data/initial_data.xml',
        'data/sequences.xml',
        'views/repository_views.xml',
        'views/branch_views.xml',
        'views/commit_views.xml',
        'views/pull_request_views.xml',
        'views/pat_views.xml',
        'views/deploy_key_views.xml',
        'views/webhook_views.xml',
        'wizards/clone_wizard_views.xml',
        'views/portal_templates.xml',
        'views/portal_commit.xml',
        'views/mail_templates.xml',
        'views/menus.xml',
    ],
    'demo': ['data/demo_data.xml'],
    'installable': True,
    'application': True,
    'post_init_hook': '_post_init_hook',
    'uninstall_hook': '_uninstall_hook',
    'assets': {
        'web.assets_backend': [
            'odoogit/static/src/scss/odoogit.scss',
        ],
        'web.assets_tests': [
            'odoogit/static/src/tours/**/*',
        ],
        'web.assets_frontend': [
            'odoogit/static/src/scss/portal.scss',
        ],
    },
}
