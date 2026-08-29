"""Seed realistic data for Git Hosting QA.

Every repository this creates is a *real* bare git repository on disk with
real commits, real branches and pull requests whose diffs actually render.

That matters more than it sounds. The previous version of this script
seeded one real repository; the rest of the demo data was records with no
git repository behind them, so their pull requests showed changed files
with line counts and an empty diff — the UI describing a history that was
never pushed. Anything seeded here goes through the same code path a real
push does, so if a diff does not render locally, that is a bug and not a
gap in the fixture.

Run with:  make seed          (add DW_GIT_RESET=1 to wipe existing data)
"""
import os
import subprocess
from datetime import datetime

# Where repositories live is the model's business, not this script's —
# see build_repo. Kept only for the reset sweep below, which removes
# directories for records that are being deleted.
BASE = '/var/lib/odoo/git/repos'
RESET = os.environ.get('DW_GIT_RESET') == '1'

Repo = env['git.repository']
Branch = env['git.branch']
Commit = env['git.commit']
PR = env['git.pull_request']
User = env['res.users']

admin = env.ref('base.user_admin')


def odoo_dt(iso):
    return datetime.fromisoformat(iso).strftime('%Y-%m-%d %H:%M:%S')


def git(*args, cwd=None):
    subprocess.run(['git'] + list(args), cwd=cwd, check=True,
                   capture_output=True)


def rev(ref, cwd):
    return subprocess.run(['git', 'rev-parse', ref], cwd=cwd,
                          capture_output=True, text=True).stdout.strip()


def build_repo(spec):
    """Create one repository end to end: disk, records, branches, PR."""
    name = spec['name']
    work = f'/tmp/seed-work-{name}'

    subprocess.run(['rm', '-rf', work], check=True)
    os.makedirs(work, exist_ok=True)
    git('init', '-q', '-b', 'main', cwd=work)
    git('config', 'user.email', 'seed@example.com', cwd=work)
    git('config', 'user.name', 'Seed Author', cwd=work)

    def commit(message, files):
        for path, content in files.items():
            full = os.path.join(work, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'w') as fh:
                fh.write(content)
        git('add', '-A', cwd=work)
        git('commit', '-m', message, cwd=work)

    for message, files in spec['commits']:
        commit(message, files)
    main_sha = rev('HEAD', work)

    git('checkout', '-q', '-b', spec['branch'], cwd=work)
    for message, files in spec['feature_commits']:
        commit(message, files)
    feat_sha = rev('HEAD', work)

    # The record comes FIRST, because the path is keyed on its id. Bare
    # repos used to live at <base>/<owner.login>/<name>.git and this script
    # built that path by hand; they now live at <base>/<id>.git, which does
    # not exist until the record does. Ask the model where the repository
    # belongs instead of constructing it here — that is the whole point of
    # keying on an immutable id, and rebuilding the old layout by hand put
    # every seeded repo somewhere the server does not look.
    repo = Repo.create({
        'name': name,
        'description': spec['description'],
        'owner_id': admin.id,
        'visibility': spec.get('visibility', 'internal'),
        'default_branch': 'main',
    })
    bare = repo._get_repo_path()
    subprocess.run(['rm', '-rf', bare], check=True)
    os.makedirs(os.path.dirname(bare), exist_ok=True)
    git('clone', '-q', '--bare', work, bare)
    git('symbolic-ref', 'HEAD', 'refs/heads/main', cwd=bare)
    main_b = Branch.create({'name': 'main', 'repository_id': repo.id,
                            'commit_sha': main_sha})
    feat_b = Branch.create({'name': spec['branch'], 'repository_id': repo.id,
                            'commit_sha': feat_sha})

    # mirror the real history into Odoo
    log = subprocess.run(
        ['git', 'log', '--all', '--format=%H%x00%an%x00%ae%x00%aI%x00%s'],
        cwd=work, capture_output=True, text=True).stdout
    made = 0
    for line in log.splitlines():
        if not line.strip():
            continue
        sha, an, ae, ad, subj = line.split('\x00')
        if Commit.search_count([('sha', '=', sha),
                                ('repository_id', '=', repo.id)]):
            continue
        Commit.create({
            'sha': sha, 'message': subj, 'author_name': an,
            'author_email': ae, 'committed_date': odoo_dt(ad),
            'repository_id': repo.id,
        })
        made += 1

    pr = PR.create({
        'title': spec['pr_title'],
        'description': spec['pr_description'],
        'state': 'open',
        'repository_id': repo.id,
        'source_branch_id': feat_b.id,
        'target_branch_id': main_b.id,
        'author_id': admin.id,
    })
    # the point of the exercise: real diffs, via the real code path
    pr.action_refresh_changes()

    bob = User.search([('login', '=', 'bob')], limit=1)
    if bob:
        repo.write({'member_ids': [(4, bob.id)]})

    subprocess.run(['rm', '-rf', work], check=True)
    return repo, pr, made


