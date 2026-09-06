import os
import sqlite3
import hashlib
import hmac
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
    con.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, service_ids TEXT, total INTEGER, contact TEXT, comment TEXT, status TEXT DEFAULT 'Новая')")
    cols = [row[1] for row in con.execute("PRAGMA table_info(orders)").fetchall()]
    if 'status' not in cols:
        con.execute("ALTER TABLE orders ADD COLUMN status TEXT DEFAULT 'Новая'")
    con.execute("UPDATE orders SET status='Новая' WHERE status IS NULL OR status=''")
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




def admin_cookie_value():
    if not ADMIN_SETUP_CODE:
        return ""
    return hmac.new(ADMIN_SETUP_CODE.encode(), b"work-spb-web-admin", hashlib.sha256).hexdigest()

def web_admin_ok(request: Request) -> bool:
    token=request.cookies.get("workspb_admin")
    expected=admin_cookie_value()
    return bool(expected and hmac.compare_digest(token or "", expected))

@app.get("/admin-web", response_class=HTMLResponse)
async def admin_web(request: Request):
    return ADMIN_HTML if web_admin_ok(request) else ADMIN_LOGIN_HTML

@app.post("/admin-web/login")
async def admin_web_login(request: Request):
    data=await request.json(); code=str(data.get("code","" )).strip()
    if not ADMIN_SETUP_CODE or not hmac.compare_digest(code, ADMIN_SETUP_CODE):
        return JSONResponse({"ok":False,"message":"Неверный код доступа."},status_code=401)
    r=JSONResponse({"ok":True}); r.set_cookie("workspb_admin",admin_cookie_value(),httponly=True,secure=True,samesite="lax",max_age=604800); return r

@app.post("/admin-web/logout")
async def admin_web_logout(request: Request):
    r=JSONResponse({"ok":True}); r.delete_cookie("workspb_admin"); return r

def service_names(service_ids):
    out=[]
    for raw in (service_ids or "").split(","):
        try: sid=int(raw.strip())
        except ValueError: continue
        s=next((x for x in SERVICES if x["id"]==sid),None)
        if s: out.append(s["name"])
    return out

