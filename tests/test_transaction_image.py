import unittest

from app.services.transaction_image import (
    create_section_image,
    create_transaction_image,
)


class TransactionImageTests(unittest.TestCase):
    def test_section_art_is_generated_as_png(self):
        image = create_section_image(
            "ACCOUNT",
            "YOUR ACCOUNT",
            "Private account overview",
            "BALANCE AND ACTIVITY",
        )
        self.assertEqual(image.read(8), b"\x89PNG\r\n\x1a\n")
        image.seek(0)

    def test_all_transaction_types_render(self):
        for operation in ("deposit", "withdraw", "received", "sent", "bonus", "reward", "refund"):
            with self.subTest(operation=operation):
                image = create_transaction_image(
                    123.45,
                    operation=operation,
                    username="TNC USER",
                    operation_id="test-reference",
                )
                self.assertEqual(image.read(8), b"\x89PNG\r\n\x1a\n")
