## What this changes

<!-- The observable behaviour, not the diff. "Portal pages no longer 500"
     beats "fixed portal.py". -->

## Why

<!-- Link the issue, or describe the symptom you hit. -->

Closes #

## How it was verified

<!-- Paste the actual output. Claims without evidence get sent back. -->

```
docker compose exec odoo odoo -d odoo -u dw_git --test-enable --test-tags /dw_git \
  --stop-after-init --http-port=8070 \
  --db_host=postgres --db_user=odoo --db_password=odoo --workers=0
```

- [ ] Test suite green (`0 failed, 0 error(s)`) — paste the count
- [ ] Install log free of `Invalid field` / `Template not found` / `have no access rules`
- [ ] `python3 qa/run.py` green, if any view or template changed
- [ ] New behaviour has a test that fails without this change

## Checklist

- [ ] A new controller route comes with an HTTP test
- [ ] A new x2many/m2m field comes with a test that populates it
- [ ] A change to access or permissions comes with a test acting as a second user
- [ ] `CHANGELOG.md` updated under `[Unreleased]` if user-visible
- [ ] `dw_git/__manifest__.py` version bumped if this needs to run on upgrade
- [ ] Anything deliberately left undone is recorded in `docs/LIMITATIONS.md`
