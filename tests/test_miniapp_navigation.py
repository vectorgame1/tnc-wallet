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

    def test_new_forest_and_copper_visual_system_replaces_old_themes(self):
        self.assertIn("--canvas:#f2f0e9", self.html)
        self.assertIn("--forest:#173b32", self.html)
        self.assertIn("TNC — Your Account", self.html)
        self.assertIn("PRIVATE ACCOUNT", self.html)
        self.assertNotIn("--blue:#2855d9", self.html)
        self.assertNotIn("TNC REDLINE visual system", self.html)
        self.assertNotIn("--gold:#ff2638", self.html)

    def test_home_uses_new_editorial_dashboard_and_architecture_photos(self):
        self.assertIn('class="home-masthead"', self.html)
        self.assertIn("Ваш счёт.", self.html)
        self.assertIn(".home-masthead-photo", self.html)
        self.assertIn("images.unsplash.com", self.html)
        self.assertNotIn("COMPLETE TNC VISUAL RESET", self.html)
        self.assertNotIn('class="crypto-orbit"', self.html)
        self.assertNotIn("coin-core", self.html)

    def test_mobile_navigation_keeps_all_sections_reachable(self):
        self.assertIn(".mobilebar{", self.html)
        self.assertIn('id="mobile-more-menu"', self.html)
        self.assertIn("mobile-more-menu", self.html)
        self.assertIn("grid-template-columns:repeat(5,minmax(0,1fr))", self.html)
        for page in ("home", "wallet", "transfer", "history", "market", "trading", "assistant", "shop", "games", "rewards", "profile"):
            self.assertIn(f'data-page="{page}"', self.html)

    def test_finance_screens_have_distinct_editorial_compositions(self):
        self.assertIn("wallet-layout", self.html)
        self.assertIn("transfer-layout", self.html)
        self.assertIn("history-hero", self.html)
        self.assertIn("shop-masthead", self.html)
        self.assertIn('id="receiver"', self.html)
        self.assertIn('id="amount"', self.html)
        self.assertIn('id="history-search"', self.html)
        self.assertIn('id="shop-custom-buy"', self.html)

    def test_new_mobile_more_drawer_keeps_secondary_pages_reachable(self):
        self.assertIn('id="mobile-more-menu"', self.html)
        self.assertIn("$('mobile-more')?.addEventListener", self.html)
        self.assertIn("$('mobile-more-menu')?.classList.remove('open')", self.html)

    def test_bot_uses_compact_reply_menu_and_secondary_destinations(self):
        bot_source = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8-sig")
        for label in ("Кошелёк TNC", "Перевести TNC", "История операций", "Мой аккаунт",
                      "Баланс GT", "Магазин TNC", "Реферальная ссылка", "Открыть приложение"):
            self.assertIn(label, bot_source)
        self.assertIn("def main_keyboard():", bot_source)
        self.assertIn("WebAppInfo(url=webapp_url)", bot_source)
        self.assertIn("def show_home(", bot_source)
        self.assertIn("photo_by_section", bot_source)
        self.assertIn("images.unsplash.com", bot_source)
        self.assertIn("photo_by_operation", bot_source)
        self.assertIn("def more_keyboard():", bot_source)
        self.assertIn('F.text == MORE', bot_source)
        self.assertIn('KeyboardButton(text=MORE)', bot_source)
        self.assertIn('ReplyKeyboardMarkup(', bot_source)


if __name__ == "__main__":
    unittest.main()
