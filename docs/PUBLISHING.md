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
| Documentation at `doc/index.rst`, valid pure RST | ✅ | `odoogit/doc/index.rst` |
| Odoo has read access to the repository | ✅ nothing to do — the repo is public | see below |

An RST description instead of HTML counts against the listing's score, which
is why `index.html` exists. Separately, `doc/index.rst` **must** be pure valid
RST — it is loaded as the module's documentation tab.

A white cube instead of the icon means the file is at the wrong path or is not
genuinely PNG. Renaming `icon.ico` to `icon.png` does not convert it; ours is
a real PNG, checked in CI.

### How images actually get published

**There is no image upload in the Apps Store.** Every asset comes out of the
repository on each scan:

| What you see on the listing | Where it comes from |
|---|---|
| App icon | `odoogit/static/description/icon.png` — must genuinely be PNG |
| Cover / thumbnail | the **first** entry in the manifest's `images` list |
| Large screenshot | the first `images` entry whose filename ends in `_screenshot` |
| Description body | `odoogit/static/description/index.html` |
| Documentation tab | `odoogit/doc/index.rst` |

So to change any of them: edit the file, push to `main`, mirror to `19.0`,
and rescan from *My Repos*. Nothing is typed into the store.

Two traps confirmed against Odoo's own `theme_enark`, which the FAQ cites as
the reference implementation:

- Its `images` are `static/description/*` — the FAQ's `images/main_screenshot.png`
  example is illustrative, not a required folder.
- The `_screenshot` slot is deliberately **not** the branding image. Odoo's
  words: *"the purpose of this screenshot format is to show a full demo page
  and not your company logo larger."* Ours is therefore
  `repositories_screenshot.png`, a real screenshot of the repository list;
  the banner is `cover.png` and serves as the thumbnail.

### Rules for `index.html`

Odoo strips things. Keep to them or the page renders wrong:

- **Keep the file pure ASCII.** The store does not render it as UTF-8: an
  em-dash shipped as a literal `—` came out on the live listing as `â€`. Use
  HTML entities (`&mdash;`, `&rarr;`, `&hellip;`) instead of the characters
  themselves. Check with:

  ```bash
  python3 -c "s=open('odoogit/static/description/index.html',encoding='utf-8').read(); \
  print(sorted({c for c in s if ord(c)>127}) or 'pure ASCII')"
  ```

- Only PNG, GIF and JPEG images, and only from `static/description/`.
- External links are invalidated. YouTube (canonical URL) and Microsoft Teams
  are the exceptions.
- Bootstrap classes and colours only; inline style is limited to `font-*`,
  `margin-*`, `padding-*`, `border-*`.

Our page keeps every `src` relative (`main_screenshot.png`, not a GitHub raw
URL) precisely because of the second rule — a GitHub-hosted image would be
stripped and the listing would show broken images.

### Submitting

1. Sign in at <https://apps.odoo.com>, then go to
   <https://apps.odoo.com/apps/upload>. The registration form does not render
   at all until you are signed in.

2. **Register this exact URL** (already done — it is listed under *My Repos*):

   ```
   ssh://git@github.com/DonsWayo/odoogit.git#19.0
   ```

   Three things about that string, each of which will fail the form if you
   get it wrong:

   - **SSH URI scheme.** Odoo normalises every repository to
     `ssh://git@gitServer(:port)/mypath#version` so it can strip passwords and
     avoid duplicate registrations. An `https://github.com/...` URL is
     rejected as badly formatted.
   - **`.git` suffix**, as in Odoo's own example
     `ssh://git@github.com/odoo/odoo.git#8.0`.
   - **The branch must be named after the Odoo series, not your default
     branch.** The form is explicit: *"The branch name exactly matches the
     series name for which your modules are meant."* `#main` would not map to
     a series. That is why this repository carries a `19.0` branch alongside
     `main` — see *Keeping the series branch current* below.

   If registration fails on the URL, check that a colon appears only before a
   port number; with no port, `gitServer` and `mypath` are separated by a
   slash.

