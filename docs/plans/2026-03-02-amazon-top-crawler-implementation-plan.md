# Amazon Top Crawler Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a production-usable MVP that crawls Amazon top categories/products (US/JP/UK), stores ranking history, and provides a web admin for query + CSV/Excel export.

**Architecture:** Implement a Python monolith with FastAPI + PostgreSQL + Redis + Playwright for crawler and scheduling, and a React admin web app. Keep crawl execution and query APIs in one backend service with modular boundaries (`crawler`, `jobs`, `ranking`, `export`).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Alembic, PostgreSQL, Redis, APScheduler, Playwright, pytest, React + Vite + TypeScript + Ant Design, Docker Compose.

---

## Global Implementation Rules

- Follow `@superpowers/test-driven-development` for every task.
- Before claiming completion, run `@superpowers/verification-before-completion` checks.
- Keep one commit per task.
- Use UTC internally; format to local timezone in UI only.

### Task 1: Bootstrap backend service and health endpoint

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/main.py`
- Create: `backend/app/api/health.py`
- Create: `backend/tests/test_health.py`
- Create: `backend/README.md`

**Step 1: Write the failing test**

```python
# backend/tests/test_health.py
from fastapi.testclient import TestClient
from app.main import app


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_health.py -v`
Expected: FAIL with import/module errors because app is not scaffolded yet.

**Step 3: Write minimal implementation**

```python
# backend/app/api/health.py
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

```python
# backend/app/main.py
from fastapi import FastAPI
from app.api.health import router as health_router

app = FastAPI(title="Amazon Top Crawler")
app.include_router(health_router, prefix="/api")
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_health.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend
git commit -m "feat(backend): bootstrap service with health endpoint"
```

### Task 2: Add database schema and migration for core entities

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/20260302_01_init_schema.py`
- Create: `backend/app/db/base.py`
- Create: `backend/app/db/models.py`
- Create: `backend/app/core/settings.py`
- Create: `backend/tests/test_schema_constraints.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_schema_constraints.py
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import Product


