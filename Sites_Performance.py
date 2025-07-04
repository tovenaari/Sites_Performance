import requests
import time
import os
import random
import threading
import csv
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# === CONFIG ===
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise RuntimeError(
        "GOOGLE_API_KEY environment variable not found. "
        "Add it locally (es: `export GOOGLE_API_KEY=...`) "
        "o configura il secret su GitHub Actions."
    )

INPUT_CSV = "sites1.csv"  # CSV file to read from root
OUTPUT_CSV = "output/website_audit_results.csv"  # CSV file to write to
MAX_BUSINESSES = 5    # Processa solo i primi 5 business

# === RELIABILITY CONFIG ===
BATCH_SIZE = 5              # Write to CSV every N businesses
RETRY_ATTEMPTS = 3          # Number of retry attempts for API calls
RETRY_DELAY = 2             # Base delay between retries (seconds)
API_DELAY = 1               # Delay between API calls to avoid rate limiting
GLOBAL_TIMEOUT = 120        # Global timeout per business (2 minutes for testing)

# === FILTERING OPTIONS ===
REGION_FILTER = None         # No region filtering
ACCOUNT_TIER_FILTER = None   # No tier filtering
FH_SITE_FILTER = None        # No filtering
EXCLUDE_TIER_0 = False       # False = include tier 0 accounts

# Expected headers for output CSV
EXPECTED_HEADERS = [
    "shortname", "website", "region", "rating_google", "reviews",
    "field_lcp", "field_cls", "field_inp", "field_fcp",
    "field_speed_problem", "field_ux_problem", "perf_score", "issues", "category",
    "accessibility", "best_practices", "seo",
    "concatenated_reviews", "title",
    "mobile", "mobile_lcp", "mobile_cls", "mobile_inp",
    "desktop", "desktop_lcp", "desktop_cls", "desktop_inp",
    "lab_speed_problem", "lab_ux_problem",
    "fh_score", "rating",
    "img_sav_kb", "js_sav_kb", "css_sav_kb",
    "photo_url", "fh_site", "account_tier", "latitude", "longitude"
]

def create_robust_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=RETRY_ATTEMPTS,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"],
        backoff_factor=RETRY_DELAY
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def safe_api_call(func, *args, **kwargs):
    for attempt in range(RETRY_ATTEMPTS): 
        try:
            print(f"🔄 API call attempt {attempt + 1}/{RETRY_ATTEMPTS}")
            result = func(*args, **kwargs)
            time.sleep(API_DELAY)
            return result
        except Exception as e:
            if attempt == RETRY_ATTEMPTS - 1:
                print(f"❌ API call failed after {RETRY_ATTEMPTS} attempts: {e}")
                raise
            print(f"⚠️ API call attempt {attempt + 1} failed: {e}")
            time.sleep(RETRY_DELAY * (2 ** attempt))
    return None

def load_csv_input(input_path=INPUT_CSV):
    """Load businesses from CSV file"""
    businesses = []
    try:
        with open(input_path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                domain = row.get("domain", "").strip()
                region = row.get("region", "").strip()
                fh_site = row.get("fh_site", "").strip()
                account_tier = row.get("account_tier", "").strip()
                if not domain:
                    continue
                if REGION_FILTER and region != REGION_FILTER:
                    continue
                if ACCOUNT_TIER_FILTER and account_tier not in ACCOUNT_TIER_FILTER:
                    continue
                if FH_SITE_FILTER and fh_site != FH_SITE_FILTER:
                    continue
                if EXCLUDE_TIER_0 and account_tier == "0":
                    continue
                businesses.append({
                    "domain": domain,
                    "region": region,
                    "fh_site": fh_site,
                    "account_tier": account_tier
                })
                if MAX_BUSINESSES and len(businesses) >= MAX_BUSINESSES:
                    break
        print(f"✅ Loaded {len(businesses)} businesses from CSV")
        return businesses
    except FileNotFoundError:
        print(f"❌ Input CSV file not found: {input_path}")
        return []
    except Exception as e:
        print(f"❌ Error reading CSV file: {e}")
        return []

def export_to_csv(rows, output_path=OUTPUT_CSV):
    """Export results to CSV file"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    if not rows:
        print("⚠️ No data to export")
        return
    headers = EXPECTED_HEADERS
    with open(output_path, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    print(f"✅ Exported {len(rows)} rows to {output_path}")

# ... (tutto il resto del codice rimane invariato, come già fornito) ...

if __name__ == "__main__":
    main()
