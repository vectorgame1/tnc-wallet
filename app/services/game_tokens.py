"""Persistent GT ledger. GT are closed-loop game points, not TNC Coin."""
import json, time
from sqlalchemy import text
from app.database.connection import engine
GT_PER_STAR=5000

def init_game_tables():
    # SQLite and PostgreSQL use different auto-increment primary-key syntax.
    auto_id = "INTEGER PRIMARY KEY AUTOINCREMENT" if engine.dialect.name == "sqlite" else "BIGSERIAL PRIMARY KEY"
    statements=[
    "CREATE TABLE IF NOT EXISTS tnc_game_wallets (user_id BIGINT PRIMARY KEY, balance BIGINT NOT NULL DEFAULT 0 CHECK(balance >= 0), updated_at BIGINT NOT NULL)",
    f"CREATE TABLE IF NOT EXISTS tnc_game_transactions (id {auto_id}, user_id BIGINT NOT NULL, amount BIGINT NOT NULL, kind VARCHAR(32) NOT NULL, description VARCHAR(255) NOT NULL DEFAULT '', reference VARCHAR(128) UNIQUE, created_at BIGINT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS tnc_game_stars_orders (payload VARCHAR(160) PRIMARY KEY, user_id BIGINT NOT NULL, stars BIGINT NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'pending', charge_id VARCHAR(255) UNIQUE, created_at BIGINT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS tnc_game_bans (user_id BIGINT PRIMARY KEY, banned BOOLEAN NOT NULL, reason VARCHAR(255) NOT NULL DEFAULT '', updated_by BIGINT NOT NULL, updated_at BIGINT NOT NULL)",
    f"CREATE TABLE IF NOT EXISTS tnc_game_admin_log (id {auto_id}, admin_id BIGINT NOT NULL, user_id BIGINT NOT NULL, action VARCHAR(32) NOT NULL, amount BIGINT NOT NULL DEFAULT 0, reason VARCHAR(255) NOT NULL DEFAULT '', created_at BIGINT NOT NULL)",
    ]
    with engine.begin() as c:
        for q in statements: c.execute(text(q))

def _ensure(c, uid):
    c.execute(text("INSERT INTO tnc_game_wallets(user_id,balance,updated_at) VALUES(:u,0,:t) ON CONFLICT(user_id) DO NOTHING"),{"u":int(uid),"t":int(time.time())})

def get_balance(user_id):
    with engine.begin() as c:
        _ensure(c,user_id)
        return int(c.execute(text("SELECT balance FROM tnc_game_wallets WHERE user_id=:u"),{"u":int(user_id)}).scalar_one())

def _change(c, uid, amount, kind, description='', reference=None):
    _ensure(c,uid)
    lock_suffix = " FOR UPDATE" if engine.dialect.name == "postgresql" else ""
    row=c.execute(text("SELECT balance FROM tnc_game_wallets WHERE user_id=:u"+lock_suffix),{"u":int(uid)}).first()
    new=int(row[0])+int(amount)
    if new<0: raise ValueError("Недостаточно GT.")
    c.execute(text("UPDATE tnc_game_wallets SET balance=:b,updated_at=:t WHERE user_id=:u"),{"b":new,"t":int(time.time()),"u":int(uid)})
    c.execute(text("INSERT INTO tnc_game_transactions(user_id,amount,kind,description,reference,created_at) VALUES(:u,:a,:k,:d,:r,:t)"),{"u":int(uid),"a":int(amount),"k":kind,"d":description[:255],"r":reference,"t":int(time.time())})
    return new

def admin_adjust_tokens(admin_id,user_id,amount,action,reason=''):
    amount=int(amount)
    if amount==0: raise ValueError("Сумма не может быть нулевой.")
    delta=abs(amount) if action in ('admin_add','admin_credit') else -abs(amount)
    with engine.begin() as c:
        new=_change(c,user_id,delta,action,reason)
        c.execute(text("INSERT INTO tnc_game_admin_log(admin_id,user_id,action,amount,reason,created_at) VALUES(:a,:u,:k,:n,:r,:t)"),{"a":int(admin_id),"u":int(user_id),"k":action,"n":delta,"r":reason[:255],"t":int(time.time())})
        return new

def set_game_ban(admin_id,user_id,banned,reason=''):
    with engine.begin() as c:
        c.execute(text("INSERT INTO tnc_game_bans(user_id,banned,reason,updated_by,updated_at) VALUES(:u,:b,:r,:a,:t) ON CONFLICT(user_id) DO UPDATE SET banned=:b,reason=:r,updated_by=:a,updated_at=:t"),{"u":int(user_id),"b":bool(banned),"r":reason[:255],"a":int(admin_id),"t":int(time.time())})
        c.execute(text("INSERT INTO tnc_game_admin_log(admin_id,user_id,action,amount,reason,created_at) VALUES(:a,:u,:k,0,:r,:t)"),{"a":int(admin_id),"u":int(user_id),"k":"game_ban" if banned else "game_unban","r":reason[:255],"t":int(time.time())})

def is_game_banned(user_id):
    with engine.begin() as c:
        row=c.execute(text("SELECT banned FROM tnc_game_bans WHERE user_id=:u"),{"u":int(user_id)}).first()
        return bool(row[0]) if row else False

def get_admin_log(limit=30):
    with engine.begin() as c:
        rows=c.execute(text("SELECT admin_id,user_id,action,amount,reason,created_at FROM tnc_game_admin_log ORDER BY id DESC LIMIT :n"),{"n":max(1,min(int(limit),100))}).mappings().all()
        return [dict(r) for r in rows]

def create_stars_order(user_id,stars,payload):
    stars=int(stars)
    if not 1<=stars<=10000: raise ValueError("Недопустимое число Stars.")
    with engine.begin() as c:
        c.execute(text("INSERT INTO tnc_game_stars_orders(payload,user_id,stars,status,created_at) VALUES(:p,:u,:s,'pending',:t)"),{"p":payload,"u":int(user_id),"s":stars,"t":int(time.time())})

def validate_stars_payload(payload,user_id,stars):
    with engine.begin() as c:
        row=c.execute(text("SELECT user_id,stars,status FROM tnc_game_stars_orders WHERE payload=:p"),{"p":payload}).first()
        if not row or int(row[0])!=int(user_id) or int(row[1])!=int(stars) or row[2]!='pending': raise ValueError("Invalid Stars order")

def complete_stars_payment(payload,user_id,stars,charge_id):
    with engine.begin() as c:
        lock_suffix = " FOR UPDATE" if engine.dialect.name == "postgresql" else ""
        row=c.execute(text("SELECT user_id,stars,status FROM tnc_game_stars_orders WHERE payload=:p"+lock_suffix),{"p":payload}).first()
        if not row or int(row[0])!=int(user_id) or int(row[1])!=int(stars): raise ValueError("Заказ не найден или не совпадает.")
        if row[2]=='paid': return 0
        if row[2]!='pending': raise ValueError("Заказ уже закрыт.")
        amount=int(stars)*GT_PER_STAR
        _change(c,user_id,amount,'stars_purchase',f'{stars} Telegram Stars',reference=charge_id)
        c.execute(text("UPDATE tnc_game_stars_orders SET status='paid',charge_id=:c WHERE payload=:p"),{"c":charge_id,"p":payload})
        return amount