SPECS = [
    {
        'name': 'hello-world',
        'description': 'Greeting helpers, used as the QA reference repository.',
        'branch': 'feature/spanish-greeting',
        'commits': [
            ('Initial commit', {'README.md': '# Hello World\n\nDemo repository for Git Hosting QA.\n'}),
            ('Add python greeting module', {'hello.py': 'def greet(name):\n    return f"Hello, {name}!"\n'}),
            ('Add math utils', {'mathutil.py': 'def add(a, b):\n    return a + b\n\n\ndef mul(a, b):\n    return a * b\n'}),
        ],
        'feature_commits': [
            ('Add spanish greeting', {
                'greetings_es.py': 'def hola(name):\n    return f"Hola, {name}!"\n',
            }),
        ],
        'pr_title': 'Add spanish greeting',
        'pr_description': '<p>Adds <code>greetings_es.py</code> with a spanish greeting helper.</p>',
    },
    {
        'name': 'payments-api',
        'description': 'Payment gateway integration service.',
        'branch': 'feature/validate-amounts',
        'commits': [
            ('Initial commit', {'README.md': '# payments-api\n\nPayment gateway integration.\n'}),
            ('Add charge endpoint', {
                'src/service.py': (
                    '"""Payment service."""\n\n\n'
                    'def charge(amount, currency="EUR"):\n'
                    '    return {"amount": amount, "currency": currency, "status": "ok"}\n'
                ),
            }),
        ],
        'feature_commits': [
            ('Reject non-positive amounts and unknown currencies', {
                'src/service.py': (
                    '"""Payment service."""\n\n'
                    'SUPPORTED = ("EUR", "USD", "GBP")\n\n\n'
                    'def charge(amount, currency="EUR"):\n'
                    '    """Charge an amount, refusing anything we cannot settle."""\n'
                    '    if amount <= 0:\n'
                    '        raise ValueError("amount must be positive")\n'
                    '    if currency not in SUPPORTED:\n'
                    '        raise ValueError(f"unsupported currency: {currency}")\n'
                    '    return {"amount": amount, "currency": currency, "status": "ok"}\n'
                ),
                'tests/test_service.py': (
                    'import pytest\n\n'
                    'from src.service import charge\n\n\n'
                    'def test_charges_a_valid_amount():\n'
                    '    assert charge(10)["status"] == "ok"\n\n\n'
                    'def test_rejects_zero():\n'
                    '    with pytest.raises(ValueError):\n'
                    '        charge(0)\n\n\n'
                    'def test_rejects_unknown_currency():\n'
                    '    with pytest.raises(ValueError):\n'
                    '        charge(10, "XYZ")\n'
                ),
            }),
        ],
        'pr_title': 'Validate charge amounts and currencies',
        'pr_description': '<p>Refuses non-positive amounts and unsupported currencies, with tests covering both.</p>',
    },
    {
        'name': 'design-system',
        'description': 'Shared component library.',
        'branch': 'feature/button-variants',
        'visibility': 'private',
        'commits': [
            ('Initial commit', {'README.md': '# design-system\n\nShared components.\n'}),
            ('Add base button', {
                'components/button.css': '.btn {\n  border-radius: 4px;\n  padding: 8px 16px;\n}\n',
            }),
        ],
        'feature_commits': [
            ('Add primary and danger button variants', {
                'components/button.css': (
                    '.btn {\n  border-radius: 4px;\n  padding: 8px 16px;\n}\n\n'
                    '.btn--primary {\n  background: #714b67;\n  color: #fff;\n}\n\n'
                    '.btn--danger {\n  background: #d9534f;\n  color: #fff;\n}\n'
                ),
            }),
        ],
        'pr_title': 'Add primary and danger button variants',
        'pr_description': '<p>Two variants on the base button, matching the brand palette.</p>',
    },
]