3. **Access:** nothing to do. `online-odoo` only needs authorising for
   **private** repositories, and this one is public. If you ever make it
   private, authorise **`online-odoo`** — note the order, `odoo-online` is a
   different account — on the repository specifically, not the whole
   organisation.

4. Set the price. LGPL-3 can be listed free or paid; Odoo suggests €100 as a
   starting point for paid modules and takes a **30% commission**. Free is the
   honest default here — much of this module's value is that people can read
   and audit it.

5. Publish, then re-scan once or twice if it reports "no icon" or "no
   thumbnail". Those errors are frequently spurious — if the assets render in
   the listing preview, ignore them.

### Rules the store enforces on authors

Odoo does not review every module, but acts on reports. Two of its six rules
bear directly on how this module is presented:

- **R3 — undocumented or hidden features inconsistent with the module
  description get the module removed.** This cuts both ways: the listing must
  not claim what the module does not do. Undelivered webhooks and the absent
  SSH transport are named explicitly in the listing for exactly this reason.
- **R6 — you must support customers who install it.** The manifest's `support`
  key points at the issue tracker; keep answering there.

The others: no stealing data or uncredited copying (R1), no downloading or
launching external code (R2), no collecting information without disclosure and
a privacy policy (R4), nothing that harms another author's reputation (R5).

### Licence compatibility

A module may only depend on compatible licences. **LGPL-3** — ours — may
depend on LGPL-3, OPL-1, OEEL-1, Other OSI approved, and Other proprietary.
Every dependency here (`base`, `mail`, `portal`, `web`, `project`) is Odoo
Community LGPL-3, so this is satisfied.

Note the asymmetry: an AGPL-3 or GPL-3 module could depend on us, but we could
not depend on one of them without relicensing.

### After registering

The repository lands in *My Repos* as **Draft** with a **Scan** toggle. Ticking
Scan queues it; Odoo crawls on its own schedule, so *Apps I registered* stays
empty for a while. Nothing is public until the scan finds the module and you
publish it.

### Keeping the series branch current

**`19.0` is the branch Odoo scans. `main` is where work happens.** If they
drift, the Apps Store serves whatever `19.0` last pointed at, indefinitely and
silently — there is no warning that a listing is stale.

Push it with every release:

```bash
git push origin main --follow-tags
git branch -f 19.0 main && git push origin 19.0
```

`docs/RELEASING.md` has this as a step in the release procedure.

### Before you press publish

Read `docs/LIMITATIONS.md` once more with a buyer's eyes. Webhooks are built
and signed but never delivered, there is no SSH transport, and branch
protection is not enforced on `git push`. The listing says all three
explicitly. **Keep it that way.** An Odoo Apps listing that oversells gets
refund requests and one-star reviews, and this module's strongest selling
point right now is that it tells you exactly where the edges are.

If you would rather ship a listing with no caveats, the shortest path is to
implement webhook delivery — it is the gap most users will notice first.

## GitHub social preview

`docs/images/social-preview.png` is 1280×640, the size GitHub asks for. It has
to be attached by hand at
<https://github.com/DonsWayo/odoogit/settings> → **Social preview** → **Edit**
→ *Upload an image…*, or by dragging the file onto that box.

There is no API for it, and browser automation does not work either: GitHub
uses a `<file-attachment>` element that asks for an upload policy, pushes the
bytes to S3, and only then submits the form. Driving the file input
programmatically creates the database record — `og:image` starts pointing at
`repository-images.githubusercontent.com/...` — while the bytes never arrive,
so the URL 404s and link previews break. That is worse than having no custom
preview at all.

If you ever see that state, open the same **Edit** menu and choose **Remove
image** to fall back to GitHub's generated card.

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
- **`doc/index.rst`** already ships, so the Apps listing gets a documentation
  tab for free. Keep it in sync with `docs/LIMITATIONS.md`.
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
