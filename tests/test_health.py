import unittest

from fastapi import HTTPException

from app.api import health, readiness


class HealthEndpointTests(unittest.TestCase):
    def test_liveness_reports_running(self):
        self.assertEqual(health(), {"status": "ok"})

    def test_readiness_checks_database(self):
        self.assertEqual(
            readiness(),
            {"status": "ready", "database": "ok"},
        )


if __name__ == "__main__":
    unittest.main()
