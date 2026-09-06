import os
import sqlite3
import hmac
import hashlib
from datetime import datetime, timezone
from html import escape
from typing import List
from urllib.parse import parse_qsl
import json
import random
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Работа в Питере — Mini App")
DB_PATH = os.getenv("DB_PATH", "orders.sqlite3")
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_SETUP_CODE = os.getenv("ADMIN_SETUP_CODE", "").strip()
RAILWAY_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
PUBLIC_URL = os.getenv("PUBLIC_URL", "").strip().rstrip("/")
if not PUBLIC_URL and RAILWAY_DOMAIN:
    PUBLIC_URL = "https://" + RAILWAY_DOMAIN
if not PUBLIC_URL:
    PUBLIC_URL = "https://work-spb-bot-production.up.railway.app"

SERVICES = [
    {
        "id": 1, "name": "БАЗОВЫЙ", "price": 250, "tag": "Быстрый старт", "type": "Разовое размещение",
        "subtitle": "Стандартное размещение вакансии без лишних действий.",
        "description": "Подходит для простых и срочных вакансий, когда важны скорость и аккуратная подача.",
        "features": ["Редактура и структура текста", "Публикация в ленте", "Навигационные хештеги", "Прямые контакты HR"],
        "accent": "silver",
    },
    {
        "id": 2, "name": "ПОД КЛЮЧ", "price": 400, "tag": "Хит продаж", "type": "Разовое размещение",
        "subtitle": "Больше внимания к вакансии и более сильная визуальная подача.",
        "description": "Оптимальный вариант, если нужно выделить вакансию в ленте и сделать объявление заметнее.",
        "features": ["Всё из тарифа «Базовый»", "Уникальное ИИ-фото", "Яркое оформление в ленте", "Приоритетная вычитка"],
        "accent": "violet",
    },
    {
        "id": 3, "name": "ПРЕМИУМ", "price": 800, "tag": "Максимум", "type": "Разовое размещение",
        "subtitle": "Максимальный пакет для срочного поиска кандидатов.",
        "description": "Для вакансий, где нужно получить максимум внимания и дополнительно усилить публикацию.",
        "features": ["Всё из тарифа «Под ключ»", "ИИ-видео креатив", "Закреп в топе на 24 часа", "Максимальное число откликов"],
        "accent": "gold",
    },
    {
        "id": 4, "name": "START", "price": 1600, "tag": "5 публикаций", "type": "Пакет",
        "subtitle": "5 публикаций по 320 ₽ за пост.",
        "description": "Для компаний, которым нужно разместить несколько вакансий или регулярно обновлять одну вакансию.",
        "features": ["5 публикаций", "База тарифа «Под ключ»", "Уникальное ИИ-фото на каждую вакансию", "Скидка 20%", "Срок 30–60 дней"],
        "accent": "blue",
    },
    {
        "id": 5, "name": "MASS-НАЙМ", "price": 2900, "tag": "10 публикаций", "type": "Пакет",
        "subtitle": "10 публикаций по 290 ₽ за пост.",
        "description": "Для массового найма, сетей и компаний с постоянным потоком вакансий.",
        "features": ["10 публикаций", "База тарифа «Под ключ»", "Уникальное ИИ-фото на каждую вакансию", "Скидка 28%", "Срок 30–60 дней"],
        "accent": "cyan",
    },
    {
        "id": 6, "name": "HR-ПАРТНЕР", "price": 5000, "tag": "20 публикаций", "type": "Пакет",
        "subtitle": "20 публикаций по 250 ₽ за пост.",
        "description": "Самый выгодный вариант для постоянного подбора персонала и нескольких направлений найма.",
        "features": ["20 публикаций", "База тарифа «Под ключ»", "Уникальное ИИ-фото на каждую вакансию", "Скидка 38%", "Срок 30–60 дней"],
        "accent": "pink",
    },
]

APP_TZ = ZoneInfo("Europe/Moscow")
WHEEL_SPIN_COST = 5
STAR_PACKS = [
    {"stars": 25, "label": "25 ⭐", "title": "25 звёзд", "description": "Баланс для 5 платных вращений колеса."},
    {"stars": 50, "label": "50 ⭐", "title": "50 звёзд", "description": "Баланс для 10 платных вращений колеса."},
    {"stars": 100, "label": "100 ⭐", "title": "100 звёзд", "description": "Баланс для 20 платных вращений колеса."},
]
WHEEL_PRIZES = [
    {"key": "empty", "label": "Пусто", "title": "Попробуй завтра", "weight": 50},
    {"key": "discount10", "label": "−10%", "title": "Скидка 10%", "weight": 20},
    {"key": "discount20", "label": "−20%", "title": "Скидка 20%", "weight": 15},
    {"key": "bonus", "label": "Бонус", "title": "Бонус к заказу", "weight": 10},
    {"key": "free", "label": "FREE", "title": "Бесплатное размещение", "weight": 5},
]

class Order(BaseModel):
    service_ids: List[int]
    contact: str = ""
    comment: str = ""


def db():
    con = sqlite3.connect(DB_PATH)
    con.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, service_ids TEXT, total INTEGER, contact TEXT, comment TEXT, status TEXT DEFAULT 'new')")
    cols = {row[1] for row in con.execute("PRAGMA table_info(orders)").fetchall()}
    if "status" not in cols:
        con.execute("ALTER TABLE orders ADD COLUMN status TEXT DEFAULT 'new'")
    con.execute("UPDATE orders SET status='new' WHERE status IS NULL OR status=''")
    con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.execute("CREATE TABLE IF NOT EXISTS users (telegram_id TEXT PRIMARY KEY, first_name TEXT DEFAULT '', last_name TEXT DEFAULT '', username TEXT DEFAULT '', started_at TEXT NOT NULL, last_seen TEXT NOT NULL)")
    con.execute("CREATE TABLE IF NOT EXISTS star_wallets (telegram_id TEXT PRIMARY KEY, balance INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL)")
    con.execute("CREATE TABLE IF NOT EXISTS star_payments (telegram_payment_charge_id TEXT PRIMARY KEY, telegram_id TEXT NOT NULL, stars INTEGER NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL)")
    con.execute("CREATE TABLE IF NOT EXISTS wheel_spins (telegram_id TEXT PRIMARY KEY, last_free_date TEXT, total_spins INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL)")
    con.execute("CREATE TABLE IF NOT EXISTS prize_inventory (id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id TEXT NOT NULL, prize_key TEXT NOT NULL, title TEXT NOT NULL, emoji TEXT NOT NULL DEFAULT '🎁', status TEXT NOT NULL DEFAULT 'available', won_at TEXT NOT NULL, activated_at TEXT, activation_code TEXT)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_prize_inventory_user ON prize_inventory(telegram_id, id DESC)")
    con.commit()
    return con


def get_admin_chat_id():
    con = db()
    row = con.execute("SELECT value FROM settings WHERE key='admin_chat_id'").fetchone()
    con.close()
    return row[0] if row else ""


def set_admin_chat_id(chat_id: str):
    con = db()
    con.execute("INSERT INTO settings(key,value) VALUES('admin_chat_id',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(chat_id),))
    con.commit(); con.close()


async def telegram(method: str, payload: dict):
    if not BOT_TOKEN:
        return None
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.post(url, json=payload)
            return r.json()
    except Exception:
        return None


def format_order(order_id, chosen, total, contact, comment):
    lines = [f"🛎 <b>НОВАЯ ЗАЯВКА #{order_id}</b>", "", "<b>Услуги:</b>"]
    for s in chosen:
        lines.append(f"• {escape(s['name'])} — {s['price']:,} ₽".replace(",", " "))
    lines += ["", f"💰 <b>Итого: {total:,} ₽</b>".replace(",", " "), f"👤 <b>Контакт:</b> {escape(contact) if contact else 'не указан'}", f"💬 <b>Комментарий:</b> {escape(comment) if comment else 'нет'}"]
    return "\n".join(lines)


def save_started_user(user: dict):
    telegram_id = str(user.get("id") or "").strip()
    if not telegram_id:
        return
    now = datetime.now(timezone.utc).isoformat()
    first_name = str(user.get("first_name") or "").strip()
    last_name = str(user.get("last_name") or "").strip()
    username = str(user.get("username") or "").strip()
    con = db()
    con.execute(
        "INSERT INTO users(telegram_id,first_name,last_name,username,started_at,last_seen) VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(telegram_id) DO UPDATE SET first_name=excluded.first_name,last_name=excluded.last_name,username=excluded.username,last_seen=excluded.last_seen",
        (telegram_id, first_name, last_name, username, now, now),
    )
    con.commit()
    con.close()



def current_user(request: Request):
    user = validate_telegram_init_data(request.headers.get("X-Telegram-Init-Data", ""))
    if user:
        save_started_user(user)
    return user

def wheel_status_for(telegram_id: str):
    today = datetime.now(APP_TZ).date().isoformat()
    con = db()
    row = con.execute("SELECT balance FROM star_wallets WHERE telegram_id=?", (str(telegram_id),)).fetchone()
    spin = con.execute("SELECT last_free_date,total_spins FROM wheel_spins WHERE telegram_id=?", (str(telegram_id),)).fetchone()
    con.close()
    return {"balance": int(row[0]) if row else 0, "free_available": not spin or spin[0] != today, "total_spins": int(spin[1]) if spin else 0}

def weighted_wheel_prize():
    total = sum(int(x["weight"]) for x in WHEEL_PRIZES)
    point = random.uniform(0, total)
    cursor = 0
    for prize in WHEEL_PRIZES:
        cursor += int(prize["weight"])
        if point < cursor:
            return prize
    return WHEEL_PRIZES[0]


def prize_emoji(key: str):
    return {"discount10":"🎟️", "discount20":"🎁", "bonus":"⭐", "free":"🆓"}.get(key, "🎁")

def inventory_for(telegram_id: str):
    con = db()
    rows = con.execute("SELECT id,prize_key,title,emoji,status,won_at,activated_at,activation_code FROM prize_inventory WHERE telegram_id=? ORDER BY id DESC", (str(telegram_id),)).fetchall()
    con.close()
    return [{"id":r[0],"key":r[1],"title":r[2],"emoji":r[3],"status":r[4],"won_at":r[5],"activated_at":r[6],"activation_code":r[7]} for r in rows]

async def setup_webhook():
    if not BOT_TOKEN or not PUBLIC_URL:
        return
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "workspb2026")
    await telegram("setWebhook", {"url": f"{PUBLIC_URL}/telegram/webhook", "secret_token": secret, "drop_pending_updates": False})


@app.on_event("startup")
async def startup():
    db().close()
    await setup_webhook()


@app.get("/", response_class=HTMLResponse)
@app.get("/shop", response_class=HTMLResponse)
async def shop():
    return HTML


@app.get("/api/services")
async def services():
    return SERVICES


@app.post("/api/checkout")
async def checkout(order: Order):
    ids = list(dict.fromkeys(order.service_ids))
    chosen = [s for s in SERVICES if s["id"] in ids]
    if not chosen:
        return JSONResponse({"ok": False, "message": "Корзина пуста."}, status_code=400)
    total = sum(s["price"] for s in chosen)
    con = db()
    cur = con.execute("INSERT INTO orders(created_at,service_ids,total,contact,comment) VALUES(?,?,?,?,?)", (datetime.now(timezone.utc).isoformat(), ",".join(map(str, ids)), total, order.contact.strip(), order.comment.strip()))
    order_id = cur.lastrowid
    con.commit(); con.close()

    admin = get_admin_chat_id()
    if BOT_TOKEN and admin:
        await telegram("sendMessage", {"chat_id": admin, "text": format_order(order_id, chosen, total, order.contact.strip(), order.comment.strip()), "parse_mode": "HTML"})

    return {"ok": True, "order_id": order_id, "total": total, "notified": bool(BOT_TOKEN and admin), "message": "Заявка отправлена! Мы свяжемся с вами для подтверждения."}



