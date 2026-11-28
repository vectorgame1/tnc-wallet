import unittest
import uuid

from fastapi import HTTPException
from sqlalchemy import text

from app.database.connection import engine
from app.routers.games_extra import settle
from app.services.game_tokens import (
    complete_stars_payment,
    create_stars_order,
    init_game_tables,
)


class GameRoundTests(unittest.TestCase):
    def setUp(self):
        init_game_tables()
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

