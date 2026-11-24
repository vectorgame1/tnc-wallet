from decimal import Decimal, InvalidOperation

from sqlalchemy import or_, select, update

from app.database.models import Wallet, Transaction


UNIT = 10 ** 6
MAX_AMOUNT = Decimal("1000000")


def amount_units(value):
    try:
        number = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        raise ValueError("Некорректная сумма.")

    if not number.is_finite() or number <= 0:
        raise ValueError("Сумма должна быть положительной.")

    scaled = number * UNIT

    if scaled != scaled.to_integral_value():
        raise ValueError("Максимум 6 знаков после запятой.")

    if number > MAX_AMOUNT:
        raise ValueError("Лимит одной операции — 1 000 000 TNC.")

    return int(scaled)


def fmt(units):
    value = Decimal(units) / UNIT
    result = f"{value:,.6f}".replace(",", " ")
    return result.rstrip("0").rstrip(".") if "." in result else result


def balance(db, uid):
    wallet = db.get(Wallet, int(uid))

    if wallet is None:
        raise ValueError("Кошелёк не найден.")

    return wallet.balance_units


def _change_balance(db, uid, units, increase):
    if increase:
        statement = (
            update(Wallet)
            .where(Wallet.user_id == uid)
            .values(balance_units=Wallet.balance_units + units)
        )
    else:
        statement = (
            update(Wallet)
            .where(
                Wallet.user_id == uid,
                Wallet.balance_units >= units,
            )
            .values(balance_units=Wallet.balance_units - units)
        )

    result = db.execute(statement)

    if result.rowcount != 1:
        if not increase:
            raise ValueError(
                "Недостаточно средств или кошелёк не найден."
            )
        raise ValueError("Кошелёк не найден.")


def _finish_transaction(db, tx):
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def deposit(db, receiver, amount, description="Пополнение TNC"):
    receiver = int(receiver)
    units = amount_units(amount)

    try:
        _change_balance(db, receiver, units, True)

        tx = Transaction(
            sender_id=None,
            receiver_id=receiver,
            amount_units=units,
            kind="deposit",
            description=description[:255],
        )

        return _finish_transaction(db, tx)

    except Exception:
        db.rollback()
        raise


def withdraw(db, sender, amount, description="Списание TNC"):
    sender = int(sender)
    units = amount_units(amount)

    try:
        _change_balance(db, sender, units, False)

        tx = Transaction(
            sender_id=sender,
            receiver_id=None,
            amount_units=units,
            kind="withdraw",
            description=description[:255],
        )

        return _finish_transaction(db, tx)

    except Exception:
        db.rollback()
        raise


def send(db, sender, receiver, amount):
    sender = int(sender)
    receiver = int(receiver)
    units = amount_units(amount)

    if sender == receiver:
        raise ValueError("Нельзя отправить самому себе.")

    try:
        receiver_wallet = db.get(Wallet, receiver)

        if receiver_wallet is None:
            raise ValueError(
                "Получатель не найден. Сначала он должен запустить TNC Wallet."
            )

        _change_balance(db, sender, units, False)
        _change_balance(db, receiver, units, True)

        tx = Transaction(
            sender_id=sender,
            receiver_id=receiver,
            amount_units=units,
            kind="transfer",
            description="Перевод TNC",
        )

        return _finish_transaction(db, tx)

    except Exception:
        db.rollback()
        raise


def history(db, uid, limit=10):
    statement = (
        select(Transaction)
        .where(
            or_(
                Transaction.sender_id == int(uid),
                Transaction.receiver_id == int(uid),
            )
        )
        .order_by(Transaction.id.desc())
        .limit(max(1, min(int(limit), 50)))
    )

    return db.execute(statement).scalars().all()
