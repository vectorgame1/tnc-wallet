import unittest
import uuid
import time

from fastapi import HTTPException
from sqlalchemy import text

from app.database.connection import engine
from app.routers.games_extra import prepare, settle
from app.services.game_tokens import (
    complete_stars_payment,
    create_stars_order,
    init_game_tables,
    admin_adjust_tokens,
    set_game_ban,
    is_game_banned,
)


class GameRoundTests(unittest.TestCase):
    def setUp(self):
        init_game_tables()
        prepare()
        self.user_id = 7_000_000_000 + (uuid.uuid4().int % 1_000_000_000)
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO tnc_game_wallets (user_id, balance)
                    VALUES (:uid, 1000)
                """),
                {"uid": self.user_id},
            )

    def tearDown(self):
        with engine.begin() as conn:
            for table in (
                "tnc_game_transactions",
                "tnc_game_stars_orders",
                "tnc_game_admin_log",
                "tnc_game_bans",
                "tnc_extra_game_rounds",
                "tnc_crash_rounds",
                "tnc_game_wallets",
            ):
                conn.execute(
                    text(f"DELETE FROM {table} WHERE user_id=:uid"),
                    {"uid": self.user_id},
                )

    def test_win_debits_and_credits_atomically(self):
        result = settle(
            self.user_id, "dice", 100, True, 198, "unit-test-win"
        )
        self.assertEqual(result["payout"], 198)
        self.assertEqual(result["net"], 98)
        self.assertEqual(result["balance"], 1098)

        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT amount, reference
                    FROM tnc_game_transactions
                    WHERE user_id=:uid
                    ORDER BY amount
                """),
                {"uid": self.user_id},
            ).all()
        self.assertEqual(sorted(row[0] for row in rows), [-100, 198])
        self.assertEqual({row[1] for row in rows}, {
            result["round_id"] + ":bet",
            result["round_id"] + ":win",
        })

    def test_loss_records_stake_and_round(self):
        result = settle(
            self.user_id, "slots", 100, False, 0, "unit-test-loss"
        )
        self.assertEqual(result["payout"], 0)
        self.assertEqual(result["balance"], 900)

        with engine.connect() as conn:
            count = conn.execute(
                text("""
                    SELECT COUNT(*) FROM tnc_game_transactions
                    WHERE user_id=:uid
                """),
                {"uid": self.user_id},
            ).scalar_one()
            rounds = conn.execute(
                text("""
                    SELECT COUNT(*) FROM tnc_extra_game_rounds
                    WHERE user_id=:uid
                """),
                {"uid": self.user_id},
            ).scalar_one()
        self.assertEqual(count, 1)
        self.assertEqual(rounds, 1)

    def test_insufficient_balance_does_not_create_round(self):
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tnc_game_wallets SET balance=50
                    WHERE user_id=:uid
                """),
                {"uid": self.user_id},
            )

        with self.assertRaises(HTTPException):
            settle(self.user_id, "dice", 100, True, 198, "unit-test-funds")

        with engine.connect() as conn:
            balance = conn.execute(
                text("""
                    SELECT balance FROM tnc_game_wallets WHERE user_id=:uid
                """),
                {"uid": self.user_id},
            ).scalar_one()
            rounds = conn.execute(
                text("""
                    SELECT COUNT(*) FROM tnc_extra_game_rounds
                    WHERE user_id=:uid
                """),
                {"uid": self.user_id},
            ).scalar_one()
        self.assertEqual(balance, 50)
        self.assertEqual(rounds, 0)

    def test_admin_adjustments_and_game_bans_are_audited(self):
        balance = admin_adjust_tokens(
            123456, self.user_id, 200, "admin_add", "test credit"
        )
        self.assertEqual(balance, 1200)

        balance = admin_adjust_tokens(
            123456, self.user_id, 100, "admin_take", "test debit"
        )
        self.assertEqual(balance, 1100)

        self.assertTrue(set_game_ban(
            123456, self.user_id, True, "test restriction"
        ))
        self.assertTrue(is_game_banned(self.user_id))
        self.assertFalse(set_game_ban(
            123456, self.user_id, False, "test unban"
        ))

        with engine.connect() as conn:
            logs = conn.execute(
                text("""
                    SELECT action FROM tnc_game_admin_log
                    WHERE user_id=:uid ORDER BY created_at
                """),
                {"uid": self.user_id},
            ).scalars().all()
        self.assertEqual(
            set(logs),
            {"admin_add", "admin_take", "game_ban", "game_unban"},
        )

    def test_stars_payment_rejects_wrong_user_or_amount(self):
        payload, expected_tokens = create_stars_order(self.user_id, 3)

        with self.assertRaises(ValueError):
            complete_stars_payment(
                payload, self.user_id + 1, 3, "wrong-user-charge"
            )
        with self.assertRaises(ValueError):
            complete_stars_payment(
                payload, self.user_id, 4, "wrong-amount-charge"
            )

        with engine.connect() as conn:
            balance = conn.execute(
                text("""
                    SELECT balance FROM tnc_game_wallets WHERE user_id=:uid
                """),
                {"uid": self.user_id},
            ).scalar_one()
            status = conn.execute(
                text("""
                    SELECT status FROM tnc_game_stars_orders WHERE payload=:payload
                """),
                {"payload": payload},
            ).scalar_one()

        self.assertEqual(balance, 1000)
        self.assertEqual(status, "pending")
        self.assertEqual(expected_tokens, 15000)

    def test_stars_charge_id_cannot_credit_two_orders(self):
        first_payload, _ = create_stars_order(self.user_id, 1)
        second_payload, _ = create_stars_order(self.user_id, 1)
        charge_id = "shared-charge-" + uuid.uuid4().hex

        first = complete_stars_payment(
            first_payload, self.user_id, 1, charge_id
        )
        self.assertFalse(first["already_processed"])

        with self.assertRaises(Exception):
            complete_stars_payment(
                second_payload, self.user_id, 1, charge_id
            )

        with engine.connect() as conn:
            balance = conn.execute(
                text("""
                    SELECT balance FROM tnc_game_wallets WHERE user_id=:uid
                """),
                {"uid": self.user_id},
            ).scalar_one()
            paid_orders = conn.execute(
                text("""
                    SELECT COUNT(*) FROM tnc_game_stars_orders
                    WHERE user_id=:uid AND status='paid'
                """),
                {"uid": self.user_id},
            ).scalar_one()

        self.assertEqual(balance, 6000)
        self.assertEqual(paid_orders, 1)

    def test_stars_payment_rejects_expired_order(self):
        payload, _ = create_stars_order(self.user_id, 1)
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE tnc_game_stars_orders
                    SET created_at=:created
                    WHERE payload=:payload
                """),
                {"created": int(time.time()) - 3601, "payload": payload},
            )

        with self.assertRaisesRegex(ValueError, "Срок действия заказа истёк"):
            complete_stars_payment(
                payload, self.user_id, 1, "expired-" + uuid.uuid4().hex
            )

        with engine.connect() as conn:
            status = conn.execute(
                text("SELECT status FROM tnc_game_stars_orders WHERE payload=:payload"),
                {"payload": payload},
            ).scalar_one()
            balance = conn.execute(
                text("SELECT balance FROM tnc_game_wallets WHERE user_id=:uid"),
                {"uid": self.user_id},
            ).scalar_one()
        self.assertEqual(status, "pending")
        self.assertEqual(balance, 1000)

    def test_stars_payment_is_idempotent(self):
        payload, expected_tokens = create_stars_order(self.user_id, 2)
        charge_id = "test-charge-" + uuid.uuid4().hex
        first = complete_stars_payment(
            payload, self.user_id, 2, charge_id
        )
        second = complete_stars_payment(
            payload, self.user_id, 2, charge_id
        )
        self.assertFalse(first["already_processed"])
        self.assertTrue(second["already_processed"])
        self.assertEqual(first["tokens"], expected_tokens)

        with engine.connect() as conn:
            balance = conn.execute(
                text("""
                    SELECT balance FROM tnc_game_wallets WHERE user_id=:uid
                """),
                {"uid": self.user_id},
            ).scalar_one()
        self.assertEqual(balance, 11000)

