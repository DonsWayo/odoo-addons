# Releasing OdooGit

## Versioning

Odoo addons carry the series in the version, so OdooGit uses:

```
19.0 . MAJOR . MINOR . PATCH
└──┬─┘   └──────┬──────┘
 Odoo series   module version (semver-ish)
```

- **PATCH** — bug fixes, no schema or behaviour change for existing data.
- **MINOR** — new fields, models, endpoints or views; additive.
- **MAJOR** — anything that requires operator action: removed fields, changed
  constraints, changed access semantics.

The version lives in exactly one place: `odoogit/__manifest__.py`. Odoo
compares it against `ir_module_module.latest_version` to decide whether a
database needs upgrading, so **bump it in the same commit as the change** — an
unbumped module will not re-run its data files on `-u`.

## Before tagging

Run the gate. Do not tag on a red result.

```bash
make release-check
```

That is: XML parse, ruff, a clean install into a throwaway database, the
upgrade path on the populated one, the full suite, and the browser flows —
dropping the throwaway database before the browser pass, because a second
database makes Odoo serve `/web/database/selector` and every flow fails at
"Password: element never appeared".

The individual steps, if you need them:

```bash
make xml lint
make install DB=release_check
make upgrade
make test
make qa
```

Expect `0 failed, 0 error(s)`, and no `Invalid field`, `Template not found` or
`have no access rules` lines in the install logs. Those three are warnings
Odoo will happily boot through — the August 2026 audit found four separate
defects announced only by a line like that.

Then the browser pass — but **drop the release-check database first**:

```bash
docker compose stop odoo
docker compose exec -T postgres psql -U odoo -d postgres \
  -c "DROP DATABASE IF EXISTS release_check;"
docker compose start odoo && sleep 12

python3 qa/run.py     # 6 flows, all must be green
```

With more than one database present, Odoo serves `/web/database/selector`
instead of the login form and every browser flow fails at "Password: element
never appeared". That is the extra database, not a regression.

## Cutting the release

1. Bump `'version'` in `odoogit/__manifest__.py`.
2. Move the `[Unreleased]` entries in `CHANGELOG.md` under a new
   `[<version>] — <date>` heading, and add the compare link at the bottom.
3. Commit: `chore(release): 19.0.x.y.z`.
4. Tag and push, **including the series branch**:

   ```bash
   git tag -a v19.0.x.y.z -m "OdooGit 19.0.x.y.z"
   git push origin main --follow-tags
   git branch -f 19.0 main && git push origin 19.0
   ```

   `19.0` is the branch registered with the Odoo Apps Store
   (`ssh://git@github.com/DonsWayo/odoogit.git#19.0`), because Odoo requires
   the branch name to match the series. Forget this and the store keeps
   serving the previous release, with nothing to tell you it has gone stale.

5. Publish the GitHub release with the changelog section as the body:

   ```bash
   gh release create v19.0.x.y.z \
     --title "OdooGit 19.0.x.y.z" \
     --notes-file <(awk '/^## \[19\.0\.x\.y\.z\]/{f=1;next} /^## \[/{f=0} f' CHANGELOG.md)
   ```

## What belongs in release notes

Each entry names the **observable symptom**, not the patch. "PATs no longer
unlock repositories their owner cannot access" tells an operator whether they
were exposed; "fixed `_get_repo`" does not.

Anything needing operator action goes under **Changed** or **Removed**, with
the action spelled out: a changed constraint, a moved route, a dropped
dependency, a parameter that stops being overwritten.

## Upgrade notes for 19.0.1.1.0

Operators coming from `19.0.1.0.0` should know:

- **Rotate every Personal Access Token and deploy key.** Raw secrets were
  previously kept in the database beside their hash. This upgrade drops those
  columns, but any secret created before it should be treated as exposed —
  especially since non-manager employees could read every deploy key.
- `POST /api/git/repositories` moved to `POST /api/git/repositories/create`,
  and all API routes are JSON-RPC POST rather than GET.
- Repository names are unique per owner instead of per company. No migration
  needed — the constraint only becomes more permissive.
- `odoogit.repo_base_path` is no longer reset on upgrade. If an earlier
  upgrade reset it and repositories appeared to vanish, the files are still at
  the path you originally configured.
