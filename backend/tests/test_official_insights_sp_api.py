from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.official_insights.sp_api import SPAPIClient, SPAPIConfig, SP_API_ENDPOINTS


class OfficialInsightsSpApiTests(unittest.TestCase):
    def test_from_env_uses_region_endpoint_default(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AMAZON_SPAPI_REGION": "na",
                "AMAZON_SPAPI_CLIENT_ID": "cid",
                "AMAZON_SPAPI_CLIENT_SECRET": "secret",
                "AMAZON_SPAPI_REFRESH_TOKEN": "refresh",
                "AMAZON_SPAPI_AWS_ACCESS_KEY_ID": "ak",
                "AMAZON_SPAPI_AWS_SECRET_ACCESS_KEY": "sk",
            },
            clear=True,
        ):
            config = SPAPIConfig.from_env()
            self.assertEqual(config.endpoint, SP_API_ENDPOINTS["na"])
            self.assertEqual(config.aws_region, "us-east-1")

    def test_validate_raises_when_required_credentials_missing(self) -> None:
        config = SPAPIConfig(
            lwa_client_id="",
            lwa_client_secret="",
            lwa_refresh_token="",
            aws_access_key_id="",
            aws_secret_access_key="",
            aws_session_token="",
            aws_region="",
            endpoint="",
        )
        with self.assertRaises(ValueError):
            config.validate()

    def test_customer_feedback_paths(self) -> None:
        config = SPAPIConfig(
            lwa_client_id="cid",
            lwa_client_secret="secret",
            lwa_refresh_token="refresh",
            aws_access_key_id="ak",
            aws_secret_access_key="sk",
            aws_session_token="",
            aws_region="us-east-1",
            endpoint=SP_API_ENDPOINTS["na"],
        )
        client = SPAPIClient(config)
        with patch.object(client, "request_json", return_value={"ok": True}) as mocked:
            client.get_item_review_topics(
                asin="B000000001",
                marketplace_id="ATVPDKIKX0DER",
                sort_by="MENTIONS",
            )
            client.get_item_review_trends(
                asin="B000000001",
                marketplace_id="ATVPDKIKX0DER",
            )

        self.assertEqual(mocked.call_count, 2)
        topics_call = mocked.call_args_list[0].kwargs
        self.assertEqual(topics_call["path"], "/customerFeedback/2024-06-01/items/B000000001/reviews/topics")
        self.assertEqual(topics_call["query"]["marketplaceId"], "ATVPDKIKX0DER")
        trends_call = mocked.call_args_list[1].kwargs
        self.assertEqual(trends_call["path"], "/customerFeedback/2024-06-01/items/B000000001/reviews/trends")


if __name__ == "__main__":
    unittest.main()
