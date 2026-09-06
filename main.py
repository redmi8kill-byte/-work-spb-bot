import os
import sqlite3
import hmac
import hashlib
from datetime import datetime, timezone
from html import escape
from typing import List

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

    today = datetime.now(timezone.utc).date().isoformat()

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
    if chat_id and text.startswith("/setadmin") and ADMIN_SETUP_CODE:
        parts = text.split(maxsplit=1)
        if len(parts) == 2 and parts[1].strip() == ADMIN_SETUP_CODE:
            set_admin_chat_id(str(chat_id))
            await telegram("sendMessage", {"chat_id": chat_id, "text": "✅ Готово! Этот чат назначен администратором. Новые заявки будут приходить сюда."})
        else:
            await telegram("sendMessage", {"chat_id": chat_id, "text": "❌ Неверный код подключения."})
    elif chat_id and text.startswith("/start"):
        await telegram("sendMessage", {"chat_id": chat_id, "text": "👋 Добро пожаловать! Нажмите «🛍 Услуги» в меню, чтобы открыть каталог."})
    elif chat_id and text.startswith("/help"):
        await telegram("sendMessage", {"chat_id": chat_id, "text": "🏙 <b>ПРАЙС — размещение вакансий в Санкт-Петербурге</b>\n\n🛍 <b>Услуги</b> — открыть каталог и выбрать тариф.\n📋 Выберите услуги, добавьте их в корзину и отправьте заявку.\n⚡ Быстрая публикация • 📣 продвижение вакансии • 🤖 AI-оформление\n\nЕсли нужна помощь, напишите администратору.", "parse_mode": "HTML"})
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

def admin_stats():
    con=db()
    total_orders=con.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    total_revenue=con.execute("SELECT COALESCE(SUM(total),0) FROM orders").fetchone()[0]
    today=datetime.now(timezone.utc).date().isoformat()
    today_orders=con.execute("SELECT COUNT(*) FROM orders WHERE created_at LIKE ?",(today+"%",)).fetchone()[0]
    today_revenue=con.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE created_at LIKE ?",(today+"%",)).fetchone()[0]
    new_orders=con.execute("SELECT COUNT(*) FROM orders WHERE status='new'").fetchone()[0]
    in_progress=con.execute("SELECT COUNT(*) FROM orders WHERE status='in_progress'").fetchone()[0]
    done=con.execute("SELECT COUNT(*) FROM orders WHERE status='done'").fetchone()[0]
    rows=con.execute("SELECT id,created_at,service_ids,total,contact,comment,status FROM orders ORDER BY id DESC LIMIT 100").fetchall()
    con.close()
    orders=[]
    for oid,created,ids,total,contact,comment,status in rows:
        orders.append({"id":oid,"created_at":created,"services":service_names(ids),"total":total,"contact":contact or "—","comment":comment or "—","status":status or "new"})
    return {"total_orders":total_orders,"total_revenue":total_revenue,"today_orders":today_orders,"today_revenue":today_revenue,"new_orders":new_orders,"in_progress":in_progress,"done":done,"orders":orders}

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