# ---------------------------------------------------------- real project
#: A genuinely real repository, mirrored from GitHub. The three synthetic
#: repos above are deterministic and fast, which is what you want when
#: asserting a specific diff — but they are also tiny, and tiny fixtures
#: hide whole categories of problem: a file tree that only ever has five
#: entries never exercises directory nesting, a two-line diff never
#: exercises the viewer's width or scrolling, and 3 commits never exercise
#: pagination or the 50-commit sync ceiling.
#:
#: Override with DW_GIT_SEED_MIRROR_URL, or skip entirely with
#: DW_GIT_SEED_MIRROR=0 (offline).
#: `or` rather than a get() default throughout: make passes these through
#: as empty strings when the caller did not set them, and an empty string
#: is *present*, so a get() default never applies. That silently disabled
#: the mirror on the first run and printed nothing about it.
#: This module's own repository, by default — dogfooding. Its history is
#: real, it mixes Python, XML, JS and SCSS (so syntax highlighting is
#: exercised across languages rather than one), and its tree is deep
#: enough that the file browser has to walk directories.
MIRROR_URL = (os.environ.get('DW_GIT_SEED_MIRROR_URL')
              or 'https://github.com/DonsWayo/odoo-addons.git')
MIRROR_NAME = os.environ.get('DW_GIT_SEED_MIRROR_NAME') or 'odoo-addons'
#: how far back the PR's target branch sits — a real, multi-file diff
MIRROR_PR_DEPTH = int(os.environ.get('DW_GIT_SEED_MIRROR_DEPTH') or '15')


def mirror_real_project():
    """Mirror a real GitHub repository and open a real pull request on it.

    Everything goes through the same code paths a genuine push would:
    the bare repo is served by git http-backend, branches and commits are
    imported by _sync_from_git(), and the diff is produced by
    action_refresh_changes() against the real merge base.
    """
    # Same as build_repo: the record first, because the path is keyed on
    # its id and the model is the only thing that knows it.
    repo = Repo.create({
        'name': MIRROR_NAME,
        'description': 'Mirrored from %s — real history, real diffs.'
                       % MIRROR_URL,
        'owner_id': admin.id,
        'visibility': 'internal',
        'is_mirror': True,
        'mirror_url': MIRROR_URL,
    })
    bare = repo._get_repo_path()
    subprocess.run(['rm', '-rf', bare], check=True)
    os.makedirs(os.path.dirname(bare), exist_ok=True)

    print('SEED: mirroring %s (this needs network)' % MIRROR_URL)
    try:
        # a full bare clone, not a blobless one: this repo is *served* over
        # Smart HTTP, and a partial clone cannot answer a fetch for blobs
        # it does not have.
        subprocess.run(['git', 'clone', '-q', '--bare', MIRROR_URL, bare],
                       check=True, capture_output=True, timeout=600)
    except Exception as exc:
        print('SEED: mirror skipped — %s' % exc)
        repo.unlink()
        return None

    head = subprocess.run(
        ['git', 'symbolic-ref', '--short', 'HEAD'], cwd=bare,
        capture_output=True, text=True).stdout.strip() or 'main'

    # a real target branch, N commits behind the default branch, so the
    # pull request carries a genuine multi-file diff instead of one hunk
    target_name = 'release/behind'
    base_sha = subprocess.run(
        ['git', 'rev-parse', f'{head}~{MIRROR_PR_DEPTH}'], cwd=bare,
        capture_output=True, text=True).stdout.strip()
    if base_sha:
        subprocess.run(['git', 'update-ref',
                        f'refs/heads/{target_name}', base_sha],
                       cwd=bare, check=True, capture_output=True)

    repo.write({'default_branch': head})
    # the real import path, not hand-built records
    repo._sync_from_git()

    Branch_ = env['git.branch']
    src = Branch_.search([('repository_id', '=', repo.id),
                          ('name', '=', head)], limit=1)
    tgt = Branch_.search([('repository_id', '=', repo.id),
                          ('name', '=', target_name)], limit=1)
    pr = None
    if src and tgt:
        pr = PR.create({
            'title': 'Ship the last %d commits to %s'
                     % (MIRROR_PR_DEPTH, target_name),
            'description': '<p>A real pull request against real upstream '
                           'history, for exercising the diff viewer and the '
                           'file browser at a realistic size.</p>',
            'state': 'open',
            'repository_id': repo.id,
            'source_branch_id': src.id,
            'target_branch_id': tgt.id,
            'author_id': admin.id,
        })
        pr.action_refresh_changes()

    bob = User.search([('login', '=', 'bob')], limit=1)
    if bob:
        repo.write({'member_ids': [(4, bob.id)]})
    return repo, pr

