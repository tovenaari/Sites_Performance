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
MAX_BUSINESSES = None    # Processa tutti i business

# === RELIABILITY CONFIG ===
BATCH_SIZE = 5              # Write to CSV every N businesses
RETRY_ATTEMPTS = 3          # Number of retry attempts for API calls
RETRY_DELAY = 2             # Base delay between retries (seconds)
API_DELAY = 1               # Delay between API calls to avoid rate limiting
GLOBAL_TIMEOUT = 120        # Global timeout per business (2 minutes for testing)

# === FILTERING OPTIONS ===
# REGION FILTER
# REGION_FILTER = "EMEA"      # Regione selezionata
# REGION_FILTER = "AMER"      # Regione commentata
# REGION_FILTER = "APAC"      # Regione commentata
REGION_FILTER = None         # No region filtering

# ACCOUNT TIER FILTER
# ACCOUNT_TIER_FILTER = ["2", "3", "4"]    # Filtra solo per questi tier
# ACCOUNT_TIER_FILTER = "0"   # Filter only tier 0 accounts
# ACCOUNT_TIER_FILTER = "1"   # Filter only tier 1 accounts
# ACCOUNT_TIER_FILTER = "2"   # Filter only tier 2 accounts
# ACCOUNT_TIER_FILTER = "3"   # Filter only tier 3 accounts
ACCOUNT_TIER_FILTER = None   # No tier filtering

# FH_SITE FILTER
# FH_SITE_FILTER = "No"         # Filter only non-FareHarbor sites
# FH_SITE_FILTER = "Yes"      # Filter only FareHarbor sites
FH_SITE_FILTER = None       # No filtering

# TIER 0 EXCLUSION
EXCLUDE_TIER_0 = False        # False = include tier 0 accounts
# EXCLUDE_TIER_0 = True       # True = exclude tier 0 accounts

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
                domain = row.get("name", "").strip()  # Changed from "domain" to "name"
                region = row.get("location_region", "").strip()  # Changed from "region" to "location_region"
                fh_site = row.get("fh_site", "").strip()
                account_tier = row.get("account_tier", "").strip()
                
                # Apply filters
                if not domain:
                    continue
                    
                # Region filter
                if REGION_FILTER and region != REGION_FILTER:
                    continue
                    
                # Account tier filter
                if ACCOUNT_TIER_FILTER and account_tier not in ACCOUNT_TIER_FILTER:
                    continue
                    
                # FH site filter
                if FH_SITE_FILTER and fh_site != FH_SITE_FILTER:
                    continue
                    
                # Tier 0 exclusion
                if EXCLUDE_TIER_0 and account_tier == "0":
                    continue
                    
                businesses.append({
                    "domain": domain,
                    "region": region,
                    "fh_site": fh_site,
                    "account_tier": account_tier
                })
                
                # Limit to MAX_BUSINESSES (if set)
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
    import os
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

def find_place(query):
    session = create_robust_session()
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"query": query, "key": GOOGLE_API_KEY}
    def api_call():
        response = session.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    try:
        response_data = safe_api_call(api_call)
        return response_data["results"][0] if response_data.get("results") else None
    except Exception as e:
        print(f"❌ Google Maps search failed for '{query}': {e}")
        return None

def get_place_details(place_id):
    session = create_robust_session()
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    fields = "name,website,rating,user_ratings_total,reviews,editorial_summary,geometry/location,photos"
    params = {"place_id": place_id, "fields": fields, "key": GOOGLE_API_KEY}
    def api_call():
        response = session.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    try:
        response_data = safe_api_call(api_call)
        return response_data.get("result", {})
    except Exception as e:
        print(f"❌ Google Maps details failed for place_id '{place_id}': {e}")
        return {}

def get_photo_url(place_details):
    photos = place_details.get("photos", [])
    if photos:
        photo_reference = photos[0]["photo_reference"]
        return f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={photo_reference}&key={GOOGLE_API_KEY}"
    return "https://via.placeholder.com/400x300?text=No+Image"

