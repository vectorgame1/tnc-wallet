import unittest
from pathlib import Path

from app.services.transaction_image import (
    GOLD,
    GREEN,
    RED,
    base_image,
    create_section_image,
    create_transaction_image,
)


class TelegramImageThemeTests(unittest.TestCase):
    def test_brand_palette_is_black_and_red(self):
        self.assertEqual(GOLD, (255, 38, 56))
        self.assertEqual(GREEN, (255, 83, 97))
        self.assertEqual(RED, (255, 38, 56))

    def test_section_card_generates_valid_png(self):
        image = create_section_image("TNC WALLET", "YOUR WALLET", "Balance and transactions")
        self.assertEqual(image.read(8), b"\x89PNG\r\n\x1a\n")
        self.assertGreater(len(image.getvalue()), 5000)

    def test_transaction_cards_generate_valid_png_for_all_operations(self):
        for operation in ("deposit", "withdraw", "received", "sent", "bonus", "reward", "refund"):
            with self.subTest(operation=operation):
                image = create_transaction_image(125.5, operation, "TNC USER", "test-id")
                self.assertEqual(image.read(8), b"\x89PNG\r\n\x1a\n")
                self.assertGreater(len(image.getvalue()), 5000)


if __name__ == "__main__":
    unittest.main()
