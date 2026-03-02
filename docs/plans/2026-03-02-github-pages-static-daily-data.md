# GitHub Pages Static Daily Data Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace runtime API dependency with static daily JSON on GitHub Pages, updated automatically by GitHub Actions with local manual fallback.

**Architecture:** Add a Python static-data publisher that crawls and emits `manifest + daily` JSON files into the Pages artifact directory. Rework the web UI to load and filter local JSON in-browser instead of calling `/api/*`. Add a scheduled workflow that regenerates data, keeps 30-day retention, commits changes, and triggers Pages deploy.

**Tech Stack:** Python 3.12+, existing stdlib crawler + sqlite modules, vanilla HTML/CSS/JS, GitHub Actions.

---

### Task 1: Build Static Data Publisher Core (Pure Functions)

**Files:**
- Create: `backend/app/static_data/__init__.py`
- Create: `backend/app/static_data/publisher.py`
- Test: `backend/tests/test_static_publisher.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_static_publisher.py
from app.static_data.publisher import (
    build_daily_payload,
    merge_available_dates,
    build_manifest,
)


def test_merge_available_dates_keeps_latest_30_days() -> None:
    existing = [f"2026-01-{day:02d}" for day in range(1, 31)]
    merged = merge_available_dates(existing=existing, new_date="2026-02-01", retention_days=30)

    assert len(merged) == 30
    assert merged[0] == "2026-02-01"
    assert "2026-01-01" not in merged


def test_build_daily_payload_groups_categories_and_stats() -> None:
    rows = [
        {
            "snapshot_date": "2026-03-02",
            "site": "amazon.com",
            "board_type": "best_sellers",
            "category_key": "cat-1",
            "category_name": "Electronics",
            "rank": 1,
            "asin": "B000000001",
            "title": "A",
            "brand": "B",
            "price_text": "$9.99",
            "rating": 4.5,
            "review_count": 10,
            "detail_url": "https://www.amazon.com/dp/B000000001",
        }
    ]

    payload = build_daily_payload(snapshot_date="2026-03-02", generated_at="2026-03-02T12:00:00Z", rows=rows)

    assert payload["stats"]["total_items"] == 1
    assert payload["stats"]["sites"] == 1
    assert payload["categories"][0]["category_name"] == "Electronics"


def test_build_manifest_stale_preserves_last_success() -> None:
    previous = {
        "last_success_date": "2026-03-01",
        "last_success_at": "2026-03-01T12:00:00Z",
        "available_dates": ["2026-03-01"],
    }

    manifest = build_manifest(
        generated_at="2026-03-02T12:00:00Z",
        status="stale",
        message="crawl failed",
        previous=previous,
        available_dates=["2026-03-01"],
        retention_days=30,
    )

    assert manifest["status"] == "stale"
    assert manifest["last_success_date"] == "2026-03-01"
    assert manifest["message"] == "crawl failed"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m unittest tests.test_static_publisher -v`
Expected: FAIL with `ModuleNotFoundError` / missing function errors.

**Step 3: Write minimal implementation**

```python
# backend/app/static_data/publisher.py (key signatures)
def merge_available_dates(existing: list[str], new_date: str | None, retention_days: int) -> list[str]:
    ...


def build_daily_payload(snapshot_date: str, generated_at: str, rows: list[dict]) -> dict:
    ...


def build_manifest(
    *,
    generated_at: str,
    status: str,
    message: str,
    previous: dict,
    available_dates: list[str],
    retention_days: int,
) -> dict:
    ...
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m unittest tests.test_static_publisher -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/static_data backend/tests/test_static_publisher.py
git commit -m "feat(static-data): add manifest and daily payload builder"
```

### Task 2: Add Static Data Publish Script (Crawl + Write JSON)

**Files:**
- Create: `backend/scripts/publish_static_data.py`
- Test: `backend/tests/test_publish_static_data_script.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_publish_static_data_script.py
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class PublishStaticDataScriptTests(unittest.TestCase):
    def test_publish_writes_manifest_and_daily_file(self) -> None:
        from scripts import publish_static_data

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            with patch.object(publish_static_data, "WEB_DATA_DIR", base / "data"):
                with patch.object(
                    publish_static_data,
                    "crawl_all_rows",
                    return_value=("2026-03-02", [{"site": "amazon.com", "board_type": "best_sellers", "category_key": "cat", "category_name": "C", "rank": 1, "asin": "B000000001", "title": "P", "brand": "", "price_text": "$1", "rating": 4.0, "review_count": 1, "detail_url": "https://www.amazon.com/dp/B000000001"}]),
                ):
                    code = publish_static_data.main([])

                self.assertEqual(code, 0)
                self.assertTrue((base / "data" / "manifest.json").exists())
                self.assertTrue((base / "data" / "daily" / "2026-03-02.json").exists())
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m unittest tests.test_publish_static_data_script -v`
Expected: FAIL because script module/symbols are missing.