@app.get("/admin-web/api/stats")
async def admin_web_stats(request: Request):
    if not web_admin_ok(request): return JSONResponse({"ok":False},status_code=401)
    con=db(); today=datetime.now(timezone.utc).date().isoformat()
    d={"total_orders":con.execute("SELECT COUNT(*) FROM orders").fetchone()[0],"revenue":con.execute("SELECT COALESCE(SUM(total),0) FROM orders").fetchone()[0],"today_orders":con.execute("SELECT COUNT(*) FROM orders WHERE created_at LIKE ?",(today+"%",)).fetchone()[0],"today_revenue":con.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE created_at LIKE ?",(today+"%",)).fetchone()[0],"new_orders":con.execute("SELECT COUNT(*) FROM orders WHERE status='Новая'").fetchone()[0]}; con.close(); return d

@app.get("/admin-web/api/orders")
async def admin_web_orders(request: Request):
    if not web_admin_ok(request): return JSONResponse({"ok":False},status_code=401)
    con=db(); rows=con.execute("SELECT id,created_at,service_ids,total,contact,comment,status FROM orders ORDER BY id DESC LIMIT 100").fetchall(); con.close()
    return [{"id":r[0],"created_at":r[1],"services":service_names(r[2]),"total":r[3],"contact":r[4],"comment":r[5],"status":r[6] or "Новая"} for r in rows]

@app.post("/admin-web/api/orders/{order_id}/status")
async def admin_web_status(order_id:int,request:Request):
    if not web_admin_ok(request): return JSONResponse({"ok":False},status_code=401)
    status=str((await request.json()).get("status","")).strip(); allowed={"Новая","В работе","Ожидает оплаты","Выполнено","Отменено"}
    if status not in allowed: return JSONResponse({"ok":False,"message":"Недопустимый статус."},status_code=400)
    con=db(); cur=con.execute("UPDATE orders SET status=? WHERE id=?",(status,order_id)); con.commit(); con.close()
    return {"ok":bool(cur.rowcount)}

HTML = r'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#f5f7fb"><title>Работа в Питере</title><style>:root{--bg:#f5f7fb;--card:#fff;--ink:#17283d;--muted:#6e7c8e;--line:#e3e8ef;--navy:#102942;--shadow:0 14px 38px rgba(21,47,76,.08)}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}.wrap{max-width:1180px;margin:auto;padding:0 22px 90px}.top{height:72px;display:flex;align-items:center;justify-content:space-between}.brand{display:flex;gap:10px;align-items:center;font-weight:900}.mark{width:34px;height:34px;border-radius:10px;background:#eaf0f5;display:grid;place-items:center}.links{display:flex;gap:26px;font-size:12px;color:#516176;font-weight:700}.links a{color:inherit;text-decoration:none}.topbtn{border:0;border-radius:999px;background:var(--navy);color:#fff;padding:11px 18px;font-size:12px;font-weight:900}.hero{min-height:330px;border-radius:28px;background:#edf1f4;position:relative;overflow:hidden;display:flex;align-items:center;padding:42px 52% 42px 42px}.hero:after{content:"";position:absolute;right:0;top:0;width:51%;height:100%;background:url('https://images.unsplash.com/photo-1497366811353-6870744d04b2?auto=format&fit=crop&w=1200&q=80') center/cover}.hero h1{font-size:40px;line-height:1.08;margin:0 0 14px;letter-spacing:-1.3px}.hero p{font-size:14px;line-height:1.55;color:#526276;margin:0 0 20px}.actions{display:flex;gap:10px;flex-wrap:wrap}.btn{border:0;border-radius:999px;padding:13px 20px;font-weight:900;font-size:12px;cursor:pointer}.dark{background:var(--navy);color:#fff}.light{background:#fff;color:var(--navy);border:1px solid #d6dee8}.features{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;padding:24px 8px}.feature{display:flex;gap:11px}.fic{width:34px;height:34px;border-radius:11px;background:#f0f4f8;display:grid;place-items:center;flex:none}.feature b{display:block;font-size:12px;margin-bottom:4px}.feature span{font-size:10px;color:var(--muted)}.section{padding-top:28px}.head{display:flex;justify-content:space-between;align-items:center;margin-bottom:15px}.head h2{font-size:22px;margin:0}.head small{font-size:11px;color:#8a96a5}.tabs{display:flex;gap:4px;background:#e8edf3;border-radius:999px;padding:4px;width:max-content}.tabs button{border:0;background:transparent;padding:9px 15px;border-radius:999px;font-size:11px;font-weight:800;color:#607085}.tabs button.active{background:var(--navy);color:#fff}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.card{background:#fff;border:1px solid var(--line);border-radius:21px;padding:21px;box-shadow:var(--shadow);position:relative}.tag{position:absolute;right:15px;top:15px;background:#eef3f7;color:#40546b;border-radius:8px;padding:5px 8px;font-size:9px;font-weight:900}.card h3{font-size:15px;margin:0 0 5px}.price{font-size:27px;font-weight:950;margin:6px 0 15px}.card ul{list-style:none;padding:0;margin:0 0 16px}.card li{font-size:11px;color:#687789;padding:5px 0}.card li:before{content:'✓';margin-right:7px;color:#6d7f92;font-weight:900}.card .btn{width:100%;padding:11px}.callout{margin-top:22px;border-radius:22px;background:linear-gradient(100deg,#122b45,#243e58);color:#fff;padding:23px 25px;display:flex;align-items:center;justify-content:space-between}.callout h3{margin:0 0 5px;font-size:17px}.callout p{margin:0;color:#cad6e2;font-size:11px}.cartbar{position:fixed;left:0;right:0;bottom:0;z-index:10;background:#ffffffed;border-top:1px solid var(--line);backdrop-filter:blur(18px);padding:10px 14px}.cartin{max-width:1135px;margin:auto;display:flex;gap:12px;align-items:center}.cartinfo{flex:1}.cartinfo small{display:block;color:var(--muted);font-size:10px}.cartinfo b{font-size:18px}.modal{position:fixed;inset:0;z-index:30;background:#10294266;display:none;align-items:flex-end;padding:10px}.sheet{width:min(650px,100%);max-height:90vh;overflow:auto;margin:auto;background:#fff;border-radius:25px;padding:20px}.sheethead{display:flex;justify-content:space-between;align-items:center}.close{border:0;border-radius:50%;width:38px;height:38px;background:#eef2f5}.cartitem{display:flex;justify-content:space-between;padding:13px 0;border-bottom:1px solid var(--line)}.muted{font-size:11px;color:var(--muted)}.total{display:flex;justify-content:space-between;margin:18px 0;font-size:18px}.total b{font-size:24px}label{display:block;font-size:11px;font-weight:800;margin:11px 0 5px}input,textarea{width:100%;border:1px solid #dbe2ea;background:#fafbfc;border-radius:13px;padding:12px;outline:none}textarea{min-height:90px}.success{padding:13px;border-radius:13px;background:#eaf8ef;color:#1c6b40;margin-top:10px;font-size:12px;font-weight:800}@media(max-width:760px){.wrap{padding:0 14px 90px}.top{height:62px}.links{display:none}.hero{min-height:470px;padding:28px 22px;align-items:flex-start}.hero:after{top:auto;bottom:0;width:100%;height:48%}.hero h1{font-size:31px}.hero>div{position:relative;z-index:2}.features{grid-template-columns:repeat(2,1fr);padding:18px 3px}.grid{grid-template-columns:1fr}.callout{flex-direction:column;align-items:flex-start;gap:14px}}
</style></head><body><div class="wrap"><header class="top"><div class="brand"><div class="mark">⚓</div>Работа в Питере</div><nav class="links"><a href="#tariffs">Тарифы</a><a href="#packages">Пакеты</a><a href="#how">Как это работает</a><a href="#contacts">Контакты</a></nav><button class="topbtn" onclick="document.getElementById('tariffs').scrollIntoView({behavior:'smooth'})">Оставить заявку</button></header><section class="hero"><div><div style="font-size:11px;font-weight:900;color:#607286;margin-bottom:10px">РАЗМЕЩЕНИЕ ВАКАНСИЙ</div><h1>Эффективное размещение вакансий в Санкт-Петербурге</h1><p>Современный подход к подбору персонала: AI-визуализация, таргетинг и быстрая публикация.</p><div class="actions"><button class="btn dark" onclick="document.getElementById('tariffs').scrollIntoView({behavior:'smooth'})">Выбрать тариф</button><button class="btn light" onclick="document.getElementById('how').scrollIntoView({behavior:'smooth'})">Как это работает</button></div></div></section><section class="features"><div class="feature"><div class="fic">🎯</div><div><b>СПб и ЛО</b><span>Целевая аудитория региона</span></div></div><div class="feature"><div class="fic">✨</div><div><b>AI-визуализация</b><span>Уникальные креативы</span></div></div><div class="feature"><div class="fic">⚡</div><div><b>Быстрый запуск</b><span>В день обращения</span></div></div><div class="feature"><div class="fic">◷</div><div><b>Поддержка</b><span>10:00–22:00</span></div></div></section><section id="tariffs" class="section"><div class="head"><h2>Тарифы и пакеты</h2><small>Все варианты →</small></div><div class="tabs"><button id="tabTariffs" class="active" onclick="showGroup('tariffs')">Тарифы</button><button id="tabPackages" onclick="showGroup('packages')">Пакеты</button></div><div id="tariffGrid" class="grid" style="margin-top:14px"></div></section><section id="packages" class="section" style="display:none"><div class="head"><h2>Пакетные предложения</h2><small>Выгоднее при регулярном найме</small></div><div id="packageGrid" class="grid"></div></section><section id="how" class="section"><div class="head"><h2>Как это работает</h2></div><div class="grid"><div class="card"><div style="font-size:11px;font-weight:900;color:#6d7e91">01</div><h3>Заявка</h3><p class="muted">Выбираете тариф и оставляете контакт.</p></div><div class="card"><div style="font-size:11px;font-weight:900;color:#6d7e91">02</div><h3>Подготовка</h3><p class="muted">Редактируем текст и готовим оформление.</p></div><div class="card"><div style="font-size:11px;font-weight:900;color:#6d7e91">03</div><h3>Публикация</h3><p class="muted">Согласуем и размещаем вакансию в канале.</p></div></div></section><section id="contacts" class="callout"><div><h3>Готовы разместить вакансию?</h3><p>Оставьте заявку — мы свяжемся с вами в ближайшее время.</p></div><button class="btn" style="background:#fff;color:#102942" onclick="document.getElementById('tariffs').scrollIntoView({behavior:'smooth'})">Оставить заявку</button></section></div><div class="cartbar"><div class="cartin"><div class="cartinfo"><small id="cartLabel">Корзина пуста</small><b id="cartSum">0 ₽</b></div><button class="btn dark" onclick="openCart()">Корзина <span id="barCount">0</span></button></div></div><div id="cartModal" class="modal" onclick="if(event.target===this)closeCart()"><div class="sheet"><div class="sheethead"><h2>Корзина</h2><button class="close" onclick="closeCart()">✕</button></div><div id="cartItems"></div><div class="total"><span>Итого</span><b id="modalTotal">0 ₽</b></div><button class="btn dark" style="width:100%" onclick="openCheckout()">Оформить заявку →</button></div></div><div id="checkoutModal" class="modal" onclick="if(event.target===this)closeCheckout()"><div class="sheet"><div class="sheethead"><h2>Оформление заявки</h2><button class="close" onclick="closeCheckout()">✕</button></div><p class="muted" id="checkoutChosen"></p><label>Контакт для связи *</label><input id="contact" placeholder="@username или номер телефона"><label>Комментарий</label><textarea id="comment" placeholder="Например: нужна публикация вакансии менеджера"></textarea><button class="btn dark" style="width:100%;margin-top:12px" onclick="sendOrder()">Отправить заявку</button><div id="result"></div></div></div><script>let services=[],cart=JSON.parse(localStorage.getItem('workspb_cart')||'[]');const rub=n=>new Intl.NumberFormat('ru-RU').format(n)+' ₽';const byId=id=>services.find(s=>s.id===id);async function init(){services=await (await fetch('/api/services')).json();render()}function card(s){return `<article class="card"><span class="tag">${s.tag}</span><h3>${s.name}</h3><div class="muted">${s.type}</div><div class="price">${rub(s.price)}</div><ul>${s.features.slice(0,4).map(x=>`<li>${x}</li>`).join('')}</ul><button class="btn ${cart.includes(s.id)?'light':'dark'}" onclick="toggle(${s.id})">${cart.includes(s.id)?'✓ В корзине':'Выбрать'}</button></article>`}function render(){document.getElementById('tariffGrid').innerHTML=services.filter(s=>s.type!=='Пакет').map(card).join('');document.getElementById('packageGrid').innerHTML=services.filter(s=>s.type==='Пакет').map(card).join('');let total=cart.reduce((a,id)=>a+byId(id).price,0),c=cart.length;document.getElementById('cartSum').textContent=rub(total);document.getElementById('modalTotal').textContent=rub(total);document.getElementById('barCount').textContent=c;document.getElementById('cartLabel').textContent=c?`${c} ${c===1?'позиция':'позиции'} в корзине`:'Корзина пуста';document.getElementById('cartItems').innerHTML=c?cart.map(id=>{let s=byId(id);return `<div class="cartitem"><div><b>${s.name}</b><div class="muted">${s.tag}</div></div><div style="text-align:right"><b>${rub(s.price)}</b><br><button class="btn" style="padding:6px 9px;background:#f5eef1;color:#a34658;font-size:10px" onclick="removeItem(${id})">Убрать</button></div></div>`}).join(''):'<p class="muted">Добавьте тарифы или пакеты.</p>';localStorage.setItem('workspb_cart',JSON.stringify(cart))}function toggle(id){cart.includes(id)?cart=cart.filter(x=>x!==id):cart.push(id);render()}function removeItem(id){cart=cart.filter(x=>x!==id);render()}function showGroup(g){document.getElementById('tariffs').style.display=g==='tariffs'?'block':'none';document.getElementById('packages').style.display=g==='packages'?'block':'none';document.getElementById('tabTariffs').classList.toggle('active',g==='tariffs');document.getElementById('tabPackages').classList.toggle('active',g==='packages')}function openCart(){render();document.getElementById('cartModal').style.display='flex'}function closeCart(){document.getElementById('cartModal').style.display='none'}function openCheckout(){if(!cart.length)return;document.getElementById('checkoutChosen').textContent='Выбрано: '+cart.map(id=>byId(id).name).join(', ')+' • '+rub(cart.reduce((a,id)=>a+byId(id).price,0));closeCart();document.getElementById('checkoutModal').style.display='flex'}function closeCheckout(){document.getElementById('checkoutModal').style.display='none'}async function sendOrder(){let c=document.getElementById('contact').value.trim();if(!c){document.getElementById('contact').focus();return}let r=await fetch('/api/checkout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({service_ids:cart,contact:c,comment:document.getElementById('comment').value})}),d=await r.json();document.getElementById('result').innerHTML=d.ok?`<div class="success">✓ Заявка #${d.order_id} отправлена. Мы свяжемся с вами для подтверждения.</div>`:`<div class="success" style="background:#fff0f3;color:#9d3a52">${d.message||'Ошибка'}</div>`;if(d.ok){cart=[];render()}}init();</script></body></html>'''
ADMIN_LOGIN_HTML = r'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Вход</title><style>body{margin:0;background:#f4f7fb;min-height:100vh;display:grid;place-items:center;padding:20px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#17283d}.box{width:min(390px,100%);background:#fff;border:1px solid #e1e7ee;border-radius:24px;padding:28px;box-shadow:0 20px 60px #15304d14}input{width:100%;box-sizing:border-box;padding:14px;border:1px solid #dce4ed;border-radius:13px;margin:10px 0 12px;font-size:16px}button{width:100%;padding:13px;border:0;border-radius:13px;background:#102942;color:#fff;font-weight:900}.muted{color:#738094;font-size:12px;line-height:1.5}.err{color:#b23b50;font-size:12px;margin-top:10px}</style></head><body><div class="box"><div style="font-size:28px">⚓</div><h1 style="font-size:25px;margin:10px 0 5px">Админ-панель</h1><div class="muted">Доступ закрыт. Используйте тот же код, который уже настроен для /setadmin.</div><input id="code" type="password" placeholder="Код доступа"><button onclick="login()">Войти</button><div id="err" class="err"></div></div><script>async function login(){let r=await fetch('/admin-web/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:document.getElementById('code').value})});if(r.ok)location.reload();else document.getElementById('err').textContent='Неверный код доступа.'}document.getElementById('code').addEventListener('keydown',e=>{if(e.key==='Enter')login()});</script></body></html>'''
ADMIN_HTML = r'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Админ — Работа в Питере</title><style>:root{--bg:#f5f7fb;--card:#fff;--ink:#17283d;--muted:#738094;--line:#e1e7ee;--navy:#102942}*{box-sizing:border-box}body{margin:0;background:var(--bg);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:var(--ink)}.app{max-width:1180px;margin:auto;padding:18px}.top{height:60px;display:flex;align-items:center;justify-content:space-between}.brand{font-weight:950;display:flex;gap:10px;align-items:center}.logo{width:34px;height:34px;border-radius:10px;background:#eaf0f6;display:grid;place-items:center}.right{display:flex;gap:12px;align-items:center;font-size:11px;color:var(--muted)}.online{color:#15966a}.logout,.refresh{border:1px solid var(--line);background:#fff;border-radius:9px;padding:9px 12px;font-weight:800;font-size:11px}.layout{display:grid;grid-template-columns:190px 1fr;gap:20px}.side{background:#fff;border:1px solid var(--line);border-radius:19px;padding:10px;height:max-content;position:sticky;top:14px}.side button{display:block;width:100%;border:0;background:transparent;text-align:left;padding:12px;border-radius:10px;color:#607085;font-weight:800}.side .active{background:#eaf1f8;color:#173a5e}.content h1{font-size:27px;margin:0 0 4px}.sub{color:var(--muted);font-size:12px;margin-bottom:18px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.stat{background:#fff;border:1px solid var(--line);border-radius:17px;padding:17px}.stat small{font-size:10px;color:var(--muted)}.stat b{display:block;font-size:23px;margin-top:7px}.panel{margin-top:18px;background:#fff;border:1px solid var(--line);border-radius:19px;overflow:hidden}.panelhead{padding:16px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between}.tablewrap{overflow:auto}table{width:100%;border-collapse:collapse;min-width:760px}th,td{text-align:left;padding:12px 14px;border-bottom:1px solid #edf0f4;font-size:11px;vertical-align:top}th{font-size:9px;color:#8a95a3;text-transform:uppercase}td strong{font-size:12px}.contact{max-width:180px;word-break:break-word;color:#516176}.select{border:1px solid var(--line);background:#fff;border-radius:8px;padding:7px;font-size:10px}.empty{padding:30px;text-align:center;color:var(--muted)}.foot{margin-top:12px;color:#8a95a3;font-size:10px}@media(max-width:800px){.layout{grid-template-columns:1fr}.side{position:static;display:flex;overflow:auto}.side button{min-width:120px}.stats{grid-template-columns:1fr 1fr}.app{padding:12px}.right span:not(.online){display:none}}</style></head><body><div class="app"><header class="top"><div class="brand"><div class="logo">⚓</div>Работа в Питере · Админ</div><div class="right"><span class="online">● Онлайн</span><span>Администратор</span><button class="logout" onclick="logout()">Выйти</button></div></header><div class="layout"><aside class="side"><button class="active">⌂ Главная</button><button onclick="document.getElementById('orders').scrollIntoView({behavior:'smooth'})">▣ Заказы</button><button onclick="location.href='/'">↗ Открыть магазин</button></aside><main class="content"><h1>Главная</h1><div class="sub">Общая статистика и быстрый доступ к заказам</div><section class="stats"><div class="stat"><small>Всего заказов</small><b id="totalOrders">—</b></div><div class="stat"><small>Выручка</small><b id="revenue">—</b></div><div class="stat"><small>Сегодня заказов</small><b id="todayOrders">—</b></div><div class="stat"><small>Сегодня сумма</small><b id="todayRevenue">—</b></div></section><section class="panel" id="orders"><div class="panelhead"><b>Последние заявки</b><button class="refresh" onclick="loadAll()">Обновить</button></div><div class="tablewrap"><table><thead><tr><th>#</th><th>Дата</th><th>Услуги</th><th>Сумма</th><th>Контакт</th><th>Комментарий</th><th>Статус</th></tr></thead><tbody id="tbody"></tbody></table></div></section><div class="foot">Статусы можно менять прямо из таблицы. Обновление — каждые 30 секунд.</div></main></div></div><script>const rub=n=>new Intl.NumberFormat('ru-RU').format(n)+' ₽';function esc(v){return String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}async function loadStats(){let r=await fetch('/admin-web/api/stats');if(r.status===401){location.reload();return}let d=await r.json();totalOrders.textContent=d.total_orders;revenue.textContent=rub(d.revenue);todayOrders.textContent=d.today_orders;todayRevenue.textContent=rub(d.today_revenue)}async function loadOrders(){let r=await fetch('/admin-web/api/orders');if(r.status===401){location.reload();return}let rows=await r.json();tbody.innerHTML=rows.length?rows.map(o=>`<tr><td><strong>#${o.id}</strong></td><td>${new Date(o.created_at).toLocaleString('ru-RU')}</td><td>${o.services.join(', ')||'—'}</td><td><strong>${rub(o.total)}</strong></td><td class="contact">${esc(o.contact||'—')}</td><td class="contact">${esc(o.comment||'—')}</td><td><select class="select" onchange="setStatus(${o.id},this.value)">${['Новая','В работе','Ожидает оплаты','Выполнено','Отменено'].map(s=>`<option ${s===o.status?'selected':''}>${s}</option>`).join('')}</select></td></tr>`).join(''):'<tr><td colspan="7"><div class="empty">Заказов пока нет.</div></td></tr>'}async function setStatus(id,status){let r=await fetch('/admin-web/api/orders/'+id+'/status',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})});if(!r.ok)alert('Не удалось изменить статус');loadStats()}async function loadAll(){await Promise.all([loadStats(),loadOrders()])}async function logout(){await fetch('/admin-web/logout',{method:'POST'});location.reload()}loadAll();setInterval(loadAll,30000);</script></body></html>'''


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
