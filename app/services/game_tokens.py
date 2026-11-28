import time
import uuid

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.database.connection import engine

GT_PER_STAR = 5000


def init_game_tables():
    statements = [
        """
        CREATE TABLE IF NOT EXISTS tnc_game_wallets (
            user_id BIGINT PRIMARY KEY,
            balance BIGINT NOT NULL DEFAULT 0
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS tnc_game_transactions (
            operation_id VARCHAR(36) PRIMARY KEY,
            user_id BIGINT NOT NULL,
            amount BIGINT NOT NULL,
            kind VARCHAR(32) NOT NULL,
            description VARCHAR(255) NOT NULL DEFAULT '',
            reference VARCHAR(128) UNIQUE,
            created_at BIGINT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS tnc_game_stars_orders (
            payload VARCHAR(80) PRIMARY KEY,
            user_id BIGINT NOT NULL,
            stars INTEGER NOT NULL,
            tokens BIGINT NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            charge_id VARCHAR(255) UNIQUE,
            created_at BIGINT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_tnc_game_transactions_user_created ON tnc_game_transactions (user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_tnc_game_stars_orders_user_created ON tnc_game_stars_orders (user_id, created_at DESC)",
    ]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def get_balance(user_id):
    init_game_tables()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT balance FROM tnc_game_wallets WHERE user_id=:uid"),
            {"uid": int(user_id)},
        ).first()
        return int(row[0]) if row else 0


def get_history(user_id, limit=30):
    init_game_tables()
    limit = max(1, min(int(limit), 100))
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT operation_id, amount, kind, description,
                       reference, created_at
                FROM tnc_game_transactions
                WHERE user_id=:uid
                ORDER BY created_at DESC
                LIMIT :lim
            """),
            {"uid": int(user_id), "lim": limit},
        ).mappings().all()
        return [dict(row) for row in rows]


def create_stars_order(user_id, stars):
    init_game_tables()
    user_id = int(user_id)
    stars = int(stars)
    if stars < 1 or stars > 10000:
        raise ValueError("Количество Stars должно быть от 1 до 10 000.")

    tokens = stars * GT_PER_STAR
    payload = "gt_" + uuid.uuid4().hex

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO tnc_game_stars_orders
                (payload, user_id, stars, tokens, status, created_at)
                VALUES (:payload, :uid, :stars, :tokens, 'pending', :created)
            """),
            {
                "payload": payload,
                "uid": user_id,
                "stars": stars,
                "tokens": tokens,
                "created": int(time.time()),
            },
        )

    return payload, tokens


def check_stars_order(payload, user_id, stars):
    init_game_tables()
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT user_id, stars, tokens, status, created_at
                FROM tnc_game_stars_orders
                WHERE payload=:payload
            """),
            {"payload": payload},
        ).mappings().first()

    if not row:
        return False
    return (
        int(row["user_id"]) == int(user_id)
        and int(row["stars"]) == int(stars)
        and row["status"] == "pending"
        and int(time.time()) - 3600 <= int(row["created_at"]) <= int(time.time()) + 60
    )


def complete_stars_payment(payload, user_id, stars, charge_id):
    """
    Вызывается ТОЛЬКО после Telegram successful_payment.
    Повторный вызов с тем же платежом не начисляет GT повторно.
    """
    init_game_tables()
    user_id = int(user_id)
    stars = int(stars)
    if not charge_id or len(str(charge_id)) > 255:
        raise ValueError("Некорректный идентификатор платежа.")
    charge_id = str(charge_id)
    now = int(time.time())

    try:
        with engine.begin() as conn:
            order = conn.execute(
                text("""
                    SELECT user_id, stars, tokens, status, charge_id, created_at
                    FROM tnc_game_stars_orders
                    WHERE payload=:payload
                """),
                {"payload": payload},
            ).mappings().first()

            if not order:
                raise ValueError("Заказ GT не найден.")

            if int(order["user_id"]) != user_id or int(order["stars"]) != stars:
                raise ValueError("Данные платежа не совпадают с заказом.")

            if order["status"] == "paid":
                if order["charge_id"] == charge_id:
                    return {
                        "already_processed": True,
                        "tokens": int(order["tokens"]),
                    }
                raise ValueError("Заказ уже оплачен другим платежом.")

            if order["status"] != "pending":
                raise ValueError("Заказ недоступен для оплаты.")
            created_at = int(order["created_at"])
            if created_at < now - 3600 or created_at > now + 60:
                raise ValueError("Заказ просрочен или имеет некорректную дату. Создай новый счёт.")

            tokens = int(order["tokens"])

            conn.execute(
                text("""
                    INSERT INTO tnc_game_wallets (user_id, balance)
                    VALUES (:uid, 0)
                    ON CONFLICT (user_id) DO NOTHING
                """),
                {"uid": user_id},
            )

            updated = conn.execute(
                text("""
                    UPDATE tnc_game_stars_orders
                    SET status='paid', charge_id=:charge
                    WHERE payload=:payload AND status='pending'
                """),
                {"charge": charge_id, "payload": payload},
            )

            if updated.rowcount != 1:
                raise ValueError("Заказ уже был обработан.")

            conn.execute(
                text("""
                    UPDATE tnc_game_wallets
                    SET balance=balance + :tokens
                    WHERE user_id=:uid
                """),
                {"tokens": tokens, "uid": user_id},
            )

            conn.execute(
                text("""
                    INSERT INTO tnc_game_transactions
                    (operation_id, user_id, amount, kind, description,
                     reference, created_at)
                    VALUES (:op, :uid, :amount, 'stars_purchase',
                            'Покупка GT за Telegram Stars', :ref, :created)
                """),
                {
                    "op": str(uuid.uuid4()),
                    "uid": user_id,
                    "amount": tokens,
                    "ref": charge_id,
                    "created": now,
                },
            )

            return {"already_processed": False, "tokens": tokens}
    except IntegrityError as error:
        # The unique charge_id constraint prevents one Telegram payment from
        # crediting multiple orders. engine.begin rolls back the failed transaction.
        raise ValueError("Этот Telegram-платёж уже привязан к другому заказу.") from error