def get_concatenated_reviews(reviews):
    if not reviews:
        return "n/a"
    review_texts = []
    for review in reviews[:5]:
        text = review.get("text", "").strip()
        if text:
            if len(text) > 200:
                text = text[:200] + "..."
            review_texts.append(text)
    return ", ".join(review_texts) if review_texts else "n/a"

def classify_speed_lab(mobile_score):
    # mobile_score è 0-100 (lab)
    if mobile_score == "n/a":      return "⚪ n/a"
    mobile_score = float(mobile_score)
    if mobile_score < 50:          return "🔴 High (Slow)"
    if mobile_score < 75:          return "🟡 Borderline"
    return "🟢 Stable"

def classify_speed_field(field_lcp):
    # field_lcp è una stringa tipo "2.2 s" oppure "n/a"
    try:
        lcp = float(field_lcp.split()[0])
    except:
        return "⚪ n/a"
    if lcp > 4:                    return "🔴 High (Slow)"
    if lcp > 2.5:                  return "🟡 Borderline"
    return "🟢 Stable"

def classify_ux_lab(mobile_cls, mobile_inp):
    try:
        cls = float(mobile_cls)
        inp = float(mobile_inp.replace("ms",""))
    except:
        return "⚪ n/a"
    if cls > 0.1 or inp > 300:     return "🔴 High"
    if cls > 0.07 or inp > 200:    return "🟡 Moderate"
    return "🟢 Stable"

def classify_ux_field(field_cls, field_inp):
    try:
        cls = float(field_cls)
        inp = float(field_inp.replace("ms",""))
    except:
        return "⚪ n/a"
    if cls > 0.1 or inp > 300:     return "🔴 High"
    if cls > 0.07 or inp > 200:    return "🟡 Moderate"
    return "🟢 Stable"

def analyze_domain(domain):
    print(f"🌐 Analyzing domain: {domain}")
    if not domain.startswith(('http://', 'https://')):
        domain_with_https = 'https://' + domain
    else:
        domain_with_https = domain
    print(f"📍 Step 1/6: Searching '{domain}' on Google Maps...")
    place = find_place(domain)
    google_data = {
        "name": domain,
        "rating_google": "n/a",
        "reviews": "n/a",
        "concatenated_reviews": "n/a",
        "photo_url": "n/a",
        "latitude": "n/a",
        "longitude": "n/a"
    }
    if place:
        print(f"📍 Step 2/6: Getting place details...")
        details = get_place_details(place["place_id"])
        location = details.get("geometry", {}).get("location", {})
        lat, lng = location.get("lat"), location.get("lng")
        google_data.update({
            "name": details.get("name", domain),
            "rating_google": details.get("rating", "n/a"),
            "reviews": details.get("user_ratings_total", "n/a"),
            "concatenated_reviews": get_concatenated_reviews(details.get("reviews", [])),
            "photo_url": get_photo_url(details),
            "latitude": lat,
            "longitude": lng
        })
    else:
        print(f"❌ No Google Maps result found for {domain}")
    print(f"⚡ Step 3/6: Running PageSpeed analysis for: {domain_with_https}")
    try:
        ps = analyze_site(domain_with_https)
        print(f"✅ PageSpeed analysis completed successfully")
    except Exception as e:
        print(f"❌ PageSpeed analysis failed: {e}")
        ps = {
            "mobile": "n/a", "mobile_lcp": "n/a", "mobile_cls": "n/a", "mobile_inp": "n/a",
            "desktop": "n/a", "desktop_lcp": "n/a", "desktop_cls": "n/a", "desktop_inp": "n/a",
            "field_lcp": "n/a", "field_cls": "n/a", "field_inp": "n/a", "field_fcp": "n/a",
            "field_speed_problem": "⚪ n/a", "field_ux_problem": "⚪ n/a",
            "lab_speed_problem": "⚪ n/a", "lab_ux_problem": "⚪ n/a",
            "perf_score": "n/a", "accessibility": "n/a", "best_practices": "n/a", "seo": "n/a", "fh_score": "n/a", "rating": "Error", "issues": f"API Fail: {str(e)}",
            "img_sav_kb": "n/a", "js_sav_kb": "n/a", "css_sav_kb": "n/a"
        }
    return {
        "shortname": domain,
        "website": domain_with_https,
        "region": "",
        "rating_google": google_data["rating_google"],
        "reviews": google_data["reviews"],
        "field_lcp": ps["field_lcp"],
        "field_cls": ps["field_cls"],
        "field_inp": ps["field_inp"],
        "field_fcp": ps["field_fcp"],
        "field_speed_problem": ps["field_speed_problem"],
        "field_ux_problem": ps["field_ux_problem"],
        "perf_score": ps["perf_score"],
        "issues": ps["issues"],
        "category": google_data["name"],
        "accessibility": ps["accessibility"],
        "best_practices": ps["best_practices"],
        "seo": ps["seo"],
        "concatenated_reviews": google_data["concatenated_reviews"],
        "title": extract_title(domain_with_https),
        "mobile": ps["mobile"],
        "mobile_lcp": ps["mobile_lcp"],
        "mobile_cls": ps["mobile_cls"],
        "mobile_inp": ps["mobile_inp"],
        "desktop": ps["desktop"],
        "desktop_lcp": ps["desktop_lcp"],
        "desktop_cls": ps["desktop_cls"],
        "desktop_inp": ps["desktop_inp"],
        "lab_speed_problem": ps["lab_speed_problem"],
        "lab_ux_problem": ps["lab_ux_problem"],
        "fh_score": ps["fh_score"],
        "rating": ps["rating"],
        "img_sav_kb": ps["img_sav_kb"],
        "js_sav_kb":  ps["js_sav_kb"],
        "css_sav_kb": ps["css_sav_kb"],
        "photo_url": google_data["photo_url"],
        "fh_site": "",
        "account_tier": "",
        "latitude": google_data["latitude"],
        "longitude": google_data["longitude"]
    }

