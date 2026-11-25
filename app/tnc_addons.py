"""TNC Mini App add-ons: generative assistant + isolated paper trading."""
from __future__ import annotations
import hashlib, hmac, json, os, sqlite3, time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from urllib.parse import parse_qsl
import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
PAPER_DB = os.getenv("TNC_PAPER_DB", "./tnc_paper_trading.sqlite3")

ASSETS = {
    "bitcoin": ("BTC", "Bitcoin"), "ethereum": ("ETH", "Ethereum"),
    "solana": ("SOL", "Solana"), "binancecoin": ("BNB", "BNB"),
    "ripple": ("XRP", "XRP"), "dogecoin": ("DOGE", "Dogecoin"),
}

def telegram_user(init_data: str) -> dict:
    if not BOT_TOKEN:
        raise HTTPException(503, "BOT_TOKEN не настроен на сервере")
    if not init_data or len(init_data) > 8192:
        raise HTTPException(401, "Отсутствуют данные Telegram Mini App")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise HTTPException(401, "Некорректные данные Telegram")
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise HTTPException(401, "Проверка подписи Telegram не пройдена")
    try:
        auth_date = int(pairs.get("auth_date", "0"))
        if auth_date > int(time.time()) + 60 or int(time.time()) - auth_date > 86400:
            raise HTTPException(401, "Срок действия Telegram-сессии истёк")
        user = json.loads(pairs.get("user", "{}"))
        user_id = int(user["id"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise HTTPException(401, "Не удалось прочитать пользователя Telegram")
    return {"id": user_id, "user": user}

def db_conn():
    conn = sqlite3.connect(PAPER_DB, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS paper_accounts(user_id INTEGER PRIMARY KEY, cash_usd TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS paper_positions(user_id INTEGER NOT NULL, asset TEXT NOT NULL, quantity TEXT NOT NULL, avg_price TEXT NOT NULL, PRIMARY KEY(user_id,asset));
      CREATE TABLE IF NOT EXISTS paper_orders(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, asset TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL, quantity TEXT NOT NULL, price TEXT NOT NULL, total_usd TEXT NOT NULL, created_at TEXT NOT NULL);
    """)
    return conn

def ensure_account(conn, user_id: int):
    conn.execute("INSERT OR IGNORE INTO paper_accounts(user_id,cash_usd) VALUES(?,?)", (user_id, "100000.00"))
    conn.commit()

async def market_price(asset: str) -> tuple[Decimal, Decimal]:
    if asset not in ASSETS:
        raise HTTPException(400, "Актив не поддерживается")
    url = "https://api.coingecko.com/api/v3/simple/price"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params={"ids": asset, "vs_currencies": "usd", "include_24hr_change": "true"})
            response.raise_for_status()
            item = response.json()[asset]
            return Decimal(str(item["usd"])), Decimal(str(item.get("usd_24h_change") or 0))
    except Exception:
        raise HTTPException(503, "Не удалось получить актуальную котировку. Повторите позже.")

class AssistantRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[dict] = Field(default_factory=list, max_length=12)

class PaperOrder(BaseModel):
    asset: str
    side: str
    quantity: Decimal = Field(gt=0, max_digits=24, decimal_places=8)

def create_tnc_addons_router() -> APIRouter:
    router = APIRouter()

    @router.post("/api/assistant/chat")
    async def assistant_chat(body: AssistantRequest, x_telegram_init_data: str = Header(default="")):
        telegram_user(x_telegram_init_data)
        if not OPENAI_API_KEY:
            raise HTTPException(503, "ИИ не подключён: добавьте OPENAI_API_KEY в переменные окружения Render")
        message = body.message.strip()
        if not message:
            raise HTTPException(400, "Пустое сообщение")
        system = (
            "Ты TNC Assistant — универсальный русскоязычный помощник. Отвечай на любые допустимые темы: "
            "обучение, программирование, технологии, тексты, анализ и криптовалюты. Пиши ясно, уточняй "
            "нехватку данных, не выдумывай состояние аккаунта или котировки. TNC Coin в этой системе — "
            "внутренний баланс, если пользователь не предоставил доказательства обратного. Не проси пароли, "
            "seed-фразы, приватные ключи и коды. Не утверждай, что совершил платежи или сделки. Для финансовых, "
            "медицинских и юридических вопросов обозначай ограничения и риски."
        )
        safe_history=[]
        for item in body.history[-12:]:
            role=item.get("role") if isinstance(item,dict) else None
            content=item.get("content") if isinstance(item,dict) else None
            if role in ("user","assistant") and isinstance(content,str) and content.strip():
                safe_history.append({"role":role,"content":content[:4000]})
        payload = {"model": OPENAI_MODEL, "messages": [{"role": "system", "content": system}, *safe_history, {"role": "user", "content": message}], "temperature": 0.6, "max_tokens": 1200}
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                r = await client.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {OPENAI_API_KEY}"}, json=payload)
                if r.status_code >= 400:
                    detail = "Провайдер ИИ временно недоступен"
                    try: detail = r.json().get("error", {}).get("message", detail)[:300]
                    except Exception: pass
                    raise HTTPException(502, detail)
                data = r.json()
                reply = data["choices"][0]["message"]["content"].strip()
                return {"reply": reply, "model": OPENAI_MODEL}
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(502, "Не удалось связаться с провайдером ИИ")

    @router.get("/api/paper-trading/quote")
    async def paper_quote(asset: str, x_telegram_init_data: str = Header(default="")):
        telegram_user(x_telegram_init_data)
        price, change = await market_price(asset)
        symbol, name = ASSETS[asset]
        return {"asset": asset, "symbol": symbol, "name": name, "price": str(price), "change_24h": str(change), "source": "CoinGecko"}

    @router.get("/api/paper-trading/account")
    async def paper_account(x_telegram_init_data: str = Header(default="")):
        user = telegram_user(x_telegram_init_data)
        conn = db_conn()
        try:
            ensure_account(conn, user["id"])
            cash = Decimal(conn.execute("SELECT cash_usd FROM paper_accounts WHERE user_id=?", (user["id"],)).fetchone()[0])
            rows = conn.execute("SELECT asset,quantity,avg_price FROM paper_positions WHERE user_id=?", (user["id"],)).fetchall()
            positions=[]; total=cash
            for row in rows:
                qty=Decimal(row["quantity"]); avg=Decimal(row["avg_price"])
                price,_=await market_price(row["asset"])
                value=qty*price; total+=value
                positions.append({"asset":row["asset"],"symbol":ASSETS[row["asset"]][0],"quantity":str(qty),"average_price":str(avg),"market_price":str(price),"market_value":str(value)})
            return {"cash_usd":str(cash),"equity_usd":str(total),"positions":positions,"mode":"paper"}
        finally: conn.close()

    @router.post("/api/paper-trading/order")
    async def paper_order(body: PaperOrder, x_telegram_init_data: str = Header(default="")):
        user=telegram_user(x_telegram_init_data)
        if body.asset not in ASSETS or body.side not in ("buy","sell"):
            raise HTTPException(400,"Некорректный актив или сторона ордера")
        if body.quantity <= 0 or body.quantity > Decimal("100000000"):
            raise HTTPException(400,"Некорректное количество")
        price,_=await market_price(body.asset)
        qty=body.quantity.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
        total=(qty*price).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        conn=db_conn()
        try:
            ensure_account(conn,user["id"])
            conn.execute("BEGIN IMMEDIATE")
            cash=Decimal(conn.execute("SELECT cash_usd FROM paper_accounts WHERE user_id=?",(user["id"],)).fetchone()[0])
            row=conn.execute("SELECT quantity,avg_price FROM paper_positions WHERE user_id=? AND asset=?",(user["id"],body.asset)).fetchone()
            old_qty=Decimal(row["quantity"]) if row else Decimal("0")
            old_avg=Decimal(row["avg_price"]) if row else Decimal("0")
            if body.side=="buy":
                if total>cash: raise HTTPException(400,"Недостаточно виртуального USD-баланса")
                new_qty=old_qty+qty
                new_avg=((old_qty*old_avg)+(qty*price))/new_qty
                cash-=total
            else:
                if qty>old_qty: raise HTTPException(400,"Недостаточно актива в виртуальной позиции")
                new_qty=old_qty-qty; cash+=total; new_avg=old_avg
            conn.execute("UPDATE paper_accounts SET cash_usd=? WHERE user_id=?",(str(cash),user["id"]))
            if new_qty==0: conn.execute("DELETE FROM paper_positions WHERE user_id=? AND asset=?",(user["id"],body.asset))
            else: conn.execute("INSERT INTO paper_positions(user_id,asset,quantity,avg_price) VALUES(?,?,?,?) ON CONFLICT(user_id,asset) DO UPDATE SET quantity=excluded.quantity,avg_price=excluded.avg_price",(user["id"],body.asset,str(new_qty),str(new_avg)))
            conn.execute("INSERT INTO paper_orders(user_id,asset,symbol,side,quantity,price,total_usd,created_at) VALUES(?,?,?,?,?,?,?,?)",(user["id"],body.asset,ASSETS[body.asset][0],body.side,str(qty),str(price),str(total),datetime.now(timezone.utc).isoformat()))
            conn.commit()
            return {"status":"filled","mode":"paper","asset":body.asset,"symbol":ASSETS[body.asset][0],"side":body.side,"quantity":str(qty),"price":str(price),"total_usd":str(total),"cash_usd":str(cash)}
        except HTTPException:
            conn.rollback(); raise
        except Exception:
            conn.rollback(); raise HTTPException(500,"Не удалось записать учебный ордер")
        finally: conn.close()

    @router.get("/api/paper-trading/orders")
    async def paper_orders(x_telegram_init_data: str = Header(default="")):
        user=telegram_user(x_telegram_init_data); conn=db_conn()
        try:
            ensure_account(conn,user["id"])
            rows=conn.execute("SELECT asset,symbol,side,quantity,price,total_usd,created_at FROM paper_orders WHERE user_id=? ORDER BY id DESC LIMIT 50",(user["id"],)).fetchall()
            return {"orders":[dict(r) for r in rows]}
        finally: conn.close()
    return router