def init_admin_tables():
    init_game_tables()
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tnc_game_bans (
                user_id BIGINT PRIMARY KEY,
                admin_id BIGINT NOT NULL,
                reason VARCHAR(255) NOT NULL DEFAULT '',
                created_at BIGINT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tnc_game_admin_log (
                id VARCHAR(36) PRIMARY KEY,
                admin_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                action VARCHAR(32) NOT NULL,
                amount BIGINT NOT NULL DEFAULT 0,
                reason VARCHAR(255) NOT NULL DEFAULT '',
                created_at BIGINT NOT NULL
            )
        """))


def admin_adjust_tokens(admin_id, user_id, amount, action, reason=""):
    init_admin_tables()
    admin_id = int(admin_id)
    user_id = int(user_id)
    amount = int(amount)
    reason = str(reason or "")[:255]

    if amount <= 0:
        raise ValueError("Количество GT должно быть больше нуля.")

    if action not in ("admin_add", "admin_take"):
        raise ValueError("Неизвестная операция.")

    now = int(time.time())

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO tnc_game_wallets (user_id, balance)
                VALUES (:uid, 0)
                ON CONFLICT (user_id) DO NOTHING
            """),
            {"uid": user_id},
        )

        if action == "admin_add":
            conn.execute(
                text("""
                    UPDATE tnc_game_wallets
                    SET balance = balance + :amount
                    WHERE user_id = :uid
                """),
                {"uid": user_id, "amount": amount},
            )
            kind = "admin_add"
            signed_amount = amount
        else:
            result = conn.execute(
                text("""
                    UPDATE tnc_game_wallets
                    SET balance = balance - :amount
                    WHERE user_id = :uid AND balance >= :amount
                """),
                {"uid": user_id, "amount": amount},
            )
            if result.rowcount != 1:
                raise ValueError("У игрока недостаточно GT.")
            kind = "admin_take"
            signed_amount = -amount

        conn.execute(
            text("""
                INSERT INTO tnc_game_transactions
                (operation_id, user_id, amount, kind, description,
                 reference, created_at)
                VALUES (:op, :uid, :amount, :kind, :description,
                        :ref, :created)
            """),
            {
                "op": str(uuid.uuid4()),
                "uid": user_id,
                "amount": signed_amount,
                "kind": kind,
                "description": reason or (
                    "Начисление GT администратором"
                    if action == "admin_add"
                    else "Списание GT администратором"
                ),
                "ref": "admin-" + uuid.uuid4().hex,
                "created": now,
            },
        )

        conn.execute(
            text("""
                INSERT INTO tnc_game_admin_log
                (id, admin_id, user_id, action, amount, reason, created_at)
                VALUES (:id, :admin, :uid, :action, :amount, :reason, :created)
            """),
            {
                "id": str(uuid.uuid4()),
                "admin": admin_id,
                "uid": user_id,
                "action": action,
                "amount": amount,
                "reason": reason,
                "created": now,
            },
        )

    return get_balance(user_id)


def set_game_ban(admin_id, user_id, banned, reason=""):
    init_admin_tables()
    admin_id = int(admin_id)
    user_id = int(user_id)
    reason = str(reason or "")[:255]
    now = int(time.time())

    with engine.begin() as conn:
        if banned:
            conn.execute(
                text("""
                    INSERT INTO tnc_game_bans
                    (user_id, admin_id, reason, created_at)
                    VALUES (:uid, :admin, :reason, :created)
                    ON CONFLICT (user_id) DO UPDATE SET
                        admin_id = excluded.admin_id,
                        reason = excluded.reason,
                        created_at = excluded.created_at
                """),
                {
                    "uid": user_id,
                    "admin": admin_id,
                    "reason": reason,
                    "created": now,
                },
            )
            action = "game_ban"
        else:
            conn.execute(
                text("DELETE FROM tnc_game_bans WHERE user_id=:uid"),
                {"uid": user_id},
            )
            action = "game_unban"

        conn.execute(
            text("""
                INSERT INTO tnc_game_admin_log
                (id, admin_id, user_id, action, amount, reason, created_at)
                VALUES (:id, :admin, :uid, :action, 0, :reason, :created)
            """),
            {
                "id": str(uuid.uuid4()),
                "admin": admin_id,
                "uid": user_id,
                "action": action,
                "reason": reason,
                "created": now,
            },
        )

    return is_game_banned(user_id)


def is_game_banned(user_id):
    init_admin_tables()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT 1 FROM tnc_game_bans WHERE user_id=:uid"),
            {"uid": int(user_id)},
        ).first()
        return row is not None


def get_admin_log(limit=30):
    init_admin_tables()
    limit = max(1, min(int(limit), 100))
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT admin_id, user_id, action, amount, reason, created_at
                FROM tnc_game_admin_log
                ORDER BY created_at DESC
                LIMIT :lim
            """),
            {"lim": limit},
        ).mappings().all()
        return [dict(row) for row in rows]
