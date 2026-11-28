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

## TNC Games (ветка tnc-rebuild)
- Отдельный баланс GT и отдельная история операций; TNC Coin и GT не смешиваются.
- Пополнение GT через Telegram Stars: 1 Star = 5 000 GT; начисление выполняется только после подтверждённого Telegram successful_payment, повторное начисление защищено.
- Серверные раунды Crash, Dice, Slots и Mines; ставка, результат, списание и выплата обрабатываются на сервере в одной транзакции БД.
- История игровых операций и раундов, прогресс достижений и недельная таблица лидеров.
- Административные команды бота: /gt_add, /gt_take, /gt_balance, /gameban, /gameunban, /gt_admin_log.
- GT — закрытые игровые баллы: без перевода в TNC, вывода или денежного призового фонда. Mines реализован как одноразовая проверка выбранного количества клеток, не как пошаговая интерактивная доска.

## Важно
TNC Coin здесь — внутренняя запись в базе, а не блокчейн-криптовалюта. Рыночные котировки BTC/ETH и учебный трейдинг не являются котировками TNC и не используют реальный брокерский счёт. Перед включением игровых функций на публичном сервисе необходимы тестирование, аудит безопасности, резервное копирование, лимиты, антифрод и юридическая проверка применимых правил. Изменения в ветке tnc-rebuild ещё не означают обновление production/Render. Не удаляй и не пересоздавай рабочую базу данных.

## Render / production notes
- The FastAPI lifespan starts Telegram long polling automatically when `BOT_TOKEN` is set. Run this service as a single instance with one worker; do not start a second bot polling process against the same token.
- Do not enable multiple Render instances or multiple Uvicorn workers until bot polling is separated into its own service and the API-side polling startup is disabled.
- Configure `BOT_TOKEN`, `DATABASE_URL` (managed PostgreSQL), `WEBAPP_URL`, and `ADMIN_IDS` in the Render environment. Keep secrets only in Render environment settings, never in Git.
- Keep the existing PostgreSQL database. Deployments must use additive migrations only; take a database backup before production changes.
- Check `/health`, Telegram bot polling logs, Mini App authorization, wallet transfers, and Stars payment confirmation after deployment. CI passing does not replace a live Telegram/Render smoke test.
