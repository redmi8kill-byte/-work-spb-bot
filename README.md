# Работа в Питере — Telegram Mini App

Готовый FastAPI-проект для Telegram Mini App сервиса размещения вакансий в Санкт-Петербурге.

## Что внутри
- тёмный neon/glass дизайн Mini App;
- тарифы и пакеты;
- корзина и оформление заявки;
- профиль и поддержка;
- официальный Telegram-канал: https://t.me/worksaintpeterburg;
- скрытая админка внутри Mini App только для Telegram-администратора;
- статистика, заказы и пользователи;
- Telegram webhook и уведомления админу;
- SQLite.

## Запуск
```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Для Railway нужны переменные:
- `BOT_TOKEN`
- `PUBLIC_URL`
- `ADMIN_SETUP_CODE`

Канал в Mini App открывается кнопкой «Перейти в Telegram-канал» и пунктом «Наш Telegram-канал» в профиле.
