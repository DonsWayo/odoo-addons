{
    'name': 'Git Hosting',
    'version': '19.0.1.8.0',
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
- Read-only file browser: branch selector, directory tree, syntax highlighting
- Pull request diffs rendered in colour, plus the raw unified patch
- Email and activity notifications on PR created, review requested,
  merged and closed
- Personal Access Tokens for git clone/push over HTTPS
- Deploy keys for CI/CD
- Webhooks with HMAC-SHA256 signatures and delivery history
- mail.thread integration on repositories and pull requests
- Translation template included (i18n/dw_git.pot)

The Documentation tab covers installation, configuration and the known
limitations. Neither README.md nor docs/ ships inside the module, so the
full feature set and the limitations list live at
https://github.com/DonsWayo/odoo-addons
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
        'static/description/pr_diff.png',
        'static/description/file_browser.png',
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
        'views/portal_pull_request.xml',
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
            'dw_git/static/src/scss/dw_git.scss',
            'dw_git/static/src/components/diff_viewer/diff_viewer_field.js',
            'dw_git/static/src/components/diff_viewer/diff_viewer_field.xml',
            'dw_git/static/src/components/file_browser/file_browser.js',
            'dw_git/static/src/components/file_browser/file_browser.xml',
        ],
        'web.assets_tests': [
            'dw_git/static/src/tours/**/*',
        ],
        'web.assets_frontend': [
            'dw_git/static/src/scss/portal.scss',
        ],
    },
}
