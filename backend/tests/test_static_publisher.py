from __future__ import annotations

import unittest


class StaticPublisherTests(unittest.TestCase):
    def test_merge_available_dates_keeps_latest_30_days(self) -> None:
        from app.static_data.publisher import merge_available_dates

        existing = [f"2026-01-{day:02d}" for day in range(1, 31)]
        merged = merge_available_dates(existing=existing, new_date="2026-02-01", retention_days=30)

        self.assertEqual(len(merged), 30)
        self.assertEqual(merged[0], "2026-02-01")
        self.assertNotIn("2026-01-01", merged)

    def test_build_daily_payload_groups_categories_and_stats(self) -> None:
        from app.static_data.publisher import build_daily_payload

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

        self.assertEqual(payload["stats"]["total_items"], 1)
        self.assertEqual(payload["stats"]["sites"], 1)
        self.assertEqual(payload["categories"][0]["category_name"], "Electronics")

    def test_build_manifest_stale_preserves_last_success(self) -> None:
        from app.static_data.publisher import build_manifest

        previous = {
            "last_success_date": "2026-03-01",
            "last_success_at": "2026-03-01T12:00:00Z",
            "available_dates": ["2026-03-01"],
            "source": "auto",
        }

        manifest = build_manifest(
            generated_at="2026-03-02T12:00:00Z",
            status="stale",
            message="crawl failed",
            previous=previous,
            available_dates=["2026-03-01"],
            retention_days=30,
            source="manual",
        )

        self.assertEqual(manifest["status"], "stale")
        self.assertEqual(manifest["last_success_date"], "2026-03-01")
        self.assertEqual(manifest["message"], "crawl failed")
        self.assertEqual(manifest["source"], "manual")


if __name__ == "__main__":
    unittest.main()
