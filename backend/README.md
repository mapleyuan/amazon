# Amazon Top Crawler Backend

## Run

```bash
cd backend
python3 -m app.main
```

Server starts on `http://127.0.0.1:8000` by default.

## Tests

```bash
cd backend
python3 -m unittest discover -s tests -v
```

## Frontend pages

Static web UI lives in `backend/app/web/` and is split into:

- `index.html`: rank browsing page
- `insights.html`: competitor insights page
- `product.html`: single competitor deep-analysis page
- `app.js`: shared logic for both pages (auto-detects page via `body[data-page]`)

## Environment variables

- `AMAZON_DB_PATH`: sqlite db file path (default `backend/data/amazon.db`)
- `AMAZON_HOST`: bind host (default `127.0.0.1`)
- `AMAZON_PORT`: bind port (default `8000`)
- `AMAZON_CRON_HOUR_UTC`: daily job hour in UTC (default `2`)
- `AMAZON_CRON_MINUTE_UTC`: daily job minute in UTC (default `0`)
- `AMAZON_MOCK_CRAWL`: `1` enables deterministic mock crawl (used in tests)
- `AMAZON_MANUAL_LIMIT_PER_SITE`: daily manual trigger limit per site (default `3`)
- `AMAZON_DETAIL_ENRICH_LIMIT`: max ASIN count per crawl run for detail-page enrichment (default `0`, disabled)
- `AMAZON_CRAWL_CATEGORY_LIMIT`: category crawl limit per site+board (default `20`)
- `AMAZON_CRAWL_SOURCE`: crawl source strategy (`direct`, `jina_ai`, or `proxy_template`, default `direct`)
- `AMAZON_CRAWL_PROXY_TEMPLATE`: used when `AMAZON_CRAWL_SOURCE=proxy_template`; must contain `{url}`

## Publish static data with fine-grained category targeting

```bash
cd backend
python3 scripts/publish_static_data.py \
  --source manual \
  --sites amazon.com \
  --boards best_sellers \
  --category-keywords candlestick,candle,home-decor \
  --category-urls http://www.amazon.com/Best-Sellers-Home-Kitchen-Candlestick-Holders/zgbs/home-garden/3734611/ref=zg_bs_nav_home-garden_4_3734591 \
  --fail-on-mock \
  --strict
```

## Sales fields in static daily data

Each item now includes:
- `sales_day`: estimated daily sales
- `sales_month`: estimated 30-day sales
- `sales_year`: estimated 1-year sales

Estimation strategy:
- Prefer explicit "bought in past month" signals when present.
- Fallback to a rank-based model when the source page omits that signal.

## Build official insights data (real reports)

You can import official reports (keywords / conversion / monthly sales / review topics / style trends)
to generate:

- `backend/app/web/data/insights/YYYY-MM-DD.json`

Example:

```bash
cd backend
python3 scripts/build_official_insights.py \
  --snapshot-date 2026-03-03 \
  --keywords-csv ./data/official/keywords.csv \
  --monthly-sales-csv ./data/official/monthly_sales.csv \
  --review-topics-json ./data/official/review_topics.json \
  --style-trends-csv ./data/official/style_trends.csv \
  --output-dir ./app/web/data/insights
```

Frontend insight panel will automatically prefer `data/insights/<date>.json` when the file exists.

## Refresh official insights (auto pull + build)

If SP-API credentials are configured, run:

```bash
cd backend
python3 scripts/refresh_official_insights.py \
  --snapshot-date 2026-03-03 \
  --marketplace-ids A1PA6795UKMFR9 \
  --lookback-days 30
```

Default behavior:

- Keywords + conversion: `GET_BRAND_ANALYTICS_SEARCH_QUERY_PERFORMANCE_REPORT`
  - `reportOptions.reportPeriod=MONTH`
  - ASIN list auto-loaded from `app/web/data/daily/<date>.json` top products (or set via `--keywords-asins`)
- Monthly sales: `GET_SALES_AND_TRAFFIC_REPORT`
  - `reportOptions.dateGranularity=MONTH`
  - `reportOptions.asinGranularity=CHILD`
- Review pain points: Customer Feedback API (`/customerFeedback/2024-06-01/.../reviews/topics`)
  - ASIN list auto-loaded from daily snapshot (or set via `--review-asins`)
- Style trend: use style report if provided; otherwise derive from official keyword rows automatically.

Useful flags:

```bash
# Manual ASIN override for SQP/review topics
--keywords-asins B000000001,B000000002
--review-asins B000000001,B000000002

# Force skip one dimension
--skip-keywords --skip-sales --skip-reviews --skip-style

# Strict mode (fail if all official rows are empty)
--strict
```

Required env vars for SP-API pull:

- `AMAZON_SPAPI_CLIENT_ID`
- `AMAZON_SPAPI_CLIENT_SECRET`
- `AMAZON_SPAPI_REFRESH_TOKEN`
- `AMAZON_SPAPI_AWS_ACCESS_KEY_ID`
- `AMAZON_SPAPI_AWS_SECRET_ACCESS_KEY`
- `AMAZON_SPAPI_AWS_REGION` (default `us-east-1`)
- `AMAZON_SPAPI_ENDPOINT` (or set `AMAZON_SPAPI_REGION` as `na/eu/fe`)

## Refresh public review insights (free fallback, no paid API)

When you do not use SP-API, you can still build real review pain-point topics from public review pages:

```bash
cd backend
python3 scripts/refresh_public_review_insights.py \
  --snapshot-date 2026-03-03 \
  --site amazon.com \
  --asin-limit 8 \
  --pages-per-asin 2
```

Behavior:

- Read top ASINs from `app/web/data/daily/<date>.json` (or override via `--asins`)
- Fetch review pages and parse rating + text
- Build positive/negative topic mentions + richer review stats:
  - `avg_rating`
  - `rating_distribution`
  - `sentiment` (positive/neutral/negative)
  - `positive_snippets` / `negative_snippets`
- Build per-ASIN diagnostics:
  - `review_fetch_diagnostics` (pages attempted/succeeded, parsed entries, per-page errors)
- Write/merge into `app/web/data/insights/<date>.json`

Strict review-topic gate:

```bash
python3 scripts/refresh_public_review_insights.py --snapshot-date 2026-03-03 --strict-review-topics
```

When `review_topic_asins` is `0`, script exits non-zero for CI alerting.

Source label in output:

- `public_reviews`: only public review-derived insights
- `mixed_reports_public_reviews`: merged official report payload + public review topics

## Refresh public keyword insights (free fallback, no paid API)

Build non-bid keyword traffic/conversion proxies from public Amazon search pages:

```bash
cd backend
python3 scripts/refresh_public_keyword_insights.py \
  --snapshot-date 2026-03-03 \
  --site amazon.com \
  --keyword-limit 20
```

Behavior:

- Derive candidate keywords from daily product titles (or pass `--keywords`)
- Fetch `/s?k=<keyword>` pages
- Parse result-count, sponsored marker count, first-page ASIN list
- Build keyword rows with proxy fields:
  - `impressions`: parsed result count
  - `cvr`: first-page tracked-ASIN overlap ratio
  - `top_asin_overlap`: overlap count

Source label in output:

- `public_search_keywords`: keyword rows from public search pages
- can be merged with other sources, e.g. `official_reports+public_reviews+public_search_keywords`
