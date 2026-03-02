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
