import os
import sqlite3
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
    con.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, service_ids TEXT, total INTEGER, contact TEXT, comment TEXT)")
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
    return {"ok": True}


HTML = r'''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#17122d">
<title>Работа в Питере — размещение вакансий</title>
<style>
:root{--bg:#f7f5ff;--card:#fff;--ink:#171526;--muted:#6f6a82;--line:#e9e5f5;--violet:#6d45ff;--violet2:#8c63ff;--cyan:#28c7ff;--pink:#ff5ea8;--shadow:0 18px 50px rgba(45,28,105,.10)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(circle at 0 0,#eee8ff 0,transparent 35%),radial-gradient(circle at 100% 10%,#e6fbff 0,transparent 28%),var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
button,input,textarea{font:inherit}.wrap{max-width:920px;margin:auto;padding:16px 16px 120px}.hero{position:relative;overflow:hidden;color:#fff;border-radius:32px;padding:26px 22px 24px;background:linear-gradient(135deg,#17122d 0%,#37206f 52%,#5e36c9 100%);box-shadow:0 25px 70px rgba(65,38,153,.28)}.hero:after{content:"";position:absolute;width:190px;height:190px;border-radius:50%;right:-50px;top:-70px;background:linear-gradient(135deg,#28c7ff66,#ff5ea866);filter:blur(4px)}.eyebrow{position:relative;z-index:1;font-size:12px;font-weight:900;letter-spacing:.14em;opacity:.72}.hero h1{position:relative;z-index:1;font-size:36px;line-height:1.02;margin:12px 0 10px;max-width:650px}.hero p{position:relative;z-index:1;margin:0;color:#e6e0ff;line-height:1.5;max-width:690px}.chips{position:relative;z-index:1;display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}.chip{padding:9px 12px;border-radius:999px;background:#ffffff18;border:1px solid #ffffff22;font-size:12px;font-weight:800}.nav{position:sticky;top:8px;z-index:5;display:flex;gap:7px;margin:14px 0;padding:7px;background:#ffffffd9;backdrop-filter:blur(18px);border:1px solid var(--line);border-radius:18px;box-shadow:0 10px 30px #25145c12}.nav button{flex:1;border:0;background:transparent;color:var(--muted);padding:11px 8px;border-radius:13px;font-weight:800;font-size:12px}.nav button.active{background:#17122d;color:#fff}.section-head{display:flex;align-items:end;justify-content:space-between;gap:12px;margin:28px 2px 12px}.section-head h2{margin:0;font-size:25px}.section-head span{color:var(--muted);font-size:12px}.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}.card{background:rgba(255,255,255,.9);border:1px solid var(--line);border-radius:25px;padding:17px;box-shadow:var(--shadow);position:relative;overflow:hidden}.card:before{content:"";position:absolute;left:0;right:0;top:0;height:4px;background:linear-gradient(90deg,var(--violet),var(--cyan))}.card.violet:before{background:linear-gradient(90deg,#6d45ff,#c27aff)}.card.gold:before{background:linear-gradient(90deg,#ffb300,#ff6f61)}.card.blue:before{background:linear-gradient(90deg,#4a7dff,#24c9ff)}.card.cyan:before{background:linear-gradient(90deg,#12b9c9,#37e5ff)}.card.pink:before{background:linear-gradient(90deg,#ff4e9b,#9a5cff)}.topline{display:flex;justify-content:space-between;gap:8px;align-items:center}.badge{display:inline-flex;padding:7px 9px;border-radius:10px;background:#f0ecff;color:#5b3ce4;font-size:10px;font-weight:900;text-transform:uppercase}.type{font-size:10px;color:#8a849a;font-weight:700}.card h3{font-size:21px;margin:13px 0 5px}.sub{font-size:13px;line-height:1.45;color:#4f4a61;min-height:38px}.price{font-size:28px;font-weight:950;margin:14px 0 8px}.per{font-size:11px;color:var(--muted)}.features{margin:13px 0 15px;padding:0;list-style:none}.features li{font-size:12px;color:#5f596f;padding:6px 0;display:flex;gap:8px}.features li:before{content:"✓";color:#6845ff;font-weight:900}.btn{width:100%;border:0;border-radius:15px;padding:13px 14px;font-weight:900;cursor:pointer}.btn.primary{background:linear-gradient(135deg,#6d45ff,#8d62ff);color:#fff;box-shadow:0 10px 22px #6d45ff2d}.btn.secondary{background:#f0edff;color:#5637d7}.btn.dark{background:#17122d;color:#fff}.note{margin-top:8px;font-size:10px;text-align:center;color:#8b8598}.info-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.info{background:#fff;border:1px solid var(--line);border-radius:21px;padding:17px;box-shadow:0 12px 30px #25145c0b}.icon{font-size:24px}.info h3{font-size:15px;margin:10px 0 6px}.info p{font-size:12px;line-height:1.45;color:var(--muted);margin:0}.steps{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.step{background:#fff;border:1px solid var(--line);border-radius:20px;padding:16px}.num{font-size:11px;font-weight:950;color:#6d45ff}.step strong{display:block;margin:8px 0 5px}.step p{margin:0;font-size:11px;line-height:1.4;color:var(--muted)}.conditions{background:linear-gradient(135deg,#fff,#f0edff);border:1px solid var(--line);border-radius:24px;padding:18px}.conditions ul{margin:0;padding-left:20px;color:#625d70;font-size:12px;line-height:1.65}.cartbar{position:fixed;left:0;right:0;bottom:0;z-index:10;padding:10px 14px calc(10px + env(safe-area-inset-bottom));background:#fffdfedc;backdrop-filter:blur(20px);border-top:1px solid var(--line)}.cartin{max-width:890px;margin:auto;display:flex;align-items:center;gap:10px}.cartsummary{flex:1}.cartsummary small{display:block;color:var(--muted);font-size:11px}.cartsummary strong{font-size:21px}.cartbtn{border:0;border-radius:15px;padding:13px 16px;background:#17122d;color:#fff;font-weight:900}.cartbtn span{background:#fff;color:#17122d;border-radius:999px;padding:2px 6px;margin-left:4px}.modal{position:fixed;inset:0;z-index:20;background:#0e0922aa;backdrop-filter:blur(6px);display:none;align-items:flex-end;justify-content:center;padding:10px}.sheet{width:min(760px,100%);max-height:90vh;overflow:auto;background:#fff;border-radius:28px;padding:20px;box-shadow:0 30px 80px #0004}.sheethead{display:flex;justify-content:space-between;align-items:center}.sheet h2{margin:0;font-size:25px}.close{border:0;background:#f1eef8;border-radius:50%;width:40px;height:40px}.cartitem{display:flex;justify-content:space-between;gap:12px;padding:13px 0;border-bottom:1px solid var(--line)}.cartitem b{font-size:13px}.remove{border:0;background:#fff0f4;color:#d83c70;border-radius:10px;padding:7px 9px;font-size:11px;font-weight:800}.totalrow{display:flex;justify-content:space-between;margin:18px 0;font-size:17px}.totalrow strong{font-size:25px}label{display:block;font-size:12px;font-weight:800;margin:12px 0 5px}input,textarea{width:100%;border:1px solid #ddd7eb;border-radius:14px;padding:13px;background:#fbfaff;outline:none}textarea{min-height:95px;resize:vertical}.success{padding:16px;border-radius:17px;background:#ecfff5;color:#176d43;font-weight:800;margin-top:12px}.muted{color:var(--muted);font-size:12px;line-height:1.5}
@media(max-width:680px){.hero h1{font-size:30px}.grid{grid-template-columns:1fr}.info-grid{grid-template-columns:1fr}.steps{grid-template-columns:1fr 1fr}.nav button{font-size:11px;padding:10px 4px}}
</style>
</head>
<body>
<div class="wrap">
<section class="hero">
<div class="eyebrow">РАБОТА В ПИТЕРЕ • TELEGRAM</div>
<h1>Разместите вакансию так, чтобы её заметили.</h1>
<p>Выберите тариф или пакет, добавьте услуги в корзину и отправьте заявку. Мы упакуем вакансию, согласуем публикацию и разместим её в канале.</p>
<div class="chips"><span class="chip">📍 Санкт-Петербург и ЛО</span><span class="chip">🤖 ИИ-визуализация</span><span class="chip">⚡ Быстрый запуск</span><span class="chip">🕙 Приём заявок 10:00–22:00</span></div>
</section>
<nav class="nav"><button class="active" onclick="go('tariffs',this)">Тарифы</button><button onclick="go('packages',this)">Пакеты</button><button onclick="go('how',this)">Как работаем</button><button onclick="openCart()">🛒 Корзина <span id="navCount">0</span></button></nav>

<section id="tariffs"><div class="section-head"><h2>Разовые тарифы</h2><span>от 250 ₽</span></div><div id="tariffGrid" class="grid"></div></section>
<section id="packages"><div class="section-head"><h2>Пакетные предложения</h2><span>выгоднее при регулярном найме</span></div><div id="packageGrid" class="grid"></div><div class="conditions" style="margin-top:12px"><b>ℹ️ Условия пакетов</b><ul><li>Все пакеты базируются на тарифе «Под ключ» и включают уникальное ИИ-фото для каждой вакансии.</li><li>Срок действия абонементов — 30–60 дней с момента оплаты.</li><li>Можно публиковать одну и ту же вакансию повторно или разные должности.</li></ul></div></section>
<section id="why"><div class="section-head"><h2>Почему выбирают нас</h2></div><div class="info-grid"><div class="info"><div class="icon">🎯</div><h3>Целевой охват</h3><p>Аудитория из Санкт-Петербурга и Ленинградской области, заинтересованная в работе и подработке.</p></div><div class="info"><div class="icon">✨</div><h3>ИИ-визуализация</h3><p>Уникальные обложки и видео помогают вакансии выделяться в ленте.</p></div><div class="info"><div class="icon">⚡</div><h3>Быстрый запуск</h3><p>Редактируем, структурируем и публикуем вакансию в день обращения.</p></div></div></section>
<section id="how"><div class="section-head"><h2>Как всё происходит</h2></div><div class="steps"><div class="step"><span class="num">01</span><strong>Заявка</strong><p>Пришлите текст вакансии или ссылку.</p></div><div class="step"><span class="num">02</span><strong>Упаковка</strong><p>Редактируем текст и готовим визуал.</p></div><div class="step"><span class="num">03</span><strong>Согласование</strong><p>Вы утверждаете готовый пост и тариф.</p></div><div class="step"><span class="num">04</span><strong>Публикация</strong><p>Выкладываем вакансию и вы получаете отклики.</p></div></div></section>
</div>
<div class="cartbar"><div class="cartin"><div class="cartsummary"><small id="cartLabel">Корзина пуста</small><strong id="cartSum">0 ₽</strong></div><button class="cartbtn" onclick="openCart()">Открыть корзину <span id="barCount">0</span></button></div></div>

<div id="cartModal" class="modal" onclick="if(event.target===this)closeCart()"><div class="sheet"><div class="sheethead"><h2>🛒 Корзина</h2><button class="close" onclick="closeCart()">✕</button></div><div id="cartItems"></div><div class="totalrow"><span>Итого</span><strong id="modalTotal">0 ₽</strong></div><button class="btn primary" onclick="openCheckout()">Оформить заявку</button></div></div>
<div id="checkoutModal" class="modal" onclick="if(event.target===this)closeCheckout()"><div class="sheet"><div class="sheethead"><h2>Заявка</h2><button class="close" onclick="closeCheckout()">✕</button></div><p class="muted" id="checkoutChosen"></p><label>Контакт для связи *</label><input id="contact" placeholder="@username или номер телефона"><label>Комментарий</label><textarea id="comment" placeholder="Например: нужно разместить вакансию менеджера с понедельника"></textarea><button class="btn primary" onclick="sendOrder()">Отправить заявку</button><div id="result"></div></div></div>
<script>
let services=[],cart=JSON.parse(localStorage.getItem('workspb_cart')||'[]');
const rub=n=>new Intl.NumberFormat('ru-RU').format(n)+' ₽';
const byId=id=>services.find(s=>s.id===id);
async function init(){services=await (await fetch('/api/services')).json();render();}
function card(s){return `<article class="card ${s.accent}"><div class="topline"><span class="badge">${s.tag}</span><span class="type">${s.type}</span></div><h3>${s.name}</h3><div class="sub">${s.subtitle}</div><div class="price">${rub(s.price)}</div><div class="per">${s.type==='Пакет'?'готовый пакет для регулярного найма':'за публикацию'}</div><ul class="features">${s.features.map(x=>`<li>${x}</li>`).join('')}</ul><button class="btn ${cart.includes(s.id)?'secondary':'dark'}" onclick="toggle(${s.id})">${cart.includes(s.id)?'✓ В корзине':'Добавить в корзину'}</button><div class="note">${s.description}</div></article>`}
function render(){tariffGrid.innerHTML=services.filter(s=>s.type!=='Пакет').map(card).join('');packageGrid.innerHTML=services.filter(s=>s.type==='Пакет').map(card).join('');let total=cart.reduce((a,id)=>a+byId(id).price,0);cartSum.textContent=rub(total);modalTotal.textContent=rub(total);let c=cart.length;barCount.textContent=c;navCount.textContent=c;cartLabel.textContent=c?`${c} ${c===1?'позиция':'позиции'} в корзине`:'Корзина пуста';localStorage.setItem('workspb_cart',JSON.stringify(cart));}
function toggle(id){cart.includes(id)?cart=cart.filter(x=>x!==id):cart.push(id);render()}
function go(id,btn){document.getElementById(id).scrollIntoView({behavior:'smooth',block:'start'});document.querySelectorAll('.nav button').forEach(x=>x.classList.remove('active'));btn.classList.add('active')}
function openCart(){render();cartModal.style.display='flex'} function closeCart(){cartModal.style.display='none'}
function removeItem(id){cart=cart.filter(x=>x!==id);render();openCart()}
function openCheckout(){if(!cart.length)return;checkoutChosen.textContent='Выбрано: '+cart.map(id=>byId(id).name).join(', ')+' • '+rub(cart.reduce((a,id)=>a+byId(id).price,0));closeCart();checkoutModal.style.display='flex'} function closeCheckout(){checkoutModal.style.display='none'}
async function sendOrder(){if(!contact.value.trim()){contact.focus();return}let r=await fetch('/api/checkout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({service_ids:cart,contact:contact.value,comment:comment.value})});let d=await r.json();if(!d.ok){result.innerHTML='<div class="success" style="background:#fff0f3;color:#a52954">'+d.message+'</div>';return}result.innerHTML='<div class="success">✅ Заявка #'+d.order_id+' отправлена. Мы свяжемся с вами для подтверждения.</div>';cart=[];render()}
cartModal.addEventListener('click',e=>{});
const oldRender=render;render=function(){oldRender();cartItems.innerHTML=cart.length?cart.map(id=>{let s=byId(id);return `<div class="cartitem"><div><b>${s.name}</b><div class="muted">${s.tag}</div></div><div style="text-align:right"><b>${rub(s.price)}</b><br><button class="remove" onclick="removeItem(${s.id})">Убрать</button></div></div>`}).join(''):'<p class="muted">Добавьте тарифы или пакеты — они появятся здесь.</p>'};
init();
</script>
</body></html>'''

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