async def orders_history(chat_id: str):
    if str(chat_id) != str(get_admin_chat_id()):
        return

    con = db()
    rows = con.execute(
        "SELECT id, created_at, service_ids, total, contact, comment "
        "FROM orders ORDER BY id DESC LIMIT 10"
    ).fetchall()
    con.close()

    if not rows:
        await telegram(
            "sendMessage",
            {"chat_id": chat_id, "text": "📋 История заказов пока пуста."}
        )
        return

    lines = ["📋 <b>ПОСЛЕДНИЕ 10 ЗАКАЗОВ</b>", ""]
    for order_id, created_at, service_ids, total, contact, comment in rows:
        names = []
        for raw_id in (service_ids or "").split(","):
            try:
                sid = int(raw_id.strip())
            except ValueError:
                continue
            service = next((s for s in SERVICES if s["id"] == sid), None)
            if service:
                names.append(service["name"])

        service_text = ", ".join(names) if names else "Услуга не найдена"
        lines.append(
            f"🧾 <b>Заказ #{order_id}</b>\n"
            f"🕐 {escape(str(created_at))}\n"
            f"🛍 {escape(service_text)}\n"
            f"💰 <b>{total} ₽</b>\n"
            f"📞 {escape(contact or '—')}\n"
            f"💬 {escape(comment or '—')}"
        )
        lines.append("")

    await telegram(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": "\n".join(lines),
            "parse_mode": "HTML",
        },
    )

async def admin_panel(chat_id: str):
    if str(chat_id) != str(get_admin_chat_id()):
        return

    con = db()

    total_orders = con.execute(
        "SELECT COUNT(*) FROM orders"
    ).fetchone()[0]

    total_revenue = con.execute(
        "SELECT COALESCE(SUM(total), 0) FROM orders"
    ).fetchone()[0]

    today = datetime.now(APP_TZ).date().isoformat()

    today_orders = con.execute(
        "SELECT COUNT(*) FROM orders WHERE created_at LIKE ?",
        (today + "%",)
    ).fetchone()[0]

    today_revenue = con.execute(
        "SELECT COALESCE(SUM(total), 0) FROM orders WHERE created_at LIKE ?",
        (today + "%",)
    ).fetchone()[0]

    con.close()

    text = (
        "📊 <b>АДМИН-ПАНЕЛЬ</b>\n\n"
        f"📦 Всего заявок: <b>{total_orders}</b>\n"
        f"💰 Общая сумма: <b>{total_revenue:,} ₽</b>\n"
        f"🗓️ Сегодня заявок: <b>{today_orders}</b>\n"
        f"💵 Сегодня сумма: <b>{today_revenue:,} ₽</b>"
    ).replace(",", " ")

    await telegram(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
    )


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "workspb2026")
    if request.headers.get("x-telegram-bot-api-secret-token") != secret:
        return JSONResponse({"ok": False}, status_code=403)
    update = await request.json()
    msg = update.get("message") or {}
    chat = msg.get("chat") or {}
    text = (msg.get("text") or "").strip()
    chat_id = chat.get("id")
    pre = update.get("pre_checkout_query") or {}
    if pre.get("id"):
        await telegram("answerPreCheckoutQuery", {"pre_checkout_query_id": pre["id"], "ok": True})
        return {"ok": True}
    successful = msg.get("successful_payment") or {}
    if successful.get("currency") == "XTR":
        payload = str(successful.get("invoice_payload") or "")
        charge_id = str(successful.get("telegram_payment_charge_id") or "")
        paid_user_id = str((msg.get("from") or {}).get("id") or chat_id or "")
        if payload.startswith("stars_pack:") and charge_id and paid_user_id:
            try: stars = int(payload.split(":")[1])
            except Exception: stars = 0
            if stars in [x["stars"] for x in STAR_PACKS]:
                con = db()
                exists = con.execute("SELECT 1 FROM star_payments WHERE telegram_payment_charge_id=?", (charge_id,)).fetchone()
                if not exists:
                    now = datetime.now(timezone.utc).isoformat()
                    con.execute("INSERT INTO star_payments(telegram_payment_charge_id,telegram_id,stars,payload,created_at) VALUES(?,?,?,?,?)", (charge_id, paid_user_id, stars, payload, now))
                    con.execute("INSERT INTO star_wallets(telegram_id,balance,updated_at) VALUES(?,?,?) ON CONFLICT(telegram_id) DO UPDATE SET balance=balance+excluded.balance,updated_at=excluded.updated_at", (paid_user_id, stars, now))
                    con.commit()
                row = con.execute("SELECT balance FROM star_wallets WHERE telegram_id=?", (paid_user_id,)).fetchone()
                con.close()
                await telegram("sendMessage", {"chat_id": paid_user_id, "text": f"⭐ Баланс пополнен на {stars} Stars.\nТекущий баланс: {int(row[0]) if row else 0} ⭐"})
        return {"ok": True}
    if chat_id and text.startswith("/setadmin") and ADMIN_SETUP_CODE:
        parts = text.split(maxsplit=1)
        if len(parts) == 2 and parts[1].strip() == ADMIN_SETUP_CODE:
            set_admin_chat_id(str(chat_id))
            await telegram("sendMessage", {"chat_id": chat_id, "text": "✅ Готово! Этот чат назначен администратором. Новые заявки будут приходить сюда."})
        else:
            await telegram("sendMessage", {"chat_id": chat_id, "text": "❌ Неверный код подключения."})
    elif chat_id and text.startswith("/start"):
        save_started_user(msg.get("from") or {"id": chat_id})
        await telegram("sendMessage", {"chat_id": chat_id, "text": "👋 Добро пожаловать! Нажмите «🛍 Услуги» в меню, чтобы открыть каталог."})
    elif chat_id and text.startswith("/help"):
        await telegram("sendMessage", {"chat_id": chat_id, "text": "🏙 <b>ПРАЙС — размещение вакансий в Санкт-Петербурге</b>\n\n🛍 <b>Услуги</b> — открыть каталог и выбрать тариф.\n📋 Выберите услуги, добавьте их в корзину и отправьте заявку.\n⚡ Быстрая публикация • 📣 продвижение вакансии • 🤖 AI-оформление\n\nЕсли нужна помощь, напишите администратору.", "parse_mode": "HTML"})
    elif chat_id and (text.startswith("/broadcast") or (msg.get("caption") or "").strip().startswith("/broadcast")):
        if str(chat_id) != str(get_admin_chat_id()):
            await telegram("sendMessage", {"chat_id": chat_id, "text": "⛔ Команда доступна только администратору."})
        else:
            source_text = text if text.startswith("/broadcast") else (msg.get("caption") or "").strip()
            parts = source_text.split(maxsplit=1)
            broadcast_text = parts[1].strip() if len(parts) > 1 else ""
            photo = msg.get("photo") or []
            photo_id = photo[-1].get("file_id") if photo else None
            if not broadcast_text and not photo_id:
                await telegram("sendMessage", {"chat_id": chat_id, "text": "📣 Формат:\n\n1) /broadcast текст\n\nили\n\n2) Прикрепи фото и в подписи напиши:\n/broadcast текст\n\nК сообщению автоматически добавится кнопка «🎡 Открыть колесо»."})
            else:
                con = db()
                users = [str(row[0]) for row in con.execute("SELECT telegram_id FROM users ORDER BY started_at ASC").fetchall()]
                con.close()
                sent = 0
                failed = 0
                keyboard = {"inline_keyboard": [[{"text": "🎡 Открыть колесо", "web_app": {"url": PUBLIC_URL}}]]}
                for uid in users:
                    if photo_id:
                        payload = {"chat_id": uid, "photo": photo_id, "caption": escape(broadcast_text)[:1024], "reply_markup": keyboard}
                        result = await telegram("sendPhoto", payload)
                    else:
                        payload = {"chat_id": uid, "text": escape(broadcast_text), "reply_markup": keyboard}
                        result = await telegram("sendMessage", payload)
                    if result and result.get("ok"):
                        sent += 1
                    else:
                        failed += 1
                    await asyncio.sleep(0.05)
                await telegram("sendMessage", {"chat_id": chat_id, "text": f"📣 Рассылка завершена.\n\n✅ Доставлено: {sent}\n⚠️ Не доставлено: {failed}\n👥 Всего получателей: {len(users)}"})
    elif chat_id and text.startswith("/paysupport"):
        await telegram("sendMessage", {"chat_id": chat_id, "text": "💳 По вопросам оплаты Stars и возврата средств напишите администратору: @RZTFrong"})
    elif chat_id and text.startswith("/admin"):
        await admin_panel(str(chat_id))
    elif chat_id and text.startswith("/orders"):
        await orders_history(str(chat_id))
    return {"ok": True}


ADMIN_WEB_COOKIE = "work_spb_admin"
ADMIN_STATUSES = {"new":"Новая","in_progress":"В работе","done":"Выполнено","cancelled":"Отменена"}

def admin_cookie_value():
    if not ADMIN_SETUP_CODE:
        return ""
    return hmac.new(ADMIN_SETUP_CODE.encode(), b"work-spb-admin", hashlib.sha256).hexdigest()

def is_admin_web(request: Request) -> bool:
    value = request.cookies.get(ADMIN_WEB_COOKIE, "")
    expected = admin_cookie_value()
    return bool(expected) and hmac.compare_digest(value, expected)

def service_names(service_ids: str):
    result=[]
    for raw in (service_ids or "").split(","):
        try: sid=int(raw.strip())
        except ValueError: continue
        item=next((x for x in SERVICES if x["id"]==sid),None)
        if item: result.append(item["name"])
    return result


def validate_telegram_init_data(init_data: str):
    """Validate Telegram Mini App initData and return the Telegram user object."""
    if not init_data or not BOT_TOKEN:
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = pairs.pop("hash", "")
        if not received_hash:
            return None
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calculated, received_hash):
            return None
        user = json.loads(pairs.get("user", "{}"))
        auth_date = int(pairs.get("auth_date", "0") or 0)
        if not user.get("id") or not auth_date:
            return None
        if abs(int(datetime.now(timezone.utc).timestamp()) - auth_date) > 86400:
            return None
        return user
    except Exception:
        return None


def is_telegram_admin(request: Request):
    user = validate_telegram_init_data(request.headers.get("X-Telegram-Init-Data", ""))
    admin_id = str(get_admin_chat_id() or "")
    return bool(user and admin_id and str(user.get("id")) == admin_id)


@app.get("/api/wheel/status")
async def wheel_status(request: Request):
    user = current_user(request)
    if not user:
        return JSONResponse({"ok": False, "message": "Откройте приложение внутри Telegram."}, status_code=401)
    return {"ok": True, **wheel_status_for(str(user["id"])), "spin_cost": WHEEL_SPIN_COST, "packs": STAR_PACKS}

@app.post("/api/wheel/spin")
async def wheel_spin(request: Request):
    user = current_user(request)
    if not user:
        return JSONResponse({"ok": False, "message": "Откройте приложение внутри Telegram."}, status_code=401)
    telegram_id = str(user["id"])
    today = datetime.now(APP_TZ).date().isoformat()
    con = db()
    row = con.execute("SELECT balance FROM star_wallets WHERE telegram_id=?", (telegram_id,)).fetchone()
    balance = int(row[0]) if row else 0
    spin = con.execute("SELECT last_free_date,total_spins FROM wheel_spins WHERE telegram_id=?", (telegram_id,)).fetchone()
    last_free = spin[0] if spin else None
    total_spins = int(spin[1]) if spin else 0
    paid = False
    now = datetime.now(timezone.utc).isoformat()
    if last_free != today:
        con.execute("INSERT INTO wheel_spins(telegram_id,last_free_date,total_spins,updated_at) VALUES(?,?,?,?) ON CONFLICT(telegram_id) DO UPDATE SET last_free_date=excluded.last_free_date,total_spins=excluded.total_spins,updated_at=excluded.updated_at", (telegram_id, today, total_spins + 1, now))
    else:
        if balance < WHEEL_SPIN_COST:
            con.close()
            return JSONResponse({"ok": False, "need_stars": True, "message": "Бесплатная попытка уже использована. Нужно 5 ⭐."}, status_code=402)
        balance -= WHEEL_SPIN_COST
        paid = True
        con.execute("UPDATE star_wallets SET balance=?,updated_at=? WHERE telegram_id=?", (balance, now, telegram_id))
        con.execute("INSERT INTO wheel_spins(telegram_id,last_free_date,total_spins,updated_at) VALUES(?,?,?,?) ON CONFLICT(telegram_id) DO UPDATE SET total_spins=excluded.total_spins,updated_at=excluded.updated_at", (telegram_id, last_free, total_spins + 1, now))
    prize = weighted_wheel_prize()
    inventory_id = None
    if prize["key"] != "empty":
        now_prize = datetime.now(timezone.utc).isoformat()
        cur = con.execute("INSERT INTO prize_inventory(telegram_id,prize_key,title,emoji,status,won_at) VALUES(?,?,?,?,?,?)", (telegram_id, prize["key"], prize["title"], prize_emoji(prize["key"]), "available", now_prize))
        inventory_id = cur.lastrowid
    con.commit(); con.close()
    return {"ok": True, "prize": {"key": prize["key"], "label": prize["label"], "title": prize["title"]}, "inventory_id": inventory_id, "paid": paid, "charged": WHEEL_SPIN_COST if paid else 0, "balance": balance, "free_available": False}

