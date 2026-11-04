#!/usr/bin/env python3
"""
Gæld tab model: turns the tingbog extract (data/debt_*.csv/json) plus the
debt config and bond prices in data.json into one JSON object the page renders.

All arithmetic lives here (Python) so it can be checked offline:
    python scripts/debt.py        → prints the model

Loan types are DERIVED FROM THE REGISTRATION DATE ("afledt af tinglysningsdato"):
  - fixed  : realkreditpantebrev without "Rentetilpasning" (2 loans, Sept 2024)
  - cibor6 : rentetilpasning loans registered in 2024
  - f5     : rentetilpasning loans registered May/June 2025 (next reset 2030)
The tingbog itself does not say F5 or CIBOR6; build_model() checks the result
against FED's reported split.
"""
import csv
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"

COMPANY = {"28720815": "Fast Ejendom Danmark 1 ApS", "33505396": "Ejendomsselskabet Ringager ApS"}
TYPE_LABEL = {"fixed": "Fast 4 %", "f5": "F5", "cibor6": "CIBOR6", "ukendt": "Ukendt"}
TYPES = ["fixed", "f5", "cibor6"]

# Tingbog property ≠ CSV address in these cases
PROPERTY_NAME = {
    1: "Aldersrogade 6C (4 ejerlejl.)", 3: "Baltorpvej 156–172", 4: "Hejrevej 37–39",
    10: "Ringager 2A", 12: "Ørbækvej 262/268", 19: "Handelsvej 28–30", 26: "Sletvej 38–40",
}
MERGE = {20: 19}  # Handelsvej 30 is a building on the Handelsvej 28 property (BFE 10108657)
NOT_FED = {13}  # in FED's property list, but the tingbog owner is not a FED company → left out (not shown)
# Fallback if data.json has no flows_2026 yet (see DEBT_FLOWS_2026 in scraper.py)
SOLD_PROPERTIES_DEBT_M = 15.267 + 34.667
# A callable (konvertibel) bond can always be redeemed at par, so a rate fall can't
# lift the debt much above 100. The quoted price can sit a little above 100 in practice.
CALL_CAP = 100.0


