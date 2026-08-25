# -*- coding: utf-8 -*-
"""Seed realistic data for Git Hosting QA: real bare git repo + branches + commits + PR.

Run inside the container:
    odoo shell -d odoo --db_host=postgres --db_user=odoo --db_password=odoo \
        < /opt/qa/seed.py

Idempotent: skips records that already exist (matched by name).
"""
import os
import subprocess
from datetime import datetime, timezone


def odoo_dt(iso):
    """ISO8601 (git %aI) -> naive UTC string for Odoo Datetime."""
    dt = datetime.fromisoformat(iso)
    return dt.astimezone(timezone.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')

REPO_NAME = 'hello-world'
OWNER_LOGIN = 'admin'
BASE = '/var/lib/odoo/git/repos'
BARE = os.path.join(BASE, OWNER_LOGIN, REPO_NAME + '.git')
WORK = '/tmp/seed-work-' + REPO_NAME

Commit = env['git.commit']
Repo = env['git.repository']
Branch = env['git.branch']
PR = env['git.pull_request']
User = env['res.users']

existing = Repo.search([('name', '=', REPO_NAME)])
if existing:
    print('SEED: repository %r already exists, skipping' % REPO_NAME)
else:
    # ---------------------------------------------------------- real git repo
    def git(*args, cwd=None):
        cmd = ['git'] + list(args)
        subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)

    subprocess.run(['rm', '-rf', WORK], check=True)
    os.makedirs(BASE, exist_ok=True)
    git('init', '-b', 'main', WORK)
    git('config', 'user.email', 'dev@example.com', cwd=WORK)
    git('config', 'user.name', 'Dev Author', cwd=WORK)

    def commit(msg, files):
        for path, content in files.items():
            full = os.path.join(WORK, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'w') as f:
                f.write(content)
        git('add', '.', cwd=WORK)
        git('commit', '-m', msg, cwd=WORK)

    commit('Initial commit', {
        'README.md': '# Hello World\n\nDemo repo for Git Hosting QA.\n',
    })
    commit('Add python greeting module', {
        'hello.py': 'def greet(name):\n    return f"Hello, {name}!"\n',
    })
    commit('Add math utils (add, mul)', {
        'mathutil.py': 'def add(a, b):\n    return a + b\n\ndef mul(a, b):\n    return a * b\n',
    })
    git('checkout', '-b', 'feature-greetings', cwd=WORK)
    commit('Add spanish greeting', {
        'greetings_es.py': 'def hola(name):\n    return "Hola, " + name\n',
    })
    main_sha = subprocess.run(
        ['git', 'rev-parse', 'main'], cwd=WORK, capture_output=True, text=True
    ).stdout.strip()
    feat_sha = subprocess.run(
        ['git', 'rev-parse', 'feature-greetings'], cwd=WORK, capture_output=True, text=True
    ).stdout.strip()

    # bare clone to the served path
    subprocess.run(['rm', '-rf', BARE], check=True)
    os.makedirs(os.path.dirname(BARE), exist_ok=True)
    git('clone', '--bare', WORK, BARE)

    # ---------------------------------------------------------- odoo records
    admin = User.search([('login', '=', OWNER_LOGIN)], limit=1)
    repo = Repo.create({
        'name': REPO_NAME,
        'description': 'Demo repository seeded for QA with a real git history.',
        'owner_id': admin.id,
        'visibility': 'internal',
        'default_branch': 'main',
    })
    Branch.create({'name': 'main', 'repository_id': repo.id, 'commit_sha': main_sha})
    Branch.create({'name': 'feature-greetings', 'repository_id': repo.id, 'commit_sha': feat_sha})

    for sha, msg in [
        (main_sha, 'Initial commit'),
    ]:
        pass  # commits synced below

    # mirror commits into odoo (both branches, walking real history)
    seen = []
    for ref in (main_sha, feat_sha):
        out = subprocess.run(
            ['git', 'log', '--format=%H%x00%an%x00%ae%x00%aI%x00%s', ref],
            cwd=WORK, capture_output=True, text=True).stdout
        for line in out.splitlines():
            if not line or line in seen:
                continue
            seen.append(line)
            sha, an, ae, ad, subj = line.split('\x00')
            if not Commit.search([('sha', '=', sha)], limit=1):
                c = Commit.create({
                    'sha': sha, 'message': subj, 'author_name': an,
                    'author_email': ae, 'committed_date': odoo_dt(ad),
                    'repository_id': repo.id,
                })
                # link branches containing this commit
                containing = subprocess.run(
                    ['git', 'branch', '-a', '--contains', sha],
                    cwd=WORK, capture_output=True, text=True).stdout
                bnames = [b.strip().lstrip('* ').replace('remotes/origin/', '')
                          for b in containing.splitlines() if b.strip()]
                c.branch_ids = [(6, 0, Branch.search([
                    ('name', 'in', bnames), ('repository_id', '=', repo.id)]).ids)]

    main_b = Branch.search([('name', '=', 'main'), ('repository_id', '=', repo.id)], limit=1)
    feat_b = Branch.search([('name', '=', 'feature-greetings'), ('repository_id', '=', repo.id)], limit=1)

    PR.create({
        'title': 'Add spanish greeting',
        'description': '<p>Adds <code>greetings_es.py</code> with a spanish greeting helper.</p>',
        'state': 'open',
        'repository_id': repo.id,
        'source_branch_id': feat_b.id,
        'target_branch_id': main_b.id,
        'author_id': admin.id,
    })
    # bob as member (collaborator E2E path)
    bob = User.search([('login', '=', 'bob')])
    if bob:
        repo.write({'member_ids': [(4, bob.id)]})
    print('SEED: created repo=%s branches=2 commits=%d pr=1' % (repo.name, len(seen)))

env.cr.commit()
print('SEED: done')
