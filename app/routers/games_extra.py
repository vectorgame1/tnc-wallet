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


def player(x_telegram_init_data: str = Header(..., alias="X-Telegram-Init-Data"),
           db: Session = Depends(get_db)):
    try:
        user = get_or_create_user(db, verify(x_telegram_init_data))
        db.commit()
        return int(user.telegram_id)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=401, detail="Telegram authorization failed")


def prepare():
    init_admin_tables()
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tnc_extra_game_rounds (
                id VARCHAR(36) PRIMARY KEY,
                user_id BIGINT NOT NULL,
                game VARCHAR(16) NOT NULL,
                stake BIGINT NOT NULL,
                outcome VARCHAR(32) NOT NULL,
                payout BIGINT NOT NULL,
                created_at BIGINT NOT NULL
            )
        """))


class DicePlay(BaseModel):
    stake: int = Field(gt=0, le=100000000)
    chance: int = Field(ge=5, le=95)


class SlotsPlay(BaseModel):
    stake: int = Field(gt=0, le=100000000)


class MinesPlay(BaseModel):
    stake: int = Field(gt=0, le=100000000)
    mines: int = Field(ge=1, le=24)
    picks: int = Field(ge=1, le=24)


def settle(user_id: int, game: str, stake: int, won: bool,
           multiplier_x100: int, outcome: str):
    prepare()
    now = int(time.time())
    round_id = str(uuid.uuid4())
    payout = stake * multiplier_x100 // 100 if won else 0
    with engine.begin() as conn:
        debit = conn.execute(text("""
            UPDATE tnc_game_wallets SET balance=balance-:stake
            WHERE user_id=:uid AND balance>=:stake
        """), {"uid": user_id, "stake": stake})
        if debit.rowcount != 1:
            raise HTTPException(status_code=400, detail="Недостаточно GT")
        conn.execute(text("""
            INSERT INTO tnc_game_transactions
            (operation_id,user_id,amount,kind,description,reference,created_at)
            VALUES (:op,:uid,:amount,:kind,:description,:ref,:created)
        """), {"op": str(uuid.uuid4()), "uid": user_id, "amount": -stake,
                "kind": game + "_bet", "description": "Ставка " + game.title(),
                "ref": round_id + ":bet", "created": now})
        if payout:
            conn.execute(text("""
                UPDATE tnc_game_wallets SET balance=balance+:payout
                WHERE user_id=:uid
            """), {"uid": user_id, "payout": payout})
            conn.execute(text("""
                INSERT INTO tnc_game_transactions
                (operation_id,user_id,amount,kind,description,reference,created_at)
                VALUES (:op,:uid,:amount,:kind,:description,:ref,:created)
            """), {"op": str(uuid.uuid4()), "uid": user_id, "amount": payout,
                    "kind": game + "_win", "description": "Выигрыш " + game.title(),
                    "ref": round_id + ":win", "created": now})
        conn.execute(text("""
            INSERT INTO tnc_extra_game_rounds
            (id,user_id,game,stake,outcome,payout,created_at)
            VALUES (:id,:uid,:game,:stake,:outcome,:payout,:created)
        """), {"id": round_id, "uid": user_id, "game": game, "stake": stake,
                "outcome": outcome, "payout": payout, "created": now})
        row = conn.execute(text("SELECT balance FROM tnc_game_wallets WHERE user_id=:uid"),
                           {"uid": user_id}).first()
    return {"round_id": round_id, "game": game, "won": won, "stake": stake,
            "payout": payout, "net": payout-stake, "balance": int(row[0]),
            "outcome": outcome}


def allowed(uid):
    if is_game_banned(uid):
        raise HTTPException(status_code=403, detail="Доступ к играм заблокирован")


@router.post("/dice/play")
def dice_play(data: DicePlay, uid: int = Depends(player)):
    allowed(uid)
    roll = secrets.randbelow(100) + 1
    won = roll <= data.chance
    # 1% house edge; gross return includes the original stake.
    multiplier = max(100, (9900 // data.chance))
    result = settle(uid, "dice", data.stake, won, multiplier, f"roll={roll}; chance={data.chance}")
    result["roll"] = roll
    result["chance"] = data.chance
    return result


@router.post("/slots/play")
def slots_play(data: SlotsPlay, uid: int = Depends(player)):
    allowed(uid)
    symbols = ["A", "B", "C", "D", "7"]
    reels = [secrets.choice(symbols) for _ in range(3)]
    if reels[0] == reels[1] == reels[2] == "7":
        multiplier = 2_000
    elif reels[0] == reels[1] == reels[2]:
        multiplier = 400
    elif len(set(reels)) == 2:
        multiplier = 140
    else:
        multiplier = 0
    result = settle(uid, "slots", data.stake, multiplier > 0, multiplier,
                    "symbols=" + ",".join(reels))
    result["symbols"] = reels
    return result


@router.post("/mines/play")
def mines_play(data: MinesPlay, uid: int = Depends(player)):
    allowed(uid)
    if data.mines + data.picks > 25:
        raise HTTPException(status_code=400, detail="Слишком много мин для выбранного числа клеток")
    safe_total = 25 - data.mines
    # One-shot pick mode: selected number of cells must all be safe.
    probability_num = 1
    probability_den = 1
    for i in range(data.picks):
        probability_num *= safe_total - i
        probability_den *= 25 - i
    if data.picks > safe_total:
        won = False
        multiplier = 0
    else:
        won = secrets.randbelow(probability_den) < probability_num
        multiplier = (probability_den * 98 // probability_num) if won else 0
    result = settle(uid, "mines", data.stake, won, multiplier,
                    f"mines={data.mines};picks={data.picks}")
    result["mines"] = data.mines
    result["picks"] = data.picks
    return result


@router.get("/extra-history")
def extra_games_history(uid: int = Depends(player)):
    allowed(uid)
    prepare()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id,game,stake,outcome,payout,created_at
            FROM tnc_extra_game_rounds WHERE user_id=:uid
            ORDER BY created_at DESC LIMIT 50
        """), {"uid": uid}).mappings().all()
    return {"items": [dict(row) for row in rows]}
