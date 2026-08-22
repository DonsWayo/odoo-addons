# -*- coding: utf-8 -*-
{
    'name': 'Git Hosting',
    'version': '18.0.1.0.0',
    'category': 'Tools/Development',
    'summary': 'Private Git repository hosting with native Odoo integration',
    'description': """
Git hosting module for Odoo 18/19 providing:
- Private/internal repositories with Git Smart HTTP
- Branch protection, merge requests, code reviews
- File browser, diff viewer, commit history
- Personal Access Tokens for CLI access
- Deploy keys for CI/CD
- Webhooks for external integrations
- Portal access for external collaborators
- Real-time notifications via bus.bus
- Full mail.thread integration for discussions
""",
    'author': 'Your Company',
    'website': 'https://yourcompany.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'portal',
        'web',
        'bus',
        'auth_oauth',
        'project',
        'hr',
        'base_setup',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/git_security.xml',
        'security/record_rules.xml',
        'data/initial_data.xml',
        'data/sequences.xml',
        'views/menus.xml',
        'views/repository_views.xml',
        'views/branch_views.xml',
        'views/commit_views.xml',
        'views/pat_views.xml',
        'views/deploy_key_views.xml',
        'views/webhook_views.xml',
        'views/portal_templates.xml',
        'views/portal_commit.xml',
        'views/mail_templates.xml',
        'wizard/clone_wizard_views.xml',
    ],
    'demo': ['data/demo_data.xml'],
    'installable': True,
    'application': True,
    'post_init_hook': '_post_init_hook',
    'uninstall_hook': '_uninstall_hook',
    'assets': {
        'web.assets_backend': [
            'git_hosting/static/src/scss/git_hosting.scss',
            'git_hosting/static/src/components/**/*',
            'git_hosting/static/src/services/**/*',
        ],
        'web.assets_frontend': [
            'git_hosting/static/src/scss/portal.scss',
        ],
    },
}