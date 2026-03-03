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