def configure_local_mail():
    """Point Odoo at the mailpit container so notifications are readable.

    Without an SMTP server Odoo queues mail and nobody ever sees it, which
    is how two notification bugs survived here: templates that rendered
    their own source, and mail addressed to nobody. Both were only obvious
    once the actual message could be read.
    """
    Server = env['ir.mail_server']
    vals = {'name': 'Mailpit (local)', 'smtp_host': 'mailpit',
            'smtp_port': 1025, 'smtp_encryption': 'none', 'sequence': 1}
    existing = Server.search([('name', '=', vals['name'])], limit=1)
    if existing:
        existing.write(vals)
    else:
        Server.create(vals)
    icp = env['ir.config_parameter'].sudo()
    icp.set_param('mail.default.from', 'git-hosting@localhost')
    icp.set_param('mail.catchall.domain', 'localhost')
    print('SEED: outgoing mail -> mailpit:1025 (read it at http://localhost:8025)')


# ---------------------------------------------------------------- run
if RESET:
    old = Repo.search([])
    print('SEED: reset — removing %d repository records and their git dirs'
          % len(old))
    for repo in old:
        path = repo._get_repo_path()
        subprocess.run(['rm', '-rf', path], check=False)
    # children cascade from the repository, except PRs which RESTRICT on
    # branches; drop them first so the repository delete can proceed.
    PR.search([]).unlink()
    old.unlink()

configure_local_mail()

report = []
for spec in SPECS:
    if Repo.search_count([('name', '=', spec['name'])]):
        print('SEED: %s already exists, skipping (DW_GIT_RESET=1 to rebuild)'
              % spec['name'])
        continue
    repo, pr, commits = build_repo(spec)
    patched = len(pr.file_ids.filtered('patch'))
    report.append((repo.name, commits, len(pr.file_ids), patched))

if (os.environ.get('DW_GIT_SEED_MIRROR') or '1') == '1':
    if Repo.search_count([('name', '=', MIRROR_NAME)]):
        print('SEED: %s already exists, skipping (DW_GIT_RESET=1 to rebuild)'
              % MIRROR_NAME)
    else:
        result = mirror_real_project()
        if result:
            repo, pr = result
            files = len(pr.file_ids) if pr else 0
            patched = len(pr.file_ids.filtered('patch')) if pr else 0
            report.append((repo.name, repo.commit_count, files, patched))
        else:
            print('SEED: WARNING — the real-project mirror did NOT run. '
                  'The demo data is synthetic only.')
else:
    print('SEED: real-project mirror disabled (DW_GIT_SEED_MIRROR=0)')

env.cr.commit()

print('\nSEED: result')
for name, commits, files, patched in report:
    ok = 'ok' if files and patched == files else 'INCOMPLETE'
    print('  %-16s commits=%-3d pr_files=%-3d with_diff=%-3d  %s'
          % (name, commits, files, patched, ok))
print('SEED: done')