def extract_title(url):
    try:
        html = requests.get(url, timeout=5).text
        soup = BeautifulSoup(html, "html.parser")
        return soup.title.string.strip() if soup.title else "n/a"
    except:
        return "n/a"

def check_site_accessibility(url):
    session = create_robust_session()
    urls_to_try = [
        url,
        url.replace('https://', 'http://'),
        url.replace('www.', ''),
        'https://www.' + url.split('://')[-1] if '://' in url else 'https://www.' + url
    ]
    for attempt_url in urls_to_try:
        try:
            response = session.head(attempt_url, timeout=10, allow_redirects=True)
            if response.status_code < 400:
                print(f"✅ Site accessible: {attempt_url}")
                return attempt_url
        except Exception as e:
            print(f"⚠️ Site not accessible: {attempt_url} - {e}")
            continue
    print(f"❌ Site not accessible: {url}")
    return None

def get_pagespeed_data(url, strategy):
    session = create_robust_session()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    urls_to_try = [
        url,
        url.replace('https://', 'http://'),
        url.replace('www.', ''),
        'https://www.' + url.split('://')[-1] if '://' in url else 'https://www.' + url
    ]
    for attempt_url in urls_to_try:
        try:
            def api_call():
                response = session.get("https://www.googleapis.com/pagespeedonline/v5/runPagespeed", 
                                      params={"url": attempt_url, "strategy": strategy, "key": GOOGLE_API_KEY},
                                      timeout=60)
                response.raise_for_status()
                return response.json()
            data = safe_api_call(api_call)
            # Extract field data (real user data)
            field_lcp = field_cls = field_inp = field_fcp = "n/a"
            try:
                metrics = data.get("loadingExperience", {}).get("metrics", {})
                if "LARGEST_CONTENTFUL_PAINT_MS" in metrics:
                    field_lcp = str(round(metrics["LARGEST_CONTENTFUL_PAINT_MS"]["percentile"] / 1000, 1)) + " s"
                if "CUMULATIVE_LAYOUT_SHIFT_SCORE" in metrics:
                    field_cls = str(metrics["CUMULATIVE_LAYOUT_SHIFT_SCORE"]["percentile"] / 1000)
                if "INP" in metrics:
                    field_inp = str(round(metrics["INP"]["percentile"])) + " ms"
                if "FIRST_CONTENTFUL_PAINT_MS" in metrics:
                    field_fcp = str(round(metrics["FIRST_CONTENTFUL_PAINT_MS"]["percentile"] / 1000, 1)) + " s"
            except:
                pass
            if data and "lighthouseResult" in data:
                score = round(data["lighthouseResult"]["categories"]["performance"]["score"] * 100)
                
                # Safely extract accessibility, best practices, and SEO scores
                accessibility_score = "n/a"
                best_practices_score = "n/a"
                seo_score = "n/a"
                
                try:
                    if "accessibility" in data["lighthouseResult"]["categories"]:
                        accessibility_score = int(data["lighthouseResult"]["categories"]["accessibility"]["score"] * 100)
                except:
                    pass
                
                try:
                    if "best-practices" in data["lighthouseResult"]["categories"]:
                        best_practices_score = int(data["lighthouseResult"]["categories"]["best-practices"]["score"] * 100)
                except:
                    pass
                
                try:
                    if "seo" in data["lighthouseResult"]["categories"]:
                        seo_score = int(data["lighthouseResult"]["categories"]["seo"]["score"] * 100)
                except:
                    pass
                
                audits = data["lighthouseResult"]["audits"]
                opps = extract_opportunity_savings(audits)
                lcp = audits["largest-contentful-paint"]["displayValue"]
                cls = audits["cumulative-layout-shift"]["displayValue"]
                inp = audits.get("interactive", {}).get("displayValue", "n/a")
                return {"score": score, "lcp": lcp, "cls": cls, "inp": inp,
                        "img_sav": opps["img"], "js_sav": opps["js"], "css_sav": opps["css"],
                        "field_lcp": field_lcp, "field_cls": field_cls, "field_inp": field_inp, "field_fcp": field_fcp,
                        "accessibility": accessibility_score,
                        "best_practices": best_practices_score,
                        "seo": seo_score}
        except Exception as e:
            print(f"⚠️ PageSpeed failed for {attempt_url} ({strategy}): {e}")
            continue
    print(f"❌ PageSpeed analysis failed for all URL variations: {url}")
    return None

