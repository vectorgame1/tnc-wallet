import re
import unittest
from pathlib import Path


class MiniAppNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (Path(__file__).resolve().parents[1] / "webapp" / "index.html").read_text(encoding="utf-8")

    def test_every_navigation_item_has_a_matching_page(self):
        navigation = set(re.findall(r'data-page="([a-z0-9_-]+)"', self.html))
        pages = set(re.findall(r'id="page-([a-z0-9_-]+)"', self.html))
        self.assertTrue(navigation)
        self.assertEqual(navigation - pages, set())

    def test_tnc_shop_uses_existing_server_invoice_endpoint(self):
        self.assertIn('id="page-shop"', self.html)
        self.assertIn("'/api/shop/invoice'", self.html)
        self.assertIn("tg.openInvoice", self.html)
        self.assertIn("data-shop-amount=", self.html)

    def test_transfer_form_has_client_side_safety_checks(self):
        self.assertIn("Нельзя отправить TNC самому себе.", self.html)
        self.assertIn("Недостаточно средств.", self.html)
        self.assertIn("не более 6 знаков после запятой", self.html)
        self.assertIn("Завершённый перевод нельзя отменить.", self.html)

    def test_graphite_lime_theme_replaces_legacy_redline(self):
        self.assertIn("--bg:#10110f", self.html)
        self.assertIn("--accent:#c8f169", self.html)
        self.assertIn("TNC — Web3 Digital Ecosystem", self.html)
        self.assertNotIn("TNC REDLINE visual system", self.html)
        self.assertNotIn("--gold:#ff2638", self.html)


if __name__ == "__main__":
    unittest.main()
