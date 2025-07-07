# -*- coding: utf-8 -*-
"""
Website Audit – SEMrush‑only
----------------------------
This script reads all domains from an input CSV (default: `sites1.csv`),
queries SEMrush APIs, and writes selected KPIs to
`output/website_audit_results.csv`.

Core KPIs collected per domain:
- **Authority Score** – from domain_ranks
- **Organic Traffic** – estimated organic visits
- **Organic Keywords** – number of keywords ranked
- **Backlinks** – total backlinks (from backlinks_overview)
- **Paid Traffic Estimate** – estimated monthly paid search traffic (from domain_adwords)

Requisites:
- `requests`
- GitHub Actions secret: `SEMRUSH_API_KEY`
"""
import csv
import os
import time
import argparse
from pathlib import Path
from typing import Dict, List, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SEMRUSH_API_KEY = os.getenv("SEMRUSH_API_KEY")
if not SEMRUSH_API_KEY:
    raise RuntimeError("Missing SEMRUSH_API_KEY environment variable. Configure it as a GitHub Actions secret.")

INPUT_CSV_DEFAULT = "sites1.csv"
OUTPUT_CSV_DEFAULT = "output/website_audit_results.csv"
RETRY_ATTEMPTS = 3
RETRY_DELAY = 2
API_DELAY = 1

def create_session() -> requests.Session:
    retry = Retry(total=RETRY_ATTEMPTS,
                  backoff_factor=RETRY_DELAY,
                  status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["GET", "HEAD"])
    adapter = HTTPAdapter(max_retries=retry)
    s = requests.Session()
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s

SESSION = create_session()


def fetch_domain_ranks(domain: str) -> Dict[str, Any]:
    params = {
        "key": SEMRUSH_API_KEY,
        "domain": domain,
        "type": "domain_ranks",
        "export": "api",
        "display_limit": 1,
    }
    r = SESSION.get("https://api.semrush.com/", params=params, timeout=30)
    time.sleep(API_DELAY)
    lines = r.text.strip().split("\n")
    if len(lines) < 2:
        return {}
    keys, values = lines[0].split(";"), lines[1].split(";")
    return dict(zip(keys, values))


def fetch_backlinks_overview(domain: str) -> Dict[str, Any]:
    params = {
        "key": SEMRUSH_API_KEY,
        "target": domain,
        "type": "backlinks_overview",
        "export": "api",
        "target_type": "root_domain"
    }
    r = SESSION.get("https://api.semrush.com/", params=params, timeout=30)
    time.sleep(API_DELAY)
    lines = r.text.strip().split("\n")
    if len(lines) < 2:
        return {}
    keys, values = lines[0].split(";"), lines[1].split(";")
    return dict(zip(keys, values))


def fetch_adwords_overview(domain: str) -> Dict[str, Any]:
    params = {
        "key": SEMRUSH_API_KEY,
        "domain": domain,
        "type": "domain_adwords",
        "export": "api",
        "display_limit": 1
    }
    r = SESSION.get("https://api.semrush.com/", params=params, timeout=30)
    time.sleep(API_DELAY)
    lines = r.text.strip().split("\n")
    if len(lines) < 2:
        return {}
    keys, values = lines[0].split(";"), lines[1].split(";")
    return dict(zip(keys, values))


def analyze_domain(domain: str) -> Dict[str, Any]:
    print(f"🔍 Processing {domain}…")
    try:
        ranks = fetch_domain_ranks(domain)
    except Exception as e:
        print(f"⚠️ domain_ranks failed: {e}")
        ranks = {}

    try:
        backlinks = fetch_backlinks_overview(domain)
    except Exception as e:
        print(f"⚠️ backlinks_overview failed: {e}")
        backlinks = {}

    try:
        adwords = fetch_adwords_overview(domain)
    except Exception as e:
        print(f"⚠️ adwords_overview failed: {e}")
        adwords = {}

    return {
        "domain": domain,
        "sem_authority_score": ranks.get("Authority Score", "n/a"),
        "sem_organic_traffic": ranks.get("Organic Traffic", "n/a"),
        "sem_organic_keywords": ranks.get("Organic Keywords", "n/a"),
        "sem_backlinks": backlinks.get("Backlinks", "n/a"),
        "paid_traffic_est": adwords.get("Paid Traffic", "n/a"),
    }


def load_input(path: str) -> List[str]:
    """Extract domains from CSV.
    Priority order:
    1. Column named 'name' (legacy)
    2. Column named 'shortname'  ⚑ NEW
    3. Column named 'website'
    4. Any field that already contains a dot ('.')  → looks like a domain
    If we still can't find a dot, append '.com' as a last‑chance fallback.
    """
    domains: List[str] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 1️⃣ direct column names
            domain = (
                row.get("name")
                or row.get("shortname")
                or row.get("website")
                or ""
            ).strip()

            # 2️⃣ If still empty, search any value that already looks like a domain
            if not domain:
                for val in row.values():
                    val = str(val).strip()
                    if "." in val:  # rudimentary domain check
                        domain = val
                        break

            # 3️⃣ Fallback – if no dot, assume .com
            if domain and "." not in domain:
                domain += ".com"

            if domain:
                domains.append(domain)
    return domains


def export_csv(rows: List[Dict[str, Any]], out_path: str):
    if not rows:
        print("⚠️ No data to export")
        return
    out_dir = Path(out_path).parent
    if out_dir.exists():
        if out_dir.is_file():
            out_dir.unlink()
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"✅ Exported {len(rows)} rows to {out_path}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=INPUT_CSV_DEFAULT)
    parser.add_argument("--output", default=OUTPUT_CSV_DEFAULT)
    args = parser.parse_args()

    print(f"📥 Loading input from {args.input}")
    domains = load_input(args.input)
    print(f"🔢 Found {len(domains)} domains")

    results = []
    for idx, domain in enumerate(domains, 1):
        print(f"\n🔢 [{idx}/{len(domains)}] Processing: {domain}")
        try:
            results.append(analyze_domain(domain))
        except Exception as e:
            print(f"❌ Error: {e}")
            results.append({"domain": domain, "error": str(e)})

    export_csv(results, args.output)



if __name__ == "__main__":
    main()