def extract_opportunity_savings(audits):
    mapping = {
        "uses-optimized-images":       "img",
        "uses-responsive-images":      "img",
        "efficient-animated-content":  "img",
        "modern-image-formats":        "img",
        "unused-javascript":           "js",
        "unminified-javascript":       "js",
        "unused-css-rules":            "css",
        "unminified-css":              "css",
    }
    savings = {"img": 0, "js": 0, "css": 0}
    for audit_id, target in mapping.items():
        audit = audits.get(audit_id)
        if audit and audit.get("details", {}).get("type") == "opportunity":
            bytes_saved = audit["details"].get("overallSavingsBytes", 0)
            savings[target] += round(bytes_saved / 1024, 1)
    return savings

def analyze_site(website):
    accessible_url = check_site_accessibility(website)
    if not accessible_url:
        return {
            "mobile": "n/a", "mobile_lcp": "n/a", "mobile_cls": "n/a", "mobile_inp": "n/a",
            "desktop": "n/a", "desktop_lcp": "n/a", "desktop_cls": "n/a", "desktop_inp": "n/a",
            "field_lcp": "n/a", "field_cls": "n/a", "field_inp": "n/a", "field_fcp": "n/a",
            "field_speed_problem": "⚪ n/a", "field_ux_problem": "⚪ n/a",
            "lab_speed_problem": "⚪ n/a", "lab_ux_problem": "⚪ n/a",
            "perf_score": "n/a", "accessibility": "n/a", "best_practices": "n/a", "seo": "n/a", "fh_score": "n/a", "rating": "Error", "issues": "Site not accessible",
            "img_sav_kb": "n/a", "js_sav_kb": "n/a", "css_sav_kb": "n/a"
        }
    mobile = get_pagespeed_data(accessible_url, "mobile")
    desktop = get_pagespeed_data(accessible_url, "desktop")
    if not mobile or not desktop:
        return {
            "mobile": "n/a", "mobile_lcp": "n/a", "mobile_cls": "n/a", "mobile_inp": "n/a",
            "desktop": "n/a", "desktop_lcp": "n/a", "desktop_cls": "n/a", "desktop_inp": "n/a",
            "field_lcp": "n/a", "field_cls": "n/a", "field_inp": "n/a", "field_fcp": "n/a",
            "field_speed_problem": "⚪ n/a", "field_ux_problem": "⚪ n/a",
            "lab_speed_problem": "⚪ n/a", "lab_ux_problem": "⚪ n/a",
            "perf_score": "n/a", "accessibility": "n/a", "best_practices": "n/a", "seo": "n/a", "fh_score": "n/a", "rating": "Error", "issues": "PageSpeed API Fail",
            "img_sav_kb": "n/a", "js_sav_kb": "n/a", "css_sav_kb": "n/a"
        }
    base_score = (mobile["score"] + desktop["score"]) / 2
    perf_score = round(base_score)
    mobile_lcp_seconds = float(mobile["lcp"].replace("s", "").strip()) if "s" in mobile["lcp"] else 0
    desktop_lcp_seconds = float(desktop["lcp"].replace("s", "").strip()) if "s" in desktop["lcp"] else 0
    avg_lcp = (mobile_lcp_seconds + desktop_lcp_seconds) / 2
    mobile_cls = float(mobile["cls"])
    desktop_cls = float(desktop["cls"])
    avg_cls = (mobile_cls + desktop_cls) / 2
    mobile_inp_ms = float(mobile["inp"].replace("ms", "").strip()) if "ms" in mobile["inp"] else 0
    desktop_inp_ms = float(desktop["inp"].replace("ms", "").strip()) if "ms" in desktop["inp"] else 0
    avg_inp = (mobile_inp_ms + desktop_inp_ms) / 2
    penalties = 0
    if avg_lcp > 2.5:
        penalties += 5
    if avg_cls > 0.1:
        penalties += 3
    if avg_inp > 300:
        penalties += 2.5
    bonus = 0
    if mobile["score"] > 75:
        bonus += 2
    if desktop["score"] > 80:
        bonus += 2
    final_score = max(0, min(100, round(base_score - penalties + bonus)))
    rating = "Good" if final_score >= 90 else "Needs Improvement" if final_score >= 50 else "Poor"
    issues = []
    if avg_lcp > 2.5:
        issues.append(f"High LCP (avg: {avg_lcp:.1f}s)")
    if avg_cls > 0.1:
        issues.append(f"Layout Shift (avg: {avg_cls:.3f})")
    if avg_inp > 300:
        issues.append(f"Poor INP (avg: {avg_inp:.0f}ms)")
    if mobile["score"] > 75:
        issues.append(f"Mobile bonus (+2)")
    if desktop["score"] > 80:
        issues.append(f"Desktop bonus (+2)")
    
    # Calculate classification values
    lab_speed   = classify_speed_lab(mobile["score"])
    field_speed = classify_speed_field(mobile["field_lcp"])
    lab_ux      = classify_ux_lab(mobile["cls"], mobile["inp"])
    field_ux    = classify_ux_field(mobile["field_cls"], mobile["field_inp"])
    
    return {
        "mobile": mobile["score"],
        "mobile_lcp": mobile["lcp"],
        "mobile_cls": mobile["cls"],
        "mobile_inp": mobile["inp"],
        "desktop": desktop["score"],
        "desktop_lcp": desktop["lcp"],
        "desktop_cls": desktop["cls"],
        "desktop_inp": desktop["inp"],
        "field_lcp": mobile["field_lcp"],
        "field_cls": mobile["field_cls"],
        "field_inp": mobile["field_inp"],
        "field_fcp": mobile["field_fcp"],
        "field_speed_problem": field_speed,
        "field_ux_problem": field_ux,
        "lab_speed_problem": lab_speed,
        "lab_ux_problem": lab_ux,
        "perf_score": perf_score,
        "accessibility": mobile.get("accessibility", "n/a") if mobile.get("accessibility") != "n/a" else "n/a",
        "best_practices": mobile.get("best_practices", "n/a") if mobile.get("best_practices") != "n/a" else "n/a",
        "seo": mobile.get("seo", "n/a") if mobile.get("seo") != "n/a" else "n/a",
        "fh_score": final_score,
        "rating": rating,
        "issues": ", ".join(issues) if issues else "None",
        "img_sav_kb":  mobile["img_sav"] + desktop["img_sav"],
        "js_sav_kb":   mobile["js_sav"]  + desktop["js_sav"],
        "css_sav_kb":  mobile["css_sav"] + desktop["css_sav"]
    }

