from __future__ import annotations

import unittest

from tests.test_helpers import isolated_env, request_json, running_server


class HealthEndpointTests(unittest.TestCase):
    def test_health_endpoint_returns_ok(self) -> None:
        with isolated_env():
            with running_server() as (host, port):
                status, body = request_json(host, port, "GET", "/api/health")

        self.assertEqual(status, 200)
        self.assertEqual(body, {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