def test_product_unique_site_asin_constraint() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(Product(site="amazon.com", asin="B0001", title="A"))
        session.add(Product(site="amazon.com", asin="B0001", title="B"))
        try:
            session.commit()
            assert False, "Expected IntegrityError"
        except IntegrityError:
            assert True
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_schema_constraints.py -v`
Expected: FAIL because model definitions are missing.

**Step 3: Write minimal implementation**

```python
# backend/app/db/models.py (excerpt)
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("site", "asin", name="uq_products_site_asin"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    site: Mapped[str] = mapped_column(String(64), nullable=False)
    asin: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
```

Also define all planned tables (`crawl_jobs`, `categories`, `category_snapshots`, `products`, `rank_records`, `export_logs`) and create initial Alembic migration.

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_schema_constraints.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend
git commit -m "feat(db): add core schema and initial migration"
```

### Task 3: Implement crawl job lifecycle (manual + scheduled metadata)

**Files:**
- Create: `backend/app/jobs/schemas.py`
- Create: `backend/app/jobs/repository.py`
- Create: `backend/app/jobs/service.py`
- Create: `backend/app/api/jobs.py`
- Create: `backend/tests/test_jobs_api.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_jobs_api.py
from fastapi.testclient import TestClient
from app.main import app


def test_manual_job_creation() -> None:
    client = TestClient(app)
    response = client.post("/api/jobs/run", json={"site": "amazon.com", "board_type": "best_sellers"})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] in {"pending", "running"}
    assert body["site"] == "amazon.com"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_jobs_api.py -v`
Expected: FAIL with missing route/service.

**Step 3: Write minimal implementation**

```python
# backend/app/api/jobs.py (excerpt)
from fastapi import APIRouter, status
from app.jobs.schemas import JobRunRequest
from app.jobs.service import create_manual_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/run", status_code=status.HTTP_202_ACCEPTED)
def run_job(payload: JobRunRequest) -> dict:
    return create_manual_job(payload)
```

Implement job persistence and list endpoint (`GET /api/jobs`).

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_jobs_api.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend
git commit -m "feat(jobs): add manual job trigger and job listing api"
```

### Task 4: Implement crawler parser and site adapters (US/JP/UK, 3 boards)

**Files:**
- Create: `backend/app/crawler/client.py`
- Create: `backend/app/crawler/parsers/ranking_parser.py`
- Create: `backend/app/crawler/adapters/amazon_com.py`
- Create: `backend/app/crawler/adapters/amazon_co_jp.py`
- Create: `backend/app/crawler/adapters/amazon_co_uk.py`
- Create: `backend/tests/fixtures/*.html`
- Create: `backend/tests/test_ranking_parser.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_ranking_parser.py
from pathlib import Path
from app.crawler.parsers.ranking_parser import parse_ranking_page


def test_parse_top_ranking_items_from_fixture() -> None:
    html = Path("tests/fixtures/amazon_best_sellers_sample.html").read_text(encoding="utf-8")
    items = parse_ranking_page(html)

    assert len(items) > 0
    assert items[0].rank == 1
    assert items[0].asin is not None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_ranking_parser.py -v`
Expected: FAIL because parser is not implemented.

**Step 3: Write minimal implementation**

```python
# backend/app/crawler/parsers/ranking_parser.py (excerpt)
from bs4 import BeautifulSoup


def parse_ranking_page(html: str):
    soup = BeautifulSoup(html, "lxml")
    # parse rank, asin, title, price, rating, review_count
    ...
```

Add site adapter mapping and URL builders for:
- `best_sellers`
- `new_releases`
- `movers_and_shakers`

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_ranking_parser.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend
git commit -m "feat(crawler): implement ranking parser and site adapters"
```

### Task 5: Persist crawl snapshots with dedupe + rank history

**Files:**
- Create: `backend/app/ranking/repository.py`
- Create: `backend/app/ranking/service.py`
- Modify: `backend/app/jobs/service.py`
- Create: `backend/tests/test_rank_persistence.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_rank_persistence.py
from app.ranking.service import upsert_rank_snapshot


def test_upsert_rank_snapshot_deduplicates_same_site_asin() -> None:
    payload = [
        {"site": "amazon.com", "asin": "B001", "category_key": "cat-1", "rank": 1},
        {"site": "amazon.com", "asin": "B001", "category_key": "cat-1", "rank": 1},
    ]
    result = upsert_rank_snapshot(payload, snapshot_date="2026-03-02")
    assert result.inserted_records == 1
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_rank_persistence.py -v`
Expected: FAIL with missing service.

**Step 3: Write minimal implementation**

```python
# backend/app/ranking/service.py (excerpt)
def upsert_rank_snapshot(payload, snapshot_date):
    # dedupe within (site, board_type, category_key, asin, snapshot_date)
    # upsert products by (site, asin)
    ...
```

Integrate persistence call into crawl job execution flow.

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_rank_persistence.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend
git commit -m "feat(ranking): persist snapshots with dedupe and history"
```

### Task 6: Add scheduled crawling and retry/block handling

**Files:**
- Create: `backend/app/scheduler/runner.py`
- Create: `backend/app/crawler/retry.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_scheduler.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_scheduler.py
from app.scheduler.runner import build_scheduler_jobs


def test_daily_job_registered() -> None:
    jobs = build_scheduler_jobs()
    assert any(j.id == "daily_full_crawl" for j in jobs)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_scheduler.py -v`
Expected: FAIL because scheduler module does not exist.

**Step 3: Write minimal implementation**

```python
# backend/app/scheduler/runner.py (excerpt)
def build_scheduler_jobs():
    return [
        {
            "id": "daily_full_crawl",
            "cron": "0 2 * * *",
            "handler": "run_full_crawl",
        }
    ]
```

Implement blocked-page detection and exponential backoff retry (max=3).

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_scheduler.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend
git commit -m "feat(scheduler): add daily crawl schedule and retry policy"
```

### Task 7: Implement ranking query APIs and change calculation

**Files:**
- Create: `backend/app/api/ranks.py`
- Create: `backend/app/ranking/query_service.py`
- Create: `backend/tests/test_ranks_api.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_ranks_api.py
from fastapi.testclient import TestClient
from app.main import app


def test_ranks_api_supports_filters() -> None:
    client = TestClient(app)
    response = client.get("/api/ranks", params={"site": "amazon.com", "board_type": "best_sellers"})
    assert response.status_code == 200
    assert "items" in response.json()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_ranks_api.py -v`
Expected: FAIL due missing endpoint.

**Step 3: Write minimal implementation**

```python
# backend/app/api/ranks.py (excerpt)
@router.get("/ranks")
def list_ranks(...):
    return query_ranks(...)


@router.get("/ranks/changes")
def list_rank_changes(...):
    return query_rank_changes(...)
```

Include pagination and filters: site, board, category, snapshot_date, keyword.

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_ranks_api.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend
git commit -m "feat(api): add rank query and rank change endpoints"
```

### Task 8: Implement CSV/Excel export APIs and audit log

**Files:**
- Create: `backend/app/export/service.py`
- Create: `backend/app/api/export.py`
- Create: `backend/tests/test_export_api.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_export_api.py
from fastapi.testclient import TestClient
from app.main import app


def test_csv_export_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/api/export/ranks.csv", params={"site": "amazon.com"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_export_api.py -v`
Expected: FAIL because endpoint is missing.

**Step 3: Write minimal implementation**

```python
# backend/app/api/export.py (excerpt)
@router.get("/export/ranks.csv")
def export_csv(...):
    # query + stream CSV + write export_logs
    ...


@router.get("/export/ranks.xlsx")
def export_xlsx(...):
    # query + generate xlsx + write export_logs
    ...
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_export_api.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend
git commit -m "feat(export): add csv xlsx export endpoints with audit logs"
```

### Task 9: Build web admin pages (jobs, ranking list, trend, export)

**Files:**
- Create: `web-admin/package.json`
- Create: `web-admin/src/main.tsx`
- Create: `web-admin/src/App.tsx`
- Create: `web-admin/src/pages/JobsPage.tsx`
- Create: `web-admin/src/pages/RankingPage.tsx`
- Create: `web-admin/src/pages/ProductTrendPage.tsx`
- Create: `web-admin/src/api/client.ts`
- Create: `web-admin/src/tests/ranking-page.test.tsx`

**Step 1: Write the failing test**

```tsx
// web-admin/src/tests/ranking-page.test.tsx
import { render, screen } from "@testing-library/react";
import { RankingPage } from "../pages/RankingPage";

it("renders filters and table", () => {
  render(<RankingPage />);
  expect(screen.getByText("Site")).toBeInTheDocument();
  expect(screen.getByText("Board Type")).toBeInTheDocument();
});
```

**Step 2: Run test to verify it fails**

Run: `cd web-admin && npm test -- --runInBand`
Expected: FAIL because page/components are not created.

**Step 3: Write minimal implementation**

```tsx
// web-admin/src/pages/RankingPage.tsx (excerpt)
export function RankingPage() {
  return (
    <div>
      <label>Site</label>
      <label>Board Type</label>
      {/* ranking table with filter-driven query */}
    </div>
  );
}
```

Implement:
- Jobs page with manual trigger button
- Ranking page with filters + table + export action
- Product trend page with line chart

**Step 4: Run test to verify it passes**

Run: `cd web-admin && npm test -- --runInBand`
Expected: PASS.

**Step 5: Commit**

```bash
git add web-admin
git commit -m "feat(web-admin): add jobs ranking trend pages and export ui"
```

### Task 10: Compose local runtime and end-to-end verification

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `Makefile`
- Create: `docs/runbook.md`
- Create: `backend/tests/test_e2e_smoke.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_e2e_smoke.py
import requests


