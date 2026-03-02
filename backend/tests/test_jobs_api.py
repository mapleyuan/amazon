from __future__ import annotations

import unittest

from tests.test_helpers import isolated_env, request_json, running_server


class JobsApiTests(unittest.TestCase):
    def test_manual_job_creation(self) -> None:
        with isolated_env():
            with running_server() as (host, port):
                status, body = request_json(
                    host,
                    port,
                    "POST",
                    "/api/jobs/run",
                    payload={"site": "amazon.com", "board_type": "best_sellers"},
                )

        self.assertEqual(status, 202)
        self.assertIn(body["status"], {"pending", "running", "success"})
        self.assertEqual(body["site"], "amazon.com")


if __name__ == "__main__":
    unittest.main()
