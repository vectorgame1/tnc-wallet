import unittest
from unittest.mock import patch

import bot


class BotNavigationTests(unittest.TestCase):
    def test_main_keyboard_is_compact_with_mini_app_and_more(self):
        with patch.object(bot.settings, "WEBAPP_URL", "https://example.test/app/"):
            keyboard = bot.main_keyboard()

        labels = [button.text for row in keyboard.keyboard for button in row]
        self.assertEqual(len(labels), 4)
        self.assertTrue({bot.WALLET, bot.TRANSFER, bot.MINI_APP, bot.MORE}.issubset(set(labels)))
        self.assertNotIn(bot.HISTORY, labels)
        self.assertNotIn(bot.SHOP, labels)
        mini_app = next(button for row in keyboard.keyboard for button in row if button.text == bot.MINI_APP)
        self.assertIsNotNone(mini_app.web_app)
        self.assertEqual(mini_app.web_app.url, "https://example.test/app/")
        self.assertEqual(keyboard.is_persistent, True)

    def test_mini_app_remains_reachable_when_url_is_not_configured(self):
        with patch.object(bot.settings, "WEBAPP_URL", ""):
            keyboard = bot.main_keyboard()

        mini_app = next(button for row in keyboard.keyboard for button in row if button.text == bot.MINI_APP)
        self.assertIsNone(mini_app.web_app)
        labels = {button.text for row in keyboard.keyboard for button in row}
        self.assertIn(bot.WALLET, labels)
        self.assertIn(bot.TRANSFER, labels)
        self.assertIn(bot.MORE, labels)
        self.assertNotIn(bot.HISTORY, labels)

    def test_secondary_menu_is_reply_keyboard_and_contains_less_used_actions(self):
        keyboard = bot.more_keyboard()
        labels = [button.text for row in keyboard.keyboard for button in row]
        self.assertEqual(len(labels), 7)
        self.assertTrue({bot.HISTORY, bot.ACCOUNT, bot.SHOP, bot.GT_BALANCE, bot.COMMUNITY, "Помощь", "← Главное меню"}.issubset(set(labels)))


    def test_menu_callbacks_route_to_existing_handlers(self):
        source = open(bot.__file__, encoding="utf-8-sig").read()
        self.assertIn('@dp.callback_query(F.data.startswith("menu:"))', source)
        for action in ("wallet", "transfer", "history", "account", "shop", "community", "games", "help", "miniapp", "more", "back"):
            self.assertIn(f'action == "{action}"', source)


if __name__ == "__main__":
    unittest.main()
