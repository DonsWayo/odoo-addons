"""Shared helpers for dw_git test suite."""
import itertools
import subprocess

from odoo.tests import TransactionCase

_counter = itertools.count(1)


class DwGitCommon(TransactionCase):
    """Base class with user/repo factories."""

    def setUp(self):
        super().setUp()
        self.User = self.env['res.users']
        self.Repo = self.env['git.repository']
        self.Branch = self.env['git.branch']
        self.Commit = self.env['git.commit']
        try:
            self.PR = self.env['git.pull_request']
        except KeyError:
            import logging
            logging.getLogger(__name__).error(
                'MODELS PRESENT: %s',
                sorted(m for m in self.env.registry.models if m.startswith('git')))
            raise
        self.PAT = self.env['git.personal_access_token']
        self.DeployKey = self.env['git.deploy_key']

        self.user = self._create_user('owner')
        self.other = self._create_user('other')

    def _create_user(self, login, groups=None):
        vals = {'name': login.title(), 'login': login, 'email': f'{login}@test.com'}
        if groups:
            vals['group_ids'] = [(4, self.env.ref(g).id) for g in groups]
        return self.User.create(vals)

    def _repo(self, name='repo', **kw):
        unique = next(_counter)
        vals = {'name': f'{name}-{unique}', 'owner_id': self.user.id}
        vals.update(kw)
        return self.Repo.create(vals)

    def _branch(self, repo, name='main', sha=None, **kw):
        vals = {
            'name': name,
            'repository_id': repo.id,
            'commit_sha': sha or 'a' * 40,
        }
        vals.update(kw)
        return self.Branch.create(vals)

    @staticmethod
    def _git(*args, cwd=None):
        cmd = ['git']
        if cwd:
            cmd += ['-C', cwd]
        cmd += list(args)
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
