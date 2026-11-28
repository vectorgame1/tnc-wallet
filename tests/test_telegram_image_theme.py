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
    def test_midnight_ice_palette_is_applied(self):
        self.assertEqual(BG, (7, 13, 24))
        self.assertEqual(PANEL, (13, 25, 43))
        self.assertEqual(INK, (239, 246, 255))
        self.assertEqual(MUTED, (137, 160, 190))
        self.assertEqual(LIME, (139, 190, 255))
        self.assertEqual(GOOD, (104, 220, 180))
        self.assertEqual(BAD, (255, 128, 145))

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
