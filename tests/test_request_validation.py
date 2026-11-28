import unittest

from pydantic import ValidationError

from app.api import GameAdminAdjustment, GameAdminBan, Transfer


class RequestValidationTests(unittest.TestCase):
    def test_transfer_receiver_must_fit_positive_bigint(self):
        with self.assertRaises(ValidationError):
            Transfer(receiver_id=9223372036854775808, amount="1")
        with self.assertRaises(ValidationError):
            Transfer(receiver_id=0, amount="1")

    def test_admin_target_ids_must_fit_positive_bigint(self):
        for model, values in (
            (GameAdminAdjustment, {"amount": 1, "action": "admin_add"}),
            (GameAdminBan, {"banned": True}),
        ):
            with self.subTest(model=model.__name__):
                with self.assertRaises(ValidationError):
                    model(user_id=9223372036854775808, **values)
                with self.assertRaises(ValidationError):
                    model(user_id=0, **values)


if __name__ == "__main__":
    unittest.main()
