import unittest
import uuid

from sqlalchemy import select, func

from app.database.connection import Base, engine, SessionLocal
from app.database.models import User, Wallet, Transaction
from app.services.wallet import send, amount_units


class WalletTransferTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.create_all(bind=engine)
        self.sender = 6_000_000_000 + (uuid.uuid4().int % 900_000_000)
        self.receiver = self.sender + 1
        with SessionLocal() as db:
            db.add_all([
                User(telegram_id=self.sender, first_name="Sender"),
                User(telegram_id=self.receiver, first_name="Receiver"),
            ])
            db.flush()
            db.add_all([
                Wallet(user_id=self.sender, balance_units=100 * 10**6),
                Wallet(user_id=self.receiver, balance_units=10 * 10**6),
            ])
            db.commit()

    def tearDown(self):
        with SessionLocal() as db:
            db.query(Transaction).filter(
                (Transaction.sender_id == self.sender) |
                (Transaction.receiver_id == self.sender) |
                (Transaction.sender_id == self.receiver) |
                (Transaction.receiver_id == self.receiver)
            ).delete(synchronize_session=False)
            db.query(Wallet).filter(
                Wallet.user_id.in_([self.sender, self.receiver])
            ).delete(synchronize_session=False)
            db.query(User).filter(
                User.telegram_id.in_([self.sender, self.receiver])
            ).delete(synchronize_session=False)
            db.commit()

    def test_transfer_updates_both_wallets_and_writes_one_record(self):
        with SessionLocal() as db:
            tx = send(db, self.sender, self.receiver, "25.5")
            self.assertEqual(tx.kind, "transfer")
            self.assertEqual(tx.amount_units, 25_500_000)

        with SessionLocal() as db:
            sender = db.get(Wallet, self.sender)
            receiver = db.get(Wallet, self.receiver)
            count = db.scalar(select(func.count()).select_from(Transaction).where(
                Transaction.operation_id == tx.operation_id
            ))
            self.assertEqual(sender.balance_units, 74_500_000)
            self.assertEqual(receiver.balance_units, 35_500_000)
            self.assertEqual(count, 1)

    def test_insufficient_transfer_changes_neither_wallet_nor_ledger(self):
        with SessionLocal() as db:
            with self.assertRaisesRegex(ValueError, "Недостаточно средств"):
                send(db, self.sender, self.receiver, "101")

        with SessionLocal() as db:
            self.assertEqual(db.get(Wallet, self.sender).balance_units, 100_000_000)
            self.assertEqual(db.get(Wallet, self.receiver).balance_units, 10_000_000)
            count = db.scalar(select(func.count()).select_from(Transaction).where(
                (Transaction.sender_id == self.sender) |
                (Transaction.receiver_id == self.sender)
            ))
            self.assertEqual(count, 0)

    def test_self_transfer_is_rejected_without_changes(self):
        with SessionLocal() as db:
            with self.assertRaisesRegex(ValueError, "самому себе"):
                send(db, self.sender, self.sender, "1")
        with SessionLocal() as db:
            self.assertEqual(db.get(Wallet, self.sender).balance_units, 100_000_000)

    def test_missing_receiver_is_rejected_without_debit(self):
        with SessionLocal() as db:
            with self.assertRaisesRegex(ValueError, "Получатель не найден"):
                send(db, self.sender, self.receiver + 100, "1")
        with SessionLocal() as db:
            self.assertEqual(db.get(Wallet, self.sender).balance_units, 100_000_000)

    def test_amount_precision_and_limit_are_enforced(self):
        self.assertEqual(amount_units("0.000001"), 1)
        for value in ("0.0000001", "1000000.000001", "NaN", "Infinity", "-1"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    amount_units(value)


if __name__ == "__main__":
    unittest.main()
