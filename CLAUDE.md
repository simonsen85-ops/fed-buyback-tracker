# FED Buyback Tracker — notes for Claude

Share-buyback tracker for Fast Ejendom Danmark A/S (FED.CO, Nasdaq Copenhagen,
CVR 28500971).
Live: https://simonsen85-ops.github.io/fed-buyback-tracker/
Owner: Rasmus (Surface Capital), a long-time FED shareholder reviewing its
capital allocation. The point of the tracker is the value created per krone of
buyback. Talk to him in English, in plain language. Dashboard text is Danish.

## Pipeline

`scripts/scraper.py` → `data.json` → `scripts/build_html.py` → `index.html`.
`index.html` is generated: never edit it by hand.

Workflow `.github/workflows/scrape.yml` runs weekdays 16:30 UTC and on manual
trigger: install requirements → scraper → build_html → commit & push → deploy
via `actions/deploy-pages`. Dependencies: `requests`, `beautifulsoup4`.

`README.md` is stale: it describes Netlify, a Wed/Fri schedule and a manual
`curKurs`. Trust the workflow and the code, and fix the README when you touch it.

## Working from a Claude Code session

- **Commit code, not data.** Don't commit `data.json` or `index.html`: the
  Actions bot commits both to `main` every weekday, so a branch that touches
  them will conflict. Change data through code (migrations in `scraper.py`)
  and let the workflow regenerate both files.
- Work on a branch and open a pull request; Rasmus merges it on GitHub. After
  a merge, the dashboard only changes when the workflow next runs. Tell him to
  run it from the Actions tab if the change should show today.
- **Cloud sessions have a network allowlist.** This repo needs: appft.gold.extension.gopublic.dk, saegressprod.blob.core.windows.net, fastejendom.dk, *.nasdaq.com, *.finance.yahoo.com.
  If a fetch fails from a cloud session, check the allowlist before concluding
  that the site or its format has changed.

## Before changing anything

- `git pull --rebase` first. The Actions bot commits every weekday.
- Test parsers offline against saved announcement fixtures before pushing.
  Open `index.html` locally and check for JavaScript errors.

## Sources (`scripts/sources/`)

Rasmus's source hierarchy: regulator/exchange first, company IR second,
commercial distributors (GlobeNewswire, Cision) last.

- `finanstilsynet_oam.py` — **primary**. The Danish FSA's public OAM database
  ("Egne aktier" announcements), via the GoPublic API at
  `appft.gold.extension.gopublic.dk`. Attachments sit on
  `saegressprod.blob.core.windows.net` and need no auth.
  Self-test: `python finanstilsynet_oam.py` from `scripts/sources/`.
- `fastejendom.py` — fallback. fastejendom.dk WordPress posts at
  `aktietilbagekoebsprogram-{N}`. N is a sequential page slug, not the
  announcement number, so the scraper scans past 404s. FED posts here 1–3 days
  after the regulatory release.
- `globenewswire.py` was retired, but the `sources/__init__.py` docstring still
  mentions it.
- `volume/`:
  - `nasdaq.py` — primary volume source (instrument `TX1484734`)
  - `yahoo.py` — fallback
  - `compute.py` — Safe Harbour metrics: 25 % of the 20-day average daily
    volume (Reg. 2016/1052) and share of market volume
- Price: Yahoo `FED.CO` → `data.current_price`.

## data.json

- `announcements[]` holds one row per buyback week: `uid`,
  `announcement_date`, `period_start` / `period_end`, `week_shares`,
  `week_amount` (DKK), `week_avg_price`, `acc_*`, `market_volume`,
  `buyback_pct_of_volume`, …
- `_dedup_by_period()` keeps one row per week and `_sanitize_dates()` fixes
  inconsistent dates. Rows are sorted by `period_start`, because the dashboard
  accumulates in array order.
- **Config lives in `scraper.py` constants** and is rewritten into `data.json`
  on every run: `TOTAL_SHARES` (issued, incl. treasury),
  `SHARES_OUTSTANDING_START` (2,606,979: outstanding excl. treasury before
  programme 1, the base for all NAV maths), `NAV_HISTORY`, `PROGRAMS`
  (`program_max` = sum). Edit the constants, not `data.json`.
- NAV: `NAV_HISTORY` is maintained by hand. `_auto_detect_nav()` also reads
  "Indre værdi: X pr. DATO" from fastejendom.dk into `nav_auto`. Add each
  reported quarter's NAV to `NAV_HISTORY`. `from` is the publication date; an
  optional `period_end` gives the balance-sheet date (default: the last
  quarter-end before `from`).
- Programmes: three DKK 10M programmes; #3 started 2026-10-05 and is open.

## Value model (dashboard)

All logic is JavaScript inside `build_html.py`.

- **NAV without buybacks (`navEx`).** Reported NAV already contains the
  accretion from buybacks made before its balance-sheet date. Strip it out:
  `navEx = (NAV × (N0 − shares bought) + amount spent) / N0`, with
  `N0 = SHARES_OUTSTANDING_START` and only trades up to the balance-sheet date.
  Don't add accretion on top of reported NAV: that double-counts.
- Trades are valued one by one (`daily_transactions`, else the week booked at
  `period_end`).
- **ROI at purchase (`roiAt`):** each trade valued at the `navEx` known on the
  trade date, minus the price paid. This is the discount captured.
- **ROI today (`roic`):** all shares bought × latest `navEx` − amount paid.
  The headline is marked to the latest NAV even if it was published after the
  last buyback week (`markNow`).
- **NAV development (`grw`)** = ROI today − ROI at purchase, in pp. This is
  growth every FED share got, not value created by the buyback itself.
- Accretion per share = value created / shares outstanding after buybacks.
- GoatCounter analytics is embedded in `build_html.py`.

## Known gaps / to check

- **No fail-loud guard.** An announcement that fails to parse is skipped without
  failing the run. This is exactly how the IMB tracker went silent for four
  weeks in Oct 2026. First improvement: record parse failures in `data.json`
  and fail the workflow on them, as the IMB repo now does.
- The "NAV-udv." column shows "-0.0" on a few early rows (floating-point
  rounding). Cosmetic.
- The latest row (29 Oct 2026) came from the fastejendom.dk fallback with uid
  `fed-fed-page158`. Check whether OAM still returns new filings, and why the
  uid is double-prefixed.
