from __future__ import annotations

import unittest

from tests.test_helpers import isolated_env, request_text, running_server


class ExportApiTests(unittest.TestCase):
    def test_csv_export_endpoint(self) -> None:
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
                    }
                ],
                snapshot_date="2026-03-02",
                job_id=1,
            )

            with running_server() as (host, port):
                status, data, content_type = request_text(host, port, "GET", "/api/export/ranks.csv?site=amazon.com")

        self.assertEqual(status, 200)
        self.assertIn("text/csv", content_type)
        self.assertIn("asin", data)


if __name__ == "__main__":
    unittest.main()
