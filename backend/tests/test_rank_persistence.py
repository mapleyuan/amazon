from __future__ import annotations

import unittest

from tests.test_helpers import isolated_env


class RankPersistenceTests(unittest.TestCase):
    def test_upsert_rank_snapshot_deduplicates_same_site_asin(self) -> None:
        with isolated_env():
            from app.ranking.service import upsert_rank_snapshot

            payload = [
                {
                    "site": "amazon.com",
                    "board_type": "best_sellers",
                    "asin": "B001",
                    "category_key": "cat-1",
                    "rank": 1,
                    "title": "A",
                },
                {
                    "site": "amazon.com",
                    "board_type": "best_sellers",
                    "asin": "B001",
                    "category_key": "cat-1",
                    "rank": 1,
                    "title": "A",
                },
            ]

            result = upsert_rank_snapshot(payload, snapshot_date="2026-03-02", job_id=1)

        self.assertEqual(result["inserted_records"], 1)


if __name__ == "__main__":
    unittest.main()
