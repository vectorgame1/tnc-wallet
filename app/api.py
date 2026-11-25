from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI,Depends,Header,HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from app.database.connection import init_database,get_db
from app.core.security import verify
from app.services.accounts import get_or_create_user
from app.services.wallet import balance,fmt,history,send
@asynccontextmanager
async def lifespan(app):
    init_database()
    from app.services.game_tokens import init_game_tables
    init_game_tables()
    yield
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

class StarsOrder(BaseModel):
    stars:int=Field(ge=1,le=10000)

@app.get("/api/games/wallet")
def games_wallet(raw:str=Header(alias="X-Telegram-Init-Data"),db:Session=Depends(get_db)):
    u=auth(raw, db)
    from app.services.game_tokens import get_balance,is_game_banned
    return {"balance":get_balance(u.telegram_id),"currency":"GT","banned":is_game_banned(u.telegram_id),"gt_per_star":5000}

@app.get("/api/games/history")
def games_history(raw:str=Header(alias="X-Telegram-Init-Data"),db:Session=Depends(get_db)):
    u=auth(raw, db)
    from sqlalchemy import text
    from app.database.connection import engine
    with engine.begin() as c:
        rows=c.execute(text("SELECT amount,kind,description,created_at FROM tnc_game_transactions WHERE user_id=:u ORDER BY id DESC LIMIT 30"),{"u":u.telegram_id}).mappings().all()
    return {"transactions":[dict(r) for r in rows]}

web=Path(__file__).resolve().parents[1]/"webapp"
app.mount("/app",StaticFiles(directory=str(web),html=True),name="webapp")
