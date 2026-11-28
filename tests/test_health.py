import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.api import health, readiness, engine


class HealthEndpointTests(unittest.TestCase):
    def test_liveness_reports_running(self):
        self.assertEqual(health(), {"status": "ok"})

    def test_readiness_checks_database(self):
        self.assertEqual(
            readiness(),
            {"status": "ready", "database": "ok"},
        )

    def test_readiness_returns_503_when_database_is_unavailable(self):
        with patch.object(engine, "connect", side_effect=RuntimeError("db down")):
            with self.assertRaises(HTTPException) as raised:
                readiness()
        self.assertEqual(raised.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
