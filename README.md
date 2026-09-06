# Работа в Питере — Mini App

Современный каталог тарифов/пакетов с отдельной корзиной, заявками и уведомлениями в Telegram.

## Railway

Start Command:
`uvicorn main:app --host 0.0.0.0 --port $PORT`

Переменные окружения:
- `BOT_TOKEN` — токен бота из BotFather (не публиковать в GitHub)
- `ADMIN_SETUP_CODE` — придумайте секретный код, например `SPB-ADMIN-2026-4817`
- `TELEGRAM_WEBHOOK_SECRET` — отдельный секрет для webhook, например `webhook-spb-2026-9x7`
- `PUBLIC_URL` — публичный адрес Railway, например `https://work-spb-bot-production.up.railway.app`

После деплоя:
1. Откройте своего бота и отправьте `/setadmin ВАШ_ADMIN_SETUP_CODE`.
2. Бот ответит, что чат назначен администратором.
3. После этого новые заявки из корзины будут приходить в этот чат.

Оплата в этой версии пока отключена. Заявки сохраняются в SQLite.
