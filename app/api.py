import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from aiogram import Bot
from fastapi import FastAPI,Depends,Header,HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from app.core.config import settings
from app.database.connection import init_database,get_db
from app.core.security import verify
from app.services.accounts import get_or_create_user
from app.services.wallet import balance,fmt,history,send
@asynccontextmanager
async def lifespan(app):
    init_database()
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
app=FastAPI(title="TNC Ecosystem",version="1.0.0",lifespan=lifespan)
def auth(raw,db):
    try:
        u=get_or_create_user(db,verify(raw)); db.commit(); return u
    except ValueError as e: db.rollback(); raise HTTPException(403,str(e))
class Transfer(BaseModel):
    receiver_id:int
    amount:str=Field(min_length=1,max_length=40)
@app.get("/")
def root(): return {"service":"TNC Ecosystem","status":"online"}
@app.get("/health")
def health(): return {"status":"ok"}
@app.get("/api/profile")
def profile(raw:str=Header(alias="X-Telegram-Init-Data"),db:Session=Depends(get_db)):
    u=auth(raw,db)
    return {"telegram_id":u.telegram_id,"username":u.username,"first_name":u.first_name,"balance":fmt(balance(db,u.telegram_id)),"currency":"TNC"}
@app.get("/api/wallet/history")
def tx_history(raw:str=Header(alias="X-Telegram-Init-Data"),db:Session=Depends(get_db)):
    u=auth(raw,db)
    return {"transactions":[{"id":t.operation_id,"sender_id":t.sender_id,"receiver_id":t.receiver_id,"amount":fmt(t.amount_units),"kind":t.kind,"created_at":t.created_at} for t in history(db,u.telegram_id)]}
@app.post("/api/wallet/transfer")
def transfer(body:Transfer,raw:str=Header(alias="X-Telegram-Init-Data"),db:Session=Depends(get_db)):
    u=auth(raw,db)
    try:
        t=send(db,u.telegram_id,body.receiver_id,body.amount)
        return {"status":"success","operation_id":t.operation_id,"amount":fmt(t.amount_units),"currency":"TNC"}
    except ValueError as e: raise HTTPException(400,str(e))
web=Path(__file__).resolve().parents[1]/"webapp"
app.mount("/app",StaticFiles(directory=str(web),html=True),name="webapp")
