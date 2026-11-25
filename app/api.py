from app.routers.games import router as games_router
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import Bot
from aiogram.types import LabeledPrice
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.connection import init_database, get_db
from app.core.security import verify
from app.services.accounts import get_or_create_user
from app.services.wallet import balance, fmt, history, send
from app.services.game_tokens import (
    init_game_tables,
    get_balance as get_gt_balance,
    get_history as get_gt_history,
    create_stars_order as create_gt_order,
    GT_PER_STAR,
)


@asynccontextmanager
async def lifespan(app):
    init_database()
    init_game_tables()

    bot = None
    polling_task = None
    dispatcher = None

    if settings.BOT_TOKEN:
        from bot import dp as dispatcher

        bot = Bot(token=settings.BOT_TOKEN)
        polling_task = asyncio.create_task(
            dispatcher.start_polling(
                bot,
                handle_signals=False,
                close_bot_session=False,
            )
        )
        logging.getLogger("tnc.api").info("Telegram bot polling started")
    else:
        logging.getLogger("tnc.api").warning("BOT_TOKEN is empty")

    try:
        yield
    finally:
        if dispatcher is not None and polling_task is not None:
            try:
                await dispatcher.stop_polling()
                await polling_task
            except Exception:
                polling_task.cancel()
                try:
                    await polling_task
                except asyncio.CancelledError:
                    pass

        if bot is not None:
            await bot.session.close()


app = FastAPI(
    title="TNC Ecosystem",
    version="1.1.0",
    lifespan=lifespan,
)

app.include_router(games_router)

def auth(raw, db):
    try:
        user = get_or_create_user(db, verify(raw))
        db.commit()
        return user
    except ValueError as error:
        db.rollback()
        raise HTTPException(403, str(error))


class Transfer(BaseModel):
    receiver_id: int
    amount: str = Field(min_length=1, max_length=40)


class ShopInvoice(BaseModel):
    amount: str = Field(min_length=1, max_length=30)


class GameStarsInvoice(BaseModel):
    stars: int = Field(ge=1)


@app.get("/")
def root():
    return {"service": "TNC Ecosystem", "status": "online"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/profile")
def profile(
    raw: str = Header(alias="X-Telegram-Init-Data"),
    db: Session = Depends(get_db),
):
    user = auth(raw, db)
    return {
        "telegram_id": user.telegram_id,
        "username": user.username,
        "first_name": user.first_name,
        "balance": fmt(balance(db, user.telegram_id)),
        "currency": "TNC",
        "game_tokens": get_gt_balance(user.telegram_id),
        "game_currency": "GT",
    }


@app.get("/api/wallet/history")
def tx_history(
    raw: str = Header(alias="X-Telegram-Init-Data"),
    db: Session = Depends(get_db),
):
    user = auth(raw, db)
    return {
        "transactions": [
            {
                "id": tx.operation_id,
                "sender_id": tx.sender_id,
                "receiver_id": tx.receiver_id,
                "amount": fmt(tx.amount_units),
                "kind": tx.kind,
                "created_at": tx.created_at,
            }
            for tx in history(db, user.telegram_id)
        ]
    }


@app.post("/api/wallet/transfer")
def transfer(
    body: Transfer,
    raw: str = Header(alias="X-Telegram-Init-Data"),
    db: Session = Depends(get_db),
):
    user = auth(raw, db)
    try:
        tx = send(db, user.telegram_id, body.receiver_id, body.amount)
        return {
            "status": "success",
            "operation_id": tx.operation_id,
            "amount": fmt(tx.amount_units),
            "currency": "TNC",
        }
    except ValueError as error:
        raise HTTPException(400, str(error))


@app.post("/api/shop/invoice")
async def shop_invoice(
    body: ShopInvoice,
    raw: str = Header(alias="X-Telegram-Init-Data"),
    db: Session = Depends(get_db),
):
    user = auth(raw, db)

    if not settings.BOT_TOKEN:
        raise HTTPException(503, "РћРїР»Р°С‚Р° РІСЂРµРјРµРЅРЅРѕ РЅРµРґРѕСЃС‚СѓРїРЅР°.")

    from app.services.stars import create_custom_order

    try:
        payload, stars = create_custom_order(
            user.telegram_id,
            body.amount,
        )
    except ValueError as error:
        raise HTTPException(400, str(error))

    bot = Bot(token=settings.BOT_TOKEN)
    try:
        invoice_url = await bot.create_invoice_link(
            title="TNC Coin",
            description=f"РџРѕРїРѕР»РЅРµРЅРёРµ Р±Р°Р»Р°РЅСЃР° РЅР° {body.amount} TNC.",
            payload=payload,
            currency="XTR",
            prices=[
                LabeledPrice(
                    label=f"{body.amount} TNC",
                    amount=stars,
                )
            ],
        )
    except Exception:
        logging.getLogger("tnc.api").exception(
            "TNC Stars invoice creation failed"
        )
        raise HTTPException(
            502,
            "РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕР·РґР°С‚СЊ СЃС‡С‘С‚ Telegram Stars.",
        )
    finally:
        await bot.session.close()

    return {
        "invoice_url": invoice_url,
        "amount": body.amount,
        "stars": stars,
        "currency": "XTR",
    }


@app.get("/api/games/wallet")
def games_wallet(
    raw: str = Header(alias="X-Telegram-Init-Data"),
    db: Session = Depends(get_db),
):
    user = auth(raw, db)
    return {
        "balance": get_gt_balance(user.telegram_id),
        "currency": "GT",
        "stars_rate": GT_PER_STAR,
    }


@app.get("/api/games/history")
def games_history(
    raw: str = Header(alias="X-Telegram-Init-Data"),
    db: Session = Depends(get_db),
):
    user = auth(raw, db)
    return {
        "transactions": get_gt_history(user.telegram_id),
    }


@app.post("/api/games/stars/invoice")
async def games_stars_invoice(
    body: GameStarsInvoice,
    raw: str = Header(alias="X-Telegram-Init-Data"),
    db: Session = Depends(get_db),
):
    user = auth(raw, db)

    if not settings.BOT_TOKEN:
        raise HTTPException(503, "РћРїР»Р°С‚Р° РІСЂРµРјРµРЅРЅРѕ РЅРµРґРѕСЃС‚СѓРїРЅР°.")

    try:
        payload, tokens = create_gt_order(
            user.telegram_id,
            body.stars,
        )
    except ValueError as error:
        raise HTTPException(400, str(error))

    bot = Bot(token=settings.BOT_TOKEN)
    try:
        invoice_url = await bot.create_invoice_link(
            title="TNC Game Tokens",
            description=f"РџРѕРєСѓРїРєР° {tokens:,} GT Р·Р° {body.stars} Stars.",
            payload=payload,
            currency="XTR",
            prices=[
                LabeledPrice(
                    label=f"{tokens:,} Game Tokens",
                    amount=body.stars,
                )
            ],
        )
    except Exception:
        logging.getLogger("tnc.api").exception(
            "GT Stars invoice creation failed"
        )
        raise HTTPException(
            502,
            "РќРµ СѓРґР°Р»РѕСЃСЊ СЃРѕР·РґР°С‚СЊ СЃС‡С‘С‚ Telegram Stars.",
        )
    finally:
        await bot.session.close()

    return {
        "invoice_url": invoice_url,
        "stars": body.stars,
        "tokens": tokens,
        "currency": "XTR",
        "rate": GT_PER_STAR,
    }


web = Path(__file__).resolve().parents[1] / "webapp"
app.mount(
    "/app",
    StaticFiles(directory=str(web), html=True),
    name="webapp",
)