def _f(s):
    s = (s or "").replace("%", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _d(s):
    d, m, y = (s or "").split(".")
    return date(int(y), int(m), int(d))


def _half(d: date) -> str:
    return f"{d.year}H{1 if d.month <= 6 else 2}"


def _next_reset(asof: date) -> date:
    """Next CIBOR6 reset date (1 January / 1 July) after asof."""
    return date(asof.year, 7, 1) if asof < date(asof.year, 7, 1) else date(asof.year + 1, 1, 1)


def bullet_dprice(coupon_pct: float, yield_pct: float, maturity: date, asof: date, dy: float) -> float:
    """Price change per 100 of an annual-coupon bullet bond when its yield moves by dy (e.g. 0.01)."""
    times, t = [], (maturity - asof).days / 365.25
    while t > 0:
        times.append(t)
        t -= 1
    price = lambda y: sum(coupon_pct / (1 + y) ** s for s in times) + 100 / (1 + y) ** times[0]
    y0 = yield_pct / 100
    return price(y0 + dy) - price(y0)


def loan_type(r: dict) -> str:
    if r["rate_class"] == "Fast rente":
        return "fixed"
    d = _d(r["registration_date"])
    if d.year == 2024:
        return "cibor6"
    if d.year == 2025 and d.month in (5, 6):
        return "f5"
    return "ukendt"


# ---------------------------------------------------------------- bond maths
def _quarter_dates(start: date, end: date) -> list[date]:
    """Coupon dates (1 Jan/Apr/Jul/Oct) strictly after start, up to and including end."""
    out, y, m = [], start.year, ((start.month - 1) // 3) * 3 + 1
    while True:
        m += 3
        if m > 12:
            m, y = m - 12, y + 1
        d = date(y, m, 1)
        if d > end:
            return out
        if d > start:
            out.append(d)


def bond_cashflows(coupon_pct: float, expiry: date, asof: date, io_until: date | None = None):
    """Quarterly cash flows per 100 of outstanding notional: interest only up to io_until
    (if given), then a level annuity to expiry. Returns ([(t_years, amount)], accrued_per_100)."""
    pays = _quarter_dates(asof, expiry)
    r = coupon_pct / 400
    io = [p for p in pays if io_until and p <= io_until]
    am = [p for p in pays if p not in io]
    pmt = 100 * r / (1 - (1 + r) ** -len(am))
    flows = [(p, 100 * r) for p in io] + [(p, pmt) for p in am]
    prev = date(pays[0].year if pays[0].month > 1 else pays[0].year - 1, (pays[0].month - 4) % 12 + 1, 1)
    accrued = 100 * r * (asof - prev).days / (pays[0] - prev).days
    return [((p - asof).days / 365.25, c) for p, c in flows], accrued


def pv(y: float, flows: list[tuple[float, float]]) -> float:
    return sum(c / (1 + y / 4) ** (4 * t) for t, c in flows)


def ytm(dirty: float, flows: list[tuple[float, float]]) -> float:
    lo, hi = -0.05, 0.25
    for _ in range(200):
        mid = (lo + hi) / 2
        if pv(mid, flows) > dirty:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def bond_metrics(coupon_pct: float, expiry: str, clean: float, asof: date, io_until: str | None = None) -> dict:
    """Yield and ±1 pp price changes. Interest-only to io_until (OA series), then annuity.
    Rate RISE: the call option moves out of the money, so the plain price holds.
    Rate FALL: the borrower can redeem at par, so the clean price is capped at CALL_CAP."""
    flows, acc = bond_cashflows(coupon_pct, date.fromisoformat(expiry), asof,
                                date.fromisoformat(io_until) if io_until else None)
    dirty = clean + acc
    y = ytm(dirty, flows)
    dirty_up = pv(y + 0.01, flows)
    clean_down_uncapped = pv(y - 0.01, flows) - acc
    macaulay = sum(t * c / (1 + y / 4) ** (4 * t) for t, c in flows) / dirty
    clean_down = min(clean_down_uncapped, max(CALL_CAP, clean))
    return {"yield_pct": y * 100, "accrued": acc, "years_left": (date.fromisoformat(expiry) - asof).days / 365.25,
            "macaulay_years": macaulay, "price_up1pp": dirty_up - acc,
            "dprice_up1pp": dirty_up - dirty, "mod_duration": (dirty - dirty_up) / (dirty * 0.01),
            "price_down1pp": clean_down, "price_down1pp_uncapped": clean_down_uncapped,
            "dprice_down1pp": clean_down - clean}


# ---------------------------------------------------------------- model
def _read_csv(path: Path, delimiter=","):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter=delimiter))


