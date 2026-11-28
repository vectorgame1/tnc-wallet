import hashlib
import hmac
import json
import time
import unittest
from urllib.parse import urlencode
from unittest.mock import patch

from fastapi import HTTPException

from app.core.security import verify
from app.core.config import settings


class TelegramInitDataTests(unittest.TestCase):
    def _signed(self, extra_pairs=()):
        user = json.dumps({"id": 123456789, "first_name": "Test"}, separators=(",", ":"))
        pairs = [("auth_date", str(int(time.time()))), ("query_id", "test-query"), ("user", user)]
        pairs.extend(extra_pairs)
        check = "\n".join(f"{key}={value}" for key, value in sorted(pairs))
        token = "test-bot-token"
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        return urlencode(pairs + [("hash", digest)])

    def test_valid_signed_init_data_is_accepted(self):
        with patch.object(settings, "BOT_TOKEN", "test-bot-token"):
            self.assertEqual(verify(self._signed())["id"], 123456789)

    def test_duplicate_parameters_are_rejected(self):
        with patch.object(settings, "BOT_TOKEN", "test-bot-token"):
            with self.assertRaises(HTTPException):
                verify(self._signed((("auth_date", str(int(time.time()))),)))

    def test_oversized_init_data_is_rejected(self):
        with patch.object(settings, "BOT_TOKEN", "test-bot-token"):
            with self.assertRaises(HTTPException):
                verify("x" * 16385)


if __name__ == "__main__":
    unittest.main()
