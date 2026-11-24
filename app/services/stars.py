import time
import uuid
from decimal import Decimal

from sqlalchemy import text
from app.database.connection import engine

UNIT = 10 ** 6
PACKAGES = {
    1: (50, 1 * UNIT),
    10: (500, 10 * UNIT),
    100: (5000, 100 * UNIT),
    1000: (50000, 1000 * UNIT),
}


def ensure_table():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tnc_stars_orders (
                payload VARCHAR(64) PRIMARY KEY,
                user_id BIGINT NOT NULL,
                stars_amount BIGINT NOT NULL,
                tnc_units BIGINT NOT NULL,
                status VARCHAR(16) NOT NULL,
                charge_id VARCHAR(255) UNIQUE,
                created_at BIGINT NOT NULL
            )
        """))


def create_order(user_id, package):
    package = int(package)
    if package not in PACKAGES:
        raise ValueError("Такого пакета нет.")

    stars, units = PACKAGES[package]
    payload = uuid.uuid4().hex
    ensure_table()

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO tnc_stars_orders
            (payload, user_id, stars_amount, tnc_units, status, created_at)
            VALUES (:payload, :uid, :stars, :units, 'pending', :created)
        """), {
            "payload": payload,
            "uid": int(user_id),
            "stars": stars,
            "units": units,
            "created": int(time.time()),
        })

    return payload, stars


def create_custom_order(user_id, amount):
    from decimal import Decimal, InvalidOperation

    try:
        number = Decimal(str(amount).replace(",", "."))
    except (InvalidOperation, ValueError):
        raise ValueError("Некорректная сумма.")

    if not number.is_finite() or number < Decimal("0.1"):
        raise ValueError("Минимальная покупка — 0,1 TNC.")

    if number > Decimal("1000000"):
        raise ValueError("Максимальная покупка — 1 000 000 TNC.")

    tenths = number * 10
    if tenths != tenths.to_integral_value():
        raise ValueError("Сумма должна быть кратна 0,1 TNC.")

    stars_value = number * 50
    if stars_value != stars_value.to_integral_value():
        raise ValueError("Некорректная стоимость в Stars.")

    units_value = number * UNIT
    if units_value != units_value.to_integral_value():
        raise ValueError("Некорректная сумма TNC.")

    stars = int(stars_value)
    units = int(units_value)
    payload = uuid.uuid4().hex
    ensure_table()

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO tnc_stars_orders
            (payload, user_id, stars_amount, tnc_units, status, created_at)
            VALUES (:payload, :uid, :stars, :units, 'pending', :created)
        """), {
            "payload": payload,
            "uid": int(user_id),
            "stars": stars,
            "units": units,
            "created": int(time.time()),
        })

    return payload, stars

def check_order(payload, user_id, stars_amount):
    ensure_table()
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT user_id, stars_amount, status, created_at
            FROM tnc_stars_orders
            WHERE payload = :payload
        """), {"payload": payload}).mappings().first()

    if not row:
        return False
    if row["status"] != "pending":
        return False
    if int(row["user_id"]) != int(user_id):
        return False
    if int(row["stars_amount"]) != int(stars_amount):
        return False
    if int(time.time()) - int(row["created_at"]) > 3600:
        return False
    return True


def complete_payment(payload, user_id, stars_amount, charge_id):
    ensure_table()

    with engine.begin() as conn:
        result = conn.execute(text("""
            UPDATE tnc_stars_orders
            SET status = 'paid', charge_id = :charge
            WHERE payload = :payload
              AND user_id = :uid
              AND stars_amount = :stars
              AND status = 'pending'
              AND charge_id IS NULL
              AND created_at >= :min_created
        """), {
            "charge": charge_id,
            "payload": payload,
            "uid": int(user_id),
            "stars": int(stars_amount),
            "min_created": int(time.time()) - 3600,
        })

        if result.rowcount != 1:
            return False

        order = conn.execute(text("""
            SELECT tnc_units FROM tnc_stars_orders
            WHERE payload = :payload
        """), {"payload": payload}).mappings().first()

        if not order:
            raise ValueError("Заказ не найден.")

        units = int(order["tnc_units"])

        wallet_result = conn.execute(text("""
            UPDATE tnc_wallets
            SET balance_units = balance_units + :units
            WHERE user_id = :uid
        """), {"units": units, "uid": int(user_id)})

        if wallet_result.rowcount != 1:
            raise ValueError("Кошелёк пользователя не найден.")

        conn.execute(text("""
            INSERT INTO tnc_transactions
            (operation_id, sender_id, receiver_id, amount_units,
             kind, description, created_at)
            VALUES (:op, NULL, :uid, :units,
                    'stars_purchase', :description, :created)
        """), {
            "op": str(uuid.uuid4()),
            "uid": int(user_id),
            "units": units,
            "description": "Покупка TNC за Telegram Stars",
            "created": int(time.time()),
        })

    return True