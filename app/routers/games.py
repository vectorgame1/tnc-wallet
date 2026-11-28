import secrets
import time
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.security import verify
from app.database.connection import engine, get_db
from app.services.accounts import get_or_create_user
from app.services.game_tokens import init_admin_tables, is_game_banned

router = APIRouter(prefix="/api/games", tags=["games"])


def current_player(
    x_telegram_init_data: str = Header(..., alias="X-Telegram-Init-Data"),
    db: Session = Depends(get_db),
):
    try:
        user = get_or_create_user(db, verify(x_telegram_init_data))
        db.commit()
        return int(user.telegram_id)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=401, detail="Telegram authorization failed")


def ensure_tables():
    init_admin_tables()
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tnc_crash_rounds (
                id VARCHAR(36) PRIMARY KEY,
                user_id BIGINT NOT NULL,
                stake BIGINT NOT NULL,
                target_multiplier INTEGER NOT NULL,
                crash_multiplier INTEGER NOT NULL,
                won BOOLEAN NOT NULL,
                payout BIGINT NOT NULL,
                created_at BIGINT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_tnc_crash_rounds_user_created
            ON tnc_crash_rounds (user_id, created_at DESC)
        """))


class CrashPlay(BaseModel):
    stake: int = Field(gt=0, le=100000000)
    target: float = Field(ge=1.10, le=10.00)


@router.get("/crash/history")
def crash_history(user_id: int = Depends(current_player)):
    ensure_tables()
    if is_game_banned(user_id):
        raise HTTPException(status_code=403, detail="Доступ к играм заблокирован")

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, stake, target_multiplier, crash_multiplier,
                       won, payout, created_at
                FROM tnc_crash_rounds
                WHERE user_id=:uid
                ORDER BY created_at DESC
                LIMIT 30
            """),
            {"uid": user_id},
        ).mappings().all()

    return {"items": [dict(row) for row in rows]}


@router.post("/crash/play")
def crash_play(data: CrashPlay, user_id: int = Depends(current_player)):
    ensure_tables()
    if is_game_banned(user_id):
        raise HTTPException(status_code=403, detail="Доступ к играм заблокирован")

    target = int(round(data.target * 100))
    if target < 110 or target > 1000:
        raise HTTPException(status_code=400, detail="Некорректный множитель")

    # Crash-point distribution: P(crash >= x) ~= 0.99 / x, giving ~99% RTP.
    # Multiplier is stored in hundredths; target remains capped at 10.00x.
    crash_multiplier = max(100, 990000 // (secrets.randbelow(10000) + 1))
    won = crash_multiplier >= target
    payout = data.stake * target // 100 if won else 0
    now = int(time.time())
    round_id = str(uuid.uuid4())

    try:
        with engine.begin() as conn:
            debit = conn.execute(
                text("""
                    UPDATE tnc_game_wallets
                    SET balance = balance - :stake
                    WHERE user_id = :uid AND balance >= :stake
                """),
                {"uid": user_id, "stake": data.stake},
            )
            if debit.rowcount != 1:
                raise HTTPException(status_code=400, detail="Недостаточно GT")

            conn.execute(
                text("""
                    INSERT INTO tnc_game_transactions
                    (operation_id, user_id, amount, kind, description,
                     reference, created_at)
                    VALUES (:op, :uid, :amount, 'crash_bet',
                            'Ставка Crash', :ref, :created)
                """),
                {
                    "op": str(uuid.uuid4()),
                    "uid": user_id,
                    "amount": -data.stake,
                    "ref": round_id + ":bet",
                    "created": now,
                },
            )

            if payout > 0:
                conn.execute(
                    text("""
                        UPDATE tnc_game_wallets
                        SET balance = balance + :payout
                        WHERE user_id = :uid
                    """),
                    {"uid": user_id, "payout": payout},
                )
                conn.execute(
                    text("""
                        INSERT INTO tnc_game_transactions
                        (operation_id, user_id, amount, kind, description,
                         reference, created_at)
                        VALUES (:op, :uid, :amount, 'crash_win',
                                'Выигрыш Crash', :ref, :created)
                    """),
                    {
                        "op": str(uuid.uuid4()),
                        "uid": user_id,
                        "amount": payout,
                        "ref": round_id + ":win",
                        "created": now,
                    },
                )

            conn.execute(
                text("""
                    INSERT INTO tnc_crash_rounds
                    (id, user_id, stake, target_multiplier,
                     crash_multiplier, won, payout, created_at)
                    VALUES (:id, :uid, :stake, :target,
                            :crash, :won, :payout, :created)
                """),
                {
                    "id": round_id,
                    "uid": user_id,
                    "stake": data.stake,
                    "target": target,
                    "crash": crash_multiplier,
                    "won": won,
                    "payout": payout,
                    "created": now,
                },
            )

            balance_row = conn.execute(
                text("SELECT balance FROM tnc_game_wallets WHERE user_id=:uid"),
                {"uid": user_id},
            ).first()

        return {
            "round_id": round_id,
            "won": won,
            "stake": data.stake,
            "target": target / 100,
            "crash_at": crash_multiplier / 100,
            "payout": payout,
            "net": payout - data.stake,
            "balance": int(balance_row[0]),
        }

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Не удалось завершить раунд")
