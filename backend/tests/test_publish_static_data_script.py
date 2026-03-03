from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys


class PublishStaticDataScriptTests(unittest.TestCase):
    def test_publish_writes_manifest_and_daily_file(self) -> None:
        from scripts import publish_static_data

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            with patch.object(publish_static_data, "WEB_DATA_DIR", base / "data"):
                with patch.object(
                    publish_static_data,
                    "crawl_all_rows_for_targets",
                    return_value=(
                        "2026-03-02",
                        [
                            {
                                "site": "amazon.com",
                                "board_type": "best_sellers",
                                "category_key": "cat-1",
                                "category_name": "Electronics",
                                "rank": 1,
                                "asin": "B000000001",
                                "title": "Product 1",
                                "brand": "Brand",
                                "price_text": "$9.99",
                                "rating": 4.5,
                                "review_count": 100,
                                "detail_url": "https://www.amazon.com/dp/B000000001",
                            }
                        ],
                    ),
                ):
                    code = publish_static_data.main([])

                self.assertEqual(code, 0)
                self.assertTrue((base / "data" / "manifest.json").exists())
                self.assertTrue((base / "data" / "daily" / "2026-03-02.json").exists())

    def test_manifest_contains_frontend_contract_keys(self) -> None:
        from scripts import publish_static_data

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            with patch.object(publish_static_data, "WEB_DATA_DIR", base / "data"):
                with patch.object(
                    publish_static_data,
                    "crawl_all_rows_for_targets",
                    return_value=(
                        "2026-03-02",
                        [
                            {
                                "site": "amazon.com",
                                "board_type": "best_sellers",
                                "category_key": "cat-1",
                                "category_name": "Electronics",
                                "rank": 1,
                                "asin": "B000000001",
                                "title": "Product 1",
                                "brand": "Brand",
                                "price_text": "$9.99",
                                "rating": 4.5,
                                "review_count": 100,
                                "detail_url": "https://www.amazon.com/dp/B000000001",
                            }
                        ],
                    ),
                ):
                    code = publish_static_data.main([])

                self.assertEqual(code, 0)
                manifest_text = (base / "data" / "manifest.json").read_text(encoding="utf-8")

                self.assertIn('"available_dates"', manifest_text)
                self.assertIn('"last_success_date"', manifest_text)
                self.assertIn('"status"', manifest_text)
                self.assertIn('"default_filters"', manifest_text)
                self.assertIn('"source"', manifest_text)

    def test_main_passes_selected_sites_and_boards_to_crawl(self) -> None:
        from scripts import publish_static_data

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            with patch.object(publish_static_data, "WEB_DATA_DIR", base / "data"):
                with patch.object(
                    publish_static_data,
                    "crawl_all_rows_for_targets",
                    return_value=("2026-03-02", []),
                ) as mocked_crawl:
                    publish_static_data.main(["--sites", "amazon.com", "--boards", "best_sellers"])

                mocked_crawl.assert_called_once_with(
                    sites=["amazon.com"],
                    boards=["best_sellers"],
                    category_keywords=[],
                    category_urls=[],
                )

    def test_main_writes_source_to_manifest(self) -> None:
        from scripts import publish_static_data

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            with patch.object(publish_static_data, "WEB_DATA_DIR", base / "data"):
                with patch.object(
                    publish_static_data,
                    "crawl_all_rows_for_targets",
                    return_value=(
                        "2026-03-02",
                        [
                            {
                                "site": "amazon.com",
                                "board_type": "best_sellers",
                                "category_key": "cat-1",
                                "category_name": "Electronics",
                                "rank": 1,
                                "asin": "B000000001",
                                "title": "Product 1",
                                "brand": "Brand",
                                "price_text": "$9.99",
                                "rating": 4.5,
                                "review_count": 100,
                                "detail_url": "https://www.amazon.com/dp/B000000001",
                            }
                        ],
                    ),
                ):
                    code = publish_static_data.main(["--source", "auto"])

                self.assertEqual(code, 0)
                manifest_text = (base / "data" / "manifest.json").read_text(encoding="utf-8")
                self.assertIn('"source": "auto"', manifest_text)

    def test_main_fail_on_mock_rows_returns_non_zero_when_strict(self) -> None:
        from scripts import publish_static_data

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            with patch.object(publish_static_data, "WEB_DATA_DIR", base / "data"):
                with patch.object(
                    publish_static_data,
                    "crawl_all_rows_for_targets",
                    return_value=(
                        "2026-03-02",
                        [
                            {
                                "site": "amazon.com",
                                "board_type": "best_sellers",
                                "category_key": "mock-best_sellers-cat-1",
                                "category_name": "Mock Category 1",
                                "rank": 1,
                                "asin": "B000000001",
                                "title": "Mock Product 1",
                                "brand": "MockBrand",
                                "price_text": "$9.99",
                                "rating": 4.5,
                                "review_count": 100,
                                "detail_url": "https://www.amazon.com/dp/B000000001",
                            }
                        ],
                    ),
                ):
                    code = publish_static_data.main(["--fail-on-mock", "--strict"])

                self.assertEqual(code, 1)
                manifest_text = (base / "data" / "manifest.json").read_text(encoding="utf-8")
                self.assertIn('"status": "stale"', manifest_text)
                self.assertIn("mock rows detected", manifest_text)

    def test_main_parses_cli_args_when_argv_is_none(self) -> None:
        from scripts import publish_static_data

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            with patch.object(publish_static_data, "WEB_DATA_DIR", base / "data"):
                with patch.object(
                    publish_static_data,
                    "crawl_all_rows_for_targets",
                    return_value=("2026-03-02", []),
                ) as mocked_crawl:
                    with patch.object(
                        sys,
                        "argv",
                        [
                            "publish_static_data.py",
                            "--sites",
                            "amazon.com",
                            "--boards",
                            "best_sellers",
                        ],
                    ):
                        publish_static_data.main(None)

                mocked_crawl.assert_called_once_with(
                    sites=["amazon.com"],
                    boards=["best_sellers"],
                    category_keywords=[],
                    category_urls=[],
                )

    def test_main_passes_category_keywords_and_urls_to_crawl(self) -> None:
        from scripts import publish_static_data

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            with patch.object(publish_static_data, "WEB_DATA_DIR", base / "data"):
                with patch.object(
                    publish_static_data,
                    "crawl_all_rows_for_targets",
                    return_value=("2026-03-02", []),
                ) as mocked_crawl:
                    publish_static_data.main(
                        [
                            "--sites",
                            "amazon.com",
                            "--boards",
                            "best_sellers",
                            "--category-keywords",
                            "candlestick,candle",
                            "--category-urls",
                            "https://www.amazon.com/gp/bestsellers/home-garden/3736561",
                        ]
                    )

                mocked_crawl.assert_called_once_with(
                    sites=["amazon.com"],
                    boards=["best_sellers"],
                    category_keywords=["candlestick", "candle"],
                    category_urls=["https://www.amazon.com/gp/bestsellers/home-garden/3736561"],
                )

    def test_main_preserves_history_across_multiple_runs(self) -> None:
        from scripts import publish_static_data

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            data_dir = base / "data"
            daily_dir = data_dir / "daily"
            daily_dir.mkdir(parents=True, exist_ok=True)

            (daily_dir / "2026-03-01.json").write_text(
                json.dumps({"snapshot_date": "2026-03-01", "items": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            (daily_dir / "2026-03-02.json").write_text(
                json.dumps({"snapshot_date": "2026-03-02", "items": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            (data_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "available_dates": ["2026-03-02", "2026-03-01"],
                        "last_success_date": "2026-03-02",
                        "last_success_at": "2026-03-02T00:00:00Z",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            row = {
                "site": "amazon.com",
                "board_type": "best_sellers",
                "category_key": "cat-1",
                "category_name": "Electronics",
                "rank": 1,
                "asin": "B000000001",
                "title": "Product 1",
                "brand": "Brand",
                "price_text": "$9.99",
                "rating": 4.5,
                "review_count": 100,
                "detail_url": "https://www.amazon.com/dp/B000000001",
            }

            with patch.object(publish_static_data, "WEB_DATA_DIR", data_dir):
                with patch.object(
                    publish_static_data,
                    "crawl_all_rows_for_targets",
                    return_value=("2026-03-03", [row]),
                ):
                    code = publish_static_data.main(["--source", "auto"])

                self.assertEqual(code, 0)
                manifest_after_run_1 = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(
                    manifest_after_run_1["available_dates"],
                    ["2026-03-03", "2026-03-02", "2026-03-01"],
                )
                self.assertTrue((daily_dir / "2026-03-01.json").exists())
                self.assertTrue((daily_dir / "2026-03-02.json").exists())
                self.assertTrue((daily_dir / "2026-03-03.json").exists())

                with patch.object(
                    publish_static_data,
                    "crawl_all_rows_for_targets",
                    return_value=("2026-03-04", [row]),
                ):
                    code = publish_static_data.main(["--source", "auto"])

                self.assertEqual(code, 0)
                manifest_after_run_2 = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(
                    manifest_after_run_2["available_dates"],
                    ["2026-03-04", "2026-03-03", "2026-03-02", "2026-03-01"],
                )
                self.assertTrue((daily_dir / "2026-03-04.json").exists())

    def test_main_with_zero_retention_keeps_all_historical_files(self) -> None:
        from scripts import publish_static_data

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            data_dir = base / "data"
            daily_dir = data_dir / "daily"
            daily_dir.mkdir(parents=True, exist_ok=True)

            historical_dates = [f"2026-01-{day:02d}" for day in range(1, 32)]
            for date in historical_dates:
                (daily_dir / f"{date}.json").write_text(
                    json.dumps({"snapshot_date": date, "items": []}, ensure_ascii=False),
                    encoding="utf-8",
                )

            (data_dir / "manifest.json").write_text(
                json.dumps({"available_dates": list(reversed(historical_dates))}, ensure_ascii=False),
                encoding="utf-8",
            )

            row = {
                "site": "amazon.com",
                "board_type": "best_sellers",
                "category_key": "cat-1",
                "category_name": "Electronics",
                "rank": 1,
                "asin": "B000000001",
                "title": "Product 1",
                "brand": "Brand",
                "price_text": "$9.99",
                "rating": 4.5,
                "review_count": 100,
                "detail_url": "https://www.amazon.com/dp/B000000001",
            }

            with patch.object(publish_static_data, "WEB_DATA_DIR", data_dir):
                with patch.object(
                    publish_static_data,
                    "crawl_all_rows_for_targets",
                    return_value=("2026-03-05", [row]),
                ):
                    code = publish_static_data.main(["--source", "auto", "--retention-days", "0"])

                self.assertEqual(code, 0)
                manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest["retention_days"], 0)
                self.assertEqual(len(manifest["available_dates"]), len(historical_dates) + 1)
                self.assertTrue((daily_dir / "2026-03-05.json").exists())
                for date in historical_dates:
                    self.assertTrue((daily_dir / f"{date}.json").exists())


if __name__ == "__main__":
    unittest.main()
