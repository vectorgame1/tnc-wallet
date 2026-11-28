import unittest
from unittest.mock import patch

import bot


class BotNavigationTests(unittest.TestCase):
    def test_main_keyboard_is_inline_command_center_with_mini_app(self):
        with patch.object(bot.settings, "WEBAPP_URL", "https://example.test/app/"):
            keyboard = bot.main_keyboard()

        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        expected = {
            bot.WALLET, bot.TRANSFER, bot.HISTORY, bot.ACCOUNT,
            bot.SHOP, bot.GT_BALANCE, bot.COMMUNITY, bot.MINI_APP,
        }
        self.assertTrue(expected.issubset(set(labels)))
        mini_app = next(button for row in keyboard.inline_keyboard for button in row if button.text == bot.MINI_APP)
        self.assertIsNotNone(mini_app.web_app)
        self.assertEqual(mini_app.web_app.url, "https://example.test/app/")

    def test_mini_app_remains_reachable_when_url_is_not_configured(self):
        with patch.object(bot.settings, "WEBAPP_URL", ""):
            keyboard = bot.main_keyboard()

        mini_app = next(button for row in keyboard.inline_keyboard for button in row if button.text == bot.MINI_APP)
        self.assertIsNone(mini_app.web_app)
        self.assertEqual(mini_app.callback_data, "menu:miniapp")
        labels = {button.text for row in keyboard.inline_keyboard for button in row}
        self.assertIn(bot.WALLET, labels)
        self.assertIn(bot.TRANSFER, labels)
        self.assertIn(bot.HISTORY, labels)

    def test_menu_callbacks_route_to_existing_handlers(self):
        source = open(bot.__file__, encoding="utf-8-sig").read()
        self.assertIn('@dp.callback_query(F.data.startswith("menu:"))', source)
        for action in ("wallet", "transfer", "history", "account", "shop", "community", "games", "help", "miniapp"):
            self.assertIn(f'action == "{action}"', source)


if __name__ == "__main__":
    unittest.main()
