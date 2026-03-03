from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.official_insights.sp_api import SPAPIConfig, SP_API_ENDPOINTS


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


if __name__ == "__main__":
    unittest.main()

