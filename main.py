from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List

app = FastAPI(title="Работа в Питере — Mini App")

SERVICES = [
    {"id": 1, "name": "БАЗОВЫЙ", "price": 250, "tag": "Быстрый старт", "desc": "Редактура, структура, публикация и навигация по вакансии."},
    {"id": 2, "name": "ПОД КЛЮЧ", "price": 400, "tag": "Популярный", "desc": "Всё из Базового + уникальная AI-обложка и яркое оформление."},
    {"id": 3, "name": "ПРЕМИУМ", "price": 800, "tag": "Максимум", "desc": "Под ключ + AI-видеокреатив и закрепление в топе на 24 часа."},
    {"id": 4, "name": "START", "price": 1600, "tag": "5 публикаций", "desc": "Пакет из 5 публикаций. 320 ₽ за публикацию."},
    {"id": 5, "name": "MASS-НАЙМ", "price": 2900, "tag": "10 публикаций", "desc": "Пакет из 10 публикаций. 290 ₽ за публикацию."},
    {"id": 6, "name": "HR-PARTNER", "price": 5000, "tag": "20 публикаций", "desc": "Пакет из 20 публикаций. 250 ₽ за публикацию."},
]

class Order(BaseModel):
    service_ids: List[int]
    contact: str = ""
    comment: str = ""

@app.get("/", response_class=HTMLResponse)
@app.get("/shop", response_class=HTMLResponse)
def shop():
    return HTML

@app.get("/api/services")
def services():
    return SERVICES

@app.post("/api/checkout")
def checkout(order: Order):
    chosen = [s for s in SERVICES if s["id"] in order.service_ids]
    total = sum(s["price"] for s in chosen)
    return {"ok": True, "total": total, "message": "Заявка принята. Для подтверждения свяжемся с вами."}

HTML = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Работа в Питере — размещение вакансий</title>
<style>
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f5f7fb;color:#111827}
.wrap{max-width:760px;margin:auto;padding:18px 16px 110px}
.hero{background:linear-gradient(135deg,#111827,#374151);color:#fff;border-radius:28px;padding:26px 22px;box-shadow:0 16px 40px #0002}
.logo{font-size:13px;font-weight:800;letter-spacing:.12em;opacity:.75}.hero h1{font-size:32px;line-height:1.05;margin:12px 0}.hero p{margin:0;color:#d1d5db;line-height:1.5}
.stats{display:flex;gap:8px;margin-top:20px;flex-wrap:wrap}.stat{background:#ffffff18;border:1px solid #ffffff22;padding:9px 12px;border-radius:14px;font-size:12px}
h2{font-size:22px;margin:28px 2px 12px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:22px;padding:16px;box-shadow:0 6px 18px #1118270a;position:relative}.badge{font-size:11px;font-weight:800;text-transform:uppercase;background:#eef2ff;color:#4f46e5;padding:6px 9px;border-radius:9px;display:inline-block}.card h3{margin:13px 0 6px;font-size:18px}.desc{font-size:13px;line-height:1.4;color:#6b7280;min-height:55px}.price{font-size:23px;font-weight:900;margin:12px 0}.btn{width:100%;border:0;border-radius:14px;padding:12px;font-weight:800;font-size:14px;background:#111827;color:#fff}.btn.add{background:#111827}.btn.added{background:#e5e7eb;color:#111827}
.cart{position:fixed;left:0;right:0;bottom:0;padding:12px 16px;background:#ffffffee;backdrop-filter:blur(14px);border-top:1px solid #e5e7eb}.cartin{max-width:728px;margin:auto;display:flex;align-items:center;justify-content:space-between;gap:12px}.total small{display:block;color:#6b7280}.total strong{font-size:22px}.checkout{background:#4f46e5;color:white;border:0;border-radius:15px;padding:14px 18px;font-weight:900}
.modal{position:fixed;inset:0;background:#0008;display:none;align-items:flex-end;justify-content:center;padding:12px}.sheet{background:#fff;border-radius:26px 26px 18px 18px;padding:22px;width:min(720px,100%)}input,textarea{width:100%;padding:13px;border:1px solid #d1d5db;border-radius:13px;margin:6px 0 10px;font:inherit}textarea{min-height:90px;resize:vertical}.close{float:right;border:0;background:#f3f4f6;border-radius:50%;width:36px;height:36px}
.empty{grid-column:1/-1;background:#fff;padding:30px;border-radius:20px;text-align:center;color:#6b7280}
@media(max-width:560px){.grid{grid-template-columns:1fr}.hero h1{font-size:29px}.desc{min-height:auto}}
</style>
</head>
<body>
<div class="wrap">
<section class="hero">
<div class="logo">РАБОТА В ПИТЕРЕ</div>
<h1>Разместите вакансию.<br>Получите отклики.</h1>
<p>Выберите тариф, добавьте услуги в корзину и отправьте заявку. Оплата пока отключена — это демо-версия.</p>
<div class="stats"><span class="stat">📍 Санкт-Петербург</span><span class="stat">⚡ Публикация в день обращения</span><span class="stat">🤖 AI-оформление</span></div>
</section>
<h2>Тарифы и пакеты</h2>
<div id="grid" class="grid"></div>
</div>
<div class="cart"><div class="cartin"><div class="total"><small id="count">0 услуг</small><strong id="sum">0 ₽</strong></div><button class="checkout" onclick="openModal()">Оформить заявку</button></div></div>
<div id="modal" class="modal" onclick="if(event.target===this)closeModal()">
<div class="sheet">
<button class="close" onclick="closeModal()">✕</button>
<h2 style="margin-top:0">Заявка</h2>
<p id="chosen" style="color:#6b7280"></p>
<input id="contact" placeholder="Контакт для связи (Telegram / телефон)">
<textarea id="comment" placeholder="Комментарий к заказу"></textarea>
<button class="checkout" style="width:100%" onclick="sendOrder()">Отправить заявку</button>
<p id="result" style="text-align:center"></p>
</div></div>
<script>
let services=[],cart=[];
const rub=n=>new Intl.NumberFormat('ru-RU').format(n)+' ₽';
async function init(){services=await (await fetch('/api/services')).json();render()}
function render(){
grid.innerHTML=services.map(s=>`<div class="card"><span class="badge">${s.tag}</span><h3>${s.name}</h3><div class="desc">${s.desc}</div><div class="price">${rub(s.price)}</div><button class="btn ${cart.includes(s.id)?'added':''}" onclick="toggle(${s.id})">${cart.includes(s.id)?'✓ В корзине':'Добавить'}</button></div>`).join('');
let total=cart.reduce((a,id)=>a+services.find(s=>s.id===id).price,0);count.textContent=cart.length+' '+(cart.length===1?'услуга':'услуг');sum.textContent=rub(total)
}
function toggle(id){cart.includes(id)?cart=cart.filter(x=>x!==id):cart.push(id);render()}
function openModal(){if(!cart.length){alert('Сначала добавьте услугу в корзину');return}chosen.textContent='Выбрано: '+cart.map(id=>services.find(s=>s.id===id).name).join(', ');modal.style.display='flex'}
function closeModal(){modal.style.display='none'}
async function sendOrder(){
let r=await fetch('/api/checkout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({service_ids:cart,contact:contact.value,comment:comment.value})});
let d=await r.json();result.textContent=d.message+' Сумма: '+rub(d.total);cart=[];render()
}
init();
</script>
</body></html>"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
