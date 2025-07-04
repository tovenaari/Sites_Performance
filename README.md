# Site Scraper + Audit Data Tool

This tool analyzes websites using Google Maps and Google PageSpeed APIs, and exports results to a CSV file.

## Setup

1. **Install dependencies:**
```bash
pip install requests beautifulsoup4
```

2. **Set Google API Key:**
   - Get a Google API key with Maps and PageSpeed APIs enabled
   - Set it as environment variable: `export GOOGLE_API_KEY=your_api_key_here`
   - For GitHub Actions: add it as a repository secret named `GOOGLE_API_KEY`

3. **Prepare input data:**
   - Create `Site Score V1 - EMEAnoFHS.csv` in the root directory with the following columns:
   ```csv
   domain,region,fh_site,account_tier
   example.com,EMEA,No,3
   test-site.com,AMER,Yes,2
   ```

## Usage

Run the script:
```bash
python Site_Scraper_Audit_Data_V3_GITHUBACTION.py
```

## Output

The script will:
1. Read sites from `input/sites.csv`
2. Analyze each site using Google Maps and PageSpeed APIs
3. Export results to `output/website_audit_results.csv`

## Output Columns

The CSV output includes 39 columns with detailed metrics:
- Basic info: shortname, website, region, rating_google, reviews
- Field data: field_lcp, field_cls, field_inp, field_fcp
- Performance scores: perf_score, mobile, desktop
- Classifications: field_speed_problem, field_ux_problem, lab_speed_problem, lab_ux_problem
- Lighthouse scores: accessibility, best_practices, seo
- Optimization opportunities: img_sav_kb, js_sav_kb, css_sav_kb
- And more...

## Configuration

Edit the script to modify:
- `MAX_BUSINESSES`: Limit number of sites to process (None = all)
- `REGION_FILTER`: Filter by region (None = all regions)
- `ACCOUNT_TIER_FILTER`: Filter by account tier (None = all tiers)
- `FH_SITE_FILTER`: Filter by FareHarbor site (None = all)
- `EXCLUDE_TIER_0`: Exclude tier 0 accounts (False = include all)

## GitHub Actions Ready

This version is ready for GitHub Actions:
- No Google Sheets dependencies
- Uses local CSV files
- No OAuth authentication required
- Uses environment variables for API keys

### GitHub Actions Setup

1. **Add repository secret:**
   - Go to your repository Settings → Secrets and variables → Actions
   - Add a new secret named `GOOGLE_API_KEY` with your Google API key

2. **Create workflow file** (`.github/workflows/audit.yml`):
```yaml
name: Website Audit
on:
  push:
    paths: ['input/sites.csv']
  workflow_dispatch:

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          pip install requests beautifulsoup4
      - name: Run audit
        env:
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
        run: python Site_Scraper_Audit_Data_V3_GITHUBACTION.py
      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: audit-results
          path: output/website_audit_results.csv
``` 
