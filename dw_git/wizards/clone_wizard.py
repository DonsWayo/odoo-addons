from odoo import fields, models


class GitCloneWizard(models.TransientModel):
    _name = 'git.clone.wizard'
    _description = 'Clone Repository Wizard'

    repository_id = fields.Many2one('git.repository', required=True, readonly=True)
    clone_url_http = fields.Char(string='HTTPS Clone URL', readonly=True)
    clone_url_ssh = fields.Char(string='SSH Clone URL', readonly=True)
    token_help = fields.Text(
        string='Authentication',
        default="For HTTPS, use your Personal Access Token as password.\n"
                "Example: git clone https://<username>:<pat_token>@host/git/user/repo.git",
        readonly=True
    )

    # action_copy_http is gone. It showed "HTTPS clone URL copied to
    # clipboard!" and copied nothing — a server-side Python method cannot
    # reach the clipboard. It was also unreachable: no view references this
    # wizard. The same class of lie as the webhook button that reported
    # "Test webhook sent!" without sending.
    #
    # Copying is a client-side concern, so it is done client-side: the
    # repository form renders the clone URLs with Odoo's own
    # CopyClipboardChar widget, which actually copies and says so.