def test_health_and_jobs_endpoint_smoke() -> None:
    assert requests.get("http://localhost:8000/api/health", timeout=5).status_code == 200
    resp = requests.get("http://localhost:8000/api/jobs", timeout=5)
    assert resp.status_code == 200
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_e2e_smoke.py -v`
Expected: FAIL before services are up.

**Step 3: Write minimal implementation**

```yaml
# docker-compose.yml (excerpt)
services:
  postgres:
    image: postgres:16
  redis:
    image: redis:7
  backend:
    build: ./backend
    ports: ["8000:8000"]
  web-admin:
    build: ./web-admin
    ports: ["5173:5173"]
```

Add startup commands and environment wiring.

**Step 4: Run test to verify it passes**

Run:
- `docker compose up -d --build`
- `cd backend && pytest tests/test_e2e_smoke.py -v`

Expected: PASS; backend and UI reachable.

**Step 5: Commit**

```bash
git add docker-compose.yml .env.example Makefile docs backend web-admin
git commit -m "chore: add local runtime and smoke verification"
```

## Final Verification Checklist

Run all before completion claim:

```bash
cd backend && pytest -v
cd ../web-admin && npm test -- --runInBand
cd .. && docker compose up -d --build
curl -f http://localhost:8000/api/health
```

Expected:
- Backend tests pass
- Web tests pass
- Services boot successfully
- Health endpoint returns 200

## Delivery Criteria

- Daily scheduled crawl + manual crawl both work
- Three sites and three board types are crawlable
- Category level 1/2 + top 100 persisted
- Admin pages allow filtering and rank change inspection
- CSV/Excel export matches current filters
