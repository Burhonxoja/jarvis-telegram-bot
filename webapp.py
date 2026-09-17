"""
Jarvis — Telegram Mini App (Web App) backend.

Bu bot.py'dagi inline-tugma menyularining o'rnini bosuvchi TO'LIQ veb-interfeys:
🏠 Bosh sahifa (biznes holati), ➕ Kirim qo'shish, 📁 Loyihalar, 👥 Xodimlar.

Alohida jarayon sifatida ishlaydi (Procfile'dagi "web" — bot.py esa "worker"),
ikkalasi ham BIR XIL Notion ma'lumotlar bazasidan (notion_api.py orqali)
foydalanadi va bir-biriga xalaqit bermaydi: bot.py hamon getUpdates orqali
Telegram komandalarini qabul qiladi, bu esa qo'shimcha ravishda Telegram
WebApp (mini-app) sifatida ochiladigan UI.

Xavfsizlik: har bir so'rovda Telegram WebApp "initData" satri Authorization
sarlavhasida ("tma <initData>") yuboriladi. Bu yerda Telegram hujjatidagi
rasmiy HMAC-SHA256 algoritmi bilan tekshiriladi va FAQAT ADMIN_CHAT_ID'ga mos
kelgan foydalanuvchiga ruxsat beriladi (bu bot hozircha faqat admin uchun
to'liq UI sifatida ishlaydi).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from calendar import monthrange
from datetime import date, datetime, timedelta
from urllib.parse import parse_qsl

import requests
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from zoneinfo import ZoneInfo

import notion_api as nx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jarvis_webapp")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
TASHKENT_TZ = ZoneInfo("Asia/Tashkent")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp_static")

app = FastAPI(title="Jarvis Mini App")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------------------
# Vaqt/oy yordamchilari (bot.py bilan bir xil mantiq)
# ----------------------------------------------------------------------------

def _tashkent_now() -> datetime:
    return datetime.now(TASHKENT_TZ).replace(tzinfo=None)


def _tashkent_today() -> date:
    return _tashkent_now().date()


def _current_month_str() -> str:
    return _tashkent_today().strftime("%Y-%m")


def _format_som(n: float) -> str:
    return f"{n:,.0f}".replace(",", " ") + " so'm"


def _send_telegram_message(chat_id: str | int, text: str) -> None:
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )
    except Exception:
        logger.exception("Telegram xabarini yuborishda xatolik")


# ----------------------------------------------------------------------------
# Xodim maosh hisob-kitobi — bot.py'dagi _hisob_period / _moliya_period_totals
# bilan AYNAN BIR XIL mantiq (ataylab dublikat qilingan: webapp alohida jarayon
# bo'lgani uchun bot.py'ni import qilib bo'lmaydi — u Telegram Application'ni
# darhol ishga tushiradi). Bot.py'da shu funksiyalarga o'zgartirish kiritilsa,
# BU YERDA HAM bir xil o'zgartirish qilish kerak.
# ----------------------------------------------------------------------------

def _hisob_period(hisob_kuni: int, today: date) -> tuple[date, date]:
    hisob_kuni = min(max(int(hisob_kuni), 1), 28)

    def _kun(year: int, month: int) -> date:
        return date(year, month, hisob_kuni)

    if today.day <= hisob_kuni:
        period_end = _kun(today.year, today.month)
        prev_month = today.month - 1 or 12
        prev_year = today.year - 1 if today.month == 1 else today.year
        period_start = _kun(prev_year, prev_month) + timedelta(days=1)
    else:
        period_start = _kun(today.year, today.month) + timedelta(days=1)
        next_month = today.month + 1 if today.month < 12 else 1
        next_year = today.year + 1 if today.month == 12 else today.year
        period_end = _kun(next_year, next_month)

    return period_start, period_end


def _moliya_period_totals(employee: dict, today: date | None = None) -> tuple:
    today = today or _tashkent_today()
    employee_id = employee["id"]
    turi = nx.get_select(employee, "Maosh turi")
    hisob_kuni = nx.get_number(employee, "Hisob kuni")

    if hisob_kuni:
        period_start, period_end = _hisob_period(int(hisob_kuni), today)
    else:
        days_in_month = monthrange(today.year, today.month)[1]
        period_start = date(today.year, today.month, 1)
        period_end = date(today.year, today.month, days_in_month)

    try:
        entries = nx.query_data_source(
            nx.DS_MOLIYA,
            filter_obj={
                "and": [
                    {"property": "Sana", "date": {"on_or_after": period_start.isoformat()}},
                    {"property": "Sana", "date": {"on_or_before": period_end.isoformat()}},
                ]
            },
        )
    except Exception:
        logger.exception("Moliya yozuvlarini olishda xatolik")
        entries = []

    chiqim = 0
    kirim_recorded = 0
    for e in entries:
        if employee_id not in nx.get_relation_ids(e, "Xodim"):
            continue
        sana_str = (nx.get_date(e, "Sana") or "")[:10]
        try:
            sana = date.fromisoformat(sana_str)
        except ValueError:
            continue
        if not (period_start <= sana <= period_end):
            continue
        e_turi = nx.get_select(e, "Turi")
        summa = nx.get_number(e, "Summa") or 0
        if e_turi == "Chiqim":
            chiqim += summa
        else:
            kirim_recorded += summa

    if turi == "Kunlik (oylik summadan)":
        maosh_summasi = nx.get_number(employee, "Maosh summasi") or 0
        total_days = (period_end - period_start).days + 1
        elapsed_days = min(max((min(today, period_end) - period_start).days + 1, 0), total_days)
        kirim = round((maosh_summasi / total_days) * elapsed_days) if total_days else 0
    else:
        kirim = kirim_recorded

    return kirim, chiqim, period_start, period_end


def _business_month_totals(month: str) -> tuple:
    try:
        entries = nx.query_data_source(nx.DS_MOLIYA)
    except Exception:
        logger.exception("Umumiy moliya hisobotini olishda xatolik")
        return 0, 0

    kirim = 0
    chiqim = 0
    for e in entries:
        sana = nx.get_date(e, "Sana") or ""
        if not sana.startswith(month):
            continue
        turi = nx.get_select(e, "Turi")
        summa = nx.get_number(e, "Summa") or 0
        xodimga_tegishli = bool(nx.get_relation_ids(e, "Xodim"))
        if turi == "Chiqim":
            chiqim += summa
        elif not xodimga_tegishli:
            kirim += summa
    return kirim, chiqim


# ----------------------------------------------------------------------------
# Telegram WebApp initData tekshiruvi
# https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app
# ----------------------------------------------------------------------------

def _validate_init_data(init_data: str) -> dict:
    if not init_data:
        raise HTTPException(status_code=401, detail="initData yo'q")
    parsed = dict(parse_qsl(init_data, strict_parsing=False))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="hash yo'q")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed_hash, received_hash):
        raise HTTPException(status_code=401, detail="Noto'g'ri imzo (initData)")
    try:
        auth_date = int(parsed.get("auth_date", "0"))
        if datetime.utcnow().timestamp() - auth_date > 86400:
            raise HTTPException(status_code=401, detail="Sessiya eskirgan, ilovani qayta oching")
    except ValueError:
        pass
    user_json = parsed.get("user")
    if not user_json:
        raise HTTPException(status_code=401, detail="Foydalanuvchi topilmadi")
    return json.loads(user_json)


def _require_admin(authorization: str | None) -> dict:
    if not authorization:
        raise HTTPException(status_code=401, detail="Ruxsat yo'q")
    init_data = authorization
    if init_data.lower().startswith("tma "):
        init_data = init_data[4:]
    user = _validate_init_data(init_data)
    user_id = str(user.get("id"))
    if not ADMIN_CHAT_ID or user_id != str(ADMIN_CHAT_ID):
        raise HTTPException(status_code=403, detail="Bu mini-app faqat admin uchun")
    return user


# ----------------------------------------------------------------------------
# Statik fayllar (frontend)
# ----------------------------------------------------------------------------

@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/healthz")
async def healthz():
    return {"ok": True}


# ----------------------------------------------------------------------------
# API: 🏠 Bosh sahifa
# ----------------------------------------------------------------------------

@app.get("/api/dashboard")
async def api_dashboard(authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    month = _current_month_str()
    biz_kirim, biz_chiqim = _business_month_totals(month)
    foyda = biz_kirim - biz_chiqim

    try:
        loyihalar = nx.query_data_source(
            nx.DS_LOYIHALAR, filter_obj={"property": "Holati", "select": {"equals": "Faol"}}
        )
    except Exception:
        logger.exception("Dashboard uchun loyihalarni olishda xatolik")
        loyihalar = []
    debit_qarzdorlar = [
        {"id": l["id"], "nomi": nx.get_title(l, "Loyiha") or "?", "summa": nx.get_number(l, "Debit") or 0}
        for l in loyihalar
        if (nx.get_number(l, "Debit") or 0) > 0
    ]
    debit_qarzdorlar.sort(key=lambda x: x["summa"], reverse=True)
    jami_debit = sum(d["summa"] for d in debit_qarzdorlar)

    try:
        employees = nx.query_data_source(nx.DS_XODIMLAR)
        target_employees = [e for e in employees if nx.get_select(e, "Maosh turi")]
        jami_kredit = 0
        for e in target_employees:
            e_turi = nx.get_select(e, "Maosh turi")
            e_kredit = nx.get_number(e, "Kredit") or 0
            if e_turi == "Kunlik (oylik summadan)":
                e_kirim, _, _, _ = _moliya_period_totals(e)
                e_kredit += e_kirim
            jami_kredit += e_kredit
    except Exception:
        logger.exception("Dashboard uchun xodimlar Kreditini yig'ishda xatolik")
        jami_kredit = 0

    return {
        "month": month,
        "biz_kirim": biz_kirim,
        "biz_chiqim": biz_chiqim,
        "foyda": foyda,
        "jami_debit": jami_debit,
        "debit_qarzdorlar": debit_qarzdorlar,
        "jami_kredit": jami_kredit,
        "format": {
            "biz_kirim": _format_som(biz_kirim),
            "biz_chiqim": _format_som(biz_chiqim),
            "foyda": _format_som(foyda),
            "jami_debit": _format_som(jami_debit),
            "jami_kredit": _format_som(jami_kredit),
        },
    }


# ----------------------------------------------------------------------------
# API: 📁 Loyihalar
# ----------------------------------------------------------------------------

@app.get("/api/loyihalar")
async def api_loyihalar(authorization: str | None = Header(default=None), holati: str = "Faol"):
    _require_admin(authorization)
    try:
        if holati and holati != "Hammasi":
            loyihalar = nx.query_data_source(
                nx.DS_LOYIHALAR, filter_obj={"property": "Holati", "select": {"equals": holati}}
            )
        else:
            loyihalar = nx.query_data_source(nx.DS_LOYIHALAR)
    except Exception:
        logger.exception("Loyihalar ro'yxatini olishda xatolik")
        raise HTTPException(status_code=500, detail="Loyihalarni olib bo'lmadi")

    loyihalar.sort(key=lambda l: (nx.get_title(l, "Loyiha") or "?").lower())
    result = []
    for l in loyihalar:
        result.append({
            "id": l["id"],
            "nomi": nx.get_title(l, "Loyiha") or "?",
            "holati": nx.get_select(l, "Holati"),
            "loyiha_turi": nx.get_select(l, "Loyiha turi"),
            "tolov_turi": nx.get_select(l, "To'lov turi"),
            "tolov_summasi": nx.get_number(l, "To'lov summasi") or 0,
            "debit": nx.get_number(l, "Debit") or 0,
            "boshlanish_sanasi": nx.get_date(l, "Boshlanish sanasi"),
            "oy": nx.get_rich_text(l, "Oy") or "",
        })
    return {"loyihalar": result}


# ----------------------------------------------------------------------------
# API: ➕ Kirim qo'shish
# ----------------------------------------------------------------------------

class KirimIn(BaseModel):
    project_id: str  # "none" — loyihasiz
    summa: float
    debit_ayirish: bool | None = None  # faqat project_id != "none" va joriy Debit > 0 bo'lganda ma'noli


@app.post("/api/kirim")
async def api_kirim(payload: KirimIn, authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    if payload.summa <= 0:
        raise HTTPException(status_code=400, detail="Summa musbat bo'lishi kerak")

    proj_nomi = "Boshqa"
    joriy_debit = None
    if payload.project_id != "none":
        try:
            proj_page = nx.get_page(payload.project_id)
            proj_nomi = nx.get_title(proj_page, "Loyiha") or "Loyiha"
            joriy_debit = nx.get_number(proj_page, "Debit") or 0
        except Exception:
            logger.exception("Kirim uchun loyihani olishda xatolik")
            raise HTTPException(status_code=404, detail="Loyiha topilmadi")

    try:
        nx.create_page(nx.DS_MOLIYA, {
            "Nomi": {"title": [{"text": {"content": f"{proj_nomi} — tushgan pul"}}]},
            "Turi": {"select": {"name": "Kirim"}},
            "Kategoriya": {"select": {"name": "Xizmat to'lovi"}},
            "Summa": {"number": payload.summa},
            "Sana": {"date": {"start": _tashkent_today().isoformat()}},
            "Izoh": {"rich_text": [{"text": {"content": f"Loyiha: {proj_nomi} (mini-app orqali)"}}]},
        })
    except Exception:
        logger.exception("Kirimni yozishda xatolik")
        raise HTTPException(status_code=500, detail="Kirimni qayd etib bo'lmadi")

    yangi_debit = None
    if payload.project_id != "none" and joriy_debit and joriy_debit > 0 and payload.debit_ayirish:
        try:
            yangi_debit = max(0, joriy_debit - payload.summa)
            nx.update_page_property(payload.project_id, {"Debit": {"number": yangi_debit}})
        except Exception:
            logger.exception("Kirim kelganda loyiha Debit'ini kamaytirishda xatolik")

    return {
        "ok": True,
        "proj_nomi": proj_nomi,
        "summa": payload.summa,
        "joriy_debit": joriy_debit,
        "yangi_debit": yangi_debit,
        "message": f"✅ {proj_nomi}dan {_format_som(payload.summa)} kirim qayd etildi.",
    }


# ----------------------------------------------------------------------------
# API: 👥 Xodimlar
# ----------------------------------------------------------------------------

@app.get("/api/xodimlar")
async def api_xodimlar(authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    try:
        employees = nx.query_data_source(nx.DS_XODIMLAR)
    except Exception:
        logger.exception("Xodimlarni olishda xatolik")
        raise HTTPException(status_code=500, detail="Xodimlarni olib bo'lmadi")

    target_employees = [e for e in employees if nx.get_select(e, "Maosh turi")]
    result = []
    for e in target_employees:
        nomi = nx.get_title(e, "Ism") or "?"
        turi = nx.get_select(e, "Maosh turi")
        kirim, chiqim, davr_boshi, davr_oxiri = _moliya_period_totals(e)
        kredit_hozir = nx.get_number(e, "Kredit") or 0
        balans = kredit_hozir + kirim - chiqim if turi == "Kunlik (oylik summadan)" else kredit_hozir
        result.append({
            "id": e["id"],
            "nomi": nomi,
            "lavozim": nx.get_select(e, "Lavozim"),
            "maosh_turi": turi,
            "hisob_kuni": nx.get_number(e, "Hisob kuni"),
            "maosh_summasi": nx.get_number(e, "Maosh summasi") or 0,
            "kredit_hozir": kredit_hozir,
            "davr_kirim": kirim,
            "davr_chiqim": chiqim,
            "davr_boshi": davr_boshi.isoformat(),
            "davr_oxiri": davr_oxiri.isoformat(),
            "balans": balans,
            "balans_fmt": _format_som(balans),
        })
    result.sort(key=lambda x: x["nomi"].lower())
    return {"xodimlar": result}


class XodimTolovIn(BaseModel):
    employee_id: str
    summa: float


def _xodim_tolov_yoki_avans(employee_id: str, summa: float, turi_nomi: str, kategoriya_izoh: str, xabar_matni: str) -> dict:
    if summa <= 0:
        raise HTTPException(status_code=400, detail="Summa musbat bo'lishi kerak")
    try:
        employee = nx.get_page(employee_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Xodim topilmadi")
    nomi = nx.get_title(employee, "Ism") or "Xodim"
    maosh_turi = nx.get_select(employee, "Maosh turi")

    try:
        nx.create_page(nx.DS_MOLIYA, {
            "Nomi": {"title": [{"text": {"content": f"{nomi} — {turi_nomi}"}}]},
            "Turi": {"select": {"name": "Chiqim"}},
            "Kategoriya": {"select": {"name": "Ish haqi"}},
            "Summa": {"number": summa},
            "Sana": {"date": {"start": _tashkent_today().isoformat()}},
            "Xodim": {"relation": [{"id": employee_id}]},
            "Izoh": {"rich_text": [{"text": {"content": f"{kategoriya_izoh} (mini-app orqali)"}}]},
        })
    except Exception:
        logger.exception(f"{nomi} uchun {turi_nomi}ni yozishda xatolik")
        raise HTTPException(status_code=500, detail="Qayd etib bo'lmadi")

    # "Kunlik (oylik summadan)" xodimlar uchun Kredit BU YERDA darhol kamaytirilmaydi —
    # ularning balansi (_moliya_period_totals) shu davrdagi barcha Chiqim'ni jonli hisoblaydi
    # va davr yakunida (bot.py'dagi scheduled_settlement_check) Kreditga bir marta qo'shiladi.
    # Aks holda ikki marta ayirilib qolar edi.
    yangi_kredit = None
    if maosh_turi != "Kunlik (oylik summadan)":
        try:
            joriy_kredit = nx.get_number(employee, "Kredit") or 0
            yangi_kredit = max(joriy_kredit - summa, 0)
            nx.update_page_property(employee_id, {"Kredit": {"number": yangi_kredit}})
        except Exception:
            logger.exception(f"{nomi} uchun Kreditni yangilashda xatolik")
            yangi_kredit = None

    chat_id_str = nx.get_rich_text(employee, "Telegram")
    if chat_id_str:
        try:
            _send_telegram_message(int(chat_id_str), f"{xabar_matni} {_format_som(summa)}.")
        except Exception:
            logger.exception("Xodimga bildirishnoma yuborishda xatolik")

    xabar = f"✅ {nomi}ga {_format_som(summa)} {turi_nomi} qayd etildi."
    if yangi_kredit is not None:
        xabar += f" Qolgan Kredit: {_format_som(yangi_kredit)}"
    return {"ok": True, "nomi": nomi, "yangi_kredit": yangi_kredit, "message": xabar}


@app.post("/api/xodim/payment")
async def api_xodim_payment(payload: XodimTolovIn, authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    return _xodim_tolov_yoki_avans(
        payload.employee_id, payload.summa, "oylik to'lovi", "Admin orqali qayd etilgan to'lov",
        "💵 Sizga to'lov qilindi:",
    )


@app.post("/api/xodim/advance")
async def api_xodim_advance(payload: XodimTolovIn, authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    return _xodim_tolov_yoki_avans(
        payload.employee_id, payload.summa, "avans", "Avans (admin orqali)",
        "🪙 Sizga avans berildi:",
    )