**Step 3: Write minimal implementation**

```python
# backend/scripts/publish_static_data.py (key flow)
def main(argv: list[str] | None = None) -> int:
    # 1) try crawl all site/board rows
    # 2) on success write daily json + update manifest(status=success)
    # 3) on failure write stale manifest(status=stale, preserve last_success)
    # 4) enforce 30-day retention by deleting extra daily files
    return 0
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m unittest tests.test_publish_static_data_script -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/scripts/publish_static_data.py backend/tests/test_publish_static_data_script.py
git commit -m "feat(static-data): add publish script with stale fallback"
```

### Task 3: Rework Web UI to Static Local Data Filtering

**Files:**
- Modify: `backend/app/web/index.html`
- Modify: `backend/app/web/app.js`
- Modify: `backend/app/web/styles.css`

**Step 1: Write the failing test (integration assertion via script output contract)**

```python
# Append to backend/tests/test_publish_static_data_script.py
# assert manifest has required keys expected by app.js:
# available_dates, last_success_date, status, default_filters
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m unittest tests.test_publish_static_data_script -v`
Expected: FAIL because manifest contract keys are incomplete.

**Step 3: Write minimal implementation**

```javascript
// backend/app/web/app.js (key behavior)
// 1) load ./data/manifest.json
// 2) select date -> load ./data/daily/<date>.json
// 3) run in-memory filtering/sorting for site/board/category/price/topN/keyword
// 4) render table + status bar + CSV export
```

Also adjust HTML:
- remove API base section and job-trigger section
- add date selector and data status summary

**Step 4: Run test to verify it passes + smoke check**

Run: `cd backend && python3 -m unittest tests.test_publish_static_data_script -v`
Expected: PASS.

Run: `cd backend/app/web && python3 -m http.server 8899`
Expected: Page opens and loads local JSON without `/api/*` calls.

**Step 5: Commit**

```bash
git add backend/app/web/index.html backend/app/web/app.js backend/app/web/styles.css
git commit -m "feat(web): switch to static daily data filtering mode"
```

### Task 4: Add Daily GitHub Action for Auto Data Refresh

**Files:**
- Create: `.github/workflows/daily-static-data.yml`
- Modify: `README.md`

**Step 1: Write the failing test (workflow dry validation via command existence checks)**

```bash
# This step intentionally fails before file exists:
test -f .github/workflows/daily-static-data.yml
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/william.yuan/gitlabhub/amazon && test -f .github/workflows/daily-static-data.yml`
Expected: non-zero exit.

**Step 3: Write minimal implementation**

```yaml
# .github/workflows/daily-static-data.yml
on:
  schedule:
    - cron: "20 2 * * *"
  workflow_dispatch:
jobs:
  refresh:
    permissions:
      contents: write
    steps:
      - checkout
      - setup python
      - run publish script
      - commit+push backend/app/web/data/** if changed
```

Update README with:
- auto daily workflow behavior
- local manual fallback command

**Step 4: Run test to verify it passes**

Run: `cd /Users/william.yuan/gitlabhub/amazon && test -f .github/workflows/daily-static-data.yml`
Expected: exit 0.

**Step 5: Commit**

```bash
git add .github/workflows/daily-static-data.yml README.md
git commit -m "ci: add daily static data refresh workflow"
```

### Task 5: End-to-End Verification and Deploy Check

**Files:**
- Verify: `backend/app/web/data/manifest.json`
- Verify: `backend/app/web/data/daily/*.json`
- Verify: `.github/workflows/deploy-pages.yml`

**Step 1: Write/execute verification checklist**

```text
- static data script runs successfully
- manifest/daily JSON generated
- tests pass
- git status clean after commits
- push triggers deploy-pages workflow
```

**Step 2: Run verification commands**

Run: `cd backend && python3 -m unittest discover -s tests -v`
Expected: all PASS.

Run: `cd backend && python3 scripts/publish_static_data.py`
Expected: exit 0 and data files updated.

Run: `cd /Users/william.yuan/gitlabhub/amazon && git status --short --branch`
Expected: only intended changes.

**Step 3: Push and verify GitHub Actions**

Run: `cd /Users/william.yuan/gitlabhub/amazon && git push origin main`
Expected: push succeeds and deploy workflow runs.

Run: `curl -I -s https://mapleyuan.github.io/amazon/`
Expected: HTTP 200.

**Step 4: Commit any final docs tweaks if needed**

```bash
git add README.md
git commit -m "docs: finalize static pages usage notes"
```

