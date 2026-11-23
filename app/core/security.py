import hashlib,hmac,json,time
from urllib.parse import parse_qsl
from fastapi import HTTPException
from app.core.config import settings
def verify(init_data):
    if not settings.BOT_TOKEN or not init_data: raise HTTPException(401,"Нет Telegram initData.")
    try:
        pairs=parse_qsl(init_data,keep_blank_values=True,strict_parsing=True)
        if len(dict(pairs))!=len(pairs): raise ValueError()
        data=dict(pairs); got=data.pop("hash")
        date=int(data["auth_date"]); now=int(time.time())
        if date<=0 or now-date>settings.AUTH_MAX_AGE or date>now+60: raise ValueError()
        check="\n".join(f"{k}={v}" for k,v in sorted(data.items()))
        secret=hmac.new(b"WebAppData",settings.BOT_TOKEN.encode(),hashlib.sha256).digest()
        want=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(want,got): raise ValueError()
        user=json.loads(data["user"])
        if not user.get("id"): raise ValueError()
        return user
    except Exception: raise HTTPException(401,"Telegram-авторизация не прошла.")
