# Fast Ejendom Danmark — Aktietilbagekøbs-Tracker

Automatisk tracker for Fast Ejendom Danmark A/S' aktietilbagekøbsprogram (Safe Harbour).

## Hvad gør den?

- Scraper ugentlige tilbagekøbsmeddelelser fra [fastejendom.dk](https://fastejendom.dk/investor/selskabsmeddelelser/)
- Beregner værdiskabelse i to lag:
  - **Lag 1:** Direkte rabat — (NAV − købskurs) × antal aktier
  - **Lag 2:** Annulleringseffekt — NAV-accretion ved annullering af tilbagekøbte aktier
- Viser ROIC på tilbagekøbet (kapitalallokeringseffektivitet)
- Opdaterer automatisk via GitHub Actions hver onsdag og fredag

## Opsætning (én gang)

### 1. Opret GitHub repository
1. Gå til [github.com/new](https://github.com/new)
2. Navngiv det f.eks. `fed-buyback-tracker`
3. Upload alle filer fra denne mappe (eller brug git push)

### 2. Opret Netlify site
1. Gå til [app.netlify.com](https://app.netlify.com)
2. Opret gratis konto (kan logge ind med GitHub)
3. "Add new site" → "Import an existing project" → vælg dit GitHub repo
4. Build settings: Lad felterne være tomme (vi builder via Actions)
5. Deploy — du får et link som `https://random-name.netlify.app`
6. Gå til "Site configuration" → "Change site name" → f.eks. `fed-tracker`

### 3. Forbind GitHub Actions til Netlify
1. I Netlify: Gå til "User settings" → "Applications" → "Personal access tokens" → "New access token"
2. Kopiér tokenet
3. I GitHub: Gå til dit repo → "Settings" → "Secrets and variables" → "Actions"
4. Tilføj to secrets:
   - `NETLIFY_AUTH_TOKEN` = dit Netlify token
   - `NETLIFY_SITE_ID` = dit site ID (findes under "Site configuration" → "General" i Netlify)

### 4. Test det
- I GitHub: Gå til "Actions" → "Scrape & Deploy" → "Run workflow"
- Vent 1-2 minutter
- Tjek dit Netlify-link — dashboardet bør nu vise data

## Vedligeholdelse

### Automatisk (ingen handling nødvendig)
- GitHub Actions scraper automatisk hver onsdag og fredag kl. 17:00 CET
- Nye meddelelser tilføjes til `data.json`
- `index.html` genbygges og deployes til Netlify

### Manuel opdatering nødvendig ved:
- **Ny kvartalsrapport med opdateret NAV:** Redigér `NAV_HISTORY` i `scripts/scraper.py` og `data.json`
- **Ændring i aktiekurs (for KPI):** Redigér `curKurs` i `scripts/build_html.py` (overvejes automatiseret)

## Filstruktur
```
├── .github/workflows/scrape.yml   ← GitHub Actions workflow
├── scripts/
│   ├── scraper.py                 ← Scraper (henter nye meddelelser)
│   └── build_html.py              ← Bygger index.html fra data.json
├── data.json                      ← Alle tilbagekøbsdata (opdateres automatisk)
├── index.html                     ← Dashboard (genereret, deploy til Netlify)
└── README.md                      ← Denne fil
```
