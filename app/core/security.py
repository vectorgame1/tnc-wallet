import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import HTTPException
from app.core.config import settings

def verify(init_data: str) -> dict:
    if not settings.BOT_TOKEN:
        raise HTTPException(500, "BOT_TOKEN не настроен на сервере.")
    if not init_data:
        raise HTTPException(401, "Нет Telegram initData.")

    try:
        # Безопасный парсинг (не падает на пустых значениях)
        pairs = parse_qsl(init_data, keep_blank_values=True)
        data = dict(pairs)
        
        if "hash" not in data:
            raise ValueError("В initData нет поля hash")
            
        got_hash = data.pop("hash")

        # Проверка времени (по умолчанию 1 день = 86400 сек, если не задано в конфиге)
        auth_date = int(data.get("auth_date", 0))
        now = int(time.time())
        max_age = getattr(settings, "AUTH_MAX_AGE", 86400) 
        
        if auth_date <= 0 or (now - auth_date) > max_age:
            raise ValueError("initData просрочен (auth_date).")
        if auth_date > now + 60:
            raise ValueError("initData из будущего (auth_date).")

        # Формирование строки для проверки
        check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        
        # Вычисление секретного ключа
        secret_key = hmac.new(
            b"WebAppData", 
            settings.BOT_TOKEN.encode(), 
            hashlib.sha256
        ).digest()
        
        # Вычисление хэша
        want_hash = hmac.new(
            secret_key, 
            check_string.encode(), 
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(want_hash, got_hash):
            raise ValueError("Хэш не совпал (неверный BOT_TOKEN или данные изменены).")

        # Извлечение пользователя
        user_data = data.get("user")
        if not user_data:
            raise ValueError("В initData нет объекта user")
            
        user = json.loads(user_data)
        if not user.get("id"):
            raise ValueError("В объекте user нет ID")

        return user

    except Exception as e:
        # Логируем реальную причину в консоль Render, чтобы видеть её
        import logging
        logging.getLogger("tnc.security").warning(f"Ошибка авторизации Telegram: {e}")
        raise HTTPException(401, "Telegram-авторизация не прошла.")