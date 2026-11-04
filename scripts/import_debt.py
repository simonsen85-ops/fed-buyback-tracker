#!/usr/bin/env python3
"""
Import the tingbog mortgage data (made offline from tinglysning.dk) into data/.

The source files live outside the repo (Rasmus's analysis folder):
  fed_debt.csv        one row per registered charge (hæftelse) per tingbog attest
  fed_debt.json       same data + "comparison" (reconciliation vs FED's reports)
  fed_properties.csv  FED's property list (segment, m², company)

Usage:
  python scripts/import_debt.py <folder with the three files>

Writes:
  data/debt_raw.csv            FED-owned attests only (see PRIVACY)
  data/debt_properties.csv     property list
  data/debt_reconciliation.json  the "comparison" block of fed_debt.json

PRIVACY: this repo is public and GitHub Pages serves the whole repo root.
The full fed_debt.csv also has units FED does not own, with private persons'
names and partial CPR numbers. Only rows whose owner is a FED company are copied,
and any remaining party name that is not a legal entity becomes "(privatperson)".
Re-run this script whenever the tingbog extract is refreshed; never copy the
raw file by hand.
"""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT = ROOT / "data"
FED_CVRS = {"28720815", "33505396"}  # Fast Ejendom Danmark 1 ApS, Ejendomsselskabet Ringager ApS

KEEP_COLS = [
    "property_id", "fed_status", "search_address", "attest_address", "bfe", "ejendomstype",
    "matrikel", "ejerlejlighed_nr", "owner", "owner_cvr", "creditor", "creditor_cvr", "debtor",
    "type", "principal", "currency", "interest_rate", "loan_type", "rate_class", "special_terms",
    "registration_date", "dato_loebenummer", "priority", "also_registered_on", "underpant",
    "source_file", "lookup_note",
]
PROP_COLS = ["id", "adresse", "postnr", "by", "segment", "areal_m2", "ejer_selskab", "ejer_cvr", "status", "note"]
CPR_RE = re.compile(r"\b\d{6}-(\d{4}|\*{4})\b")
PARTY_COLS = ["owner", "creditor", "debtor", "underpant"]
# A party name counts as a legal entity if it carries one of these markers; anything
# else (e.g. an old ejerpantebrev's underpant holder) is treated as a private person.
ENTITY_RE = re.compile(r"(?i)\b(ApS|A/S|I/S|K/S|P/S|IVS|kommune|bank|fond)\b|forening|kredit|selskab|Byrde lyst")


def _redact_persons(value: str) -> str:
    parts = [p for p in (value or "").split("; ") if p]
    return "; ".join(p if ENTITY_RE.search(p) else "(privatperson)" for p in parts)


def main(src: Path) -> None:
    OUT.mkdir(exist_ok=True)

    with open(src / "fed_debt.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    kept = [r for r in rows if set((r.get("owner_cvr") or "").split("; ")) & FED_CVRS]
    for r in kept:
        for c in PARTY_COLS:
            r[c] = _redact_persons(r.get(c, ""))
        blob = " ".join(r.get(c, "") for c in KEEP_COLS)
        if CPR_RE.search(blob):
            raise SystemExit(f"CPR-like number in a FED-owned row (property {r['property_id']}); refusing to write")
    with open(OUT / "debt_raw.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=KEEP_COLS, delimiter=";", extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(kept)

    with open(src / "fed_properties.csv", encoding="utf-8-sig", newline="") as f:
        props = list(csv.DictReader(f))
    with open(OUT / "debt_properties.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PROP_COLS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(props)

    comp = json.loads((src / "fed_debt.json").read_text(encoding="utf-8"))["comparison"]
    with open(OUT / "debt_reconciliation.json", "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(comp, indent=1, ensure_ascii=False) + "\n")

    print(f"debt_raw.csv: {len(kept)} of {len(rows)} rows (FED-owned only)")
    print(f"debt_properties.csv: {len(props)} properties")
    print("debt_reconciliation.json: written")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]))
