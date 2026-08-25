# Git Hosting — Manual QA Checklist

> Run against a fresh install: `docker compose up -d` → http://localhost:8069 (admin/admin)
> Every checkbox = one manual verification a human performs in the browser.

## 1. Installation & First Boot
- [ ] Module appears in Apps as **Git Hosting**, installs without errors
- [ ] "Git Hosting" main menu appears with sub-menus: Repositories, Pull Requests, Webhooks, Personal Access Tokens, Deploy Keys
- [ ] No red tracebacks in `docker compose logs -f odoo`

## 2. Repository CRUD
- [ ] Create repo via **New** → name `my-test-repo`, visibility Private → saves
- [ ] Clone URL auto-fills: `http://localhost:8069/git/admin/my-test-repo.git`
- [ ] Duplicate name rejected with user-friendly error
- [ ] Name with space/special chars rejected
- [ ] Edit description (HTML editor), save, reload — persists

## 3. Visibility & Access
- [ ] Create second user (no Git groups) → sees NO private repos of admin
- [ ] Set repo to Internal → second user now sees it read-only
- [ ] Add second user as Member → can edit repo record
- [ ] Record rules: second user cannot open admin's private repo by direct URL

## 4. Branches & Protection
- [ ] Open repo → Branches tab → add branch `main`, SHA 40-hex
- [ ] Enable **Protected** + Require PR Reviews on `main`
- [ ] Second non-manager cannot toggle protection (group-gated tab)
- [ ] Duplicate branch name in same repo rejected; same name in different repo OK

## 5. Real Git Flow (terminal)
- [ ] `git clone http://admin@localhost:8069/git/admin/my-test-repo.git` works (password = PAT)
- [ ] Commit + `git push origin main` succeeds on unprotected branch
- [ ] Push to protected branch is rejected by pre-receive validation
- [ ] `git log` in clone shows commits that appear in Odoo Commits list

## 6. Pull Requests
- [ ] Create PR feature→main from UI; number auto-increments (PR0001…)
- [ ] Review Approve → approval count increments on form stat button
- [ ] Request Changes → banner shows changes requested
- [ ] Merge button hidden while unapproved on protected target
- [ ] Close → state Closed, Reopen returns to Open
- [ ] Chatter posts visible when state changes (tracking)

## 7. Personal Access Tokens
- [ ] Create PAT → token shown once, hash stored not plaintext
- [ ] Revoke → find_by_token fails (verify via git clone failing)
- [ ] Regenerate produces new token, old stops working

## 8. Deploy Keys
- [ ] Create deploy key scoped to repo (read-only) → clone works, push denied
- [ ] Toggle can_push → push now allowed

## 9. Webhooks
- [ ] Add webhook URL https://webhook.site/xyz, enable Push events
- [ ] Test delivery button fires → delivery log row appears with response code
- [ ] Failed delivery shows in list with retry button functional

## 10. Notifications & Chatter
- [ ] PR created → followers get email template (configure catchall or check mail queue)
- [ ] Chatter on repository logs member additions
- [ ] Scheduled activities can be set on PR and appear in systray

## 11. Portal
- [ ] `/my/repositories` lists repos shared to portal user
- [ ] Private repo page shows lock screen for unauthorized portal user
- [ ] Public/internal repo page shows branches + recent commits tables

## 12. Multi-company
- [ ] Same repo name allowed under different company
- [ ] Company B user cannot see Company A repo (record rule)

## 13. Regression Sweep
- [ ] Uninstall module → no orphan tables (`\dt git.*` in psql empty)
- [ ] Reinstall clean → demo data loads if enabled
- [ ] `docker compose logs odoo | grep ERROR` empty after full sweep
