# -*- coding: utf-8 -*-
{
    'name': 'OdooGit',
    'version': '19.0.1.0.0',
    'category': 'Tools/Development',
    'summary': 'OdooGit — private Git repository hosting with native Odoo integration',
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
            'odoogit/static/src/components/**/*',
            'odoogit/static/src/services/**/*',
        ],
        'web.assets_tests': [
            'odoogit/static/src/tours/**/*',
        ],
        'web.assets_frontend': [
            'odoogit/static/src/scss/portal.scss',
        ],
    },
}