def build_model(data: dict, asof: date | None = None) -> dict:
    asof = asof or date.today()
    cfg = data.get("debt_config") or {}
    raw = _read_csv(DATA_DIR / "debt_raw.csv", ";")
    props = {int(p["id"]): p for p in _read_csv(DATA_DIR / "debt_properties.csv")}
    rec = json.loads((DATA_DIR / "debt_reconciliation.json").read_text(encoding="utf-8"))
    bonds = {b["loan_ref"]: b for b in cfg.get("bonds", [])}
    tax = cfg.get("tax_rate", 0.22)

    # unique realkredit loans (a joint loan appears once per unit it is registered on)
    loans, seen, owners = [], set(), {}
    for r in raw:
        pid = MERGE.get(int(r["property_id"]), int(r["property_id"]))
        owners.setdefault(pid, set()).update(c for c in r["owner_cvr"].split("; ") if c in COMPANY)
        if r["type"] != "Realkreditpantebrev" or r["dato_loebenummer"] in seen:
            continue
        seen.add(r["dato_loebenummer"])
        t = loan_type(r)
        b = bonds.get(r["dato_loebenummer"])
        if t == "fixed":
            reset = f"Udløb {date.fromisoformat(b['expiry']).strftime('%d.%m.%Y')}" if b else "Fast rente"
        elif t == "f5":
            reset = "Rentetilpasning ca. april 2030"   # FED Q3 2026: "ca. 3,5 år tilbage" pr. 30.09.26
        elif t == "cibor6":
            reset = "Halvårlig (1/1, 1/7)"
        else:
            reset = "—"
        loans.append({
            "property_id": pid, "ref": r["dato_loebenummer"], "type": t, "type_label": TYPE_LABEL[t],
            "principal_m": float(r["principal"]) / 1e6, "rate_pct": _f(r["interest_rate"]),
            "registered": r["registration_date"], "reset": reset, "loan_type": r["loan_type"],
            "joint_units": int(r["also_registered_on"]) + 1 if r["also_registered_on"] else 1,
            "bond": b["name"] if b else None,
        })

    # property table
    table = []
    for pid, p in sorted(props.items()):
        if p["status"] != "ejet" or pid in NOT_FED or pid in MERGE:
            continue
        m2 = sum(_f(props[i]["areal_m2"]) or 0 for i in [pid] + [k for k, v in MERGE.items() if v == pid])
        company = "; ".join(COMPANY[c] for c in sorted(owners.get(pid, []))) or p["ejer_selskab"]
        pl = sorted((l for l in loans if l["property_id"] == pid), key=lambda l: (_d(l["registered"]), -l["principal_m"]))
        table.append({"id": pid, "name": PROPERTY_NAME.get(pid, p["adresse"]), "by": p["by"],
                      "segment": p["segment"], "m2": m2, "company": company,
                      "mortgage_free": not pl, "loans": pl})

    # registered principal by derived type vs FED's reported split
    reg = {t: sum(l["principal_m"] for l in loans if l["type"] == t) for t in TYPES}
    mix = [{**m, "amounts": {t: m[t] / 100 * m["base_m"] for t in TYPES}}
           for m in sorted(cfg.get("mix_history", []), key=lambda m: m["period_end"])]
    ye = next((m for m in mix if m["period_end"] == "2025-12-31"), None)
    q3 = mix[-1] if mix else None
    recon = []
    for t in TYPES:
        row = {"type": t, "label": TYPE_LABEL[t], "registered_m": reg[t],
               "periods_m": [m["amounts"][t] for m in mix],
               "ye_m": ye["amounts"][t] if ye else None, "latest_m": q3["amounts"][t] if q3 else None}
        if q3:
            row["gap_latest_m"] = reg[t] - row["latest_m"]
            row["ok_latest"] = row["gap_latest_m"] >= -0.005 * q3["base_m"]   # within 'ca.' rounding
        if ye and q3:
            row["change_m"] = row["latest_m"] - row["ye_m"]
        recon.append(row)
    f5_ye_excess = (ye["amounts"]["f5"] - reg["f5"]) if ye else None

    # How each type fell in 2026, and what was paid down since registration (afledt):
    #  - sale: debt on the four sold properties → F5 (refinanced with the rest in May/June 2025;
    #    F5 at 31.12.25 exceeds the registered F5 on today's properties by f5_ye_excess)
    #  - voluntary: early redemption on retained loans = indfrielse − sale → fixed (the only type
    #    that fell beyond amortisation; its share was flat to H1 and dropped in Q3)
    #  - ordinary: the residual (includes FED's rounding of the percentages)
    # paid_before_2026 + voluntary + ordinary = registered − outstanding (sold loans are on neither side).
    flows = cfg.get("flows_2026") or {}
    sale = flows.get("sale_debt_m", SOLD_PROPERTIES_DEBT_M)
    voluntary = flows["indfrielse_m"] - sale if "indfrielse_m" in flows else 0.0
    alloc_sale = {"fixed": 0.0, "f5": sale, "cibor6": 0.0}
    alloc_vol = {"fixed": voluntary, "f5": 0.0, "cibor6": 0.0}
    if ye and q3:
        for row in recon:
            t = row["type"]
            row["fall_2026_m"] = row["ye_m"] - row["latest_m"]
            row["fall_sale_m"] = alloc_sale[t]
            row["fall_voluntary_m"] = alloc_vol[t]
            row["fall_ordinary_m"] = row["fall_2026_m"] - alloc_sale[t] - alloc_vol[t]
            row["paid_before_2026_m"] = row["registered_m"] - (row["ye_m"] - alloc_sale[t])

    # fixed debt: outstanding (FED split) allocated to the two proxy bonds pro rata registered principal
    fixed_loans = [l for l in loans if l["type"] == "fixed"]
    fixed_out = q3["amounts"]["fixed"] if q3 else None
    bond_rows, mv, dmv, dmv_dn = [], 0.0, 0.0, 0.0
    for l in fixed_loans:
        b = bonds.get(l["ref"])
        hist = (data.get("bond_prices") or {}).get(b["isin"], []) if b else []
        last = hist[-1] if hist else None
        alloc = fixed_out * l["principal_m"] / reg["fixed"] if fixed_out else None
        row = {"property": b["property"] if b else "", "bond": b["name"] if b else None, "isin": b["isin"] if b else None,
               "repayment": b["repayment"] if b else "", "expiry": b["expiry"] if b else None,
               "registered_m": l["principal_m"], "alloc_m": alloc, "price": last["price"] if last else None,
               "price_date": last["date"] if last else None, "history": hist}
        if last and b:
            row.update(bond_metrics(b["coupon_pct"], b["expiry"], last["price"], asof, b.get("io_until")))
            row["io_until"] = b.get("io_until")
            row["mv_m"] = alloc * last["price"] / 100
            row["dmv_up1pp_m"] = alloc * row["dprice_up1pp"] / 100
            row["dmv_down1pp_m"] = alloc * row["dprice_down1pp"] / 100
            mv += row["mv_m"]
            dmv += row["dmv_up1pp_m"]
            dmv_dn += row["dmv_down1pp_m"]
        bond_rows.append(row)
    priced = all(r["price"] is not None for r in bond_rows) and bond_rows
    fixed_yield = (sum(r["yield_pct"] * r["alloc_m"] for r in bond_rows) / fixed_out) if priced else None

    n0 = data.get("shares_outstanding_start") or 2606979
    shares_out = n0 - sum(a.get("week_shares") or 0 for a in data.get("announcements", []))
    nav_gain_m = -dmv * (1 - tax) if priced else None
    nav_loss_dn_m = -dmv_dn * (1 - tax) if priced else None

    # redemption yields ("afkast ved indfrielse")
    f5_loans = [l for l in loans if l["type"] == "f5"]
    f5_rate = sum(l["rate_pct"] * l["principal_m"] for l in f5_loans) / reg["f5"] if f5_loans else None
    c6 = cfg.get("cibor6") or {}
    fix_hist = {h["period"]: h["pct"] for h in c6.get("history", [])}
    c6_loans = [l for l in loans if l["type"] == "cibor6"]
    for l in c6_loans:   # DLR margin = rate at registration − fixing for that coupon period
        fx = fix_hist.get(_half(_d(l["registered"])))
        l["margin_pp"] = l["rate_pct"] - fx if fx is not None and l["rate_pct"] is not None else None
    if c6.get("margin_pp") is not None:
        c6_margin, c6_margin_src = c6["margin_pp"], "manuel"
    elif c6_loans and all(l["margin_pp"] is not None for l in c6_loans):
        c6_margin = sum(l["margin_pp"] * l["principal_m"] for l in c6_loans) / reg["cibor6"]
        c6_margin_src = "afledt"
    else:
        c6_margin, c6_margin_src = None, None
    c6_coupon = c6["fixing_pct"] + c6_margin if c6.get("fixing_pct") is not None and c6_margin is not None else None
    # Bidrag ≈ FED's average loan rate over Q1-Q3 2026 minus the weighted coupons.
    # CIBOR6 coupons for 2026 come from the 2026H1/H2 fixings if entered, else today's fixing (provisional).
    fx2026 = [fix_hist[p] for p in ("2026H1", "2026H2") if p in fix_hist]
    c6_cpn_2026 = (sum(fx2026) / len(fx2026) + c6_margin) if fx2026 and c6_margin is not None else c6_coupon
    bidrag, bidrag_basis = None, None
    if q3 and fixed_loans and f5_rate is not None and c6_cpn_2026 is not None:
        w = {t: q3[t] / 100 for t in TYPES}
        coupons = w["fixed"] * 4.0 + w["f5"] * f5_rate + w["cibor6"] * c6_cpn_2026
        bidrag = cfg.get("avg_loan_rate_pct", 4.06) - coupons
        bidrag_basis = "2026-fixings" if fx2026 else "aktuel fixing (foreløbigt)"

    # ±1 pp rate sensitivity per type, NAV per share after tax (debt is at fair value)
    def per_share(dmv_m):
        return -dmv_m * (1 - tax) * 1e6 / shares_out
    sens = {}
    if priced:
        sens["fixed"] = {"up": nav_gain_m * 1e6 / shares_out, "down": nav_loss_dn_m * 1e6 / shares_out,
                         "method": "Konvertibel 4 %-obligation. +1 pp er en øvre grænse (tæt på kurs 100 falder kursen lidt mindre); ved −1 pp er kursen begrænset af 100"}
    if q3 and f5_rate is not None:
        f5_mat = date(2030, 4, 1)   # FED Q3 2026: ca. 3,5 år tilbage af fastrenteperioden pr. 30.09.26
        out = q3["amounts"]["f5"]
        sens["f5"] = {"up": per_share(out * bullet_dprice(f5_rate, f5_rate, f5_mat, asof, +0.01) / 100),
                      "down": per_share(out * bullet_dprice(f5_rate, f5_rate, f5_mat, asof, -0.01) / 100),
                      "method": "Inkonvertibel, stående til ca. 1.4.2030, modelleret til kurs 100 — symmetrisk"}
    if q3:
        out = q3["amounts"]["cibor6"]
        dur = (_next_reset(asof) - asof).days / 365.25
        y6 = (c6_coupon or 3.0) / 100
        dp = dur / (1 + y6 / 2) * 1.0   # % price change per 1 pp
        sens["cibor6"] = {"up": per_share(-out * dp / 100), "down": per_share(out * dp / 100),
                          "method": f"Rentetilpasses {_next_reset(asof).strftime('%d.%m.%Y')} — næsten ingen kursfølsomhed"}

    def ytr(base):
        if base is None:
            return {"base_pct": None, "bidrag_pct": bidrag, "total_pct": None, "after_tax_pct": None}
        tot = base + (bidrag or 0)
        return {"base_pct": base, "bidrag_pct": bidrag, "total_pct": tot if bidrag is not None else None,
                "after_tax_pct": (tot if bidrag is not None else base) * (1 - tax)}

    nav = (data.get("nav_history") or [{}])[-1].get("nav")
    kurs = data.get("current_price")
    redemption = [
        {"type": "fixed", "label": TYPE_LABEL["fixed"], **ytr(fixed_yield),
         "basis": "Effektiv rente ved køb af obligationerne til aktuel kurs (proxy-serier)"},
        {"type": "cibor6", "label": TYPE_LABEL["cibor6"], **ytr(c6_coupon),
         "basis": "Aktuel 6M CIBOR + DLR-tillæg afledt af tinglysningsrenten" if c6_coupon is not None else "Afventer CIBOR6-fixing og tillæg (manuel input i scraper.py)"},
        {"type": "f5", "label": TYPE_LABEL["f5"], **ytr(f5_rate),
         "basis": "Låst rente ved tinglysning maj/juni 2025, til rentetilpasning 2030"},
    ]

    return {
        "asof": asof.isoformat(),
        "tax_rate": tax,
        "nominal_latest_m": cfg.get("nominal_latest_m"),
        "latest_label": q3["label"] if q3 else None,
        "outstanding_latest_m": q3["amounts"] if q3 else None,
        "mix": [{"label": m["label"], "basis": m["basis"], "base_m": m["base_m"],
                 "pct": {t: m[t] for t in TYPES}, "amounts": m["amounts"]} for m in mix],
        "registered_m": reg,
        "registered_total_m": sum(reg.values()),
        "recon": recon,
        "f5_ye_excess_m": f5_ye_excess,
        "sold_properties_debt_m": sale,
        "flows_2026": {**flows, "voluntary_m": voluntary},
        "fixed": {"outstanding_m": fixed_out, "bonds": bond_rows, "mv_m": mv if priced else None,
                  "yield_pct": fixed_yield, "nav_gain_up1pp_m": nav_gain_m,
                  "nav_gain_per_share": nav_gain_m * 1e6 / shares_out if priced else None,
                  "nav_down1pp_m": nav_loss_dn_m,
                  "nav_down1pp_per_share": nav_loss_dn_m * 1e6 / shares_out if priced else None,
                  "nav_per_point_above_par": fixed_out / 100 * (1 - tax) * 1e6 / shares_out if fixed_out else None,
                  "call_cap": CALL_CAP,
                  "shares_out": shares_out},
        "redemption": redemption,
        "bidrag_pct": bidrag,
        "bidrag_basis": bidrag_basis,
        "cibor6": c6,
        "cibor6_margin_pp": c6_margin,
        "cibor6_margin_src": c6_margin_src,
        "cibor6_coupon_pct": c6_coupon,
        "sens": sens,
        "next_krone_pct": (nav / kurs - 1) * 100 if nav and kurs else None,
        "nav": nav, "kurs": kurs,
        "properties": table,
        "loans_count": len(loans),
        "bridge_B": rec.get("reconciliation_dkk_000", {}).get("version_B_current", {}).get("bridge", []),
    }


if __name__ == "__main__":
    d = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
    m = build_model(d)
    m["properties"] = f"{len(m['properties'])} properties"
    for b in m["fixed"]["bonds"]:
        b["history"] = f"{len(b['history'])} obs"
    print(json.dumps(m, indent=1, ensure_ascii=False, default=str))
