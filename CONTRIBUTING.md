# Contributing to OdooGit

## Before you start

Read [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md). Webhook delivery, SSH
transport and push-time branch protection are deliberately absent, each for a
reason — a PR that adds one is welcome, but it needs a design discussion
first, not just an implementation.

If you use a coding agent, point it at [`AGENTS.md`](AGENTS.md) and
[`.agents/skills/odoo19-dev/SKILL.md`](.agents/skills/odoo19-dev/SKILL.md).
Those encode every Odoo 17→19 breaking change this module has already hit;
ignoring them costs a rebuild cycle per mistake.

## Setup

```bash
git clone https://github.com/DonsWayo/odoogit.git
cd odoogit
docker compose build && docker compose up -d
docker compose exec odoo odoo -d odoo -i odoogit --stop-after-init \
  --db_host=postgres --db_user=odoo --db_password=odoo --workers=0
```

The module is baked into the image, so code changes normally need a rebuild.
For a faster loop:

```bash
cp docker-compose.override.yml.example docker-compose.override.yml
docker compose up -d --force-recreate odoo
# then: edit, docker compose restart odoo
```

On colima/Lima, confirm the mount actually populated before trusting it —
a stale virtiofs share silently mounts an empty directory:

```bash
docker compose exec odoo ls /mnt/extra-addons/odoogit
```

## The loop

```bash
# 1. XML must parse before you build — a bad view fails the install
python3 -c "from xml.etree import ElementTree as ET; import glob; \
[ET.parse(f) for f in glob.glob('odoogit/**/*.xml', recursive=True)]; print('XML OK')"

# 2. upgrade
docker compose exec odoo odoo -d odoo -u odoogit --stop-after-init \
  --db_host=postgres --db_user=odoo --db_password=odoo --workers=0

# 3. tests
docker compose exec odoo odoo -d odoo --test-enable --test-tags /odoogit \
  --stop-after-init --http-port=8070 \
  --db_host=postgres --db_user=odoo --db_password=odoo --workers=0

# 4. browser QA, if you touched a view or template
python3 qa/run.py
```

### Read the install log, not just the test result

Odoo boots straight through these three lines. Each one hid a real defect in
the August 2026 audit, while the suite reported 54/54 green:

- `Invalid field <model>.<field>` — code references a field that does not exist
- `Template not found: '<id>'` — a renamed or missing QWeb template
- `The models [...] have no access rules` — a model anyone can read and write

CI fails on all three.

## Testing rules

The audit's central finding was that a green suite proves nothing about code
it never calls. So:

- **A new controller route comes with an HTTP test.** Eight endpoints returned
  405 or 500 on first call while looking healthy.
- **A new x2many or m2m field comes with a test that populates it.** One
  unpopulated `group_ids` hid a renamed field for months.
- **A change to access or permissions comes with a test acting as a second
  user.** Authorisation bugs surface no other way.
- **Build fixtures by calling production code.** Seeding repositories with
  `shutil.copytree()` instead of `_init_git_repo()` meant that method had
  never run under test — it raised `NameError` on its first line.

New tests go in the file matching their kind: `test_unit_models.py`,
`test_integration_git.py` (real `git` binary), `test_e2e_tours.py` (browser),
or `test_regressions.py` (one test per fixed defect, with the symptom in the
docstring).

Write the failing test first and confirm it fails for the reason you expect.

## Commits and pull requests

Conventional commits: `fix:`, `feat:`, `docs:`, `test:`, `chore:`, `refactor:`,
with `!` or a `BREAKING CHANGE:` footer for anything requiring operator action.

Describe the **observable symptom**, not the patch. "Portal pages no longer
return 500" tells a reader whether they were affected; "fixed portal.py" does
not.

Update `CHANGELOG.md` under `[Unreleased]` for anything user-visible, and bump
`odoogit/__manifest__.py` if the change must run on upgrade — Odoo compares
that version against `ir_module_module.latest_version` to decide.

## Releases

See [`docs/RELEASING.md`](docs/RELEASING.md). Tags are `v19.0.x.y.z` and must
match the manifest version; CI enforces it.

## License

Contributions are licensed under LGPL-3, the same as Odoo.
