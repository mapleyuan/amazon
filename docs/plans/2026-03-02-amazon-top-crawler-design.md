# Amazon Top Categories & Products Crawler Design

## 1. Background and Goal

Build a system to crawl Amazon hot top categories and products, and provide a web admin backend for searching, reviewing, and exporting the data.

### Confirmed scope
- Target sites: `amazon.com`, `amazon.co.jp`, `amazon.co.uk`
- Ranking boards: `Best Sellers`, `New Releases`, `Movers & Shakers`
- Crawling mode: pure web crawling (not API)
- Category depth: 2 levels (parent/child categories)
- Product volume: Top 100 items per category
- Trigger mode: daily scheduled crawl + manual trigger
- Web admin MVP: dashboard/list queries + CSV/Excel export

## 2. Architecture

Adopt a Python monolith for MVP, prioritizing speed and operational simplicity.

### Components
- `crawler`:
  - Uses Playwright to crawl ranking pages per site/board/category
  - Extracts category hierarchy and top product ranking records
- `scheduler`:
  - Daily cron job for full crawl
  - Supports manual crawl trigger from backend
- `api` (FastAPI):
  - Query jobs, rankings, and trend data
  - Export CSV/Excel
- `database` (PostgreSQL):
  - Stores jobs, categories, products, and rank snapshots
- `redis`:
  - Task deduplication, lightweight queue/cache, rate-limit state
- `web-admin`:
  - Manage jobs, search rankings, inspect product trends, export data

## 3. Data Model

### 3.1 `crawl_jobs`
Track each crawl task execution.
- Fields:
  - `id`
  - `site`
  - `board_type`
  - `trigger_type` (`cron` / `manual`)
  - `status` (`pending` / `running` / `success` / `partial_success` / `failed` / `blocked`)
  - `started_at`
  - `finished_at`
  - `error_message`

### 3.2 `categories`
Stable category dimension table.
- Fields:
  - `id`
  - `site`
  - `board_type`
  - `level` (`1` / `2`)
  - `category_key`
  - `name`
  - `parent_category_key`
- Constraint:
  - unique (`site`, `board_type`, `category_key`)

### 3.3 `category_snapshots`
Category snapshot by crawl date/job.
- Fields:
  - `id`
  - `job_id`
  - `site`
  - `board_type`
  - `category_key`
  - `snapshot_date`

### 3.4 `products`
Product master table.
- Fields:
  - `id`
  - `site`
  - `asin`
  - `title`
  - `brand`
  - `image_url`
  - `detail_url`
- Constraint:
  - unique (`site`, `asin`)

### 3.5 `rank_records`
Core ranking history table.
- Fields:
  - `id`
  - `job_id`
  - `snapshot_date`
  - `site`
  - `board_type`
  - `category_key`
  - `asin`
  - `rank`
  - `price_text`
  - `rating`
  - `review_count`
- Suggested indexes:
  - (`site`, `board_type`, `category_key`, `snapshot_date`, `rank`)
  - (`site`, `asin`, `snapshot_date`)

### 3.6 `export_logs`
Export audit table.
- Fields:
  - `id`
  - `user_id` (nullable for MVP)
  - `filter_json`
  - `file_type`
  - `created_at`

### Data strategy notes
- Rank delta is computed at query time against previous snapshot date.
- Keep `price_text` for MVP to preserve locale-specific formats; normalize later with `price_value` + `currency`.

## 4. Crawling Workflow and Anti-Bot Strategy

### Crawl workflow
- Order:
  - Site -> Board type -> Level-1 category -> Level-2 category -> Top100 products
- Each category is an isolated unit of work.
- Persist by `job_id + snapshot_date` in batches.
- Category-level failures are logged; remaining categories continue.

### Anti-bot and stability
- Use Playwright headless by default; keep headed mode switchable.
- Concurrency per site: 2-3 workers.
- Add randomized delay between category requests (e.g. 1.5s-4s).
- Use site-matched `User-Agent` and `Accept-Language`.
- Retry policy: exponential backoff, max 3 retries.
- Detect captcha/challenge pages; mark as `blocked` and queue delayed retry.

### Data quality
- De-duplicate ranks within the same category snapshot.
- De-duplicate products by (`site`, `asin`).
- Allow nullable optional fields (rating/review/price) while keeping rank rows complete.

### Compliance and risk controls
- Expose crawl-rate settings in system config.
- Keep default low frequency (daily).
- Manual trigger quota: max 3 per site per day (MVP default).
- Reserve extension points for proxy pool / unblock providers, but do not include complex proxy management in MVP.

## 5. Web Admin and API Design

### 5.1 Admin pages
- Job page:
  - View run status, site, board, duration, and failures
  - Manual trigger crawl action
- Ranking page:
  - Filters by site/board/category/date/keyword
  - Displays top ranking list with paging
- Product trend page:
  - Query by ASIN or product title
  - Display ranking changes over recent days
- Export entry:
  - Export CSV/Excel from current filtered result set

### 5.2 Core APIs
- `POST /api/jobs/run`
  - Manual trigger (optional site/board filters)
- `GET /api/jobs`
  - Job history listing
- `GET /api/ranks`
  - Ranking query with filters + pagination
- `GET /api/ranks/changes`
  - Ranking delta vs previous snapshot
- `GET /api/products/{asin}/trend`
  - Product ranking trend
- `GET /api/export/ranks.csv`
- `GET /api/export/ranks.xlsx`

### 5.3 Auth (MVP)
- Single-admin mode first (env credentials or internal-network only).
- Keep architecture compatible with future RBAC.

### 5.4 MVP performance targets
- Typical ranking query: under 2s.
- Export up to ~100k rows in acceptable time; async export can be introduced later.

## 6. Testing and Acceptance Criteria

### Crawl correctness
- Each site + board must crawl non-empty level-1/level-2 categories.
- Per category: up to 100 rows with unique and continuous rank values.
- (`site`, `asin`) uniqueness is enforced.

### Reliability
- Daily scheduled job runs and persists data.
- Manual run can be triggered from backend.
- Category-level failures do not abort whole run.

### Web usability
- Ranking data can be filtered by site/board/category/date.
- Rank delta against previous snapshot is visible.
- CSV/Excel exports match current filter conditions.

### Non-functional baseline
- API input validation and consistent error responses.
- Logs carry `job_id` for end-to-end traceability.
- Challenge-page detection prevents infinite retry loops.

## 7. Out-of-Scope for MVP

- Full proxy pool management
- Multi-role RBAC permission system
- Near real-time crawling
- Advanced anomaly alerting (can be phase 2)

## 8. Milestone Suggestion

- M1: crawler + data model + scheduled/manual jobs
- M2: query APIs + admin list pages
- M3: export + trend view + hardening and acceptance tests