HTML = r'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#eef6ff"><title>Работа в Питере</title><style>:root{--ink:#102b55;--muted:#71829a;--line:#dce8f5;--bg:#f5f9ff;--blue:#1268ff;--violet:#754dff;--cyan:#20c7ef;--pink:#ff5db3;--shadow:0 18px 50px #153d7112}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 0 0,#eaf4ff,transparent 35%),radial-gradient(circle at 100% 8%,#f6eaff,transparent 30%),var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}.wrap{max-width:1180px;margin:auto;padding:12px 18px 105px}.topnav{display:flex;align-items:center;justify-content:space-between;padding:7px 4px 14px}.logo{font-weight:950;font-size:17px}.logo span{display:inline-grid;place-items:center;width:32px;height:32px;border-radius:10px;background:linear-gradient(135deg,#1768ff,#7950ff);color:#fff;margin-right:8px}.links{display:flex;gap:20px}.links button{border:0;background:none;color:#536780;font-size:12px;font-weight:800}.open{border:0;border-radius:13px;padding:10px 15px;background:linear-gradient(135deg,#1268ff,#754dff);color:#fff;font-weight:900}.hero{position:relative;overflow:hidden;display:grid;grid-template-columns:1.05fr .95fr;min-height:360px;border:1px solid var(--line);border-radius:30px;background:linear-gradient(115deg,#fff,#eef7ff 55%,#f8efff);box-shadow:var(--shadow)}.heroText{padding:42px 40px;position:relative;z-index:2}.eyebrow{display:inline-flex;padding:7px 10px;border-radius:999px;background:#e9f2ff;color:#2560c7;font-size:10px;font-weight:900}.hero h1{font-size:44px;line-height:1.02;margin:17px 0 12px;max-width:650px}.hero h1 b{color:#1768ff}.hero p{color:#61738d;line-height:1.55;max-width:610px}.actions{display:flex;gap:10px;margin-top:20px}.btn{border:0;border-radius:15px;padding:13px 18px;font-weight:900;cursor:pointer}.btn.primary{background:linear-gradient(135deg,#1268ff,#754dff);color:#fff;box-shadow:0 12px 25px #1268ff2a}.btn.light{background:#fff;border:1px solid var(--line);color:var(--ink)}.heroArt{position:relative;min-height:300px;background:linear-gradient(145deg,#e9f4ff,#f6eaff)}.heroArt:before{content:"";position:absolute;width:360px;height:360px;border-radius:50%;right:-60px;top:-45px;background:radial-gradient(circle,#fff 0,#d9edff 48%,#d9caff 72%,transparent 73%);box-shadow:0 0 55px #53a6ff40}.desk{position:absolute;right:34px;top:48px;width:80%;height:220px;border-radius:18px;background:linear-gradient(145deg,#fff,#eef4fb);box-shadow:0 30px 55px #24518b20;transform:rotate(-3deg);border:1px solid #fff}.laptop{position:absolute;right:55px;top:55px;width:62%;height:145px;border-radius:12px;background:linear-gradient(145deg,#1d365b,#d9e8fb);box-shadow:0 15px 30px #19365b35}.coffee{position:absolute;right:45%;bottom:24px;width:70px;height:70px;border-radius:50%;background:linear-gradient(145deg,#fff,#dce8f4);box-shadow:0 12px 25px #19365b20}.coffee:after{content:"☕";position:absolute;inset:0;display:grid;place-items:center;font-size:34px}.neon{position:absolute;right:15px;top:35px;width:250px;height:250px;border-radius:50%;border:3px solid #6e58ff55;box-shadow:0 0 30px #6e58ff55,0 0 70px #20c7ef30}.features{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;margin:14px 0;background:var(--line);border-radius:20px;overflow:hidden}.feature{background:#fff;padding:18px}.feature strong{display:block;font-size:12px}.feature span{display:block;color:var(--muted);font-size:10px;margin-top:4px}.section{margin-top:28px}.sectionhead{display:flex;justify-content:space-between;align-items:end;margin-bottom:13px}.sectionhead h2{margin:0;font-size:24px}.sectionhead span{font-size:11px;color:var(--muted)}.tabs{display:flex;gap:7px;margin-bottom:13px}.tabs button{border:1px solid var(--line);background:#fff;color:var(--muted);border-radius:999px;padding:9px 14px;font-size:11px;font-weight:900}.tabs button.active{background:#102b55;color:#fff}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.card{position:relative;overflow:hidden;background:#fff;border:1px solid var(--line);border-radius:24px;padding:18px;box-shadow:var(--shadow)}.card:before{content:"";position:absolute;left:0;right:0;top:0;height:4px;background:linear-gradient(90deg,var(--blue),var(--cyan))}.card.violet:before{background:linear-gradient(90deg,var(--violet),var(--pink))}.card.gold:before{background:linear-gradient(90deg,#ffb226,#ff7c55)}.card.cyan:before{background:linear-gradient(90deg,#18b7cf,#47e4ff)}.card.pink:before{background:linear-gradient(90deg,#ff4eaa,#7a52ff)}.badge{display:inline-flex;padding:6px 8px;border-radius:9px;background:#eef4ff;color:#2161cb;font-size:9px;font-weight:900}.card h3{font-size:19px;margin:13px 0 5px}.sub{font-size:11px;color:var(--muted);min-height:32px;line-height:1.45}.price{font-size:27px;font-weight:950;margin:13px 0 5px}.featuresList{padding:0;margin:10px 0 14px;list-style:none}.featuresList li{font-size:11px;color:#63748c;padding:5px 0}.featuresList li:before{content:"✓";color:#1768ff;font-weight:950;margin-right:6px}.packageNote{margin-top:12px;padding:15px;border:1px solid var(--line);border-radius:20px;background:linear-gradient(135deg,#fff,#eef7ff);font-size:11px;color:var(--muted);line-height:1.55}.why{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.why .box,.step{background:#fff;border:1px solid var(--line);border-radius:20px;padding:16px;box-shadow:var(--shadow)}.ico{font-size:22px}.why b{display:block;margin-top:9px;font-size:13px}.why p,.step p{font-size:11px;line-height:1.45;color:var(--muted);margin:6px 0 0}.steps{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.step strong{font-size:12px}.num{color:#1768ff;font-size:10px;font-weight:950}.cta{margin-top:28px;border-radius:25px;padding:25px 28px;background:linear-gradient(120deg,#102b55,#2258a4 55%,#734dff);color:#fff;display:flex;justify-content:space-between;align-items:center;gap:20px;box-shadow:0 20px 45px #102b5530}.cta h2{margin:0 0 6px;font-size:22px}.cta p{margin:0;color:#d7e6ff;font-size:11px}.cartbar{position:fixed;left:0;right:0;bottom:0;z-index:15;padding:9px 14px calc(9px + env(safe-area-inset-bottom));background:#ffffffdb;backdrop-filter:blur(18px);border-top:1px solid var(--line)}.cartin{max-width:1140px;margin:auto;display:flex;gap:10px;align-items:center}.cartinfo{flex:1}.cartinfo small{display:block;color:var(--muted);font-size:10px}.cartinfo b{font-size:18px}.cartopen{border:0;border-radius:14px;padding:12px 16px;background:#102b55;color:#fff;font-weight:900}.modal{position:fixed;inset:0;z-index:30;background:#102b5566;backdrop-filter:blur(5px);display:none;align-items:flex-end;justify-content:center;padding:10px}.sheet{width:min(760px,100%);max-height:92vh;overflow:auto;background:#fff;border-radius:27px;padding:20px;box-shadow:0 30px 80px #102b5540}.sheethead{display:flex;justify-content:space-between;align-items:center}.sheethead h2{margin:0;font-size:24px}.close{border:0;background:#edf3fa;border-radius:50%;width:38px;height:38px}.item{display:flex;justify-content:space-between;gap:10px;padding:13px 0;border-bottom:1px solid var(--line)}.item b{font-size:12px}.remove{border:0;background:#fff0f3;color:#c23b5a;border-radius:9px;padding:7px;font-size:10px;font-weight:800}label{display:block;font-size:11px;font-weight:900;margin:12px 0 6px}input,textarea{width:100%;border:1px solid var(--line);border-radius:13px;padding:12px;background:#fbfdff;font:inherit;outline:none}textarea{min-height:90px}.total{display:flex;justify-content:space-between;align-items:center;margin:17px 0}.total b{font-size:24px}.success{margin-top:12px;padding:12px;border-radius:13px;background:#eafff4;color:#15764b;font-size:12px;font-weight:800}.profile{display:grid;grid-template-columns:1fr 1fr;gap:12px}.profilebox{background:#fff;border:1px solid var(--line);border-radius:22px;padding:18px;box-shadow:var(--shadow)}@media(max-width:760px){.wrap{padding:8px 10px 98px}.links{display:none}.hero{grid-template-columns:1fr;min-height:auto}.heroText{padding:26px 22px}.hero h1{font-size:31px}.heroArt{height:190px;min-height:190px}.desk{right:20px;top:24px;width:74%;height:130px}.laptop{right:40px;top:32px;height:95px}.neon{width:180px;height:180px;right:-30px;top:5px}.coffee{width:55px;height:55px;right:43%;bottom:15px}.features{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}.why{grid-template-columns:1fr 1fr}.steps{grid-template-columns:1fr 1fr}.cta{align-items:flex-start;flex-direction:column}.profile{grid-template-columns:1fr}.topnav{padding-bottom:8px}}</style></head><body><div class="wrap"><header class="topnav"><div class="logo"><span>✦</span>Работа в Питере</div><nav class="links"><button onclick="scrollToId('tariffs')">Тарифы</button><button onclick="scrollToId('packages')">Пакеты</button><button onclick="scrollToId('how')">Как это работает</button><button onclick="scrollToId('profile')">Профиль</button></nav><button class="open" onclick="scrollToId('tariffs')">Открыть заявку</button></header><section class="hero"><div class="heroText"><span class="eyebrow">✦ НАДЁЖНЫЙ СЕРВИС ДЛЯ HR</span><h1>Эффективное размещение вакансий <b>в Санкт-Петербурге</b></h1><p>Современный подход к подбору персонала: AI-визуализация, таргетинг и быстрая публикация.</p><div class="actions"><button class="btn primary" onclick="scrollToId('tariffs')">Выбрать тариф →</button><button class="btn light" onclick="scrollToId('how')">Как это работает</button></div></div><div class="heroArt"><div class="neon"></div><div class="desk"></div><div class="laptop"></div><div class="coffee"></div></div></section><div class="features"><div class="feature">🎯 <strong>СПб и ЛО</strong><span>Готовые шаблоны и охват</span></div><div class="feature">✨ <strong>AI-визуализация</strong><span>Уникальные креативы</span></div><div class="feature">⚡ <strong>Быстрый запуск</strong><span>В день обращения</span></div><div class="feature">♧ <strong>Поддержка</strong><span>10:00–22:00</span></div></div><section id="tariffs" class="section"><div class="sectionhead"><h2>Тарифы и пакеты</h2><span>Все варианты →</span></div><div class="tabs"><button class="active" onclick="scrollToId('tariffs')">Тарифы</button><button onclick="scrollToId('packages')">Пакеты</button></div><div id="tariffGrid" class="grid"></div></section><section id="packages" class="section"><div class="sectionhead"><h2>Пакетные предложения</h2><span>выгоднее при регулярном найме</span></div><div id="packageGrid" class="grid"></div><div class="packageNote"><b>ℹ️ Условия пакетов</b><br>Все пакеты базируются на тарифе «Под ключ» и включают уникальное ИИ-фото для каждой вакансии. Срок действия — 30–60 дней.</div></section><section class="section"><div class="sectionhead"><h2>Почему выбирают нас</h2></div><div class="why"><div class="box"><div class="ico">🎯</div><b>Целевой охват</b><p>Аудитория Санкт-Петербурга и Ленинградской области.</p></div><div class="box"><div class="ico">✨</div><b>AI-креативы</b><p>Уникальные обложки помогают вакансии выделиться.</p></div><div class="box"><div class="ico">⚡</div><b>Быстрый запуск</b><p>Редактируем и публикуем в день обращения.</p></div><div class="box"><div class="ico">💎</div><b>Прозрачная цена</b><p>Тарифы понятны до отправки заявки.</p></div></div></section><section id="how" class="section"><div class="sectionhead"><h2>Как это работает?</h2></div><div class="steps"><div class="step"><span class="num">01</span><strong>Оставляете заявку</strong><p>Выбираете подходящий тариф.</p></div><div class="step"><span class="num">02</span><strong>Мы готовим креатив</strong><p>Текст, оформление и AI-визуал.</p></div><div class="step"><span class="num">03</span><strong>Публикуем вакансию</strong><p>После согласования размещаем в ленте.</p></div><div class="step"><span class="num">04</span><strong>Вы получаете отклики</strong><p>Следите за результатом и связываетесь с кандидатами.</p></div></div></section><section id="profile" class="section"><div class="sectionhead"><h2>Ваш профиль</h2><span>Telegram Mini App</span></div><div class="profile"><div class="profilebox"><b>📋 Мои заказы</b><p style="color:var(--muted);font-size:11px">История заявок и их статусы.</p><button class="btn light" style="width:100%" onclick="alert('Пользовательская история появится следующим этапом.')">Открыть</button></div><div class="profilebox"><b>🔔 Уведомления</b><p style="color:var(--muted);font-size:11px">Поддержка и информация по заявке.</p><button class="btn light" style="width:100%" onclick="alert('Настройка уведомлений будет подключена через Telegram WebApp.')">Настроить</button></div></div></section><div class="cta"><div><h2>Готовы разместить вакансию?</h2><p>Оставьте заявку — мы свяжемся с вами в ближайшее время.</p></div><button class="btn light" onclick="openCart()">Оставить заявку →</button></div></div><div class="cartbar"><div class="cartin"><div class="cartinfo"><small id="cartLabel">Корзина пуста</small><b id="cartSum">0 ₽</b></div><button class="cartopen" onclick="openCart()">🛒 Корзина <span id="barCount">0</span></button></div></div><div id="cartModal" class="modal" onclick="if(event.target===this)closeCart()"><div class="sheet"><div class="sheethead"><h2>🛒 Корзина</h2><button class="close" onclick="closeCart()">✕</button></div><div id="cartItems"></div><div class="total"><span>Итого</span><b id="modalTotal">0 ₽</b></div><button class="btn primary" style="width:100%" onclick="openCheckout()">Оформить заявку →</button></div></div><div id="checkoutModal" class="modal" onclick="if(event.target===this)closeCheckout()"><div class="sheet"><div class="sheethead"><h2>Оформление заявки</h2><button class="close" onclick="closeCheckout()">✕</button></div><p id="checkoutChosen" style="color:var(--muted);font-size:11px"></p><label>Контакт для связи *</label><input id="contact" placeholder="@username или номер телефона"><label>Комментарий</label><textarea id="comment" placeholder="Например: нужно разместить вакансию менеджера с понедельника"></textarea><button class="btn primary" style="width:100%" onclick="sendOrder()">Отправить заявку →</button><div id="result"></div></div></div><script>let services=[],cart=JSON.parse(localStorage.getItem('workspb_cart')||'[]');const rub=n=>new Intl.NumberFormat('ru-RU').format(n)+' ₽';const byId=id=>services.find(s=>s.id===id);async function init(){services=await (await fetch('/api/services')).json();render()}function scrollToId(id){document.getElementById(id)?.scrollIntoView({behavior:'smooth',block:'start'})}function card(s){return `<article class="card ${s.accent}"><span class="badge">${s.tag}</span><h3>${s.name}</h3><div class="sub">${s.subtitle}</div><div class="price">${rub(s.price)}</div><ul class="featuresList">${s.features.map(x=>`<li>${x}</li>`).join('')}</ul><button class="btn ${cart.includes(s.id)?'light':'primary'}" style="width:100%" onclick="toggle(${s.id})">${cart.includes(s.id)?'✓ В корзине':'Выбрать'}</button></article>`}function render(){tariffGrid.innerHTML=services.filter(s=>s.type!=='Пакет').map(card).join('');packageGrid.innerHTML=services.filter(s=>s.type==='Пакет').map(card).join('');let total=cart.reduce((a,id)=>a+byId(id).price,0);cartSum.textContent=rub(total);modalTotal.textContent=rub(total);barCount.textContent=cart.length;cartLabel.textContent=cart.length?`${cart.length} ${cart.length===1?'позиция':'позиции'} в корзине`:'Корзина пуста';cartItems.innerHTML=cart.length?cart.map(id=>{let s=byId(id);return `<div class="item"><div><b>${s.name}</b><div style="font-size:10px;color:var(--muted)">${s.tag}</div></div><div style="text-align:right"><b>${rub(s.price)}</b><br><button class="remove" onclick="removeItem(${s.id})">Убрать</button></div></div>`}).join(''):'<p style="color:var(--muted);font-size:12px">Добавьте тариф или пакет — он появится здесь.</p>';localStorage.setItem('workspb_cart',JSON.stringify(cart))}function toggle(id){cart.includes(id)?cart=cart.filter(x=>x!==id):cart.push(id);render()}function removeItem(id){cart=cart.filter(x=>x!==id);render()}function openCart(){render();cartModal.style.display='flex'}function closeCart(){cartModal.style.display='none'}function openCheckout(){if(!cart.length)return;checkoutChosen.textContent='Выбрано: '+cart.map(id=>byId(id).name).join(', ')+' • '+rub(cart.reduce((a,id)=>a+byId(id).price,0));closeCart();checkoutModal.style.display='flex'}function closeCheckout(){checkoutModal.style.display='none'}async function sendOrder(){if(!contact.value.trim()){contact.focus();return}let r=await fetch('/api/checkout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({service_ids:cart,contact:contact.value,comment:comment.value})});let d=await r.json();if(!d.ok){result.innerHTML='<div class="success" style="background:#fff0f3;color:#b52e51">'+d.message+'</div>';return}result.innerHTML='<div class="success">✅ Заявка #'+d.order_id+' отправлена. Мы свяжемся с вами для подтверждения.</div>';cart=[];render()}init();</script></body></html>'''


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
