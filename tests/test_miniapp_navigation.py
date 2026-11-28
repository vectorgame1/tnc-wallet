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

    def test_home_uses_new_editorial_hero_instead_of_crypto_orbit(self):
        self.assertIn('class="brand-hero home-only"', self.html)
        self.assertIn("Без лишнего шума.", self.html)
        self.assertIn(".brand-hero-art", self.html)
        self.assertNotIn('class="crypto-orbit"', self.html)
        self.assertNotIn("coin-core", self.html)

    def test_mobile_navigation_is_swipeable_and_keeps_all_sections(self):
        self.assertIn(".mobilebar{display:flex", self.html)
        self.assertIn("overflow-x:auto", self.html)
        for page in ("home", "wallet", "transfer", "history", "market", "trading", "assistant", "shop", "games", "rewards", "profile"):
            self.assertIn(f'data-page="{page}"', self.html)

    def test_bot_keyboard_keeps_full_menu_and_single_miniapp_entry(self):
        bot_source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8-sig")
        for label in ("Кошелёк TNC", "Перевести TNC", "История операций", "Мой аккаунт",
                      "Баланс GT", "Магазин TNC", "Реферальная ссылка", "Открыть приложение"):
            self.assertIn(label, bot_source)
        self.assertIn("def main_keyboard():", bot_source)
        self.assertIn("WebAppInfo(url=webapp_url)", bot_source)
        self.assertIn("def show_home(", bot_source)


if __name__ == "__main__":
    unittest.main()
