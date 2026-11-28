import unittest

from app.services.transaction_image import (
    BG,
    PANEL,
    INK,
    MUTED,
    LIME,
    GOOD,
    BAD,
    create_section_image,
    create_transaction_image,
)


class TelegramImageThemeTests(unittest.TestCase):
    def test_editorial_graphite_lime_palette_is_applied(self):
        self.assertEqual(BG, (17, 19, 16))
        self.assertEqual(PANEL, (27, 30, 25))
        self.assertEqual(INK, (242, 241, 232))
        self.assertEqual(MUTED, (157, 162, 145))
        self.assertEqual(LIME, (200, 241, 105))
        self.assertEqual(GOOD, (184, 233, 134))
        self.assertEqual(BAD, (255, 140, 130))

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
