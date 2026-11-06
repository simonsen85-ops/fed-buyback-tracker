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
  Actions bot commits both to `main` every weekday, so a commit that touches
  them will conflict. Change data through code (migrations in `scraper.py`)
  and let the workflow regenerate both files.
- **Preview, approve, push to `main`.** Build `index.html` locally and show
  Rasmus the page (screenshots plus the HTML file) before pushing. Push
  directly to `main` once he approves. No pull requests. If you parked work
  on a branch while waiting, don't delete it yourself: cloud sessions can't
  delete branches. `.github/workflows/cleanup-branches.yml` deletes every
  `claude/*` branch whose changes are all on `main` when you push to `main`.
  The dashboard only changes when the
  workflow next runs: tell him to run it from the Actions tab if the change
  should show today.
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

The dashboard judges capital-allocation decisions: was each krone spent on
buybacks a better use than the alternative? Everything is measured at
purchase.

**NAV development after purchase is deliberately not shown anywhere** — not
in the KPI cards, the methodology note, the weekly table or the charts. It is
property performance, not a buyback effect: every FED share got it. Rasmus
removed the "today" figures (ROI i dag, total incl. NAV development) on
purpose; don't add them back.

The alternative is paying down debt: ~3.2 % = FED's average loan rate of
4.06 % (Q3 2026 report) after 22 % tax. It is the `DEBT_AT` constant in
`build_html.py` (KPI subtitle and the dashed line in the Afkast pr. krone
chart). Update it when a new report changes the loan rate.

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
- **Not displayed:** `calc()` still computes `vc`/`roic` (all shares × latest
  `navEx` − amount paid), `grw` (= `roic` − `roiAt`) and `accr`, and
  `markNow()` re-marks them to the latest NAV. None of these reach the page.
  `markNow()` is still needed: it supplies the latest reported NAV (header
  and Afkast på næste krone).
- **Per share** (subtitle of the Værdi skabt v. køb card) = value created at
  purchase (`vAt`) / shares outstanding today (`nSh` = N0 − shares bought).
- **Afkast pr. krone** (per week) = NAV v. køb / avg price − 1 (`aPK()`).
  **Afkast på næste krone** = reported NAV / current price − 1.

Presentation (calculations above are unchanged by it):

- KPI cards: Tilbagekøbt, Investeret, Gns. købskurs, ROI v. køb, Værdi skabt
  v. køb, Afkast på næste krone.
- "Sådan måles værdien": a text-only methodology note under the KPI cards
  (NAV uden tilbagekøb, why earlier buybacks' accretion is removed, how value
  and value per share are measured, why NAV development is left out). It
  replaced the old three-box value flow, which only repeated the KPI cards:
  show each number once.
- Weekly table: Dato, Købt, Gns. kurs, Beløb, NAV v. køb, Afkast pr. krone,
  Markedsvolumen, Udnyttelse (Safe Harbour utilisation), Akk. investeret,
  Værdi skabt (cumulative value at purchase). The last row's Værdi skabt must
  equal the Værdi skabt v. køb card.
- Charts: Købskurs vs. NAV; Afkast pr. krone (weekly bars vs. the dashed
  3.2 % line); Værdi skabt v. køb (cumulative); Udnyttelse af Safe
  Harbour-loft (weekly `utilization_pct` = shares bought / max allowed, where
  max = 25 % of the 20-day average daily volume × trading days; y-axis fixed
  0–100 %, dashed line at 100 %); buyback as % of market volume.
- GoatCounter analytics is embedded in `build_html.py`.

## Gæld tab (mortgage debt)

The page has two tabs: Tilbagekøb (everything above) and Gæld (`#gaeld`).

- **Inputs:** `data/debt_raw.csv`, `data/debt_properties.csv`,
  `data/debt_reconciliation.json` — a tingbog extract Rasmus made offline from
  tinglysning.dk (MitID). Regenerate with
  `python scripts/import_debt.py <folder with fed_debt.csv, fed_debt.json, fed_properties.csv>`.
  It keeps FED-owned attests only and replaces non-entity party names with
  "(privatperson)": the repo and Pages are public. Never copy the raw files by hand.
- **Config** in `scraper.py` (rewritten to `data.json["debt_config"]`):
  `DEBT_MIX_HISTORY` (FED's reported fixed/F5/CIBOR6 split per quarter — add
  each new report), `DEBT_NOMINAL_LATEST_M`, `DEBT_AVG_LOAN_RATE_PCT`,
  `DEBT_BONDS`, `CIBOR6_INPUT`.
- **Bond prices:** `sources/bonds.py` stores Nasdaq's last price for the two
  proxy bonds once per run in `data.json["bond_prices"]` (history from
  2026-11-04). Nasdaq's chart/download endpoint times out for these bonds — don't
  rely on it. The bonds (DLR 4 B 2053 OA / 4 B 2053) are proxies inferred from
  the loan terms; the tingbog doesn't name the series.
- **CIBOR6 is a manual input** (`CIBOR6_INPUT`): Rasmus copies the 6-month
  fixing from DFBF's information portal (his own login) about monthly. Don't
  automate it. DLR's margin is derived per loan: rate at registration − the
  fixing in `CIBOR6_INPUT["history"]` for that coupon period (≈0.06 pp weighted).
  The bidrag estimate (FED's 4.06 % average − weighted coupons) is provisional
  until the 2026H1/2026H2 fixings are added to `history`.
- Rate sensitivity (NAV/share after tax, shown in each type's KPI card):
  fixed = cash-flow repricing (Baltorpvej's OA bond interest-only to `io_until`
  1.10.2034 = 10 years from the loan, FED's stated policy; Kærup a normal annuity,
  its pantebrev has no afdragsfrihed), −1 pp capped at price 100 (`CALL_CAP`);
  F5 = non-callable bullet to ~1.4.2030 at par (symmetric); CIBOR6 = duration to
  the first reset whose coupon isn't fixed yet (tiny).
- Back-test vs AR 2025 note 28 (31.12.25 balances): +1 pp ≈ −33.5m vs FED −39.7m.
  The gap is mostly method (FED: linear 5.28 y × debt; we reprice a full 1 pp) —
  leave it. FED's −1 pp (+22.1m) lets the bonds trade above 100; we cap at 100.
- `DEBT_MIX_HISTORY` has 31.12.25, 30.06.26 and 30.09.26; 31.03.26 is missing.
- **Model:** `scripts/debt.py` (Python, run it directly to print the model);
  `build_html.py` injects it as `DB` and the JS only renders. Loan type is
  derived from the registration date: no "Rentetilpasning" = fixed; 2024 =
  CIBOR6; May/June 2025 = F5 (reset 2030). Registered principal is an upper
  bound (repayments don't reduce the pantebrev).
- Series colours (validated against `#141a24`): fixed `#3987e5`, F5 `#d95926`,
  CIBOR6 `#199e70`.

## Known gaps / to check

- **No fail-loud guard.** An announcement that fails to parse is skipped without
  failing the run. This is exactly how the IMB tracker went silent for four
  weeks in Oct 2026. First improvement: record parse failures in `data.json`
  and fail the workflow on them, as the IMB repo now does.
- The latest row (29 Oct 2026) came from the fastejendom.dk fallback with uid
  `fed-fed-page158`. Check whether OAM still returns new filings, and why the
  uid is double-prefixed.
