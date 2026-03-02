from __future__ import annotations

import unittest


class SchedulerTests(unittest.TestCase):
    def test_daily_job_registered(self) -> None:
        from app.scheduler.runner import build_scheduler_jobs

        jobs = build_scheduler_jobs()
        ids = {job["id"] for job in jobs}
        self.assertIn("daily_full_crawl", ids)


if __name__ == "__main__":
    unittest.main()
