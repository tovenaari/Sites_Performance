#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SEO Visibility Audit – SEMrush-only
===================================

Reads up to three domains from an input CSV, pulls SEMrush data
(domain_ranks + backlinks_overview + domain_adwords) and writes the
results to `output/website_audit_results.csv`.

Add or rename columns freely – the workflow never relies on a fixed header.
"""
import csv, time, argparse
from pathlib import Path
from typing import Dict, List, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ──────────────────────────────────  CONFIG  ──────────────────────────────────
SEMRUSH_KEY_PATH = Path(__file__).parent / "semrush_api_key.txt"
if not SEMRUSH_KEY_PATH.exists():
    raise RuntimeError("🔑  semrush_api_key.txt not found")

SEMRUSH_API_KEY = SEMRUSH_KEY_PATH.read_text(errors="ignore").strip().lstrip("\ufeff")
INPUT_CSV_DEFAULT  = "sites1.csv"
OUTPUT_CSV_DEFAULT = "output/website_audit_results.csv"
MAX_DOMAINS        = 3          # bump to None when you’re done testing
RETRY_ATTEMPTS     = 3
RETRY_DELAY        = 2
API_DELAY          = 1

# ─────────────────────────────── HTTP session with retry ──────────────────────
def make_session() -> requests.Session:
    retry = Retry(
        total=RETRY_ATTEMPTS,
        backoff_factor=RETRY_DELAY,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s

S = make_session()

# ──────────────────────────────  SEMrush helpers  ─────────────────────────────
API = "https://api.semrush.com/"

def csv_request(params: Dict[str, Any]) -> Dict[str, str]:
    """Return the first (only) row as a dict; empty dict if no data."""
    params["key"] = SEMRUSH_API_KEY
    r = S.get(API, params=params, timeout=30)
    time.sleep(API_DELAY)
    rows = r.text.strip().splitlines()
    if len(rows) < 2:
        return {}
    header, values = rows[0].split(";"), rows[1].split(";")
    return dict(zip(header, values))

def domain_ranks(domain: str)          -> Dict[str, str]:
    return csv_request({"type": "domain_ranks", "domain": domain, "export": "api"})

def backlinks_overview(domain: str)    -> Dict[str, str]:
    return csv_request({
        "type": "backlinks_overview",
        "target": domain,
        "target_type": "root_domain",
        "export": "api"
    })

def adwords_overview(domain: str)      -> Dict[str, str]:
    # only one row (totals) – will be empty if no Ads
    return csv_request({"type": "domain_adwords", "domain": domain, "display_limit": 1})

# ───────────────────────────────  Domain audit  ───────────────────────────────
def audit(domain: str) -> Dict[str, Any]:
    ranks      = domain_ranks(domain)
    links      = backlinks_overview(domain)
    ads        = adwords_overview(domain)

    return {
        "domain"              : domain,
        "sem_authority_score" : ranks.get("Authority Score",  "n/a"),
        "sem_organic_traffic" : ranks.get("Organic Traffic",  "n/a"),
        "sem_organic_keywords": ranks.get("Organic Keywords", "n/a"),
        "sem_backlinks"       : links.get("Backlinks",        "n/a"),
        "paid_traffic_est"    : ads.get("Traffic",            "n/a"),
    }

# ───────────────────────────── CSV I/O convenience ────────────────────────────
def load_domains(path: str) -> List[str]:
    out: List[str] = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            d = (row.get("name") or row.get("domain") or "").strip()
            if d:
                out.append(d)
            if MAX_DOMAINS and len(out) >= MAX_DOMAINS:
                break
    return out

def save(rows: List[Dict[str, Any]], dest: str) -> None:
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        print("⚠️  Nothing to export.")
        return
    with open(dest, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"✅  Saved {len(rows)} rows to {dest}")

# ───────────────────────────────────  CLI  ────────────────────────────────────
def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input",  default=INPUT_CSV_DEFAULT,
                   help="CSV containing a 'name' or 'domain' column")
    p.add_argument("--output", default=OUTPUT_CSV_DEFAULT,
                   help="Where to write the audit results")
    args = p.parse_args()

    domains = load_domains(args.input)
    print(f"🔢  Auditing {len(domains)} domain(s)…")

    results = [audit(d) for d in domains]
    save(results, args.output)

if __name__ == "__main__":
    main()
