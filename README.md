# TNC Ecosystem — deployment package

This rebuild consolidates the supplied project into one FastAPI service, Telegram bot, shared SQL database, TNC wallet ledger and persistent GT ledger. Russian source files are UTF-8.

## Included
- Telegram bot: /start, /menu, /help, wallet, transfer flow, transaction history, profile.
- Admin: /credit, /debit, /gt_add, /gt_take, /gt_balance, /gameban, /gameunban, /gt_admin_log.
- Telegram Stars GT purchase: /buygt N. 1 Star = 5,000 GT; GT cannot be converted to TNC Coin. Fulfilment is tied to successful_payment and charge ID.
- Mini App backend: Telegram initData verification, profile, wallet history, TNC transfers, GT wallet/history.
- PostgreSQL-compatible schema; existing TNC tables are not dropped. GT tables are created additively.
- PWA service worker corrected so waitUntil is called synchronously inside install/activate handlers.

## Environment
Copy `.env.example` to `.env` for local use, then set BOT_TOKEN, WEBAPP_URL, DATABASE_URL and ADMIN_IDS. Never commit `.env`. In Render, set the same variables in the service environment. Use a PostgreSQL URL with the `postgresql+psycopg://` scheme.

## Run
```powershell
pip install -r requirements.txt
python -m uvicorn app.api:app --host 0.0.0.0 --port 8000
```
Run the bot as a separate process/service with: `python bot.py`. Do not run multiple polling bot instances with the same token.

Render start command for a combined single process is not recommended for production. Prefer one web service for `uvicorn app.api:app --host 0.0.0.0 --port $PORT` and one worker/service for `python bot.py`, sharing the same DATABASE_URL. If using one Render service only, use a process supervisor; do not start two polling instances.

## Important limits
This is a strengthened working foundation, not a claim of audited enterprise production readiness. The supplied archive did not contain the full games UI, crash round engine, tournaments, task/reward management, admin dashboard, payment refund workflow, migrations, automated test suite or production monitoring. Those are not silently represented as completed. The existing `webapp/index.html` is retained. TNC Coin is an internal ledger balance, not an on-chain token. GT are non-convertible in-app game points.

Before production: add Alembic migrations, automated integration tests, rate limits, structured audit/alerting, payment reconciliation/refunds, privacy/terms and legal review for game mechanics.
