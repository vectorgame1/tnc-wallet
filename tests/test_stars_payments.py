import time
import unittest
import uuid

from sqlalchemy import text

from app.database.connection import Base, SessionLocal, engine
from app.database.models import User, Wallet, Transaction
from app.services.stars import create_custom_order, complete_payment, ensure_table, UNIT


class TNCStarsPaymentTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.create_all(bind=engine)
        ensure_table()
        self.user_id = 8_000_000_000 + (uuid.uuid4().int % 900_000_000)
        with SessionLocal() as db:
            db.add(User(telegram_id=self.user_id, first_name="Stars test"))
            db.flush()
            db.add(Wallet(user_id=self.user_id, balance_units=0))
            db.commit()

    def tearDown(self):
        with engine.begin() as conn:
            conn.execute(text("""
                DELETE FROM tnc_transactions
                WHERE sender_id=:uid OR receiver_id=:uid
            """), {"uid": self.user_id})
            conn.execute(text("DELETE FROM tnc_stars_orders WHERE user_id=:uid"),
                         {"uid": self.user_id})
            conn.execute(text("DELETE FROM tnc_wallets WHERE user_id=:uid"),
                         {"uid": self.user_id})
            conn.execute(text("DELETE FROM users WHERE telegram_id=:uid"),
                         {"uid": self.user_id})

    def balance(self):
        with engine.connect() as conn:
            return conn.execute(text("""
                SELECT balance_units FROM tnc_wallets WHERE user_id=:uid
            """), {"uid": self.user_id}).scalar_one()

    def test_payment_credits_once_and_is_idempotent(self):
        payload, stars = create_custom_order(self.user_id, "2")
        charge = "tnc-stars-" + uuid.uuid4().hex

        self.assertTrue(complete_payment(payload, self.user_id, stars, charge))
        self.assertFalse(complete_payment(payload, self.user_id, stars, charge))
        self.assertEqual(self.balance(), 2 * UNIT)

        with engine.connect() as conn:
            count = conn.execute(text("""
                SELECT COUNT(*) FROM tnc_transactions
                WHERE receiver_id=:uid AND kind='stars_purchase'
            """), {"uid": self.user_id}).scalar_one()
        self.assertEqual(count, 1)

    def test_payment_rejects_wrong_user_or_amount(self):
        payload, stars = create_custom_order(self.user_id, "1")
        charge = "tnc-wrong-" + uuid.uuid4().hex

        self.assertFalse(complete_payment(payload, self.user_id + 1, stars, charge))
        self.assertFalse(complete_payment(payload, self.user_id, stars + 1, charge))
        self.assertEqual(self.balance(), 0)

    def test_same_telegram_charge_cannot_pay_two_orders(self):
        first_payload, first_stars = create_custom_order(self.user_id, "1")
        second_payload, second_stars = create_custom_order(self.user_id, "1")
        charge = "tnc-shared-" + uuid.uuid4().hex

        self.assertTrue(complete_payment(
            first_payload, self.user_id, first_stars, charge
        ))
        with self.assertRaises(Exception):
            complete_payment(
                second_payload, self.user_id, second_stars, charge
            )

        self.assertEqual(self.balance(), UNIT)
        with engine.connect() as conn:
            second_status = conn.execute(text("""
                SELECT status FROM tnc_stars_orders WHERE payload=:payload
            """), {"payload": second_payload}).scalar_one()
        self.assertEqual(second_status, "pending")

    def test_expired_order_is_not_credited(self):
        payload, stars = create_custom_order(self.user_id, "1")
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE tnc_stars_orders SET created_at=:created
                WHERE payload=:payload
            """), {"created": int(time.time()) - 3601, "payload": payload})

        self.assertFalse(complete_payment(
            payload, self.user_id, stars, "tnc-expired-" + uuid.uuid4().hex
        ))
        self.assertEqual(self.balance(), 0)


if __name__ == "__main__":
    unittest.main()
