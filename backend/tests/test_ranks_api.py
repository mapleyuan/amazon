from __future__ import annotations

import unittest

from tests.test_helpers import isolated_env, request_json, running_server


class RanksApiTests(unittest.TestCase):
    def test_ranks_api_supports_filters(self) -> None:
        with isolated_env():
            from app.ranking.service import upsert_rank_snapshot

            upsert_rank_snapshot(
                [
                    {
                        "site": "amazon.com",
                        "board_type": "best_sellers",
                        "category_key": "cat-1",
                        "asin": "B001",
                        "rank": 1,
                        "title": "A",
                        "price_text": "$9.99",
                    }
                ],
                snapshot_date="2026-03-02",
                job_id=1,
            )

            with running_server() as (host, port):
                status, body = request_json(
                    host,
                    port,
                    "GET",
                    "/api/ranks?site=amazon.com&board_type=best_sellers",
                )

        self.assertEqual(status, 200)
        self.assertIn("items", body)
        self.assertGreaterEqual(len(body["items"]), 1)

    def test_ranks_api_supports_sort_and_topn(self) -> None:
        with isolated_env():
            from app.ranking.service import upsert_rank_snapshot

            upsert_rank_snapshot(
                [
                    {
                        "site": "amazon.com",
                        "board_type": "best_sellers",
                        "category_key": "cat-1",
                        "asin": "B001",
                        "rank": 3,
                        "title": "A",
                        "price_text": "$9.99",
                        "review_count": 10,
                    },
                    {
                        "site": "amazon.com",
                        "board_type": "best_sellers",
                        "category_key": "cat-1",
                        "asin": "B002",
                        "rank": 1,
                        "title": "B",
                        "price_text": "$19.99",
                        "review_count": 200,
                    },
                    {
                        "site": "amazon.com",
                        "board_type": "best_sellers",
                        "category_key": "cat-1",
                        "asin": "B003",
                        "rank": 2,
                        "title": "C",
                        "price_text": "$29.99",
                        "review_count": 50,
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
                    "/api/ranks?site=amazon.com&board_type=best_sellers&sort_by=review_count&sort_order=desc&top_n=2",
                )

        self.assertEqual(status, 200)
        self.assertEqual(len(body["items"]), 2)
        self.assertEqual(body["items"][0]["asin"], "B002")


if __name__ == "__main__":
    unittest.main()
