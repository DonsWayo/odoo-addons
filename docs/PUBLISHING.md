# Publishing and getting OdooGit used

Two separate jobs: getting listed on the Odoo Apps Store, and getting anyone
to hear about it. The store is a checklist; the rest is not.

## Odoo Apps Store

### What the store checks

| Requirement | Status | Where |
|---|---|---|
| `__manifest__.py` present, `name` ≤ 25 chars | ✅ `OdooGit` (7) | `odoogit/__manifest__.py` |
| Icon at `static/description/icon.png`, genuinely PNG | ✅ 128×128 RGBA | `odoogit/static/description/icon.png` |
| HTML description at `static/description/index.html` | ✅ | same folder |
| `license` a recognised value | ✅ `LGPL-3` | manifest |
| Cover image via the `images` manifest key | ✅ 4 images | manifest |
| One app per folder at the repository root | ✅ `odoogit/` | — |
| No downloading or executing external code | ✅ | — |
| Odoo has read access to the repository | ⬜ **you must do this** | see below |

An RST description instead of HTML counts against the listing's score, which
is why `index.html` exists.

### Rules for `index.html`

Odoo strips things. Keep to them or the page renders wrong:

- Only PNG, GIF and JPEG images, and only from `static/description/`.
- External links are invalidated. YouTube (canonical URL) and Microsoft Teams
  are the exceptions.
- Bootstrap classes and colours only; inline style is limited to `font-*`,
  `margin-*`, `padding-*`, `border-*`.

Our page keeps every `src` relative (`main_screenshot.png`, not a GitHub raw
URL) precisely because of the second rule — a GitHub-hosted image would be
stripped and the listing would show broken images.

### Submitting

1. Go to <https://apps.odoo.com/apps/upload>, signed in with your Odoo account.
2. Grant read access to the repository: on GitHub, add the user **`online-odoo`**
   as a collaborator (read is enough), or make the repository public — it
   already is.
3. Point the upload form at `https://github.com/DonsWayo/odoogit`, branch
   `main`, and let it scan.
4. Set the price. LGPL-3 code can be listed free or paid; free is the honest
   default for a module whose value is partly that people read and audit it.
5. Publish, then re-scan once or twice if it reports "no icon" or "no
   thumbnail". Those errors are frequently spurious — if the assets render on
   the listing preview, ignore them.

### Before you press publish

Read `docs/LIMITATIONS.md` once more with a buyer's eyes. Webhooks are built
and signed but never delivered, there is no SSH transport, and branch
protection is not enforced on `git push`. The listing says all three
explicitly. **Keep it that way.** An Odoo Apps listing that oversells gets
refund requests and one-star reviews, and this module's strongest selling
point right now is that it tells you exactly where the edges are.

If you would rather ship a listing with no caveats, the shortest path is to
implement webhook delivery — it is the gap most users will notice first.

## Getting it in front of people

Ranked by effort-to-reach for a self-hosted Odoo developer tool.

### Worth doing first

- **Odoo Community Association (OCA).** <https://odoo-community.org> — the
  centre of gravity for serious Odoo modules. Ask in their GitHub discussions
  whether OdooGit fits an existing repository or belongs standalone. An OCA
  association is worth more than any amount of self-promotion.
- **Odoo's own forum**, in Developers:
  <https://www.odoo.com/forum/help-1>. Answer existing "self-hosted git in
  Odoo" questions rather than posting an advert.
- **r/Odoo** on Reddit. Small but exactly your audience. Lead with the
  problem it solves, not the feature list.
- **A written post with a real story.** The August 2026 audit is unusually
  good material: *"My test suite was 54/54 green while twelve entry points
  crashed on first call."* That is a post people share, on dev.to, Lobsters,
  or Hacker News as a Show HN. It sells the module by demonstrating how it is
  maintained.

### Worth doing, lower yield

- LinkedIn, if you already have Odoo people in your network.
- **awesome-odoo** lists on GitHub — send a PR adding OdooGit.
- Odoo partner Slack/Discord communities, if you are in any.
- A 60-second screen recording of clone → push → PR → merge. YouTube links are
  allowed in the Apps listing, so one video serves both channels.

### Do not bother

Paid ads, mass-emailing Odoo partners, or posting the same announcement in
twenty subreddits. This is a niche technical tool; ten users who actually run
it are worth more than a thousand impressions.

## What would most increase adoption

Honest ranking, based on what the audit found:

1. **Deliver webhooks.** The most visible half-built feature. Needs an SSRF
   policy first — see `docs/LIMITATIONS.md`.
2. **Enforce branch protection on push.** Right now the settings exist and a
   `git push` ignores them, which is the kind of gap that becomes a security
   report.
3. **A file browser and diff view.** The single most common "why would I use
   this instead of Gitea" answer.
4. **SSH transport**, or drop `clone_url_ssh` from the UI so it stops
   advertising something that does not exist.