def run_with_timeout(func, *args, timeout=GLOBAL_TIMEOUT, **kwargs):
    """Run a function with a timeout using threading (Windows compatible)"""
    result = [None]
    exception = [None]
    
    def target():
        try:
            result[0] = func(*args, **kwargs)
        except Exception as e:
            exception[0] = e
    
    thread = threading.Thread(target=target)
    thread.daemon = True
    thread.start()
    thread.join(timeout)
    
    if thread.is_alive():
        print(f"⏰ Operation timed out after {timeout} seconds")
        raise TimeoutError(f"Operation timed out after {timeout} seconds")
    
    if exception[0]:
        raise exception[0]
    
    return result[0]

def print_progress_bar(current, total, width=50):
    """Print a progress bar in the terminal"""
    progress = current / total
    filled_width = int(width * progress)
    bar = '█' * filled_width + '░' * (width - filled_width)
    percentage = progress * 100
    print(f"\r📊 Progress: [{bar}] {current}/{total} ({percentage:.1f}%)", end='', flush=True)

def main():
    print(f"🔍 Reading businesses from '{INPUT_CSV}'")
    if REGION_FILTER:
        print(f"🔍 Filtering for region: {REGION_FILTER}")
    else:
        print(f"🔍 No region filtering applied")
    if EXCLUDE_TIER_0:
        print(f"🔍 Excluding tier 0 accounts")
    else:
        print(f"🔍 Including tier 0 accounts")
    if ACCOUNT_TIER_FILTER:
        print(f"🔍 Additional filter: account_tier = {ACCOUNT_TIER_FILTER}")
    else:
        print(f"🔍 No additional account tier filtering applied")
    if FH_SITE_FILTER:
        print(f"🔍 Additional filter: fh_site = {FH_SITE_FILTER}")
    else:
        print(f"🔍 No additional fh_site filtering applied")
    
    businesses = load_csv_input()
    if not businesses:
        print(f"❌ No businesses found")
        if REGION_FILTER:
            print(f"   for region {REGION_FILTER}")
        if ACCOUNT_TIER_FILTER:
            print(f"   and account_tier {ACCOUNT_TIER_FILTER}")
        if EXCLUDE_TIER_0:
            print(f"   (tier 0 accounts are excluded)")
        if FH_SITE_FILTER:
            print(f"   and fh_site {FH_SITE_FILTER}")
        return
    
    total_businesses = len(businesses)
    print(f"✅ Found {total_businesses} business(es) to analyze")
    
    processed_count = 0
    failed_count = 0
    
    print("\n" + "="*60)
    print("🚀 STARTING ANALYSIS")
    print("="*60)
    
    results = []
    
    for index, business in enumerate(businesses, 1):
        # Print progress bar
        print_progress_bar(index, total_businesses)
        
        print(f"\n\n🏢 Processing: {business['domain']} (Region: {business['region']}, FH: {business['fh_site']}, Tier: {business['account_tier']})")
        print(f"📍 Step 1/6: Analyzing domain: {business['domain']}")
        
        try:
            # Run analysis with timeout
            try:
                row = run_with_timeout(analyze_domain, business['domain'], timeout=GLOBAL_TIMEOUT)
            except TimeoutError:
                print(f"⏰ Analysis timed out for {business['domain']}, creating error row")
                row = {
                    "shortname": business['domain'],
                    "website": f"https://{business['domain']}",
                    "region": "",
                    "rating_google": "n/a",
                    "reviews": "n/a",
                    "field_lcp": "n/a", "field_cls": "n/a", "field_inp": "n/a", "field_fcp": "n/a",
                    "field_speed_problem": "⚪ n/a", "field_ux_problem": "⚪ n/a",
                    "perf_score": "n/a", "issues": "Analysis timed out", "category": "n/a",
                    "accessibility": "n/a", "best_practices": "n/a", "seo": "n/a",
                    "concatenated_reviews": "n/a",
                    "title": "n/a",
                    "mobile": "n/a",
                    "mobile_lcp": "n/a",
                    "mobile_cls": "n/a",
                    "mobile_inp": "n/a",
                    "desktop": "n/a",
                    "desktop_lcp": "n/a",
                    "desktop_cls": "n/a",
                    "desktop_inp": "n/a",
                    "lab_speed_problem": "⚪ n/a", "lab_ux_problem": "⚪ n/a",
                    "fh_score": "n/a",
                    "rating": "Error",
                    "img_sav_kb": "n/a", "js_sav_kb": "n/a", "css_sav_kb": "n/a",
                    "photo_url": "n/a",
                    "fh_site": business.get('fh_site', ''),
                    "account_tier": business.get('account_tier', ''),
                    "latitude": "n/a",
                    "longitude": "n/a"
                }
            
            row['region'] = business['region']
            row['fh_site'] = business['fh_site']  # Add fh_site to output
            row['account_tier'] = business['account_tier']  # Add account_tier to output
            results.append(row)
            processed_count += 1
            print(f"✅ Data collected for '{OUTPUT_CSV}'")
            
        except Exception as e:
            failed_count += 1
            print(f"❌ Failed to process {business['domain']}: {e}")
            # Add error row to results
            error_row = {
                "shortname": business['domain'],
                "website": f"https://{business['domain']}",
                "region": "",
                "rating_google": "n/a",
                "reviews": "n/a",
                "field_lcp": "n/a", "field_cls": "n/a", "field_inp": "n/a", "field_fcp": "n/a",
                "field_speed_problem": "⚪ n/a", "field_ux_problem": "⚪ n/a",
                "perf_score": "n/a", "issues": f"Processing failed: {str(e)}", "category": "n/a",
                "accessibility": "n/a", "best_practices": "n/a", "seo": "n/a",
                "concatenated_reviews": "n/a",
                "title": "n/a",
                "mobile": "n/a",
                "mobile_lcp": "n/a",
                "mobile_cls": "n/a",
                "mobile_inp": "n/a",
                "desktop": "n/a",
                "desktop_lcp": "n/a",
                "desktop_cls": "n/a",
                "desktop_inp": "n/a",
                "lab_speed_problem": "⚪ n/a", "lab_ux_problem": "⚪ n/a",
                "fh_score": "n/a",
                "rating": "Error",
                "img_sav_kb": "n/a", "js_sav_kb": "n/a", "css_sav_kb": "n/a",
                "photo_url": "n/a",
                "fh_site": business.get('fh_site', ''),
                "account_tier": business.get('account_tier', ''),
                "latitude": "n/a",
                "longitude": "n/a"
            }
            results.append(error_row)

    # Final progress bar
    print_progress_bar(total_businesses, total_businesses)
    print(f"\n\n{'='*60}")
    print(f"🎉 ANALYSIS COMPLETE!")
    print(f"📊 Processed: {processed_count}/{total_businesses} businesses successfully")
    print(f"❌ Failed: {failed_count}/{total_businesses} businesses")
    print(f"📋 Results saved to: '{OUTPUT_CSV}'")
    print(f"🔧 Reliability features enabled:")
    print(f"   - Retry mechanism for API calls")
    print(f"   - Exponential backoff for failures")
    print(f"{'='*60}")

    export_to_csv(results)

if __name__ == "__main__":
    main() 
