from odoo import fields, models


class GitImportWizard(models.TransientModel):
    _name = 'git.import.wizard'
    _description = 'Import Repository Wizard'

    name = fields.Char(string='Repository Name', required=True)
    source_url = fields.Char(
        string='Source URL',
        required=True,
        help="Remote to import from. https://, http://, git://, ssh:// or "
             "user@host:path.")
    visibility = fields.Selection([
        ('private', 'Private'),
        ('internal', 'Internal'),
    ], default='private', required=True)

    def action_import(self):
        """Create the repository and pull the source's branches into it.

        This used to create an empty record and tell the user that import
        "is not yet implemented", while source_url was a required field that
        nothing read. The fetch reuses git.repository._fetch_refs_from(),
        which validates the URL against the same allowlist as mirroring —
        git treats ext:// as a command and file:// as a local path.
        """
        self.ensure_one()
        repo = self.env['git.repository'].create({
            'name': self.name,
            'visibility': self.visibility,
            'owner_id': self.env.user.id,
        })
        repo._init_git_repo()
        # raises UserError on a hostile or unreachable URL, rolling the
        # whole wizard back rather than leaving an empty repository behind
        repo._fetch_refs_from(self.source_url)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'git.repository',
            'res_id': repo.id,
            'view_mode': 'form',
            'target': 'current',
        }