@app.get("/api/inventory")
async def inventory(request: Request):
    user = current_user(request)
    if not user:
        return JSONResponse({"ok": False, "message": "Откройте приложение внутри Telegram."}, status_code=401)
    return {"ok": True, "items": inventory_for(str(user["id"]))}

@app.post("/api/inventory/{item_id}/activate")
async def inventory_activate(item_id: int, request: Request):
    user = current_user(request)
    if not user:
        return JSONResponse({"ok": False, "message": "Откройте приложение внутри Telegram."}, status_code=401)
    telegram_id = str(user["id"])
    con = db()
    row = con.execute("SELECT id,prize_key,title,status,activation_code FROM prize_inventory WHERE id=? AND telegram_id=?", (item_id, telegram_id)).fetchone()
    if not row:
        con.close()
        return JSONResponse({"ok": False, "message": "Приз не найден."}, status_code=404)
    code = row[4]
    if not code:
        code = "SPB-" + ''.join(random.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
        con.execute("UPDATE prize_inventory SET status='activated',activated_at=?,activation_code=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), code, item_id))
        con.commit()
        admin = get_admin_chat_id()
        if BOT_TOKEN and admin:
            uname = str(user.get("username") or "").strip()
            who = f"@{escape(uname)}" if uname else escape(str(user.get("first_name") or "Пользователь"))
            text = f"🎁 <b>АКТИВАЦИЯ ПРИЗА</b>\n\nПользователь: {who}\nПриз: <b>{escape(row[2])}</b>\nКод: <code>{code}</code>\n\nПопросите пользователя показать этот код при оформлении заявки."
            await telegram("sendMessage", {"chat_id": admin, "text": text, "parse_mode": "HTML"})
    con.close()
    return {"ok": True, "status": "activated", "title": row[2], "code": code, "message": "Приз активирован. Покажите код администратору при оформлении заявки."}

@app.post("/api/stars/invoice")
async def stars_invoice(request: Request):
    user = current_user(request)
    if not user:
        return JSONResponse({"ok": False, "message": "Откройте приложение внутри Telegram."}, status_code=401)
    body = await request.json()
    try: stars = int(body.get("stars", 0))
    except Exception: stars = 0
    pack = next((x for x in STAR_PACKS if x["stars"] == stars), None)
    if not pack:
        return JSONResponse({"ok": False, "message": "Такого пакета нет."}, status_code=400)
    result = await telegram("createInvoiceLink", {"title": pack["title"], "description": pack["description"], "payload": f"stars_pack:{stars}:user:{user['id']}", "provider_token": "", "currency": "XTR", "prices": [{"label": pack["title"], "amount": stars}]})
    if not result or not result.get("ok"):
        return JSONResponse({"ok": False, "message": "Не удалось создать оплату Stars. Проверьте настройки бота."}, status_code=502)
    return {"ok": True, "invoice_url": result["result"], "stars": stars}

@app.get("/api/admin/me")
async def admin_me(request: Request):
    return {"ok": True, "admin": is_telegram_admin(request)}


@app.get("/api/admin/users")
async def admin_users(request: Request):
    if not is_telegram_admin(request):
        return JSONResponse({"ok": False, "message": "Нет доступа"}, status_code=403)
    con = db()
    rows = con.execute(
        "SELECT telegram_id,first_name,last_name,username,started_at,last_seen FROM users ORDER BY started_at DESC LIMIT 500"
    ).fetchall()
    con.close()
    users=[]
    for uid,first,last,username,started,last_seen in rows:
        users.append({"telegram_id":uid,"first_name":first or "Пользователь","last_name":last or "","username":username or "","started_at":started,"last_seen":last_seen})
    return {"ok":True,"users":users,"total":len(users)}


@app.get("/api/admin/dashboard")
async def admin_dashboard(request: Request):
    if not is_telegram_admin(request):
        return JSONResponse({"ok": False, "message": "Нет доступа"}, status_code=403)
    data = admin_stats()
    stars = data.pop("stars")
    live = await telegram("getMyStarBalance", {})
    bot_balance = None
    if live and live.get("ok"):
        try:
            bot_balance = int((live.get("result") or {}).get("amount", 0))
        except (TypeError, ValueError):
            bot_balance = None
    stars["bot_balance"] = bot_balance
    return {"ok": True, "data": {**data, "stars": stars}}


@app.post("/api/admin/orders/{order_id}/status")
async def admin_order_status(order_id: int, request: Request):
    if not is_telegram_admin(request):
        return JSONResponse({"ok": False, "message": "Нет доступа"}, status_code=403)
    body = await request.json()
    status = str(body.get("status", "new"))
    if status not in ADMIN_STATUSES:
        return JSONResponse({"ok": False, "message": "Неизвестный статус"}, status_code=400)
    con = db()
    cur = con.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    con.commit()
    con.close()
    if cur.rowcount == 0:
        return JSONResponse({"ok": False, "message": "Заказ не найден"}, status_code=404)
    return {"ok": True}


def admin_stats():
    con=db()
    total_orders=con.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    total_revenue=con.execute("SELECT COALESCE(SUM(total),0) FROM orders").fetchone()[0]
    today=datetime.now(APP_TZ).date().isoformat()
    today_orders=con.execute("SELECT COUNT(*) FROM orders WHERE created_at LIKE ?",(today+"%",)).fetchone()[0]
    today_revenue=con.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE created_at LIKE ?",(today+"%",)).fetchone()[0]
    new_orders=con.execute("SELECT COUNT(*) FROM orders WHERE status='new'").fetchone()[0]
    in_progress=con.execute("SELECT COUNT(*) FROM orders WHERE status='in_progress'").fetchone()[0]
    done=con.execute("SELECT COUNT(*) FROM orders WHERE status='done'").fetchone()[0]
    user_count=con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    stars_total=con.execute("SELECT COALESCE(SUM(stars),0) FROM star_payments").fetchone()[0]
    stars_today=con.execute("SELECT COALESCE(SUM(stars),0) FROM star_payments WHERE created_at LIKE ?", (today+"%",)).fetchone()[0]
    stars_payments=con.execute("SELECT COUNT(*) FROM star_payments").fetchone()[0]
    rows=con.execute("SELECT id,created_at,service_ids,total,contact,comment,status FROM orders ORDER BY id DESC LIMIT 100").fetchall()
    con.close()
    orders=[]
    for oid,created,ids,total,contact,comment,status in rows:
        orders.append({"id":oid,"created_at":created,"services":service_names(ids),"total":total,"contact":contact or "—","comment":comment or "—","status":status or "new"})
    return {"total_orders":total_orders,"total_revenue":total_revenue,"today_orders":today_orders,"today_revenue":today_revenue,"new_orders":new_orders,"in_progress":in_progress,"done":done,"user_count":user_count,"orders":orders,"stars":{"bot_balance":None,"received_total":int(stars_total),"received_today":int(stars_today),"payments_count":int(stars_payments)}}

ADMIN_LOGIN_HTML = """<!doctype html><html lang='ru'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Вход — Админ-панель</title><style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle at 20% 10%,#eaf1ff,transparent 35%),radial-gradient(circle at 90% 20%,#f5eaff,transparent 35%),#f7faff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#14213d}.box{width:min(410px,calc(100% - 32px));background:#fff;border:1px solid #dce6f5;border-radius:28px;padding:28px;box-shadow:0 25px 70px #18315a18}.logo{font-weight:950;font-size:18px}.logo span{display:inline-grid;place-items:center;width:38px;height:38px;margin-right:8px;border-radius:12px;background:linear-gradient(135deg,#246bff,#7b4dff);color:#fff}.box h1{font-size:28px;margin:24px 0 8px}.muted{color:#71809a;font-size:13px;line-height:1.5}label{display:block;margin:22px 0 7px;font-size:12px;font-weight:800}input{width:100%;box-sizing:border-box;border:1px solid #d7e1ef;border-radius:15px;padding:14px;background:#f9fbff;font-size:16px}button{width:100%;border:0;border-radius:15px;padding:14px;margin-top:14px;background:linear-gradient(135deg,#1268ff,#704cff);color:#fff;font-weight:900;font-size:15px}.error{margin-top:12px;padding:11px;border-radius:12px;background:#fff0f2;color:#b52c51;font-size:12px}</style></head><body><form class='box' method='post' action='/admin-web/login'><div class='logo'><span>✦</span>Работа в Питере</div><h1>Админ-панель</h1><div class='muted'>Закрытый раздел управления заказами и статистикой.</div><label>Код администратора</label><input type='password' name='code' placeholder='Введите код' required autofocus><button>Войти в панель →</button>{error}</form></body></html>"""

@app.get("/admin-web", response_class=HTMLResponse)
async def admin_web(request: Request):
    if not is_admin_web(request): return HTMLResponse(ADMIN_LOGIN_HTML.replace("{error}",""))
    return HTMLResponse(render_admin_web(admin_stats()))

@app.post("/admin-web/login")
async def admin_web_login(request: Request):
    from fastapi.responses import RedirectResponse
    form=await request.form(); code=str(form.get("code",""))
    if not ADMIN_SETUP_CODE or not hmac.compare_digest(code,ADMIN_SETUP_CODE):
        return HTMLResponse(ADMIN_LOGIN_HTML.replace("{error}","<div class='error'>Неверный код администратора.</div>"),status_code=401)
    response=RedirectResponse("/admin-web",status_code=303)
    response.set_cookie(ADMIN_WEB_COOKIE,admin_cookie_value(),httponly=True,samesite="lax",secure=True,max_age=60*60*24*30)
    return response

@app.post("/admin-web/logout")
async def admin_web_logout(request: Request):
    from fastapi.responses import RedirectResponse
    response=RedirectResponse("/admin-web",status_code=303); response.delete_cookie(ADMIN_WEB_COOKIE); return response

@app.post("/admin-web/orders/{order_id}/status")
async def admin_web_status(order_id:int,request:Request):
    from fastapi.responses import RedirectResponse
    if not is_admin_web(request): return JSONResponse({"ok":False,"message":"Нет доступа"},status_code=403)
    form=await request.form(); status=str(form.get("status","new"))
    if status not in ADMIN_STATUSES: return JSONResponse({"ok":False,"message":"Неизвестный статус"},status_code=400)
    con=db(); cur=con.execute("UPDATE orders SET status=? WHERE id=?",(status,order_id)); con.commit(); con.close()
    if cur.rowcount==0: return JSONResponse({"ok":False,"message":"Заказ не найден"},status_code=404)
    return RedirectResponse("/admin-web#orders",status_code=303)

def render_admin_web(data):
    import json
    html=ADMIN_WEB_HTML
    replacements={"__DATA__":json.dumps(data["orders"],ensure_ascii=False),"__SERVICES__":json.dumps(SERVICES,ensure_ascii=False),"__TOTAL_ORDERS__":f'{data["total_orders"]:,}'.replace(","," "),"__TOTAL_REVENUE__":f'{data["total_revenue"]:,}'.replace(","," "),"__TODAY_ORDERS__":f'{data["today_orders"]:,}'.replace(","," "),"__TODAY_REVENUE__":f'{data["today_revenue"]:,}'.replace(","," "),"__NEW__":str(data["new_orders"]),"__IN_PROGRESS__":str(data["in_progress"]),"__DONE__":str(data["done"])}
    for k,v in replacements.items(): html=html.replace(k,v)
    return html

ADMIN_WEB_HTML = """<!doctype html><html lang='ru'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Работа в Питере — Админ</title><style>:root{--ink:#13233e;--muted:#74839b;--line:#dfe8f5;--bg:#f4f8fd;--blue:#1468ff;--green:#17a66a;--shadow:0 16px 45px #18365b10}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 0 0,#e9f1ff,transparent 32%),radial-gradient(circle at 100% 0,#f5eaff,transparent 28%),var(--bg);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:var(--ink)}.app{display:flex;min-height:100vh}.side{width:235px;background:#102341;color:#fff;padding:22px 14px;position:fixed;inset:0 auto 0 0}.brand{font-weight:950;padding:10px 12px 22px}.brand small{display:block;opacity:.55;font-weight:600;margin-top:4px}.menu{display:grid;gap:6px}.menu button{border:0;background:transparent;color:#b8c7dc;text-align:left;padding:12px 13px;border-radius:12px;font-weight:800;cursor:pointer}.menu button.active,.menu button:hover{background:#1d63db;color:#fff}.logout{position:absolute;left:14px;right:14px;bottom:18px}.logout button{width:100%;border:1px solid #ffffff20;background:#ffffff0d;color:#fff;border-radius:12px;padding:11px;font-weight:800}.main{margin-left:235px;width:calc(100% - 235px);padding:26px;max-width:1500px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px}.top h1{margin:0;font-size:28px}.online{font-size:12px;color:#21895f;font-weight:800;background:#e7fff3;padding:8px 11px;border-radius:999px}.tab{display:none}.tab.active{display:block}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.stat{background:#fff;border:1px solid var(--line);border-radius:20px;padding:17px;box-shadow:var(--shadow)}.stat small{color:var(--muted);font-size:11px}.stat strong{display:block;font-size:26px;margin-top:8px}.stat em{font-style:normal;color:var(--green);font-size:10px}.panel{background:#fff;border:1px solid var(--line);border-radius:22px;box-shadow:var(--shadow);padding:18px;margin-top:16px}.panelhead{display:flex;justify-content:space-between;align-items:center;gap:12px}.panel h2{margin:0;font-size:18px}.tablewrap{overflow:auto;margin-top:14px}table{width:100%;border-collapse:collapse;min-width:760px}th,td{text-align:left;padding:12px 10px;border-bottom:1px solid #edf1f7;font-size:12px}th{color:var(--muted);font-size:10px;text-transform:uppercase}tr:hover td{background:#fafcff}.pill{display:inline-flex;padding:6px 9px;border-radius:999px;font-size:10px;font-weight:900}.new{background:#fff3dc;color:#b86b0c}.in_progress{background:#e8f1ff;color:#2363cb}.done{background:#e5fff2;color:#168455}.cancelled{background:#fff0f3;color:#bd3d5b}.filters{display:flex;gap:8px;flex-wrap:wrap}.filters input,.filters select{border:1px solid var(--line);border-radius:11px;padding:10px;background:#fbfdff}.ordergrid{display:grid;grid-template-columns:1.4fr .8fr;gap:14px}.orderbox{border:1px solid var(--line);border-radius:18px;padding:15px}.orderbox h3{margin:0 0 10px}.row{display:flex;justify-content:space-between;gap:15px;padding:8px 0;border-bottom:1px solid #edf1f7;font-size:12px}.row:last-child{border-bottom:0}.btn{border:0;border-radius:11px;padding:10px 12px;font-weight:800;cursor:pointer}.primary{background:linear-gradient(135deg,#1268ff,#704cff);color:#fff}.ghost{background:#edf4ff;color:#1755bb}.servicegrid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.service{border:1px solid var(--line);border-radius:18px;padding:15px;background:#fff}.service .price{font-size:24px;font-weight:950;margin:8px 0}.service ul{padding-left:17px;color:var(--muted);font-size:11px;line-height:1.6}.setting{display:flex;justify-content:space-between;align-items:center;padding:14px 0;border-bottom:1px solid #edf1f7}.setting:last-child{border:0}.mobilebar{display:none}@media(max-width:900px){.side{display:none}.main{margin:0;width:100%;padding:16px 14px 88px}.cards{grid-template-columns:repeat(2,1fr)}.ordergrid{grid-template-columns:1fr}.servicegrid{grid-template-columns:1fr}.mobilebar{display:flex;position:fixed;left:10px;right:10px;bottom:10px;z-index:20;background:#102341ef;backdrop-filter:blur(16px);border-radius:18px;padding:7px;gap:5px;box-shadow:0 15px 40px #10234140}.mobilebar button{flex:1;border:0;background:transparent;color:#c3d0e2;border-radius:12px;padding:10px 4px;font-size:10px;font-weight:800}.mobilebar button.active{background:#1d63db;color:#fff}.top h1{font-size:24px}}</style></head><body><div class='app'><aside class='side'><div class='brand'>Работа в Питере<small>Админ-панель</small></div><div class='menu'><button class='active' data-tab='home'>⌂ Главная</button><button data-tab='orders'>▣ Заказы</button><button data-tab='tariffs'>◈ Тарифы</button><button data-tab='packages'>▦ Пакеты</button><button data-tab='stats'>◌ Статистика</button><button data-tab='settings'>⚙ Настройки</button></div><form class='logout' method='post' action='/admin-web/logout'><button>Выйти</button></form></aside><main class='main'><div class='top'><h1 id='title'>Главная</h1><span class='online'>● Онлайн</span></div><section id='home' class='tab active'><div class='cards'><div class='stat'><small>Всего заказов</small><strong>__TOTAL_ORDERS__</strong></div><div class='stat'><small>Выручка</small><strong>__TOTAL_REVENUE__ ₽</strong></div><div class='stat'><small>Сегодня</small><strong>__TODAY_ORDERS__</strong><em>заявок</em></div><div class='stat'><small>Сумма сегодня</small><strong>__TODAY_REVENUE__ ₽</strong></div></div><div class='panel'><div class='panelhead'><h2>Последние заявки</h2><button class='btn ghost' onclick="openTab('orders')">Все заказы →</button></div><div class='tablewrap'><table><thead><tr><th>#</th><th>Дата</th><th>Услуги</th><th>Сумма</th><th>Контакт</th><th>Статус</th></tr></thead><tbody id='homeRows'></tbody></table></div></div></section><section id='orders' class='tab'><div class='panel'><div class='panelhead'><h2>Заказы</h2><div class='filters'><input id='search' placeholder='Поиск по заказам...'><select id='filter'><option value='all'>Все статусы</option><option value='new'>Новая</option><option value='in_progress'>В работе</option><option value='done'>Выполнено</option><option value='cancelled'>Отменена</option></select></div></div><div class='tablewrap'><table><thead><tr><th>#</th><th>Дата</th><th>Услуги</th><th>Сумма</th><th>Контакт</th><th>Статус</th><th></th></tr></thead><tbody id='orderRows'></tbody></table></div></div><div class='panel' id='detailPanel'><h2>Выберите заказ</h2><p style='color:#74839b;font-size:12px'>Нажмите «Открыть».</p></div></section><section id='tariffs' class='tab'><div class='panel'><div class='panelhead'><h2>Разовые тарифы</h2><span class='online'>__NEW__ новых</span></div><div class='servicegrid' id='tariffAdmin'></div></div></section><section id='packages' class='tab'><div class='panel'><div class='panelhead'><h2>Пакеты</h2><span class='online'>__IN_PROGRESS__ в работе</span></div><div class='servicegrid' id='packageAdmin'></div></div></section><section id='stats' class='tab'><div class='cards'><div class='stat'><small>Новые</small><strong>__NEW__</strong></div><div class='stat'><small>В работе</small><strong>__IN_PROGRESS__</strong></div><div class='stat'><small>Выполнено</small><strong>__DONE__</strong></div><div class='stat'><small>Всего</small><strong>__TOTAL_ORDERS__</strong></div></div><div class='panel'><h2>Сводка</h2><p style='color:#74839b;font-size:13px;line-height:1.6'>После подключения WEBPAY сюда можно добавить оплату, конверсию и финансовые показатели.</p></div></section><section id='settings' class='tab'><div class='panel'><h2>Настройки</h2><div class='setting'><div><b>Telegram-уведомления</b><div style='color:#74839b;font-size:11px'>Новые заявки отправляются в админ-чат.</div></div><span class='pill done'>Включено</span></div><div class='setting'><div><b>Администратор</b><div style='color:#74839b;font-size:11px'>Доступ защищён ADMIN_SETUP_CODE.</div></div><span class='pill in_progress'>Защищено</span></div><div class='setting'><div><b>WEBPAY</b><div style='color:#74839b;font-size:11px'>Подключим после одобрения.</div></div><span class='pill new'>Ожидает</span></div></div></section></main></div><div class='mobilebar'><button class='active' data-tab='home'>⌂<br>Главная</button><button data-tab='orders'>▣<br>Заказы</button><button data-tab='tariffs'>◈<br>Тарифы</button><button data-tab='stats'>◌<br>Статистика</button></div><script>
const orders=__DATA__;const services=__SERVICES__;const titles={home:'Главная',orders:'Заказы',tariffs:'Тарифы',packages:'Пакеты',stats:'Статистика',settings:'Настройки'};const rub=n=>new Intl.NumberFormat('ru-RU').format(n)+' ₽';function pill(s){return `<span class='pill ${s}'>${({new:'Новая',in_progress:'В работе',done:'Выполнено',cancelled:'Отменена'})[s]||s}</span>`}function esc(v){return String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]))}function rows(list,a=false){return list.map(o=>`<tr><td><b>#${o.id}</b></td><td>${String(o.created_at).replace('T',' ').slice(0,16)}</td><td>${o.services.join(', ')||'—'}</td><td><b>${rub(o.total)}</b></td><td>${esc(o.contact)}</td><td>${pill(o.status)}</td>${a?`<td><button class='btn ghost' onclick='detail(${o.id})'>Открыть</button></td>`:''}</tr>`).join('')}function render(){homeRows.innerHTML=rows(orders.slice(0,7));renderOrders();renderServices()}function renderOrders(){const q=(search.value||'').toLowerCase(),f=filter.value;const list=orders.filter(o=>(f==='all'||o.status===f)&&((String(o.id)+' '+o.contact+' '+o.services.join(' ')).toLowerCase().includes(q)));orderRows.innerHTML=rows(list,true)||`<tr><td colspan='7'>Заказов не найдено.</td></tr>`}function renderServices(){const make=s=>`<div class='service'><div style='font-size:11px;color:#74839b'>${esc(s.tag)}</div><h3 style='margin:8px 0'>${esc(s.name)}</h3><div class='price'>${rub(s.price)}</div><ul>${s.features.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`;tariffAdmin.innerHTML=services.filter(s=>s.type!=='Пакет').map(make).join('');packageAdmin.innerHTML=services.filter(s=>s.type==='Пакет').map(make).join('')}function openTab(id){document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));document.getElementById(id).classList.add('active');document.querySelectorAll('[data-tab]').forEach(x=>x.classList.toggle('active',x.dataset.tab===id));title.textContent=titles[id];if(id==='orders')renderOrders();history.replaceState(null,'','#'+id)}function detail(id){const o=orders.find(x=>x.id===id);if(!o)return;detailPanel.innerHTML=`<div class='panelhead'><h2>Заказ #${o.id}</h2>${pill(o.status)}</div><div class='ordergrid' style='margin-top:14px'><div class='orderbox'><h3>Информация</h3><div class='row'><span>Дата</span><b>${esc(o.created_at).replace('T',' ')}</b></div><div class='row'><span>Услуги</span><b>${o.services.map(esc).join(', ')}</b></div><div class='row'><span>Сумма</span><b>${rub(o.total)}</b></div><div class='row'><span>Контакт</span><b>${esc(o.contact)}</b></div><div class='row'><span>Комментарий</span><b>${esc(o.comment)}</b></div></div><div class='orderbox'><h3>Изменить статус</h3><form method='post' action='/admin-web/orders/${o.id}/status'><select name='status' style='width:100%;padding:11px;border:1px solid #dfe8f5;border-radius:11px'><option value='new' ${o.status==='new'?'selected':''}>Новая</option><option value='in_progress' ${o.status==='in_progress'?'selected':''}>В работе</option><option value='done' ${o.status==='done'?'selected':''}>Выполнено</option><option value='cancelled' ${o.status==='cancelled'?'selected':''}>Отменена</option></select><button class='btn primary' style='margin-top:10px'>Сохранить статус</button></form></div></div>`;detailPanel.scrollIntoView({behavior:'smooth',block:'start'})}document.querySelectorAll('[data-tab]').forEach(b=>b.addEventListener('click',()=>openTab(b.dataset.tab)));search.addEventListener('input',renderOrders);filter.addEventListener('change',renderOrders);render();if(location.hash)openTab(location.hash.slice(1));</script></body></html>"""


HTML = r'''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#061321">
<title>Работа в Питере</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
:root{--bg:#03060b;--panel:#09111c;--line:#1b3146;--text:#f8fbff;--muted:#8f9db0;--gold:#ffd76a;--gold2:#fff0a8;--cyan:#42e8ff;--purple:#8b5cff;--blue:#4b83ff;--green:#27e6a0;--red:#ff6678;--shadow:0 24px 70px rgba(0,0,0,.48)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(circle at 15% -5%,#153a55 0,transparent 28%),radial-gradient(circle at 90% 8%,#39205d 0,transparent 25%),radial-gradient(circle at 50% 70%,#08283b 0,transparent 32%),#02050a;color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI",sans-serif}
button,input,textarea,select{font:inherit}button{cursor:pointer}.app{max-width:620px;margin:auto;min-height:100vh;padding-bottom:96px}
.topbar{height:72px;display:flex;align-items:center;justify-content:space-between;padding:12px 18px;position:sticky;top:0;z-index:20;background:rgba(3,11,20,.84);backdrop-filter:blur(18px);border-bottom:1px solid rgba(255,255,255,.05)}
.brand{display:flex;align-items:center;gap:10px;font-weight:900}.brandIcon{width:40px;height:40px;border:1px solid #35556d;border-radius:14px;display:grid;place-items:center;color:#fff;font-size:20px;background:linear-gradient(135deg,#0d2135,#17233e);box-shadow:0 0 22px #42e8ff18, inset 0 0 18px #8b5cff18}.brand small{display:block;color:#8494a8;font-size:10px;margin-top:1px;font-weight:600}.topActions{display:flex;gap:7px}.iconBtn{width:40px;height:40px;border:1px solid #29455d;background:linear-gradient(135deg,#0a1725,#0d1322);color:#dce6f2;border-radius:13px;box-shadow:0 0 18px #42e8ff0d}
.view{display:none;padding:14px 16px}.view.active{display:block}.hero{position:relative;overflow:hidden;border:1px solid #244158;border-radius:26px;min-height:470px;padding:28px 20px 24px;background:linear-gradient(180deg,rgba(4,15,27,.05),rgba(3,10,17,.86)),url("https://images.unsplash.com/photo-1556610961-2fecc5927173?auto=format&fit=crop&w=1200&q=85") center/cover;box-shadow:var(--shadow)}
.hero:after{content:"";position:absolute;inset:auto -25% -150px;height:300px;background:radial-gradient(ellipse,#42e8ff22,transparent 45%),radial-gradient(ellipse,#8b5cff26,transparent 62%),radial-gradient(ellipse,#ffd76a1c,transparent 70%);pointer-events:none}.badge{display:inline-flex;padding:8px 12px;border-radius:999px;background:linear-gradient(90deg,#42e8ff12,#8b5cff1c,#ffd76a14);border:1px solid #42e8ff45;color:#e8fbff;font-size:10px;font-weight:900;letter-spacing:.7px;text-transform:uppercase;box-shadow:0 0 20px #42e8ff12}
.hero h1{position:relative;z-index:1;font-family:Georgia,serif;font-size:38px;line-height:1.02;margin:20px 0 12px;max-width:470px}.hero h1 span{background:linear-gradient(90deg,#fff0a8,#42e8ff,#a98cff);-webkit-background-clip:text;background-clip:text;color:transparent}.hero p{position:relative;z-index:1;color:#d2dae4;line-height:1.5;font-size:14px;max-width:440px}.actions{display:flex;gap:10px;position:relative;z-index:1;margin-top:22px;flex-wrap:wrap}
.btn{border:1px solid #53677c;background:#091a2a;color:#fff;border-radius:15px;padding:13px 18px;font-weight:900}.btn.gold{background:linear-gradient(135deg,#fff0a8,#ffd76a 48%,#8b5cff);color:#06101b;border-color:transparent;box-shadow:0 8px 28px #ffd76a22,0 0 22px #8b5cff18}.btn.full{width:100%}
.features{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin:14px 0}.feature{padding:14px 8px;border:1px solid #1b354a;background:linear-gradient(180deg,#091a2a,#06101a);border-radius:15px;text-align:center;box-shadow:inset 0 0 22px #42e8ff06}.feature b{display:block;color:var(--cyan);font-size:17px;text-shadow:0 0 14px #42e8ff55}.feature small{display:block;color:#aab6c5;font-size:9px;line-height:1.3;margin-top:5px}
.sectionTitle{display:flex;justify-content:space-between;align-items:end;margin:24px 2px 12px}.sectionTitle h2{margin:0;font-size:22px}.sectionTitle span{color:#8393a7;font-size:11px}.tabs{display:flex;gap:7px;margin-bottom:12px}.tabBtn{border:1px solid var(--line);background:#071827;color:#95a6b8;border-radius:999px;padding:8px 13px;font-size:11px;font-weight:800}.tabBtn.active{background:linear-gradient(90deg,#ffd76a,#8b5cff);color:#071321;border-color:transparent;box-shadow:0 0 18px #8b5cff22}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}.card{position:relative;border:1px solid #214058;border-radius:18px;background:linear-gradient(180deg,#0b1d2e,#06101a);padding:14px 11px;box-shadow:0 14px 34px #00000038, inset 0 0 28px #42e8ff05}.card.hot{border-color:#ffd76a;box-shadow:0 14px 34px #00000038,0 0 24px #ffd76a18,inset 0 0 28px #ffd76a07}.card h3{font-size:14px;margin:0 0 4px}.price{font-size:21px;color:var(--gold2);font-weight:950;margin:5px 0 10px}.card ul{list-style:none;padding:0;margin:0 0 13px;color:#aab6c5;font-size:9px;line-height:1.65}.card li:before{content:"◉";color:var(--gold);font-size:6px;margin-right:5px;vertical-align:middle}.miniBtn{width:100%;border:0;border-radius:11px;padding:10px;background:linear-gradient(135deg,#fff0a8,#ffd76a,#8b5cff);color:#071321;font-size:10px;font-weight:950;box-shadow:0 0 18px #ffd76a18}.tag{position:absolute;right:9px;top:9px;background:linear-gradient(90deg,#ffd76a,#fff0a8);color:#071321;padding:4px 7px;border-radius:7px;font-size:8px;font-weight:950;box-shadow:0 0 16px #ffd76a55}
.channelCard{position:relative;display:flex;align-items:center;gap:14px;margin-top:15px;overflow:hidden;border:1px solid #6b39ff;border-radius:21px;padding:17px;background:radial-gradient(circle at 85% 15%,#ff2fb34a,transparent 28%),radial-gradient(circle at 20% 100%,#1f8dff38,transparent 34%),linear-gradient(120deg,#081a31,#17113a 55%,#230d35);box-shadow:0 14px 38px #00000044,0 0 28px #8b5cff1e,inset 0 0 35px #42e8ff08}.channelGlow{position:absolute;inset:-60px auto auto 35%;width:220px;height:160px;background:radial-gradient(circle,#8b5cff28,transparent 65%);pointer-events:none}.channelIcon{position:relative;z-index:1;width:68px;height:68px;flex:0 0 68px;border-radius:50%;display:grid;place-items:center;font-size:33px;color:#fff;background:linear-gradient(135deg,#29d9ff,#376cff 52%,#8b5cff);border:1px solid #74edff;box-shadow:0 0 28px #42e8ff66,0 0 45px #8b5cff35}.channelBody{position:relative;z-index:1;min-width:0;flex:1}.channelBadge{display:inline-flex;padding:5px 8px;border-radius:999px;border:1px solid #42e8ff66;background:#42e8ff10;color:#55eaff;font-size:8px;font-weight:900}.channelBody h3{margin:7px 0 4px;font-size:17px}.channelBody p{margin:0 0 11px;color:#c1cada;font-size:10px;line-height:1.45}.channelBtn{width:100%;border:1px solid #a95cff;background:linear-gradient(90deg,#7b32ff,#c52dff);color:#fff;border-radius:12px;padding:10px 12px;font-size:10px;font-weight:950;box-shadow:0 0 22px #8b5cff30}.channelBtn b{float:right;font-size:15px;line-height:10px}.cta{margin-top:15px;border:1px solid #29445b;border-radius:19px;padding:18px;background:linear-gradient(100deg,#0b2033aa,#071321dd),url("https://images.unsplash.com/photo-1513326738677-b964603b136d?auto=format&fit=crop&w=900&q=80") center/cover}.cta h3{margin:0 0 7px}.cta p{font-size:11px;color:#b7c3d1;margin:0 0 12px}
.wheelPromo{display:flex;align-items:center;gap:12px;margin-top:15px;padding:13px 14px;border:1px solid #5d4b2b;border-radius:17px;background:linear-gradient(110deg,#17141a,#11182a);box-shadow:0 10px 25px #0006;cursor:pointer}.wheelPromoIcon{width:44px;height:44px;border-radius:13px;display:grid;place-items:center;background:linear-gradient(135deg,#ffd86a,#9c6a24);font-size:24px}.wheelPromo div:nth-child(2){flex:1}.wheelPromo b{display:block;font-size:13px}.wheelPromo small{display:block;color:#8998aa;font-size:10px;margin-top:3px}.wheelPromo>span{color:#ffd76a;font-size:22px}.wheelHead{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}.wheelHead h2{margin:0;font-size:23px;letter-spacing:.5px}.wheelHead span{display:block;color:#8291a2;font-size:10px;margin-top:4px}.starBalance{padding:9px 12px;border-radius:999px;border:1px solid #5e4a24;background:#15130f;color:#ffe29a;font-weight:950;white-space:nowrap}.wheelCard{border:1px solid #72572c;border-radius:24px;background:radial-gradient(circle at 50% 42%,#3b2947 0,#171526 28%,#090e18 62%);padding:18px 14px 20px;text-align:center;box-shadow:0 18px 45px #0008,inset 0 0 40px #d3a44710}.wheelTitle{font-size:19px;font-weight:950;color:#f4d889;margin-bottom:8px}.wheelWrap{position:relative;width:min(330px,88vw);aspect-ratio:1;margin:0 auto 18px;display:grid;place-items:center}.wheel{width:100%;height:100%;border-radius:50%;padding:12px;box-sizing:border-box;background:conic-gradient(from -36deg,#164b7a 0 72deg,#8e1020 72deg 144deg,#08703f 144deg 216deg,#4b287f 216deg 288deg,#164b7a 288deg 360deg);border:11px solid #c89a45;box-shadow:0 0 0 4px #6d4d22,0 0 28px #d8a83c2e,inset 0 0 0 3px #f8d77855;position:relative;transition:transform 4.8s cubic-bezier(.12,.75,.15,1)}.wheel:before{content:"";position:absolute;inset:0;border-radius:50%;background:repeating-conic-gradient(from -36deg,transparent 0 70.5deg,#f8d778aa 70.5deg 72deg);pointer-events:none}.wheel:after{content:"";position:absolute;inset:10px;border-radius:50%;border:2px solid #f2d27a66;pointer-events:none}.wheelLabel{position:absolute;z-index:1;width:112px;text-align:center;color:#f4e8d0;font-size:10px;line-height:1.12;font-weight:950;letter-spacing:.1px;text-shadow:0 2px 3px #000,0 0 6px #000;pointer-events:none}.wheelLabel i{display:block;font-style:normal;font-size:24px;line-height:1;margin-bottom:5px}.wheelLabel b{font-size:9.5px}.l1{left:50%;top:19%;transform:translate(-50%,-50%)}.l2{left:76%;top:39%;transform:translate(-50%,-50%)}.l3{left:75%;top:68%;transform:translate(-50%,-50%)}.l4{left:25%;top:68%;transform:translate(-50%,-50%)}.l5{left:24%;top:39%;transform:translate(-50%,-50%)}.wheelInner{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:92px;height:92px;border-radius:50%;display:grid;place-items:center;align-content:center;background:radial-gradient(circle at 35% 30%,#f7d97e,#8e6225 68%,#4b3217);border:7px solid #d0a44f;box-shadow:0 0 0 3px #5c411e,0 0 25px #f0c85c40;z-index:2}.wheelInner b{font-size:24px;color:#24180d;letter-spacing:2px}.wheelInner small{font-size:7px;color:#4e3214;font-weight:950;letter-spacing:2px}.pointer{position:absolute;z-index:4;top:-5px;left:50%;transform:translateX(-50%);width:0;height:0;border-left:17px solid transparent;border-right:17px solid transparent;border-top:34px solid #ffe18a;filter:drop-shadow(0 4px 5px #000)}.spinBtn{width:min(330px,90%);border:1px solid #b88a39;border-radius:14px;padding:14px;background:linear-gradient(180deg,#f3cf70,#a87327);color:#21170d;font-size:13px;font-weight:950;letter-spacing:.4px}.spinBtn:disabled{opacity:.55}.wheelNote{margin-top:10px;color:#9ba7b5;font-size:10px}.starPanel{margin-top:12px;border:1px solid #2b3f53;border-radius:20px;padding:15px;background:#071522}.starPanelTop{display:flex;align-items:center;justify-content:space-between;gap:10px}.starPanelTop b{display:block;font-size:14px}.starPanelTop small{display:block;color:#8190a2;font-size:9px;margin-top:3px}.starPanelTop strong{font-size:19px;color:#ffd86a}.packGrid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:13px}.packGrid button{border:1px solid #3d4c61;background:#0b1b2b;color:#fff;border-radius:13px;padding:12px 5px}.packGrid b{display:block;color:#ffd86a;font-size:14px}.packGrid small{display:block;color:#8494a7;font-size:9px;margin-top:3px}.wheelRules{margin-top:11px;color:#78889b;font-size:9px;line-height:1.45}.winModal{position:fixed;z-index:90;inset:0;display:none;place-items:center;background:#02050bc9;padding:20px}.winBox{width:min(360px,100%);border:1px solid #a57b35;border-radius:24px;background:linear-gradient(150deg,#151326,#091827);padding:24px;text-align:center;box-shadow:0 25px 70px #000}.winBox .big{font-size:48px}.winBox h3{font-size:22px;margin:8px 0}.winBox p{color:#93a1b2;font-size:11px}.winBox button{width:100%;margin-top:10px}.inventoryCard{margin-top:12px;border:1px solid #72572c;border-radius:20px;background:linear-gradient(145deg,#121523,#081421);padding:15px}.inventoryHead{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}.inventoryHead h3{margin:0;font-size:16px}.inventoryHead span{color:#ffd86a;font-size:11px}.inventoryEmpty{padding:20px 8px;text-align:center;color:#8493a5;font-size:11px;line-height:1.5}.inventoryItem{display:flex;align-items:center;gap:11px;padding:12px;border:1px solid #2c4054;border-radius:15px;background:#091827;margin-top:8px}.inventoryIcon{width:42px;height:42px;flex:0 0 42px;border-radius:13px;display:grid;place-items:center;background:linear-gradient(145deg,#3b2b14,#a9762d);font-size:22px}.inventoryMain{min-width:0;flex:1}.inventoryMain b{display:block;font-size:12px}.inventoryMain small{display:block;color:#8392a5;font-size:9px;margin-top:3px}.inventoryAction{border:1px solid #b98a38;background:linear-gradient(180deg,#f3cf70,#a87327);color:#21170d;border-radius:10px;padding:9px 10px;font-size:9px;font-weight:950;white-space:nowrap}.inventoryUsed{color:#7e91a5;font-size:9px;font-weight:800}.inventoryCode{margin-top:7px;padding:8px;border-radius:9px;background:#111b28;color:#ffd86a;font-size:11px;font-weight:950;letter-spacing:1px;text-align:center}.list{display:grid;gap:9px}.rowCard{display:flex;align-items:center;justify-content:space-between;gap:10px;border:1px solid var(--line);background:#071827;border-radius:16px;padding:13px}.rowCard .left{min-width:0}.rowCard b{display:block}.rowCard small{color:#8fa0b3;font-size:10px}.qty{display:flex;align-items:center;gap:7px}.qty button{width:27px;height:27px;border-radius:9px;border:1px solid #304960;background:#0b2135;color:#fff}
.sum{margin-top:12px;border:1px solid #28455c;background:#071827;border-radius:19px;padding:17px}.sumline{display:flex;justify-content:space-between;margin:7px 0;color:#aeb9c7}.sumline.total{font-size:20px;color:var(--gold2);font-weight:950;border-top:1px solid var(--line);padding-top:13px;margin-top:12px}
.form{display:grid;gap:10px}.form input,.form textarea,.form select{width:100%;border:1px solid #29455d;background:#071827;color:#fff;border-radius:13px;padding:13px;outline:none}.form textarea{min-height:90px;resize:vertical}
.profileHead{display:flex;align-items:center;gap:13px;padding:18px;border:1px solid var(--line);border-radius:19px;background:linear-gradient(120deg,#0c2236,#071522)}.avatar{width:54px;height:54px;border-radius:50%;display:grid;place-items:center;background:linear-gradient(135deg,#caa45c,#ffe7a5);color:#091321;font-size:22px;font-weight:950}.profileName{font-weight:950}.muted{color:#91a0b1;font-size:11px}.profileList{margin-top:10px;border:1px solid var(--line);border-radius:18px;background:#071827;overflow:hidden}.profileItem{display:flex;align-items:center;justify-content:space-between;padding:15px;border-bottom:1px solid var(--line)}.profileItem:last-child{border:0}.profileItem b{font-size:12px}.profileItem small{display:block;color:#7f90a4;margin-top:3px}
.empty{padding:28px 16px;text-align:center;color:#8293a6;border:1px dashed #2b465d;border-radius:17px}.adminHero{border:1px solid #4b4967;background:linear-gradient(135deg,#101f31,#121027 55%,#071321);border-radius:22px;padding:19px;box-shadow:0 0 30px #8b5cff10,inset 0 0 30px #42e8ff05}.lock{font-size:26px;color:var(--gold)}.adminHero h2{margin:8px 0 4px}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:12px}.stat{border:1px solid var(--line);background:#071827;border-radius:15px;padding:13px}.stat small{color:#7f91a5;font-size:9px}.stat b{display:block;font-size:20px;margin-top:5px;color:var(--gold2)}.adminActions{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:12px}.starsRevenue{margin-top:14px;border:1px solid #4b4967;background:linear-gradient(135deg,#111d2b,#151126);border-radius:20px;padding:15px;box-shadow:0 0 28px #ffd76a08}.starsRevenueGrid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:11px}.starsMetric{border:1px solid #2a3f53;background:#071827;border-radius:15px;padding:12px}.starsMetric small{display:block;color:#7f91a5;font-size:9px}.starsMetric b{display:block;color:var(--gold2);font-size:19px;margin-top:5px}.starsHint{margin-top:9px;color:#7f91a5;font-size:9px;line-height:1.45}.adminAction{border:1px solid var(--line);background:#071827;color:#d9e3ee;border-radius:14px;padding:13px 5px;text-align:center;font-size:9px}.adminAction strong{display:block;color:var(--gold);font-size:18px;margin-bottom:4px}.orderAdmin{border:1px solid #203b52;background:#071827;border-radius:16px;padding:13px}.orderTop{display:flex;justify-content:space-between;gap:10px}.orderMeta{color:#8192a5;font-size:9px;margin-top:3px}.status{font-size:9px;font-weight:950;padding:6px 8px;border-radius:999px;white-space:nowrap}.s-new{background:#f5d38a;color:#071321}.s-in_progress{background:#285eaa;color:#dcecff}.s-done{background:#1d744d;color:#dcffed}.s-cancelled{background:#7b3040;color:#ffe3e8}.orderInfo{margin-top:9px;color:#b5c1ce;font-size:10px;line-height:1.55}.orderControls{display:flex;gap:6px;margin-top:10px}.orderControls select{flex:1;border:1px solid #2a455d;background:#0a1d2f;color:#fff;border-radius:10px;padding:8px;font-size:10px}.orderControls button{border:0;border-radius:10px;background:var(--gold);color:#071321;font-weight:950;padding:8px 11px;font-size:10px}.usersPanel{margin-top:14px}.userCard{display:flex;align-items:center;gap:11px;border:1px solid #203b52;background:#071827;border-radius:16px;padding:12px}.userAvatar{width:38px;height:38px;flex:0 0 38px;border-radius:50%;display:grid;place-items:center;background:linear-gradient(135deg,#42e8ff,#8b5cff);color:#fff;font-weight:950}.userMain{min-width:0;flex:1}.userMain b{display:block;font-size:11px}.userMain small{display:block;color:#8192a5;font-size:9px;margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.userDate{color:#8f9db0;font-size:9px;text-align:right}.bottom{position:fixed;z-index:50;left:50%;transform:translateX(-50%);bottom:9px;width:min(590px,calc(100% - 18px));padding:7px;border:1px solid #29485f;border-radius:22px;background:rgba(4,10,18,.91);backdrop-filter:blur(22px);box-shadow:0 15px 45px #000b,0 0 28px #42e8ff0d;display:flex;gap:3px}.nav{flex:1;border:0;background:transparent;color:#7f91a6;border-radius:15px;padding:8px 3px 7px;font-size:8px;font-weight:800}.nav .ico{display:block;font-size:17px;margin-bottom:3px}.nav.active{background:linear-gradient(135deg,#102c42,#1b1740);color:#fff0a8;box-shadow:inset 0 0 18px #42e8ff0b}.nav.admin{color:#ffd76a;text-shadow:0 0 10px #ffd76a44}.toast{position:fixed;z-index:80;left:50%;transform:translateX(-50%);bottom:90px;width:min(500px,calc(100% - 30px));padding:13px 15px;border-radius:14px;background:#10273a;border:1px solid #31516b;color:#fff;text-align:center;font-size:12px;display:none}
@media(min-width:700px){.app{max-width:1100px}.view{padding:20px}.hero{min-height:520px;padding:40px}.hero h1{font-size:50px}.cards{gap:14px}.card{padding:18px}.bottom{width:min(650px,calc(100% - 30px))}}@media(max-width:380px){.hero h1{font-size:33px}.features{grid-template-columns:repeat(2,1fr)}.cards{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}.adminActions{grid-template-columns:repeat(2,1fr)}.starsRevenueGrid{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<div class="app">
<header class="topbar"><div class="brand"><div class="brandIcon">♜</div><div>Работа в Питере<small>mini app</small></div></div><div class="topActions"><button class="iconBtn" onclick="showToast('Работаем ежедневно')">✦</button><button class="iconBtn" onclick="go('profile')">⋯</button></div></header>

<section id="home" class="view active"><div class="hero"><div class="badge">Публичные вакансии</div><h1>Найдите лучших<br>сотрудников в <span>Санкт-Петербурге</span></h1><p>Современные инструменты, AI-визуализация, целевой охват и быстрая публикация.</p><div class="actions"><button class="btn gold" onclick="go('tariffs')">Выбрать тариф →</button><button class="btn" onclick="showHow()">Как это работает</button></div></div><div class="features"><div class="feature"><b>◎</b><small>СПб и ЛО<br>Региональный охват</small></div><div class="feature"><b>✧</b><small>AI-визуализация<br>Уникальные креативы</small></div><div class="feature"><b>◉</b><small>Быстрый запуск<br>В течение 15 минут</small></div><div class="feature"><b>♧</b><small>Поддержка<br>24/7</small></div></div><div class="sectionTitle"><h2>Наши тарифы</h2><span>Выберите подходящий вариант</span></div><div class="tabs"><button class="tabBtn active">Тарифы</button><button class="tabBtn" onclick="go('packages')">Пакеты</button></div><div id="homeCards" class="cards"></div><div class="wheelPromo" onclick="go('wheel')"><div class="wheelPromoIcon">🎡</div><div><b>Колесо удачи</b><small>1 бесплатная попытка сегодня • потом 5 ⭐</small></div><span>→</span></div><div class="channelCard"><div class="channelGlow"></div><div class="channelIcon">✈</div><div class="channelBody"><span class="channelBadge">Официальный канал</span><h3>💼 Работа в Питере | Вакансии</h3><p>Свежие вакансии Санкт-Петербурга, новости и новые предложения каждый день.</p><button class="channelBtn" onclick="openChannel()">Перейти в Telegram-канал <b>→</b></button></div></div><div class="cta"><h3>Готовы найти свою команду?</h3><p>Оставьте заявку — мы подберём лучший формат размещения под вашу задачу.</p><button class="btn gold" onclick="go('tariffs')">Оставить заявку</button></div></section>

<section id="wheel" class="view"><div class="wheelHead"><div><h2>КОЛЕСО УДАЧИ</h2><span>1 бесплатная попытка каждый день</span></div><div class="starBalance" id="wheelBalance">0 ⭐</div></div><div class="wheelCard"><div class="wheelTitle">Испытай удачу</div><div class="wheelWrap"><div class="pointer" aria-hidden="true"></div><div class="wheel" id="wheelDisk"><div class="wheelLabel l1"><i>😄</i><b>ПОПРОБУЙ<br>ЗАВТРА</b></div><div class="wheelLabel l2"><i>🎟️</i><b>−10%<br>СКИДКА</b></div><div class="wheelLabel l3"><i>🎁</i><b>−20%<br>СКИДКА</b></div><div class="wheelLabel l4"><i>⭐</i><b>БОНУС<br>К ЗАКАЗУ</b></div><div class="wheelLabel l5"><i>🆓</i><b>БЕСПЛАТНОЕ<br>РАЗМЕЩЕНИЕ</b></div><div class="wheelInner"><b>SPB</b><small>УДАЧА</small></div></div></div><button class="spinBtn" id="spinBtn" onclick="spinWheel()">КРУТИТЬ КОЛЕСО</button><div class="wheelNote" id="wheelNote">После бесплатной попытки — 5 ⭐ за вращение.</div></div><div class="starPanel"><div class="starPanelTop"><div><b>⭐ Баланс</b><small>Внутренний баланс для платных вращений</small></div><strong id="starBalanceLarge">0 ⭐</strong></div><div class="packGrid"><button onclick="buyStars(25)"><b>25 ⭐</b><small>5 вращений</small></button><button onclick="buyStars(50)"><b>50 ⭐</b><small>10 вращений</small></button><button onclick="buyStars(100)"><b>100 ⭐</b><small>20 вращений</small></button></div><div class="wheelRules">Бесплатная попытка доступна раз в сутки. После неё — 5 ⭐ за вращение.</div></div></section>

<section id="tariffs" class="view"><div class="sectionTitle"><div><h2>Тарифы</h2><span>Разовое размещение вакансии</span></div></div><div id="tariffCards" class="cards"></div></section>
<section id="packages" class="view"><div class="sectionTitle"><div><h2>Пакеты</h2><span>Готовые решения для регулярного найма</span></div></div><div id="packageCards" class="list"></div></section>
<section id="cart" class="view"><div class="sectionTitle"><div><h2>Корзина <span id="cartCount"></span></h2><span onclick="clearCart()" style="cursor:pointer;color:var(--gold)">Очистить</span></div></div><div id="cartList" class="list"></div><div id="cartSummary"></div></section>

<section id="profile" class="view"><div class="sectionTitle"><div><h2>Профиль</h2><span>Ваши заявки и настройки</span></div></div><div class="profileHead"><div class="avatar" id="avatar">Р</div><div><div class="profileName" id="profileName">Работодатель</div><div class="muted">Клиент сервиса «Работа в Питере»</div></div></div><div class="profileList"><div class="profileItem" onclick="showHistory()"><div><b>📋 Мои заказы</b><small>История отправленных заявок</small></div><b>›</b></div><div class="profileItem" onclick="showHow()"><div><b>💡 Как это работает</b><small>От заявки до публикации</small></div><b>›</b></div><div class="profileItem" onclick="go('wheel')"><div><b>🎡 Колесо удачи</b><small>Бесплатная попытка + вращения за ⭐</small></div><b>›</b></div><div class="profileItem" onclick="showInventory()"><div><b>🎁 Мои выигрыши</b><small>Призы, скидки и бесплатные размещения</small></div><b>›</b></div><div class="profileItem" onclick="openChannel()"><div><b>📢 Наш Telegram-канал</b><small>Вакансии и новости Санкт-Петербурга</small></div><b>›</b></div><div class="profileItem" onclick="openSupport()"><div><b>💬 Поддержка</b><small>Написать администратору в Telegram</small></div><b>›</b></div></div><div id="inventoryPanel" class="inventoryCard" style="display:none"><div class="inventoryHead"><h3>🎁 Мои выигрыши</h3><span id="inventoryCount">0</span></div><div id="inventoryList"></div></div><div id="history"></div><div class="cta"><h3>Нужна помощь?</h3><p>Свяжитесь с нами по любому вопросу по размещению вакансии.</p><button class="btn gold" onclick="openSupport()">Написать администратору →</button></div></section>

<section id="checkout" class="view"><div class="sectionTitle"><div><h2>Оформление заявки</h2><span id="checkoutChosen">Выбранные услуги</span></div></div><div class="form"><input id="contact" placeholder="Ваш Telegram / телефон" autocomplete="off"><textarea id="comment" placeholder="Комментарий (необязательно)"></textarea><button class="btn gold full" onclick="sendOrder()">Отправить заявку →</button></div><div id="result"></div></section>

<section id="admin" class="view"><div class="adminHero"><div class="lock">♛</div><h2>Админ-панель</h2><div class="muted">Только для владельца сервиса</div><div class="stats"><div class="stat"><small>Сегодня</small><b id="aToday">0</b><small>заявок</small></div><div class="stat"><small>Всего</small><b id="aTotal">0</b><small>заявок</small></div><div class="stat"><small>Выручка</small><b id="aRevenue">0 ₽</b><small>за всё время</small></div></div></div><div class="adminActions"><button class="adminAction" onclick="loadAdmin()"><strong>↻</strong>Обновить</button><button class="adminAction" onclick="filterAdmin('new')"><strong id="aNew">0</strong>Новые</button><button class="adminAction" onclick="filterAdmin('in_progress')"><strong id="aWork">0</strong>В работе</button><button class="adminAction" onclick="filterAdmin('done')"><strong id="aDone">0</strong>Выполнено</button><button class="adminAction" onclick="showUsers()"><strong id="aUsers">0</strong>Пользователи</button></div><div class="starsRevenue"><div class="sectionTitle"><h2>💰 Доход / Stars</h2><span>реальный баланс бота</span></div><div class="starsRevenueGrid"><div class="starsMetric"><small>Баланс бота</small><b id="aStarsBalance">—</b></div><div class="starsMetric"><small>Получено через приложение</small><b id="aStarsReceived">0 ⭐</b></div><div class="starsMetric"><small>Сегодня</small><b id="aStarsToday">0 ⭐</b></div><div class="starsMetric"><small>Платежей</small><b id="aStarsPayments">0</b></div></div><div class="starsHint">«Баланс бота» берётся напрямую из Telegram Bot API. Остальные показатели — оплаты, записанные нашим сервисом. Это реальные Stars бота, а не внутренний баланс пользователей.</div></div><div id="usersPanel" class="usersPanel" style="display:none"><div class="sectionTitle"><h2>Пользователи</h2><span id="usersTotal">0 запустили бота</span></div><div id="adminUsers" class="list"></div></div><div class="sectionTitle"><h2>Последние заказы</h2><span>до 100</span></div><div id="adminOrders" class="list"></div></section>
</div>

<nav class="bottom"><button class="nav active" data-go="home"><span class="ico">⌂</span>Главная</button><button class="nav" data-go="tariffs"><span class="ico">◎</span>Тарифы</button><button class="nav" data-go="packages"><span class="ico">◇</span>Пакеты</button><button class="nav" data-go="cart"><span class="ico">🛒</span>Корзина <span id="navCount"></span></button><button class="nav" data-go="profile"><span class="ico">♙</span>Профиль</button><button class="nav admin" id="adminNav" data-go="admin" style="display:none"><span class="ico">♛</span>Админка</button></nav>
<div id="toast" class="toast"></div>
<div id="winModal" class="winModal"><div class="winBox"><div class="big" id="winEmoji">🎉</div><h3 id="winTitle">Поздравляем!</h3><p id="winText"></p><button class="btn gold full" id="winInventoryBtn" style="display:none" onclick="openInventoryFromWin()">🎁 Открыть инвентарь</button><button class="btn full" onclick="closeWin()">Закрыть</button></div></div>

<script>
const tg=window.Telegram&&window.Telegram.WebApp?window.Telegram.WebApp:null;if(tg){tg.ready();tg.expand();try{tg.setHeaderColor('#070b13');tg.setBackgroundColor('#03060b')}catch(e){}}
const initData=tg?.initData||'';let services=[],cart=JSON.parse(localStorage.getItem('workspb_cart')||'[]'),orders=JSON.parse(localStorage.getItem('workspb_orders')||'[]'),adminData=null,adminFilter='all';
const rub=n=>new Intl.NumberFormat('ru-RU').format(n)+' ₽',byId=id=>services.find(s=>s.id===id);function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}function apiHeaders(){return {'X-Telegram-Init-Data':initData,'Content-Type':'application/json'}}function showToast(msg){const x=document.getElementById('toast');x.textContent=msg;x.style.display='block';clearTimeout(window.__toast);window.__toast=setTimeout(()=>x.style.display='none',2600)}
async function loadWheel(){try{const r=await fetch('/api/wheel/status',{headers:apiHeaders()});const d=await r.json();if(!r.ok){showToast(d.message||'Откройте приложение в Telegram');return}document.getElementById('wheelBalance').textContent=d.balance+' ⭐';document.getElementById('starBalanceLarge').textContent=d.balance+' ⭐';document.getElementById('wheelNote').textContent=d.free_available?'Сегодня доступна бесплатная попытка.':'Бесплатная попытка уже использована • следующее вращение 5 ⭐.'}catch(e){showToast('Не удалось загрузить баланс')}}
async function buyStars(stars){try{const r=await fetch('/api/stars/invoice',{method:'POST',headers:apiHeaders(),body:JSON.stringify({stars})});const d=await r.json();if(!r.ok){showToast(d.message||'Не удалось создать счёт');return}if(tg&&typeof tg.openInvoice==='function'){tg.openInvoice(d.invoice_url,status=>{if(status==='paid'){showToast('⭐ Оплата прошла');setTimeout(loadWheel,700)}})}else{window.location.href=d.invoice_url}}catch(e){showToast('Ошибка оплаты Stars')}}
async function spinWheel(){const btn=document.getElementById('spinBtn');if(btn.disabled)return;btn.disabled=true;try{const r=await fetch('/api/wheel/spin',{method:'POST',headers:apiHeaders(),body:'{}'});const d=await r.json();if(r.status===402&&d.need_stars){btn.disabled=false;showToast('Нужно 5 ⭐ за платное вращение');return}if(!r.ok){btn.disabled=false;showToast(d.message||'Не удалось прокрутить колесо');return}const disk=document.getElementById('wheelDisk');const sectorMap={empty:0,discount10:1,discount20:2,bonus:3,free:4};const sector=sectorMap[d.prize.key]??0;const turns=6+Math.floor(Math.random()*3);const stop=(270-sector*72)%360;disk.style.transform=`rotate(${turns*360+stop}deg)`;setTimeout(()=>{document.getElementById('winTitle').textContent=d.prize.title;document.getElementById('winText').textContent=(d.prize.key==='empty'?'🙂 Ничего не выиграно. ': '🎁 Приз сохранён в ваш инвентарь. ')+(d.paid?'Списано 5 ⭐ с баланса.':'Бесплатная попытка использована.');document.getElementById('winEmoji').textContent=d.prize.key==='empty'?'🙂':d.prize.key==='free'?'🎁':'⭐';document.getElementById('winInventoryBtn').style.display=d.inventory_id?'block':'none';document.getElementById('winModal').style.display='grid';btn.disabled=false;loadWheel()},4900)}catch(e){btn.disabled=false;showToast('Ошибка вращения')}}
async function showInventory(){const panel=document.getElementById('inventoryPanel');panel.style.display='block';panel.scrollIntoView({behavior:'smooth',block:'start'});const box=document.getElementById('inventoryList');box.innerHTML='<div class="inventoryEmpty">Загрузка…</div>';try{const r=await fetch('/api/inventory',{headers:apiHeaders()});const d=await r.json();if(!r.ok){box.innerHTML='<div class="inventoryEmpty">Не удалось загрузить инвентарь.</div>';return}document.getElementById('inventoryCount').textContent=d.items.length+' шт.';if(!d.items.length){box.innerHTML='<div class="inventoryEmpty">Здесь будут храниться ваши выигрыши после колеса удачи.</div>';return}box.innerHTML=d.items.map(i=>{const date=new Date(i.won_at).toLocaleDateString('ru-RU');if(i.status==='activated'){return `<div class="inventoryItem"><div class="inventoryIcon">${i.emoji}</div><div class="inventoryMain"><b>${esc(i.title)}</b><small>Выигрыш от ${date}</small><div class="inventoryCode">Код: ${esc(i.activation_code)}</div></div><span class="inventoryUsed">АКТИВИРОВАН</span></div>`}return `<div class="inventoryItem"><div class="inventoryIcon">${i.emoji}</div><div class="inventoryMain"><b>${esc(i.title)}</b><small>Выигрыш от ${date}</small></div><button class="inventoryAction" onclick="activatePrize(${i.id})">Активировать</button></div>`}).join('')}catch(e){box.innerHTML='<div class="inventoryEmpty">Ошибка загрузки инвентаря.</div>'}}
async function activatePrize(id){try{const r=await fetch('/api/inventory/'+id+'/activate',{method:'POST',headers:apiHeaders(),body:'{}'});const d=await r.json();if(!r.ok){showToast(d.message||'Не удалось активировать приз');return}await showInventory();showToast('🎁 Приз активирован. Код показан в инвентаре.')}catch(e){showToast('Ошибка активации')}}
function closeWin(){document.getElementById('winModal').style.display='none'}
function openInventoryFromWin(){closeWin();go('profile');setTimeout(()=>showInventory(),80)}
function openChannel(){const url='https://t.me/worksaintpeterburg';if(tg&&tg.openTelegramLink){tg.openTelegramLink(url)}else{window.open(url,'_blank')}}function go(id){document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));document.getElementById(id).classList.add('active');document.querySelectorAll('.nav').forEach(x=>x.classList.toggle('active',x.dataset.go===id));window.scrollTo({top:0,behavior:'smooth'});if(id==='cart')renderCart();if(id==='profile')renderProfile();if(id==='admin')loadAdmin();if(id==='checkout')renderCheckout();if(id==='wheel')loadWheel()}
function card(s){return `<article class="card ${s.id===2?'hot':''}">${s.id===2?'<span class="tag">Хит</span>':''}<h3>${esc(s.name)}</h3><div class="price">${rub(s.price)}</div><ul>${s.features.slice(0,4).map(f=>`<li>${esc(f)}</li>`).join('')}</ul><button class="miniBtn" onclick="add(${s.id})">Выбрать</button></article>`}
function packageCard(s){return `<div class="rowCard"><div class="left"><b>${esc(s.name)}</b><small>${esc(s.subtitle)}</small><div class="price" style="font-size:19px;margin:5px 0">${rub(s.price)}</div><small>${s.features.slice(0,4).map(esc).join(' · ')}</small></div><button class="btn gold" onclick="add(${s.id})">Выбрать</button></div>`}
function renderTariffs(){const ts=services.filter(s=>s.type==='Разовое размещение');document.getElementById('tariffCards').innerHTML=ts.map(card).join('');document.getElementById('homeCards').innerHTML=ts.map(card).join('')}function renderPackages(){document.getElementById('packageCards').innerHTML=services.filter(s=>s.type==='Пакет').map(packageCard).join('')}
function add(id){if(!cart.includes(id))cart.push(id);localStorage.setItem('workspb_cart',JSON.stringify(cart));renderCart();showToast('Добавлено в корзину')}function remove(id){cart=cart.filter(x=>x!==id);localStorage.setItem('workspb_cart',JSON.stringify(cart));renderCart()}function clearCart(){cart=[];localStorage.setItem('workspb_cart','[]');renderCart()}
function renderCart(){const list=document.getElementById('cartList');document.getElementById('cartCount').textContent=cart.length?`(${cart.length})`:'';document.getElementById('navCount').textContent=cart.length?` ${cart.length}`:'';if(!cart.length){list.innerHTML='<div class="empty">🛒<br><br>Корзина пока пуста.<br>Выберите тариф или пакет.</div>';document.getElementById('cartSummary').innerHTML='';return}list.innerHTML=cart.map(id=>{const s=byId(id);return `<div class="rowCard"><div class="left"><b>${esc(s.name)}</b><small>${esc(s.subtitle)}</small></div><div class="qty"><b>${rub(s.price)}</b><button onclick="remove(${id})">×</button></div></div>`}).join('');const total=cart.reduce((a,id)=>a+byId(id).price,0);document.getElementById('cartSummary').innerHTML=`<div class="sum"><div class="sumline total"><span>Итого</span><b>${rub(total)}</b></div><button class="btn gold full" onclick="go('checkout')">Оформить заявку →</button></div>`}
function renderCheckout(){if(!cart.length){go('cart');return}document.getElementById('checkoutChosen').textContent='Выбрано: '+cart.map(id=>byId(id).name).join(', ')+' · '+rub(cart.reduce((a,id)=>a+byId(id).price,0))}
function sendOrder(){const c=document.getElementById('contact').value.trim(),comment=document.getElementById('comment').value.trim();if(!c){showToast('Укажите контакт');document.getElementById('contact').focus();return}fetch('/api/checkout',{method:'POST',headers:apiHeaders(),body:JSON.stringify({service_ids:cart,contact:c,comment})}).then(r=>r.json()).then(d=>{if(!d.ok){showToast(d.message||'Ошибка');return}orders.unshift({id:d.order_id,total:d.total,contact:c,comment,created_at:new Date().toISOString(),services:cart.map(id=>byId(id).name)});localStorage.setItem('workspb_orders',JSON.stringify(orders.slice(0,20)));document.getElementById('result').innerHTML=`<div class="sum" style="border-color:#2e7b5b;margin-top:12px">✅ Заявка #${d.order_id} отправлена.<br><small>Мы свяжемся с вами для подтверждения.</small></div>`;cart=[];localStorage.setItem('workspb_cart','[]');document.getElementById('contact').value='';document.getElementById('comment').value='';renderCart()})}
function renderProfile(){const u=tg?.initDataUnsafe?.user;if(u){document.getElementById('profileName').textContent=(u.first_name||'Пользователь')+(u.last_name?' '+u.last_name:'');document.getElementById('avatar').textContent=(u.first_name||'Р').slice(0,1).toUpperCase()}}
function showHistory(){const h=document.getElementById('history');if(!orders.length){h.innerHTML='<div class="empty">📋 История заявок появится после первой отправки.</div>';return}h.innerHTML='<h3 style="margin:18px 0 9px">Мои заказы</h3><div class="list">'+orders.map(o=>`<div class="rowCard"><div class="left"><b>Заказ #${o.id}</b><small>${esc(o.services?.join(', '))} · ${new Date(o.created_at).toLocaleDateString('ru-RU')}</small></div><b>${rub(o.total)}</b></div>`).join('')+'</div>'}
function showHow(){showToast('Выберите тариф → заполните контакт → отправьте заявку → менеджер свяжется с вами.')}
function openSupport(){const url='https://t.me/RZTFrong';try{if(tg&&typeof tg.openTelegramLink==='function'){tg.openTelegramLink(url);return}}catch(e){}window.location.href=url;}
async function checkAdmin(){try{const r=await fetch('/api/admin/me',{headers:apiHeaders()});const d=await r.json();if(d.admin){document.getElementById('adminNav').style.display='block';return true}}catch(e){}return false}
async function loadAdmin(){if(!initData){showToast('Админка доступна только внутри Telegram');return}try{const r=await fetch('/api/admin/dashboard',{headers:apiHeaders()});if(!r.ok){showToast('Нет доступа');return}const d=await r.json();adminData=d.data;document.getElementById('aToday').textContent=adminData.today_orders;document.getElementById('aTotal').textContent=adminData.total_orders;document.getElementById('aRevenue').textContent=rub(adminData.total_revenue);document.getElementById('aNew').textContent=adminData.new_orders;document.getElementById('aWork').textContent=adminData.in_progress;document.getElementById('aDone').textContent=adminData.done;document.getElementById('aUsers').textContent=adminData.user_count||0;const st=adminData.stars||{};document.getElementById('aStarsBalance').textContent=st.bot_balance===null?'—':st.bot_balance+' ⭐';document.getElementById('aStarsReceived').textContent=(st.received_total||0)+' ⭐';document.getElementById('aStarsToday').textContent=(st.received_today||0)+' ⭐';document.getElementById('aStarsPayments').textContent=st.payments_count||0;renderAdminOrders()}catch(e){showToast('Не удалось загрузить админку')}}
async function showUsers(){
  const panel=document.getElementById('usersPanel');
  panel.style.display='block';
  const box=document.getElementById('adminUsers');
  box.innerHTML='<div class="empty">Загрузка пользователей…</div>';
  try{
    const r=await fetch('/api/admin/users',{headers:apiHeaders()});
    if(!r.ok){box.innerHTML='<div class="empty">Нет доступа</div>';return}
    const d=await r.json();
    document.getElementById('usersTotal').textContent=`${d.total} запустили бота`;
    document.getElementById('aUsers').textContent=d.total;
    if(!d.users.length){box.innerHTML='<div class="empty">Пока никто не запускал бота через /start.</div>';return}
    box.innerHTML=d.users.map(u=>{const name=esc((u.first_name||'Пользователь')+(u.last_name?' '+u.last_name:''));const uname=u.username?'@'+esc(u.username):'без username';const date=u.started_at?new Date(u.started_at).toLocaleString('ru-RU'):'—';const initial=esc((u.first_name||'П').slice(0,1).toUpperCase());return `<div class="userCard"><div class="userAvatar">${initial}</div><div class="userMain"><b>${name}</b><small>${uname} · ID ${esc(u.telegram_id)}</small></div><div class="userDate">${date}<br><span style="color:var(--cyan)">/start</span></div></div>`}).join('');
  }catch(e){box.innerHTML='<div class="empty">Не удалось загрузить пользователей.</div>'}
}

function filterAdmin(f){adminFilter=f;renderAdminOrders()}function renderAdminOrders(){const box=document.getElementById('adminOrders');if(!adminData){box.innerHTML='<div class="empty">Загрузка…</div>';return}let rows=adminData.orders;if(adminFilter!=='all')rows=rows.filter(o=>o.status===adminFilter);if(!rows.length){box.innerHTML='<div class="empty">Заказов в этом разделе нет.</div>';return}box.innerHTML=rows.map(o=>{const status=o.status||'new';return `<div class="orderAdmin"><div class="orderTop"><div><b>#${o.id} · ${rub(o.total)}</b><div class="orderMeta">${new Date(o.created_at).toLocaleString('ru-RU')}</div></div><span class="status s-${status}">${({'new':'Новая','in_progress':'В работе','done':'Выполнено','cancelled':'Отменена'})[status]}</span></div><div class="orderInfo"><b>${esc(o.services.join(', '))}</b><br>👤 ${esc(o.contact)}${o.comment&&o.comment!=='—'?'<br>💬 '+esc(o.comment):''}</div><div class="orderControls"><select id="st-${o.id}"><option value="new" ${status==='new'?'selected':''}>Новая</option><option value="in_progress" ${status==='in_progress'?'selected':''}>В работе</option><option value="done" ${status==='done'?'selected':''}>Выполнено</option><option value="cancelled" ${status==='cancelled'?'selected':''}>Отменена</option></select><button onclick="saveStatus(${o.id})">Сохранить</button></div></div>`}).join('')}
async function saveStatus(id){const status=document.getElementById('st-'+id).value;const r=await fetch('/api/admin/orders/'+id+'/status',{method:'POST',headers:apiHeaders(),body:JSON.stringify({status})});if(!r.ok){showToast('Не удалось изменить статус');return}showToast('Статус заказа обновлён');await loadAdmin()}
function render(){renderTariffs();renderPackages();renderCart();renderProfile()}document.querySelectorAll('.nav').forEach(b=>b.addEventListener('click',()=>go(b.dataset.go)));(async()=>{try{services=await (await fetch('/api/services')).json();render();await checkAdmin()}catch(e){showToast('Не удалось загрузить каталог')}})();
</script>
</body></html>
'''


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
