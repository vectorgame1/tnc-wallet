# TNC Ecosystem — runnable starter release

## Что уже работает
- Telegram-бот с главным меню: TNC Wallet, Account, история, Crypto, Games, Community, настройки.
- Общий Telegram Account и SQLite-база.
- Внутренний баланс TNC Coin с точностью 6 знаков.
- Перевод TNC между зарегистрированными пользователями через Mini App API.
- История операций.
- Telegram Mini App с тёмным интерфейсом.
- Проверка подписи Telegram initData на API.

## Установка на Windows / PowerShell
1. Распакуй архив в папку проекта (сохрани свои `.env` и `tnc.db`, если они уже есть).
2. В терминале VS Code выполни:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. Скопируй `.env.example` в `.env` и впиши токен бота. Не отправляй токен никому.
4. Запусти API:
   ```powershell
   python -m uvicorn app.api:app --reload --host 127.0.0.1 --port 8000
   ```
5. Во втором терминале запусти бота:
   ```powershell
   python bot.py
   ```
6. Проверь `http://127.0.0.1:8000/health` и `http://127.0.0.1:8000/docs`.

## Для Mini App
Telegram требует HTTPS URL. Размести API и webapp на HTTPS-хостинге, затем укажи публичный URL Mini App в `WEBAPP_URL` (например `https://домен/app/`) и настрой его в BotFather. Локальный `127.0.0.1` не является публичным Mini App URL.

## Важно
TNC Coin здесь — внутренняя запись в базе, а не блокчейн-криптовалюта. TNC Crypto и TNC Games пока представлены разделами интерфейса, а не полноценными блокчейн/игровыми сервисами. Перед реальным запуском с ценностью средств нужны тестирование, аудит безопасности, резервное копирование, лимиты, антифрод и юридическая проверка. Старую базу перед заменой кода обязательно скопируй в резервную копию.
