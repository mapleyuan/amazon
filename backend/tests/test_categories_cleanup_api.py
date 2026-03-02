from __future__ import annotations

import unittest

from tests.test_helpers import isolated_env, request_json, running_server


class CategoriesAndCleanupApiTests(unittest.TestCase):
    def test_categories_endpoint_returns_known_categories(self) -> None:
        with isolated_env():
            from app.ranking.service import upsert_rank_snapshot

            upsert_rank_snapshot(
                [
                    {
                        "site": "amazon.com",
                        "board_type": "best_sellers",
                        "category_key": "cat-1",
                        "category_name": "Books",
                        "asin": "B001",
                        "rank": 1,
                        "title": "Book A",
                        "price_text": "$10.00",
                    },
                    {
                        "site": "amazon.com",
                        "board_type": "best_sellers",
                        "category_key": "cat-2",
                        "category_name": "Electronics",
                        "asin": "B002",
                        "rank": 1,
                        "title": "Device B",
                        "price_text": "$20.00",
                    },
                ],
                snapshot_date="2026-03-02",
                job_id=1,
            )

            with running_server() as (host, port):
                status, body = request_json(
                    host,
                    port,
                    "GET",
                    "/api/categories?site=amazon.com&board_type=best_sellers",
                )

        self.assertEqual(status, 200)
        self.assertIn("items", body)
        keys = {item["category_key"] for item in body["items"]}
        self.assertIn("cat-1", keys)
        self.assertIn("cat-2", keys)

    def test_cleanup_invalid_removes_rows_without_price(self) -> None:
        with isolated_env():
            from app.db.connection import get_connection
            from app.ranking.service import upsert_rank_snapshot

            upsert_rank_snapshot(
                [
                    {
                        "site": "amazon.com",
                        "board_type": "best_sellers",
                        "category_key": "cat-1",
                        "category_name": "Books",
                        "asin": "B001",
                        "rank": 1,
                        "title": "Book A",
                        "price_text": "$10.00",
                    },
                    {
                        "site": "amazon.com",
                        "board_type": "best_sellers",
                        "category_key": "cat-1",
                        "category_name": "Books",
                        "asin": "B002",
                        "rank": 2,
                        "title": "Book B",
                        "price_text": None,
                    },
                ],
                snapshot_date="2026-03-02",
                job_id=1,
            )

            conn = get_connection()
            invalid_before = conn.execute(
                "SELECT COUNT(1) FROM rank_records WHERE price_text IS NULL OR TRIM(price_text) = ''"
            ).fetchone()[0]
            self.assertEqual(invalid_before, 1)

            with running_server() as (host, port):
                status, body = request_json(
                    host,
                    port,
                    "POST",
                    "/api/maintenance/cleanup-invalid",
                    payload={"site": "amazon.com", "board_type": "best_sellers"},
                )

            self.assertEqual(status, 200)
            self.assertGreaterEqual(body["deleted_rank_records"], 1)

            invalid_after = conn.execute(
                "SELECT COUNT(1) FROM rank_records WHERE price_text IS NULL OR TRIM(price_text) = ''"
            ).fetchone()[0]
            self.assertEqual(invalid_after, 0)


if __name__ == "__main__":
    unittest.main()
