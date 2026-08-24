"""
Jarvis Telegram Bot — Notion bilan ishlaydigan yagona boshqaruv boti.

BUYRUQLAR
  /start                         - botni ishga tushirish, asosiy menyu (tugmalar)
  /menu                          - asosiy menyuni qayta ko'rsatish (tugmalar)
  /men <Ism>                     - o'zingizni xodim sifatida ro'yxatdan o'tkazish
                                    (Xodimlar bazasidagi "Ism" bilan bir xil bo'lishi kerak)
  /hisobot                       - bugungi vazifalar va kontent-reja holati
  /vazifalarim                   - sizga tayinlangan, hali bajarilmagan vazifalar
  /vazifa                        - yangi TZ berish: tugma orqali xodim va muddat tanlanadi, keyin matn yoziladi
  /vazifa <Ism> | <matn>         - (eski usul) xodimga yangi TZ (vazifa) beradi, unga xabar yuboradi
  /kontent                       - "Yozildi" statusidagi postlar, Tasdiqlash/Rad etish tugmalari bilan
  /joylash                       - "Tasdiqlandi" statusidagi postlarni haqiqiy Telegram kanaliga joylaydi
  /target                        - barcha yo'nalishlar bo'yicha target/bajarildi progressi
  /reels                         - bugungi reels sonini loyiha bo'yicha kiritish
  /moliya                        - moliya: admin hammani, xodim faqat o'z balansini ko'radi

  Har bir vazifa xabarida "💬 Izoh" tugmasi bor — xodim vazifaga izoh yozib qoldirishi mumkin
  (izoh Notion'dagi vazifa sahifasiga komment sifatida qo'shiladi).

MOLIYA / MAOSH HISOBLASH
  - Xodimlar bazasida har bir xodim uchun "Maosh turi" belgilanadi:
      "Kunlik (oylik summadan)" — oylik summa kunlar soniga bo'linib, har kuni avtomatik qo'shiladi
      "Vazifa boshiga" — har "✅ Bajardim" bosilganda summa/maqsad_soni miqdorida qo'shiladi
  - Balans = shu oy jamg'argan (Kirim) − shu oy to'langan (Chiqim), Notion "Moliya" bazasida saqlanadi
  - Har bir xodimning o'z "Hisob kuni"si bor (Xodimlar bazasida, masalan Hasan=10, Mubina=20) —
    shu kuni SETTLEMENT_HOUR'da adminga o'sha xodim bo'yicha balans + to'lov/avans/stavka tugmalari yuboriladi
  - "💸 Avans" tugmasi orqali oylik hisob-kitobdan oldin ham to'lov (Chiqim) qayd etish mumkin

AVTOMATIK
  - Har kuni ADMIN_CHAT_ID'ga belgilangan vaqtda (standart 20:00) kunlik hisobot yuboriladi
  - Har kuni REELS_HOUR'da (standart 19:30) ADMIN_CHAT_ID'dan reels soni so'raladi
  - REMINDER_HOURS'da ko'rsatilgan har bir soatda (standart 9,11,13,15,17,19) kimda ochiq
    vazifa bo'lsa, o'sha xodimga eslatma boradi
  - Har kuni MOTIVATION_HOUR'da (standart 08:00) hammaga (ALLOWED_CHAT_IDS) motivatsion gap yuboriladi
  - Har kuni MOOD_HOUR'da (standart 21:00) hammadan "kuningiz qanday o'tdi?" so'raladi
    (😞 Yomon / 😐 O'rta / 🔥 Zo'r tugmalari bilan)
  - "Kunlik (oylik summadan)" turidagi xodimlarning jamg'arilgan maoshi REAL VAQTDA hisoblanadi
    (bugungi kungacha o'tgan kunlar asosida) — alohida tungi cron-job shart emas
  - Har kuni SETTLEMENT_HOUR'da (standart 09:00) tekshiriladi: kimning "Hisob kuni"si bugunga to'g'ri
    kelsa, o'sha xodim uchun adminga balans + to'lov/avans/stavka tugmalari yuboriladi
  - Har AUTO_PUBLISH_INTERVAL_MINUTES daqiqada (standart 5) "Tasdiqlandi" statusidagi postlar
    orasidan Sana+Vaqt'i kelib yetganlari avtomatik kanalga joylanadi (qo'lda /joylash shart emas),
    har safar adminga xabar boradi

ISHGA TUSHIRISH
  1) pip install -r requirements.txt
  2) Muhit o'zgaruvchilari: TELEGRAM_BOT_TOKEN, NOTION_TOKEN (majburiy)
     ADMIN_CHAT_ID (kunlik avtomatik hisobot uchun tavsiya etiladi)
     CHANNEL_UROLOG_SHOVKAT, CHANNEL_ARK_HOSPITAL, CHANNEL_18_NATIJALAR (kanalga joylash uchun,
     bot shu kanallarda admin/post huquqiga ega bo'lishi kerak — @kanal_username yoki -100xxxxxxxxxx ko'rinishida)
  3) python bot.py
"""
from __future__ import annotations  # Python 3.9 bilan moslik uchun (dict | None yozuvi)

import functools
import html
import logging
import os
import random
import re
from calendar import monthrange
from datetime import date, datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

# Barcha rejalashtirilgan vaqtlar (eslatmalar, hisobotlar va h.k.) shu vaqt zonasida
# hisoblanadi — server (Railway) odatda UTC'da ishlaydi, lekin biznes Toshkentda joylashgan.
TASHKENT_TZ = ZoneInfo("Asia/Tashkent")


def _tashkent_now() -> datetime:
    """Joriy vaqtni Toshkent mahalliy vaqtida, lekin tzinfo'siz (naive) qaytaradi —
    Notion'dagi Sana/Vaqt qiymatlari ham tzinfo'siz va Toshkent vaqti deb hisoblanadi,
    shuning uchun ular bilan to'g'ridan-to'g'ri solishtirish mumkin bo'lishi kerak."""
    return datetime.now(TASHKENT_TZ).replace(tzinfo=None)


def _tashkent_today() -> date:
    return _tashkent_now().date()

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.error import TelegramError

import notion_api as nx
import gemini_api as gx
import openai_api as ox
import dashboard

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("jarvis-bot")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")  # kunlik hisobot va xodim bildirishnomalari uchun
REPORT_HOUR = int(os.environ.get("REPORT_HOUR", "20"))
REPORT_MINUTE = int(os.environ.get("REPORT_MINUTE", "0"))
REELS_HOUR = int(os.environ.get("REELS_HOUR", "19"))
REELS_MINUTE = int(os.environ.get("REELS_MINUTE", "30"))

# Har necha daqiqada "Tasdiqlandi" statusidagi postlar orasidan Sana+Vaqt'i kelib yetganlarini
# tekshirib, avtomatik ravishda haqiqiy kanalga joylaydi (qo'lda /joylash bosish shart emas).
AUTO_PUBLISH_INTERVAL_MINUTES = int(os.environ.get("AUTO_PUBLISH_INTERVAL_MINUTES", "5"))

# Gemini (Nano Banana) orqali avtomatik yasalgan rasmlar shu papkada saqlanadi
# (Notion'ning "Rasm/Video havolasi" maydoni haqiqiy internet-URL talab qiladi, shuning uchun
# generatsiya qilingan rasm avval shu yerga, keyin — kerak bo'lganda — kanalga yuboriladi).
GENERATED_IMAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated_images")
os.makedirs(GENERATED_IMAGES_DIR, exist_ok=True)

# Vazifa eslatmalari: shu soatlarda, kimda ochiq (bajarilmagan) vazifa bo'lsa, o'sha odamga eslatma boradi.
REMINDER_HOURS = [int(x.strip()) for x in os.environ.get("REMINDER_HOURS", "9,11,13,15,17,19").split(",") if x.strip()]

MOTIVATION_HOUR = int(os.environ.get("MOTIVATION_HOUR", "8"))
MOTIVATION_MINUTE = int(os.environ.get("MOTIVATION_MINUTE", "0"))

MOOD_HOUR = int(os.environ.get("MOOD_HOUR", "19"))
MOOD_MINUTE = int(os.environ.get("MOOD_MINUTE", "30"))

# Har bir xodimning o'z "Hisob kuni" (oyning qaysi sanasida hisob-kitob qilinishi) bor —
# shu kuni SETTLEMENT_HOUR'da adminga o'sha xodim bo'yicha balans + amallar (to'lov/avans/stavka) yuboriladi.
SETTLEMENT_HOUR = int(os.environ.get("SETTLEMENT_HOUR", "9"))
SETTLEMENT_MINUTE = int(os.environ.get("SETTLEMENT_MINUTE", "0"))

# "Oylik (fixed)" turidagi loyihalar uchun: har oy loyihaning "Boshlanish sanasi"
# kuni (kun raqami) kelganda, "To'lov summasi" avtomatik "Debit"ga qo'shiladi.
LOYIHA_BILLING_HOUR = int(os.environ.get("LOYIHA_BILLING_HOUR", "9"))
LOYIHA_BILLING_MINUTE = int(os.environ.get("LOYIHA_BILLING_MINUTE", "30"))

# "Tungi tinchlik" — shu vaqt oralig'ida (standart 20:00–07:00) xodimlarga HECH QANDAY
# avtomatik xabar (eslatma, motivatsiya, kayfiyat so'rovi, yangi vazifa bildirishnomasi)
# yuborilmaydi. Shu oraliqda tayinlangan yangi vazifa xabari QUIET_HOURS_END'da yuboriladi.
QUIET_HOURS_START = int(os.environ.get("QUIET_HOURS_START", "20"))
QUIET_HOURS_END = int(os.environ.get("QUIET_HOURS_END", "7"))


def _is_quiet_hours(now: "datetime | None" = None) -> bool:
    now = now or _tashkent_now()
    hour = now.hour
    if QUIET_HOURS_START == QUIET_HOURS_END:
        return False
    if QUIET_HOURS_START < QUIET_HOURS_END:
        return QUIET_HOURS_START <= hour < QUIET_HOURS_END
    # Kechadan tongga o'tuvchi oraliq (masalan 20 -> 7)
    return hour >= QUIET_HOURS_START or hour < QUIET_HOURS_END


UZ_WEEKDAYS = ["Dush", "Sesh", "Chor", "Pay", "Juma", "Shan", "Yak"]

MOTIVATION_QUOTES = [
    "Bugun ham bir qadam oldinga — kichik harakatlar katta natijalar beradi. 💪",
    "Yaxshi kun kayfiyatdan emas, harakatdan boshlanadi. Omad! 🚀",
    "Har bir bajarilgan vazifa — katta maqsad tomon bir qadam. Ishga kirishaylik! 🔥",
    "Bugungi mehnating ertangi natijang. Ishonch bilan boshla! ✨",
    "Kichik intizom, katta yutuq keltiradi. Zo'r kun tilaymiz! 💼",
    "Sen qila olasan — faqat birinchi qadamni tashla. Xayrli kun! 🌅",
    "Jamoa bo'lib ishlasak, har qanday maqsad qo'lga kiradi. Omad, jamoa! 🤝",
    "Bugun kim bo'lishing — bugungi tanlovlaring bilan belgilanadi. Zo'r bo'l! ⭐",
    "Muvaffaqiyat — har kungi kichik g'alabalar yig'indisi. Boshladik! 📈",
    "Qiyinchilik — o'sish uchun imkoniyat. Bugun ham o'sib boraylik! 🌱",
    "Fokusni saqla, vazifalarni bittalab bajar — natija o'zi keladi. 🎯",
    "Yaxshi boshlanish — yarim g'alaba. Xayrli va samarali kun! 🌤",
    "Bugun ham professional bo'lib, mijozlarimizga eng yaxshisini beramiz. 🏥",
    "Sabr va mehnat — har qanday to'siqni yengadi. Ishga! 💪",
    "Har kuni biroz yaxshiroq bo'lish — buning o'zi katta yutuq. Omad! 🙌",
]

# --- Ruxsat berilgan foydalanuvchilar ---
# ALLOWED_CHAT_IDS: vergul bilan ajratilgan chat_id ro'yxati (masalan "1890595434,7388057342")
# ADMIN_CHAT_ID avtomatik ruxsat etilganlar ro'yxatiga qo'shiladi.
_raw_allowed = os.environ.get("ALLOWED_CHAT_IDS", "")
AUTHORIZED_IDS = {int(x.strip()) for x in _raw_allowed.split(",") if x.strip()}
if ADMIN_CHAT_ID:
    AUTHORIZED_IDS.add(int(ADMIN_CHAT_ID))


def _is_authorized(chat_id: int) -> bool:
    return chat_id in AUTHORIZED_IDS


def _sender_display_name(chat_id: int, tg_user=None, fallback: str = "Xodim") -> str:
    """Xabar/izoh/vazifa-bajarildi/kayfiyat kabi holatlarda ADMIN'ga kimdan kelganini
    ko'rsatish uchun ism aniqlaydi. Avval Notion'dagi ro'yxatdan o'tgan xodim nomini
    ("Ism" propertysi) ishlatadi — bu Telegram profil ismidan ko'ra ishonchliroq (ba'zi
    xodimlarning Telegram ismi taxallus/bo'sh bo'lishi mumkin). Topilmasa Telegram
    profil ismiga, undan ham keyin fallback qiymatiga tushadi."""
    try:
        employee = nx.find_employee_by_chat_id(chat_id)
        if employee:
            ism = nx.get_title(employee, "Ism")
            if ism:
                return ism
    except Exception:
        logger.exception("Xodim nomini Notion'dan aniqlashda xatolik")
    if tg_user and getattr(tg_user, "first_name", None):
        return tg_user.first_name
    return fallback


def require_auth(func):
    """Faqat AUTHORIZED_IDS ro'yxatidagi foydalanuvchilarga buyruqni bajarishga ruxsat beradi."""

    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *a, **kw):
        chat_id = update.effective_chat.id
        if not _is_authorized(chat_id):
            user = update.effective_user
            logger.warning(f"Ruxsatsiz urinish: chat_id={chat_id}, user={user.username if user else '?'}")
            await update.effective_message.reply_text(
                "⛔ Sizga bu botdan foydalanishga ruxsat berilmagan. Administratorga chat ID'ingizni yuboring."
            )
            if ADMIN_CHAT_ID:
                try:
                    uname = f"@{user.username}" if user and user.username else (user.first_name if user else "Noma'lum")
                    await context.bot.send_message(
                        chat_id=ADMIN_CHAT_ID,
                        text=f"⚠️ Ruxsatsiz foydalanuvchi botga murojaat qildi: {uname} (chat_id: {chat_id})",
                    )
                except Exception:
                    logger.exception("Adminga ruxsatsiz urinish haqida xabar berib bo'lmadi")
            return
        return await func(update, context, *a, **kw)

    return wrapper


def io_bytes(b: bytes):
    import io
    bio = io.BytesIO(b)
    bio.name = "dashboard.png"
    return bio


# ----------------------------------------------------------------------------
# Asosiy menyu (inline tugmalar)
# ----------------------------------------------------------------------------

def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 Vazifa berish", callback_data="menu:vazifa"),
            InlineKeyboardButton("✅ Vazifalarim", callback_data="menu:vazifalarim"),
        ],
        [
            InlineKeyboardButton("👥 Jamoa vazifalari", callback_data="menu:jamoa"),
            InlineKeyboardButton("📊 Kunlik hisobot", callback_data="menu:hisobot"),
        ],
        [
            InlineKeyboardButton("🎯 Oylik dashboard", callback_data="menu:oylik"),
            InlineKeyboardButton("📊 Progress", callback_data="menu:target"),
        ],
        [
            InlineKeyboardButton("📝 Kontent tasdiqlash", callback_data="menu:kontent"),
            InlineKeyboardButton("🚀 Kanalga joylash", callback_data="menu:joylash"),
        ],
        [
            InlineKeyboardButton("🎬 Reels hisobot", callback_data="menu:reels"),
            InlineKeyboardButton("🎯 Target hisobot", callback_data="menu:target_hisobot"),
        ],
        [
            InlineKeyboardButton("💰 Moliya", callback_data="menu:moliya"),
            InlineKeyboardButton("➕ Kirim qo'shish", callback_data="menu:kirim"),
        ],
        [
            InlineKeyboardButton("📁 Loyihalar", callback_data="menu:loyihalar"),
            InlineKeyboardButton("🆕 Yangi loyiha qo'shish", callback_data="menu:yangiloyiha"),
        ],
    ])


NEW_LOYIHA_CHANNELS = ["Telegram - Urolog Shovkat", "Telegram - ARK Hospital", "Telegram - 18+ Natijalar"]


def _new_loyiha_channel_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"📢 {k}", callback_data=f"newloyiha_kanal:{i}")]
        for i, k in enumerate(NEW_LOYIHA_CHANNELS)
    ]
    rows.append([InlineKeyboardButton("🚫 Yo'q / keyinroq belgilayman", callback_data="newloyiha_kanal:none")])
    return InlineKeyboardMarkup(rows)


def _new_loyiha_turi_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📁 Media loyiha (reels/video/post kuzatiladi)", callback_data="newloyiha_turi:media")],
        [InlineKeyboardButton("🎯 Target loyiha (faqat to'lov, kuzatuv yo'q)", callback_data="newloyiha_turi:target")],
        [InlineKeyboardButton("🔀 Aralash (ham video/reels, ham target)", callback_data="newloyiha_turi:aralash")],
    ])


def _new_loyiha_tolov_keyboard(donaga_option: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if donaga_option:
        rows.append([InlineKeyboardButton("🎬 Video/Reels donasiga", callback_data="newloyiha_tolov:video")])
    rows.append([InlineKeyboardButton("📅 Oylik (belgilangan summa)", callback_data="newloyiha_tolov:oylik")])
    rows.append([InlineKeyboardButton("🚫 Hozircha belgilamayman", callback_data="newloyiha_tolov:yoq")])
    return InlineKeyboardMarkup(rows)


def _date_picker_keyboard() -> InlineKeyboardMarkup:
    """Bugun + keyingi 6 kun uchun tugmalar. Toq kunlar 🔵, juft kunlar ⚪ bilan ajratiladi."""
    rows = []
    today = _tashkent_today()
    for i in range(7):
        d = today + timedelta(days=i)
        marker = "🔵" if d.day % 2 == 1 else "⚪"
        prefix = "Bugun — " if i == 0 else ("Ertaga — " if i == 1 else "")
        weekday = UZ_WEEKDAYS[d.weekday()]
        text = f"{marker} {prefix}{d.day:02d}.{d.month:02d} ({weekday})"
        rows.append([InlineKeyboardButton(text, callback_data=f"vazifa_date:{d.isoformat()}")])
    return InlineKeyboardMarkup(rows)


# ----------------------------------------------------------------------------
# /start, /menu, /men
# ----------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id

    if not _is_authorized(chat_id):
        # Ruxsat berilmagan foydalanuvchiga faqat chat_id'ini ko'rsatamiz —
        # buni administratorga yuborib, ALLOWED_CHAT_IDS ro'yxatiga qo'shdirishi mumkin.
        await update.message.reply_text(
            "Salom. Bu bot faqat ruxsat berilgan foydalanuvchilar uchun.\n\n"
            f"Sizning chat ID'ingiz: {chat_id}\n"
            "Bu ID'ni administratorga yuboring — sizga ruxsat berilgach, botdan foydalana olasiz."
        )
        user = update.effective_user
        logger.warning(f"Ruxsatsiz /start: chat_id={chat_id}, user={user.username if user else '?'}")
        if ADMIN_CHAT_ID:
            try:
                uname = f"@{user.username}" if user and user.username else (user.first_name if user else "Noma'lum")
                await context.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=f"⚠️ Yangi foydalanuvchi /start bosdi: {uname} (chat_id: {chat_id}) — ALLOWED_CHAT_IDS'ga qo'shishni xohlasangiz shu ID'ni qo'shing.",
                )
            except Exception:
                logger.exception("Adminga xabar berib bo'lmadi")
        return

    await update.message.reply_text(
        "Salom! Men Jarvis — sizning Notion bilan ulangan yordamchingizman.\n\n"
        f"Sizning chat ID'ingiz: {chat_id}\n\n"
        "Quyidagi tugmalardan foydalaning (yoki / buyruqlarini yozing):",
        reply_markup=_main_menu_keyboard(),
    )


@require_auth
async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("📋 Asosiy menyu:", reply_markup=_main_menu_keyboard())


@require_auth
async def men(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ism = " ".join(context.args).strip()
    if not ism:
        await update.message.reply_text("Foydalanish: /men <Ismingiz> (Notion'dagi Xodimlar bazasidagi ismingiz bilan bir xil bo'lsin)")
        return

    employee = nx.find_employee_by_name(ism)
    if not employee:
        await update.message.reply_text(
            f"'{ism}' ismli xodim Notion'dagi Xodimlar bazasida topilmadi. "
            "Avval u yerga qo'shilganingizga ishonch hosil qiling."
        )
        return

    chat_id = update.effective_chat.id
    nx.register_employee_chat_id(employee["id"], chat_id)
    nomi = nx.get_title(employee, "Ism")
    await update.message.reply_text(f"✅ Ro'yxatdan o'tdingiz: {nomi}. Endi sizga TZ va bildirishnomalar shu chatga keladi.")


# ----------------------------------------------------------------------------
# /hisobot (qo'lda va avtomatik)
# ----------------------------------------------------------------------------

def _fetch_daily_data():
    today = _tashkent_today().isoformat()
    try:
        # "on_or_before" ishlatamiz — shunda bugungi va muddati o'tib ketgan (hali bajarilmagan)
        # vazifalar ham hisobotda ko'rinadi, faqat "aynan bugun"gilar emas.
        vazifalar = nx.query_data_source(
            nx.DS_VAZIFALAR, filter_obj={"property": "Muddat", "date": {"on_or_before": today}}
        )
    except Exception:
        logger.exception("Vazifalarni olishda xatolik")
        vazifalar = []

    try:
        postlar = nx.query_data_source(
            nx.DS_KONTENT_REJA, filter_obj={"property": "Sana", "date": {"equals": today}}
        )
    except Exception:
        logger.exception("Kontent-rejani olishda xatolik")
        postlar = []

    return vazifalar, postlar


def _build_daily_caption(vazifalar: list, postlar: list) -> str:
    today = _tashkent_today().strftime("%d.%m.%Y")
    return (
        f"📊 *Kunlik dashboard* — {today}\n"
        f"Vazifalar: {len(vazifalar)} ta | Kontent postlari: {len(postlar)} ta"
    )


async def _send_daily_dashboard(bot, chat_id) -> None:
    vazifalar, postlar = _fetch_daily_data()
    png_bytes = dashboard.render_daily_dashboard(
        vazifalar, postlar, nx.get_status, nx.get_select, nx.get_title
    )
    caption = _build_daily_caption(vazifalar, postlar)
    await bot.send_photo(chat_id=chat_id, photo=io_bytes(png_bytes), caption=caption, parse_mode=ParseMode.MARKDOWN)


def _compute_team_today_data() -> list:
    """Har bir xodim uchun bugungi (Muddat <= bugun) vazifalar soni va nechtasi bajarilgan."""
    try:
        employees = nx.query_data_source(nx.DS_XODIMLAR)
    except Exception:
        logger.exception("Xodimlarni olishda xatolik (jamoa dashboard)")
        return []

    today = _tashkent_today().isoformat()
    team_data = []
    for e in employees:
        emp_id = e["id"]
        nomi = nx.get_title(e, "Ism") or "Noma'lum"
        try:
            tasks = nx.query_data_source(
                nx.DS_VAZIFALAR,
                filter_obj={
                    "and": [
                        {"property": "Mas'ul", "relation": {"contains": emp_id}},
                        {"property": "Muddat", "date": {"on_or_before": today}},
                    ]
                },
            )
        except Exception:
            logger.exception(f"{nomi} uchun vazifalarni olishda xatolik")
            continue
        if not tasks:
            continue  # umuman vazifasi yo'q xodimni dashboard'da ko'rsatmaymiz
        total = len(tasks)
        done = sum(1 for t in tasks if nx.get_status(t, "Holati") == "Done")
        team_data.append({"name": nomi, "done": done, "total": total})
    return team_data


async def _send_team_donuts(bot, chat_id) -> None:
    team_data = _compute_team_today_data()
    if not team_data:
        return
    png_bytes = dashboard.render_team_donuts(team_data)
    await bot.send_photo(
        chat_id=chat_id,
        photo=io_bytes(png_bytes),
        caption="👥 *Jamoa — bugungi bajarilish*",
        parse_mode=ParseMode.MARKDOWN,
    )


async def _do_hisobot(bot, chat_id) -> None:
    await bot.send_message(chat_id=chat_id, text="Dashboard tayyorlanmoqda...")
    try:
        await _send_daily_dashboard(bot, chat_id)
    except Exception:
        logger.exception("Dashboard yuborishda xatolik")
        await bot.send_message(chat_id=chat_id, text="⚠️ Dashboard rasmini yaratib bo'lmadi.")

    try:
        await _send_team_donuts(bot, chat_id)
    except Exception:
        logger.exception("Jamoa dashboard yuborishda xatolik")


@require_auth
async def hisobot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _do_hisobot(context.bot, update.effective_chat.id)


def _current_month_str() -> str:
    return _tashkent_today().strftime("%Y-%m")


def _parse_flexible_date(text: str) -> date | None:
    """'bugun'/'hozir', 'DD.MM.YYYY' yoki 'YYYY-MM-DD' formatlarini qabul qiladi. Noto'g'ri bo'lsa None qaytaradi."""
    t = text.strip().lower()
    if t in ("bugun", "hozir", "hoziroq"):
        return _tashkent_today()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _compute_loyiha_dashboard_data() -> list:
    """Loyihalar bazasidan barcha FAOL (Pauzada/Arxivlangan bo'lmagan) loyihalar bo'yicha
    target/bajarildi ma'lumotlarini yig'adi. "Oy" bo'yicha filtrlanmaydi — loyiha bir marta
    qo'shilgach, har oy qayta yaratish shart emas, u doim "joriy" hisoblanadi (faqat pauzaga
    qo'yilsa yoki o'chirilsa chetlanadi). Telegram post soni esa JORIY OYGA filtrlanadi (Sana
    maydoni shu oy ichida bo'lgan "Joylandi" postlar sanaladi) — chunki hisobot "(YYYY-MM)"
    deb chiqadi, shuning uchun eski oylardagi postlar joriy oy hisobiga aralashmasligi kerak."""
    try:
        loyihalar = nx.query_data_source(
            nx.DS_LOYIHALAR,
            filter_obj={
                "and": [
                    {"property": "Holati", "select": {"does_not_equal": "Pauzada"}},
                    {"property": "Holati", "select": {"does_not_equal": "Arxivlangan"}},
                ]
            },
        )
    except Exception:
        logger.exception("Loyihalarni olishda xatolik")
        return []

    try:
        joylangan_postlar = nx.query_data_source(
            nx.DS_KONTENT_REJA, filter_obj={"property": "Status", "select": {"equals": "Joylandi"}}
        )
    except Exception:
        logger.exception("Kontent-rejani olishda xatolik (loyiha dashboard)")
        joylangan_postlar = []

    joriy_oy = _current_month_str()  # masalan "2026-08"

    result = []
    for l in loyihalar:
        nomi = nx.get_title(l, "Loyiha") or "?"
        kanal = nx.get_select(l, "Bog'liq kanal")
        reels_t = nx.get_number(l, "Reels target") or 0
        reels_d = nx.get_number(l, "Reels bajarildi") or 0
        video_t = nx.get_number(l, "Target video soni") or 0
        video_d = nx.get_number(l, "Target video bajarildi") or 0
        post_t = nx.get_number(l, "Telegram post target") or 0
        obuna_t = nx.get_number(l, "Obunachi target") or 0
        obuna_d = nx.get_number(l, "Obunachi hozirgi") or 0

        # Faqat JORIY OYDAGI "Joylandi" postlar sanaladi (Sana maydoni "YYYY-MM" bilan mos
        # kelsa) — eski oylardagi postlar bu oy hisobiga qo'shilmaydi.
        post_d = 0
        if kanal:
            for p in joylangan_postlar:
                if nx.get_select(p, "Kanal") != kanal:
                    continue
                sana = nx.get_date(p, "Sana") or ""
                if sana[:7] == joriy_oy:
                    post_d += 1

        metrics = [("Reels", reels_d, reels_t)]
        if video_t or video_d:
            metrics.append(("Target", video_d, video_t))
        metrics.append(("TG post", post_d, post_t))
        if obuna_t or obuna_d:
            metrics.append(("Obunachi", obuna_d, obuna_t))
        result.append({"name": nomi, "metrics": metrics})

    return result


async def _do_oylik(bot, chat_id) -> None:
    await bot.send_message(chat_id=chat_id, text="Oylik dashboard tayyorlanmoqda...")
    try:
        yonalishlar = nx.query_data_source(nx.DS_YONALISHLAR)
        png_bytes = dashboard.render_monthly_dashboard(
            yonalishlar, nx.get_title, nx.get_rich_text, nx.get_number
        )
        await bot.send_photo(
            chat_id=chat_id,
            photo=io_bytes(png_bytes),
            caption="🎯 *Oylik Target Dashboard*",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:
        logger.exception("Oylik dashboard yuborishda xatolik")
        await bot.send_message(chat_id=chat_id, text="⚠️ Oylik dashboard rasmini yaratib bo'lmadi.")

    try:
        loyiha_data = _compute_loyiha_dashboard_data()
        png_bytes2 = dashboard.render_loyiha_dashboard(loyiha_data)
        await bot.send_photo(
            chat_id=chat_id,
            photo=io_bytes(png_bytes2),
            caption="📁 *Loyihalar bo'yicha oylik kelishuv*",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:
        logger.exception("Loyihalar dashboard yuborishda xatolik")
        await bot.send_message(chat_id=chat_id, text="⚠️ Loyihalar dashboardini yaratib bo'lmadi.")


@require_auth
async def oylik(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _do_oylik(context.bot, update.effective_chat.id)


async def scheduled_daily_report(context: ContextTypes.DEFAULT_TYPE) -> None:
    if not ADMIN_CHAT_ID:
        return
    try:
        await _send_daily_dashboard(context.bot, ADMIN_CHAT_ID)
    except Exception:
        logger.exception("Avtomatik hisobot yuborishda xatolik")
    try:
        await _send_team_donuts(context.bot, ADMIN_CHAT_ID)
    except Exception:
        logger.exception("Avtomatik jamoa dashboard yuborishda xatolik")


async def scheduled_reels_prompt(context: ContextTypes.DEFAULT_TYPE) -> None:
    if not ADMIN_CHAT_ID:
        return
    try:
        await _do_reels_menu(context.bot, ADMIN_CHAT_ID)
    except Exception:
        logger.exception("Avtomatik reels so'rovini yuborishda xatolik")



_AUTO_PUBLISH_XATO_MARKER = "⚠️AUTO-XATOLIK"


async def scheduled_auto_publish(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Har AUTO_PUBLISH_INTERVAL_MINUTES daqiqada ishlaydi: "Tasdiqlandi" statusidagi
    postlar orasidan Sana+Vaqt'i kelib yetganlarini avtomatik ravishda haqiqiy kanalga
    joylaydi — admin qo'lda "/joylash" bosishi shart emas. Muvaffaqiyatli joylashda har
    safar adminga xabar boradi; xatolikda esa har bir post uchun FAQAT BIR MARTA xabar
    beriladi (muammo tuzatilib, joylash muvaffaqiyatli bo'lgunicha qayta-qayta yuborilmaydi).
    Bu holat postning Notion "Izoh" maydonida saqlanadi (bot QAYTA ISHGA TUSHIRILSA — masalan
    yangi deploy'dan keyin — HAM eski xatoliklar qayta-qayta xabar qilinmaydi)."""
    try:
        postlar = nx.query_data_source(
            nx.DS_KONTENT_REJA, filter_obj={"property": "Status", "select": {"equals": "Tasdiqlandi"}}
        )
    except Exception:
        logger.exception("Avtomatik joylash uchun postlarni olishda xatolik")
        return

    now = _tashkent_now()
    for p in postlar:
        sana_str = nx.get_date(p, "Sana")
        vaqt_str = (nx.get_rich_text(p, "Vaqt") or "").strip()
        if not sana_str:
            continue
        try:
            sana = date.fromisoformat(sana_str[:10])
            soat_str, daqiqa_str = (vaqt_str or "00:00").split(":")[:2]
            rejalashtirilgan = datetime.combine(sana, dtime(hour=int(soat_str), minute=int(daqiqa_str)))
        except (ValueError, IndexError):
            logger.warning(f"'{nx.get_title(p, 'Post nomi')}' uchun Sana/Vaqt formatini o'qib bo'lmadi, o'tkazib yuborildi.")
            continue

        if rejalashtirilgan > now:
            continue  # vaqti hali kelmagan

        mavjud_izoh = nx.get_rich_text(p, "Izoh") or ""
        allaqachon_xabar_berilgan = _AUTO_PUBLISH_XATO_MARKER in mavjud_izoh

        ok, xabar = await _publish_kontent_post(context.bot, p["id"])

        should_notify = True
        if ok:
            if allaqachon_xabar_berilgan:
                try:
                    tozalangan = mavjud_izoh.replace(_AUTO_PUBLISH_XATO_MARKER, "").strip()
                    nx.update_page_property(p["id"], {"Izoh": {"rich_text": [{"text": {"content": tozalangan}}]}})
                except Exception:
                    logger.exception("Muvaffaqiyatdan keyin Izohni tozalashda xatolik")
        elif allaqachon_xabar_berilgan:
            should_notify = False  # bu post uchun xatolik haqida allaqachon (Notion'da) xabar berilgan
        else:
            try:
                yangi_izoh = f"{mavjud_izoh}\n\n{_AUTO_PUBLISH_XATO_MARKER}".strip() if mavjud_izoh else _AUTO_PUBLISH_XATO_MARKER
                nx.update_page_property(p["id"], {"Izoh": {"rich_text": [{"text": {"content": yangi_izoh}}]}})
            except Exception:
                logger.exception("Izohga xatolik belgisini yozishda xatolik")

        if should_notify and ADMIN_CHAT_ID:
            try:
                await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"⏱ Avtomatik joylash: {xabar}")
            except Exception:
                logger.exception("Adminga avtomatik joylash xabarini yuborib bo'lmadi")


DAILY_PUBLISH_CHECK_HOUR = int(os.environ.get("DAILY_PUBLISH_CHECK_HOUR", "21"))
DAILY_PUBLISH_CHECK_MINUTE = int(os.environ.get("DAILY_PUBLISH_CHECK_MINUTE", "30"))


async def scheduled_publish_watchdog(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Har kuni bir marta (kech, DAILY_PUBLISH_CHECK_HOUR'da) ishlaydi: har bir sozlangan
    Telegram kanal uchun bugun kamida bitta post real ravishda "Joylandi" bo'lganini
    tekshiradi. Agar bugun uchun reja bo'lmasa yoki reja bor-u lekin hech narsa
    joylanmagan bo'lsa, adminga ogohlantirish yuboradi — shunda kunlik postlash
    "ko'zdan chetda" qolib ketmaydi."""
    if not ADMIN_CHAT_ID:
        return

    active_channels = [k for k, v in nx.CHANNEL_MAP.items() if v]
    if not active_channels:
        return

    today = _tashkent_today()
    today_iso = today.isoformat()
    try:
        postlar = nx.query_data_source(
            nx.DS_KONTENT_REJA,
            filter_obj={"property": "Sana", "date": {"equals": today_iso}},
            page_size=100,
        )
    except Exception:
        logger.exception("Kunlik joylash nazorati uchun postlarni olishda xatolik")
        return

    muammoli_qatorlar = []
    for kanal in active_channels:
        kanal_postlari = [p for p in postlar if (nx.get_select(p, "Kanal") or "") == kanal]
        if not kanal_postlari:
            muammoli_qatorlar.append(f"⚠️ *{kanal}*: bugunga kontent-rejada birorta post ham yo'q.")
            continue
        joylandimi = any((nx.get_select(p, "Status") or "") == "Joylandi" for p in kanal_postlari)
        if not joylandimi:
            holatlar = ", ".join(sorted({nx.get_select(p, "Status") or "?" for p in kanal_postlari}))
            muammoli_qatorlar.append(
                f"⚠️ *{kanal}*: {len(kanal_postlari)} ta post rejalashtirilgan, "
                f"lekin hali birortasi ham kanalga joylanmagan (holati: {holatlar})."
            )

    if not muammoli_qatorlar:
        return  # hammasi joyida — spam qilmaymiz

    matn = (
        f"🔎 *Kunlik post nazorati — {today.strftime('%d.%m.%Y')}*\n\n"
        + "\n".join(muammoli_qatorlar)
        + "\n\n/kontent orqali tekshiring yoki /joylash bilan qo'lda joylang."
    )
    try:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=matn, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        logger.exception("Kunlik joylash nazorati xabarini yuborishda xatolik")


# ----------------------------------------------------------------------------
# Har 2 soatda vazifa eslatmasi, kunlik motivatsiya, kechki kayfiyat so'rovi
# ----------------------------------------------------------------------------

async def scheduled_task_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kimda ochiq (Muddat <= bugun, Holati != Done) vazifa bo'lsa, o'sha odamga eslatma yuboradi."""
    if _is_quiet_hours():
        return
    try:
        employees = nx.query_data_source(nx.DS_XODIMLAR)
    except Exception:
        logger.exception("Eslatma uchun xodimlarni olishda xatolik")
        return

    today = _tashkent_today().isoformat()
    for e in employees:
        chat_id_str = nx.get_rich_text(e, "Telegram")
        if not chat_id_str:
            continue  # botga hali ro'yxatdan o'tmagan xodim

        nomi = nx.get_title(e, "Ism") or "Xodim"
        try:
            tasks = nx.query_data_source(
                nx.DS_VAZIFALAR,
                filter_obj={
                    "and": [
                        {"property": "Mas'ul", "relation": {"contains": e["id"]}},
                        {"property": "Holati", "status": {"does_not_equal": "Done"}},
                        {"property": "Muddat", "date": {"on_or_before": today}},
                    ]
                },
            )
        except Exception:
            logger.exception(f"{nomi} uchun eslatma vazifalarini olishda xatolik")
            continue

        if not tasks:
            continue

        lines = [f"⏰ Eslatma: sizda {len(tasks)} ta ochiq vazifa bor:\n"]
        for t in tasks[:10]:
            nomi_t = nx.get_title(t, "Vazifa") or "?"
            lines.append(f"📋 {nomi_t}")
        if len(tasks) > 10:
            lines.append(f"... va yana {len(tasks) - 10} ta")

        try:
            await context.bot.send_message(chat_id=int(chat_id_str), text="\n".join(lines))
        except TelegramError:
            logger.exception(f"{nomi}ga eslatma yuborilmadi")


async def scheduled_morning_task_notify(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Har kuni QUIET_HOURS_END'da (standart 07:00) ishlaydi: tungi tinchlik vaqtida
    (QUIET_HOURS_START–QUIET_HOURS_END) tayinlangani uchun xabari kechiktirilgan ("Xabar
    berildi" belgisiz) vazifalarni topib, endi xodimga yuboradi va belgilaydi."""
    try:
        tasks = nx.query_data_source(
            nx.DS_VAZIFALAR,
            filter_obj={
                "and": [
                    {"property": "Xabar berildi", "checkbox": {"equals": False}},
                    {"property": "Holati", "status": {"does_not_equal": "Done"}},
                ]
            },
        )
    except Exception:
        logger.exception("Ertalabki vazifa navbatini olishda xatolik")
        return

    for t in tasks:
        emp_ids = nx.get_relation_ids(t, "Mas'ul")
        if not emp_ids:
            continue
        vazifa_nomi = nx.get_title(t, "Vazifa") or "?"
        muddat = nx.get_date(t, "Muddat")
        muddat_str = date.fromisoformat(muddat[:10]).strftime("%d.%m.%Y") if muddat else "belgilanmagan"

        for emp_id in emp_ids:
            try:
                employee = nx.get_page(emp_id)
            except Exception:
                logger.exception("Ertalabki navbat uchun xodimni olishda xatolik")
                continue
            chat_id_str = nx.get_rich_text(employee, "Telegram")
            if not chat_id_str:
                continue
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Bajardim", callback_data=f"done:{t['id']}"),
                InlineKeyboardButton("💬 Izoh", callback_data=f"comment:{t['id']}"),
            ]])
            try:
                await context.bot.send_message(
                    chat_id=int(chat_id_str),
                    text=f"📋 Sizga yangi vazifa berildi (muddat: {muddat_str}):\n\n{vazifa_nomi}",
                    reply_markup=keyboard,
                )
            except TelegramError:
                logger.exception("Ertalabki vazifa xabarini yuborishda xatolik")
                continue

        try:
            nx.update_page_property(t["id"], {"Xabar berildi": {"checkbox": True}})
        except Exception:
            logger.exception("'Xabar berildi' belgisini yangilashda xatolik")


async def scheduled_motivation(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Har tongda hammaga tasodifiy motivatsion gap yuboradi."""
    if _is_quiet_hours():
        return
    text = random.choice(MOTIVATION_QUOTES)
    for chat_id in AUTHORIZED_IDS:
        try:
            await context.bot.send_message(chat_id=chat_id, text=f"🌅 {text}")
        except TelegramError:
            logger.exception(f"Motivatsion xabar yuborilmadi: {chat_id}")


def _mood_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("😞 Yomon", callback_data="mood:yomon"),
        InlineKeyboardButton("😐 O'rta", callback_data="mood:orta"),
        InlineKeyboardButton("🔥 Zo'r", callback_data="mood:zor"),
    ]])


async def scheduled_mood_checkin(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Har kuni kechqurun hammadan kunining qanday o'tganini so'raydi (3 ta tugma: yomon/o'rta/zo'r)."""
    if _is_quiet_hours():
        return
    for chat_id in AUTHORIZED_IDS:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="🌙 Bugungi kuningiz qanday o'tdi?",
                reply_markup=_mood_keyboard(),
            )
        except TelegramError:
            logger.exception(f"Kayfiyat so'rovi yuborilmadi: {chat_id}")


# ----------------------------------------------------------------------------
# /vazifa (tugma orqali yoki eski "Ism | matn" usulida), /vazifalarim, vazifani bajarish
# ----------------------------------------------------------------------------

def _employee_picker_keyboard():
    try:
        employees = nx.query_data_source(nx.DS_XODIMLAR)
    except Exception:
        logger.exception("Xodimlarni olishda xatolik")
        return None

    if not employees:
        return None

    rows = []
    for e in employees:
        nomi = nx.get_title(e, "Ism") or "Noma'lum"
        rows.append([InlineKeyboardButton(f"👤 {nomi}", callback_data=f"vazifa_emp:{e['id']}")])
    return InlineKeyboardMarkup(rows)


async def _do_vazifa_menu(bot, chat_id) -> None:
    keyboard = _employee_picker_keyboard()
    if not keyboard:
        await bot.send_message(chat_id=chat_id, text="⚠️ Xodimlar bazasida (Notion) hech kim topilmadi.")
        return
    await bot.send_message(chat_id=chat_id, text="Vazifani kimga berasiz? 👇", reply_markup=keyboard)


_VAZIFA_ITEM_SPLIT_RE = re.compile(r"(?:(?<=^)|(?<=\n)|(?<=\s))\d{1,2}[.)]\s+")


def _split_vazifa_lines(text: str) -> list[str]:
    """Agar xodimga berilgan vazifa matni ro'yxat shaklida yozilgan bo'lsa (masalan
    '1. birinchi ish\n2. ikkinchi ish' yoki bitta qatorda '1. ... 2. ... 3. ...'),
    har bir bandni alohida vazifa matni sifatida qaytaradi. Aks holda butun matnni
    o'zgarishsiz, bitta elementli ro'yxatda qaytaradi."""
    text = text.strip()
    if not text:
        return []
    parts = [p.strip() for p in _VAZIFA_ITEM_SPLIT_RE.split(text)]
    parts = [p for p in parts if p]
    return parts if len(parts) > 1 else [text]


async def _create_vazifa(
    bot, requester_chat_id, employee: dict | None, ism: str, vazifa_matni: str, muddat: str | None = None
) -> None:
    muddat = muddat or _tashkent_today().isoformat()
    properties = {
        "Vazifa": {"title": [{"text": {"content": vazifa_matni}}]},
        "Holati": {"status": {"name": "Not started"}},
        "Muddat": {"date": {"start": muddat}},
    }
    if employee:
        properties["Mas'ul"] = {"relation": [{"id": employee["id"]}]}

    try:
        new_page = nx.create_page(nx.DS_VAZIFALAR, properties)
    except Exception:
        logger.exception("Vazifa yaratishda xatolik")
        await bot.send_message(chat_id=requester_chat_id, text="⚠️ Vazifani yaratib bo'lmadi.")
        return

    if not employee:
        await bot.send_message(
            chat_id=requester_chat_id,
            text=f"✅ Vazifa yaratildi (mas'ulsiz — '{ism}' xodim topilmadi): {vazifa_matni}",
        )
        return

    chat_id = nx.get_rich_text(employee, "Telegram")
    muddat_str = date.fromisoformat(muddat).strftime("%d.%m.%Y")
    await bot.send_message(
        chat_id=requester_chat_id,
        text=f"✅ Vazifa yaratildi va {ism}ga tayinlandi (muddat: {muddat_str}): {vazifa_matni}",
    )

    if chat_id:
        if _is_quiet_hours():
            # Tungi tinchlik vaqti (QUIET_HOURS_START–QUIET_HOURS_END) — xodimga hozir
            # yubormaymiz, "Xabar berildi" belgisiz qoldiramiz, ertalab QUIET_HOURS_END'da
            # scheduled_morning_task_notify orqali avtomatik yuboriladi.
            await bot.send_message(
                chat_id=requester_chat_id,
                text=(
                    f"🌙 Hozir tungi tinchlik vaqti ({QUIET_HOURS_START:02d}:00–{QUIET_HOURS_END:02d}:00) — "
                    f"{ism}ga xabar ertalab soat {QUIET_HOURS_END:02d}:00da avtomatik boradi."
                ),
            )
            return

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Bajardim", callback_data=f"done:{new_page['id']}"),
            InlineKeyboardButton("💬 Izoh", callback_data=f"comment:{new_page['id']}"),
        ]])
        try:
            await bot.send_message(
                chat_id=int(chat_id),
                text=f"📋 Sizga yangi vazifa berildi (muddat: {muddat_str}):\n\n{vazifa_matni}",
                reply_markup=keyboard,
            )
            nx.update_page_property(new_page["id"], {"Xabar berildi": {"checkbox": True}})
        except TelegramError:
            logger.exception("Xodimga xabar yuborishda xatolik")
            await bot.send_message(
                chat_id=requester_chat_id,
                text=f"⚠️ {ism}ga xabar yuborilmadi — u hali botga /start bosmagan yoki /men buyrug'i bilan ro'yxatdan o'tmagan bo'lishi mumkin.",
            )
    else:
        await bot.send_message(
            chat_id=requester_chat_id,
            text=f"ℹ️ {ism} hali botda ro'yxatdan o'tmagan (/men buyrug'i bilan), shuning uchun unga xabar yuborilmadi.",
        )


@require_auth
async def vazifa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    matn = " ".join(context.args)

    if not matn.strip():
        # Argumentsiz /vazifa — tugma orqali xodimni tanlash oqimi
        await _do_vazifa_menu(context.bot, update.effective_chat.id)
        return

    if "|" not in matn:
        await update.message.reply_text(
            "Argumentsiz /vazifa deb yozsangiz, tugmalar orqali xodimni tanlaysiz.\n\n"
            "Yoki eski usulda: /vazifa <Ism> | <vazifa matni>\n"
            "Masalan: /vazifa Hasan | 3 ta reels suratga oling"
        )
        return

    ism_qismi, vazifa_matni = matn.split("|", 1)
    ism = ism_qismi.strip()
    vazifa_matni = vazifa_matni.strip()

    if not ism or not vazifa_matni:
        await update.message.reply_text("Ism yoki vazifa matni bo'sh bo'lmasin.")
        return

    employee = nx.find_employee_by_name(ism)
    await _create_vazifa(context.bot, update.effective_chat.id, employee, ism, vazifa_matni)


def _format_comments(comments: list) -> str:
    """Notion izohlar ro'yxatini vazifa xabariga qo'shiladigan matn qismiga aylantiradi."""
    lines = []
    for c in comments:
        parts = c.get("rich_text", [])
        text = "".join(p.get("plain_text", "") for p in parts).strip()
        if text:
            lines.append(f"• {text}")
    if not lines:
        return ""
    return "\n\n💬 Izohlar:\n" + "\n".join(lines)


async def _do_vazifalarim(bot, chat_id) -> None:
    employee = nx.find_employee_by_chat_id(chat_id)
    if not employee:
        await bot.send_message(
            chat_id=chat_id,
            text="Siz hali ro'yxatdan o'tmagansiz. Avval /men <Ismingiz> buyrug'ini yuboring.",
        )
        return

    try:
        vazifalar = nx.query_data_source(
            nx.DS_VAZIFALAR,
            filter_obj={
                "and": [
                    {"property": "Mas'ul", "relation": {"contains": employee["id"]}},
                    {"property": "Holati", "status": {"does_not_equal": "Done"}},
                ]
            },
        )
    except Exception:
        logger.exception("Vazifalarni olishda xatolik")
        await bot.send_message(chat_id=chat_id, text="Xatolik yuz berdi.")
        return

    if not vazifalar:
        await bot.send_message(chat_id=chat_id, text="Sizga tayinlangan ochiq vazifa yo'q. ✅")
        return

    for v in vazifalar[:15]:
        nomi = nx.get_title(v, "Vazifa")
        muddat = nx.get_date(v, "Muddat") or "muddatsiz"
        try:
            izoh_matni = _format_comments(nx.get_comments(v["id"]))
        except Exception:
            logger.exception("Vazifa izohlarini olishda xatolik")
            izoh_matni = ""
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Bajardim", callback_data=f"done:{v['id']}"),
            InlineKeyboardButton("💬 Izoh", callback_data=f"comment:{v['id']}"),
        ]])
        await bot.send_message(
            chat_id=chat_id, text=f"📋 {nomi}\n🗓 Muddat: {muddat}{izoh_matni}", reply_markup=keyboard
        )


@require_auth
async def vazifalarim(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _do_vazifalarim(context.bot, update.effective_chat.id)


@require_auth
async def qildim(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Donasiga ('Vazifa boshiga') to'lanadigan xodim uchun — alohida vazifa tayinlanishini
    kutmasdan, o'zi bajargan ish sonini to'g'ridan-to'g'ri yozib qo'yishi uchun (masalan
    Mubinaning montajlari)."""
    chat_id = update.effective_chat.id
    employee = nx.find_employee_by_chat_id(chat_id)
    if not employee:
        await update.message.reply_text("Siz hali xodim sifatida ro'yxatdan o'tmagansiz. Avval /men buyrug'ini yuboring.")
        return
    turi = nx.get_select(employee, "Maosh turi")
    if turi != "Vazifa boshiga":
        await update.message.reply_text(
            "Bu buyruq faqat donasiga (har bir ish uchun alohida) to'lanadigan xodimlar uchun. "
            "Savolingiz bo'lsa admin bilan bog'laning."
        )
        return
    context.user_data["pending_self_ish_employee_id"] = employee["id"]
    await update.message.reply_text("✏️ Nechta ish bajardingiz? Raqam bilan yozing (masalan: 1):")


async def _do_jamoa_vazifalar(bot, chat_id) -> None:
    """Admin uchun: har bir xodimda hozir qanday ochiq vazifalar borligini (izohlari bilan) ko'rsatadi."""
    if not (ADMIN_CHAT_ID and str(chat_id) == str(ADMIN_CHAT_ID)):
        await bot.send_message(chat_id=chat_id, text="Bu buyruq faqat admin uchun.")
        return

    try:
        employees = nx.query_data_source(nx.DS_XODIMLAR)
    except Exception:
        logger.exception("Jamoa vazifalari uchun xodimlarni olishda xatolik")
        await bot.send_message(chat_id=chat_id, text="Xatolik yuz berdi.")
        return

    any_task = False
    for e in employees:
        nomi = nx.get_title(e, "Ism") or "Noma'lum"
        try:
            vazifalar = nx.query_data_source(
                nx.DS_VAZIFALAR,
                filter_obj={
                    "and": [
                        {"property": "Mas'ul", "relation": {"contains": e["id"]}},
                        {"property": "Holati", "status": {"does_not_equal": "Done"}},
                    ]
                },
            )
        except Exception:
            logger.exception(f"{nomi} vazifalarini olishda xatolik")
            continue
        if not vazifalar:
            continue

        any_task = True
        lines = [f"👤 <b>{html.escape(nomi)}</b> — {len(vazifalar)} ta ochiq vazifa:"]
        for v in vazifalar[:20]:
            v_nomi = nx.get_title(v, "Vazifa") or "?"
            muddat = nx.get_date(v, "Muddat") or "muddatsiz"
            try:
                izoh_matni = _format_comments(nx.get_comments(v["id"]))
            except Exception:
                logger.exception("Vazifa izohlarini olishda xatolik")
                izoh_matni = ""
            lines.append(f"• {html.escape(v_nomi)} (muddat: {muddat}){html.escape(izoh_matni)}")
        if len(vazifalar) > 20:
            lines.append(f"... va yana {len(vazifalar) - 20} ta")
        await bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode=ParseMode.HTML)

    if not any_task:
        await bot.send_message(chat_id=chat_id, text="Hech kimda ochiq vazifa yo'q. ✅")


@require_auth
async def jamoa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _do_jamoa_vazifalar(context.bot, update.effective_chat.id)


def _auto_income_for_units(page: dict, nomi: str, qoshimcha: int, birlik: str, narx: float | None = None) -> str:
    """Loyiha "Video/Reels boshiga" to'lov qilsa, qo'shilgan reels/video sonlari uchun
    mijoz qancha TO'LASHI KERAKLIGINI hisoblab, loyihaning "Debit"iga qo'shadi (Debit =
    mandan qarzdorlar, ya'ni mijoz bizga qarzdor bo'lgan summa). E'TIBOR: bu haqiqiy
    Moliya Kirim EMAS — pul hali kelmagan. Pul haqiqatda kelganda "➕ Kirim qo'shish"
    orqali qayd etilganda, o'sha summa shu Debit'dan avtomatik ayiriladi. Qo'shimcha
    xabar matnini qaytaradi.

    `narx` berilmasa (None), standart holatda "To'lov turi"=="Video/Reels boshiga" bo'lganda
    "To'lov summasi" narx sifatida ishlatiladi (reels/video uchun asl xulq-atvor). `narx`
    aniq berilsa (masalan Aralash loyihalarda target uchun alohida "Target narxi"), o'sha
    qiymat ishlatiladi — reels narxi bilan ARALASHIB ketmasligi uchun."""
    if narx is None:
        tolov_turi = nx.get_select(page, "To'lov turi")
        tolov_summasi = nx.get_number(page, "To'lov summasi") or 0
        if tolov_turi != "Video/Reels boshiga" or not tolov_summasi:
            return ""
        narx = tolov_summasi
    if not narx:
        return ""

    debit_qoshimcha = qoshimcha * narx
    try:
        joriy_debit = nx.get_number(page, "Debit") or 0
        yangi_debit = joriy_debit + debit_qoshimcha
        nx.update_page_property(page["id"], {"Debit": {"number": yangi_debit}})
        return (
            f"\n💳 Debitga qo'shildi: {_format_som(debit_qoshimcha)} "
            f"(jami Debit: {_format_som(yangi_debit)}). Pul kelganda \"➕ Kirim qo'shish\" orqali qayd eting."
        )
    except Exception:
        logger.exception("Loyiha Debit'ini yangilashda xatolik")
        return f"\n⚠️ {birlik.capitalize()} qo'shildi, lekin Debit summasini yozib bo'lmadi."


# ----------------------------------------------------------------------------
# Vazifa matnini "oddiy xabar" sifatida kutish (tugma orqali xodim tanlangandan keyin)
# ----------------------------------------------------------------------------

async def on_plain_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not _is_authorized(chat_id):
        return  # ruxsatsizlarga sukut saqlaymiz

    text_val = (update.message.text or "").strip()

    # 0) Faoliyat uchun qo'lda sana oralig'i kutilyaptimi?
    if context.user_data.get("pending_faoliyat_range"):
        context.user_data.pop("pending_faoliyat_range", None)
        parts = text_val.replace("-", " ").split()
        if len(parts) != 2:
            await update.message.reply_text(
                "⚠️ Format noto'g'ri. Masalan: 01.08.2026 15.08.2026"
            )
            return
        try:
            def _parse_kun(s: str) -> date:
                bits = s.split(".")
                if len(bits) == 2:
                    bits.append(str(_tashkent_today().year))
                d, m, y = (int(x) for x in bits)
                return date(y, m, d)
            start = _parse_kun(parts[0])
            end = _parse_kun(parts[1])
        except (ValueError, IndexError):
            await update.message.reply_text(
                "⚠️ Sanani o'qib bo'lmadi. Masalan: 01.08.2026 15.08.2026"
            )
            return
        if start > end:
            start, end = end, start
        await update.message.reply_text(f"⏳ {start.strftime('%d.%m.%Y')} – {end.strftime('%d.%m.%Y')} uchun yig'ilmoqda...")
        await _do_faoliyat_report(context.bot, chat_id, start, end)
        return

    # 1) Vazifaga izoh kutilyaptimi?
    pending_comment = context.user_data.get("pending_comment_page_id")
    if pending_comment:
        context.user_data.pop("pending_comment_page_id", None)
        if not text_val:
            await update.message.reply_text("Izoh matni bo'sh bo'lmasin.")
            return

        user = update.effective_user
        uname = _sender_display_name(chat_id, user)

        try:
            nx.create_comment(pending_comment, f"Izoh ({uname}): {text_val}")
        except Exception:
            logger.exception("Izoh qo'shishda xatolik")
            await update.message.reply_text("⚠️ Izoh qo'shib bo'lmadi.")
            return

        await update.message.reply_text("✅ Izohingiz vazifaga qo'shildi.")

        if ADMIN_CHAT_ID and str(chat_id) != str(ADMIN_CHAT_ID):
            try:
                task_page = nx.get_page(pending_comment)
                vazifa_nomi = nx.get_title(task_page, "Vazifa") or "vazifa"
            except Exception:
                logger.exception("Izoh uchun vazifa nomini olishda xatolik")
                vazifa_nomi = "vazifa"
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=f"💬 {uname} — \"{vazifa_nomi}\" vazifasiga izoh qoldirdi:\n{text_val}",
                )
            except Exception:
                logger.exception("Adminga izoh haqida xabar berib bo'lmadi")
        return

    # 1b) Kontent-Reja postini tahrirlash kutilyaptimi?
    pending_kontent_edit = context.user_data.get("pending_kontent_edit_page_id")
    if pending_kontent_edit:
        context.user_data.pop("pending_kontent_edit_page_id", None)
        if not text_val:
            await update.message.reply_text("Post matni bo'sh bo'lmasin.")
            return
        try:
            nx.update_page_property(pending_kontent_edit, {"Ssenariy/Matn": {"rich_text": [{"text": {"content": text_val}}]}})
            page = nx.get_page(pending_kontent_edit)
        except Exception:
            logger.exception("Postni tahrirlashda xatolik")
            await update.message.reply_text("⚠️ Postni yangilab bo'lmadi.")
            return

        await update.message.reply_text("✅ Post yangilandi. Yangi holatini ko'rib chiqing:")
        await _send_kontent_post_message(context.bot, chat_id, page)
        return

    # 2) Bugungi reels soni kutilyaptimi?
    pending_reels = context.user_data.get("pending_reels_project_id")
    if pending_reels:
        try:
            qoshimcha = int(text_val)
        except ValueError:
            await update.message.reply_text("Iltimos, faqat butun son yuboring (masalan: 3).")
            return
        context.user_data.pop("pending_reels_project_id", None)
        try:
            page = nx.get_page(pending_reels)
            joriy = nx.get_number(page, "Reels bajarildi") or 0
            yangi = joriy + qoshimcha
            nx.update_page_property(pending_reels, {"Reels bajarildi": {"number": yangi}})
            nomi = nx.get_title(page, "Loyiha") or "loyiha"
            qoshimcha_xabar = _auto_income_for_units(page, nomi, qoshimcha, "reels")
            await update.message.reply_text(
                f"✅ {nomi}: +{qoshimcha} reels qo'shildi (jami: {int(yangi)}).{qoshimcha_xabar}"
            )
        except Exception:
            logger.exception("Reels sonini yangilashda xatolik")
            await update.message.reply_text("⚠️ Yangilab bo'lmadi.")
        return

    # 2a2) Target hisobot: bugungi video soni kutilyaptimi?
    pending_target_video = context.user_data.get("pending_target_video_project_id")
    if pending_target_video:
        try:
            qoshimcha = int(text_val)
        except ValueError:
            await update.message.reply_text("Iltimos, faqat butun son yuboring (masalan: 2).")
            return
        context.user_data.pop("pending_target_video_project_id", None)
        try:
            page = nx.get_page(pending_target_video)
            joriy = nx.get_number(page, "Target video bajarildi") or 0
            yangi = joriy + qoshimcha
            nx.update_page_property(pending_target_video, {"Target video bajarildi": {"number": yangi}})
            nomi = nx.get_title(page, "Loyiha") or "loyiha"
            proj_turi = nx.get_select(page, "Loyiha turi") or "Media"
            birlik_soz = "target" if proj_turi in ("Target", "Aralash") else "video"
            if proj_turi == "Aralash":
                # Aralash loyihalarda target narxi REELS narxidan MUSTAQIL — ikkalasi
                # aralashib ketmasligi uchun alohida "Target narxi" maydonidan olinadi.
                target_narx = nx.get_number(page, "Target narxi") or 0
                qoshimcha_xabar = _auto_income_for_units(page, nomi, qoshimcha, birlik_soz, narx=target_narx or None)
                if birlik_soz == "target" and not target_narx:
                    qoshimcha_xabar += (
                        "\n💡 Bu loyiha uchun \"Target narxi\" hali belgilanmagan — avtomatik "
                        "Debit hisoblanmadi. Kerak bo'lsa Notion'da \"Target narxi\"ni to'ldiring."
                    )
            else:
                qoshimcha_xabar = _auto_income_for_units(page, nomi, qoshimcha, birlik_soz)
            await update.message.reply_text(
                f"✅ {nomi}: +{qoshimcha} {birlik_soz} qo'shildi (jami: {int(yangi)}).{qoshimcha_xabar}"
            )
        except Exception:
            logger.exception("Target video sonini yangilashda xatolik")
            await update.message.reply_text("⚠️ Yangilab bo'lmadi.")
        return

    # 2a3) Target hisobot: hozirgi jami obunachi soni kutilyaptimi?
    pending_target_obuna = context.user_data.get("pending_target_obuna_project_id")
    if pending_target_obuna:
        try:
            jami = int(text_val.replace(" ", ""))
        except ValueError:
            await update.message.reply_text("Iltimos, faqat butun son yuboring (masalan: 350).")
            return
        context.user_data.pop("pending_target_obuna_project_id", None)
        try:
            page = nx.get_page(pending_target_obuna)
            eski = nx.get_number(page, "Obunachi hozirgi") or 0
            nx.update_page_property(pending_target_obuna, {"Obunachi hozirgi": {"number": jami}})
            nomi = nx.get_title(page, "Loyiha") or "loyiha"
            target_son = nx.get_number(page, "Obunachi target") or 0
            farq = jami - eski
            farq_str = f"+{farq}" if farq >= 0 else str(farq)
            progress = f" ({jami}/{int(target_son)})" if target_son else ""
            await update.message.reply_text(
                f"✅ {nomi}: obunachi soni {jami} ga yangilandi{progress} ({farq_str} o'zgarish)."
            )
        except Exception:
            logger.exception("Obunachi sonini yangilashda xatolik")
            await update.message.reply_text("⚠️ Yangilab bo'lmadi.")
        return

    # 2b) Loyihadan tushgan pul (kirim) summasi kutilyaptimi?
    pending_income = context.user_data.get("pending_income_project_id")
    if pending_income:
        try:
            summa = float(text_val.replace(" ", "").replace(",", ""))
        except ValueError:
            await update.message.reply_text("Iltimos, faqat summa (raqam) yuboring, masalan: 2000000")
            return
        context.user_data.pop("pending_income_project_id", None)
        proj_nomi = context.user_data.pop("pending_income_project_name", "Boshqa")
        try:
            nx.create_page(nx.DS_MOLIYA, {
                "Nomi": {"title": [{"text": {"content": f"{proj_nomi} — tushgan pul"}}]},
                "Turi": {"select": {"name": "Kirim"}},
                "Kategoriya": {"select": {"name": "Xizmat to'lovi"}},
                "Summa": {"number": summa},
                "Sana": {"date": {"start": _tashkent_today().isoformat()}},
                "Izoh": {"rich_text": [{"text": {"content": f"Loyiha: {proj_nomi}"}}]},
            })

            if pending_income != "none":
                # Bu pul aynan shu loyihaning joriy (Notion'da hisoblanayotgan) Debit'i uchunmi,
                # yoki boshqa/eski (tizimda kuzatilmagan) qarz uchunmi — buni har doim SO'RAB
                # tasdiqlatamiz. Aks holda avtomatik ayirish noto'g'ri summani kamaytirib
                # qo'yishi mumkin (masalan eski, tizimdan tashqari qarz to'lovini joriy oy
                # hisobidan ayirib qo'yish kabi xatoliklar bo'lgan).
                try:
                    proj_page = nx.get_page(pending_income)
                    joriy_debit = nx.get_number(proj_page, "Debit") or 0
                except Exception:
                    logger.exception("Kirim kelganda loyiha Debit'ini olishda xatolik")
                    joriy_debit = None
                if joriy_debit and joriy_debit > 0:
                    context.user_data["pending_debit_confirm"] = {
                        "project_id": pending_income, "summa": summa, "proj_nomi": proj_nomi,
                    }
                    await update.message.reply_text(
                        f"✅ {proj_nomi}dan {_format_som(summa)} kirim qayd etildi.\n\n"
                        f"💳 Bu pul shu loyihaning joriy Debit'idan (hozir: {_format_som(joriy_debit)}) "
                        f"ayirilsinmi, yoki bu boshqa/eski (tizimda hisoblanmagan) qarz uchunmi?",
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("✅ Ha, Debitdan ayir", callback_data="debit_confirm:yes"),
                            InlineKeyboardButton("❌ Yo'q, boshqa/eski qarz", callback_data="debit_confirm:no"),
                        ]]),
                    )
                    return

            await update.message.reply_text(f"✅ {proj_nomi}dan {_format_som(summa)} kirim qayd etildi.")
        except Exception:
            logger.exception("Kirimni yozishda xatolik")
            await update.message.reply_text("⚠️ Kirimni qayd etib bo'lmadi.")
        return

    # 3) Xodimga to'lov summasi kutilyaptimi?
    pending_payment = context.user_data.get("pending_payment_employee_id")
    if pending_payment:
        try:
            summa = float(text_val.replace(" ", "").replace(",", ""))
        except ValueError:
            await update.message.reply_text("Iltimos, faqat summa (raqam) yuboring, masalan: 3000000")
            return
        context.user_data.pop("pending_payment_employee_id", None)
        try:
            employee = nx.get_page(pending_payment)
            nomi = nx.get_title(employee, "Ism") or "Xodim"
            nx.create_page(nx.DS_MOLIYA, {
                "Nomi": {"title": [{"text": {"content": f"{nomi} — oylik to'lovi"}}]},
                "Turi": {"select": {"name": "Chiqim"}},
                "Kategoriya": {"select": {"name": "Ish haqi"}},
                "Summa": {"number": summa},
                "Sana": {"date": {"start": _tashkent_today().isoformat()}},
                "Xodim": {"relation": [{"id": pending_payment}]},
                "Izoh": {"rich_text": [{"text": {"content": "Admin orqali qayd etilgan to'lov"}}]},
            })
            try:
                joriy_kredit = nx.get_number(employee, "Kredit") or 0
                yangi_kredit = max(joriy_kredit - summa, 0)
                nx.update_page_property(pending_payment, {"Kredit": {"number": yangi_kredit}})
            except Exception:
                logger.exception(f"{nomi} uchun to'lovdan keyin Kreditni yangilashda xatolik")
                yangi_kredit = None
            xabar = f"✅ {nomi}ga {_format_som(summa)} to'lov qayd etildi."
            if yangi_kredit is not None:
                xabar += f"\n💳 Qolgan Kredit: {_format_som(yangi_kredit)}"
            await update.message.reply_text(xabar)
            chat_id_str = nx.get_rich_text(employee, "Telegram")
            if chat_id_str:
                try:
                    await context.bot.send_message(
                        chat_id=int(chat_id_str), text=f"💵 Sizga {_format_som(summa)} to'lov qilindi."
                    )
                except TelegramError:
                    logger.exception("Xodimga to'lov haqida xabar yuborilmadi")
        except Exception:
            logger.exception("To'lovni yozishda xatolik")
            await update.message.reply_text("⚠️ To'lovni qayd etib bo'lmadi.")
        return

    # 3b) Xodimga avans summasi kutilyaptimi?
    pending_advance = context.user_data.get("pending_advance_employee_id")
    if pending_advance:
        try:
            summa = float(text_val.replace(" ", "").replace(",", ""))
        except ValueError:
            await update.message.reply_text("Iltimos, faqat summa (raqam) yuboring, masalan: 1000000")
            return
        context.user_data.pop("pending_advance_employee_id", None)
        try:
            employee = nx.get_page(pending_advance)
            nomi = nx.get_title(employee, "Ism") or "Xodim"
            nx.create_page(nx.DS_MOLIYA, {
                "Nomi": {"title": [{"text": {"content": f"{nomi} — avans"}}]},
                "Turi": {"select": {"name": "Chiqim"}},
                "Kategoriya": {"select": {"name": "Ish haqi"}},
                "Summa": {"number": summa},
                "Sana": {"date": {"start": _tashkent_today().isoformat()}},
                "Xodim": {"relation": [{"id": pending_advance}]},
                "Izoh": {"rich_text": [{"text": {"content": "Avans (admin orqali)"}}]},
            })
            try:
                joriy_kredit = nx.get_number(employee, "Kredit") or 0
                yangi_kredit = max(joriy_kredit - summa, 0)
                nx.update_page_property(pending_advance, {"Kredit": {"number": yangi_kredit}})
            except Exception:
                logger.exception(f"{nomi} uchun avansdan keyin Kreditni yangilashda xatolik")
                yangi_kredit = None
            xabar = f"✅ {nomi}ga {_format_som(summa)} avans qayd etildi."
            if yangi_kredit is not None:
                xabar += f"\n💳 Qolgan Kredit: {_format_som(yangi_kredit)}"
            await update.message.reply_text(xabar)
            chat_id_str = nx.get_rich_text(employee, "Telegram")
            if chat_id_str:
                try:
                    await context.bot.send_message(
                        chat_id=int(chat_id_str), text=f"🪙 Sizga {_format_som(summa)} avans berildi."
                    )
                except TelegramError:
                    logger.exception("Xodimga avans haqida xabar yuborilmadi")
        except Exception:
            logger.exception("Avansni yozishda xatolik")
            await update.message.reply_text("⚠️ Avansni qayd etib bo'lmadi.")
        return

    # 3c) "Vazifa boshiga" xodim uchun qo'lda bajarilgan ish soni kutilyaptimi?
    pending_work = context.user_data.get("pending_work_employee_id")
    if pending_work:
        try:
            son = int(text_val.replace(" ", ""))
        except ValueError:
            await update.message.reply_text("Iltimos, faqat butun son yuboring, masalan: 29")
            return
        context.user_data.pop("pending_work_employee_id", None)
        try:
            employee = nx.get_page(pending_work)
            nomi = nx.get_title(employee, "Ism") or "Xodim"
            summa = nx.get_number(employee, "Maosh summasi") or 0
            maqsad = nx.get_number(employee, "Maosh maqsad soni") or 0
            if not summa or not maqsad:
                await update.message.reply_text(
                    f"⚠️ {nomi} uchun 'Maosh summasi' yoki 'Maosh maqsad soni' Notion'da to'ldirilmagan."
                )
                return
            per_ish = summa / maqsad
            qoshiladigan = per_ish * son
            nx.create_page(nx.DS_MOLIYA, {
                "Nomi": {"title": [{"text": {"content": f"{nomi} — {son} ta ish (qo'lda kiritildi)"}}]},
                "Turi": {"select": {"name": "Kirim"}},
                "Kategoriya": {"select": {"name": "Ish haqi"}},
                "Summa": {"number": qoshiladigan},
                "Sana": {"date": {"start": _tashkent_today().isoformat()}},
                "Xodim": {"relation": [{"id": pending_work}]},
                "Izoh": {"rich_text": [{"text": {"content": f"{son} ta ish, admin tomonidan qo'lda kiritildi"}}]},
            })
            try:
                joriy_kredit = nx.get_number(employee, "Kredit") or 0
                nx.update_page_property(pending_work, {"Kredit": {"number": joriy_kredit + qoshiladigan}})
            except Exception:
                logger.exception(f"{nomi} uchun qo'lda ish qo'shilganda Kreditga qo'shishda xatolik")
            await update.message.reply_text(
                f"✅ {nomi}ga {son} ta ish uchun {_format_som(qoshiladigan)} qo'shildi.\n"
                f"/moliya orqali yangilangan balansni ko'rishingiz mumkin."
            )
        except Exception:
            logger.exception("Bajarilgan ish sonini yozishda xatolik")
            await update.message.reply_text("⚠️ Ish sonini qayd etib bo'lmadi.")
        return

    # 3d) Xodim o'zi "/qildim" bilan nechta ish bajarganini yozyaptimi (alohida vazifa
    # tayinlanmagan, donasiga to'lanadigan ishlar uchun — masalan Mubinaning montajlari)?
    pending_self_ish = context.user_data.get("pending_self_ish_employee_id")
    if pending_self_ish:
        try:
            son = int(text_val.replace(" ", ""))
            if son <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Iltimos, musbat butun son yuboring, masalan: 1")
            return
        context.user_data.pop("pending_self_ish_employee_id", None)
        try:
            employee = nx.get_page(pending_self_ish)
            nomi = nx.get_title(employee, "Ism") or "Xodim"
            summa = nx.get_number(employee, "Maosh summasi") or 0
            maqsad = nx.get_number(employee, "Maosh maqsad soni") or 0
            if not summa or not maqsad:
                await update.message.reply_text(
                    "⚠️ Sizning donaviy stavkangiz Notion'da to'liq sozlanmagan. Admin bilan bog'laning."
                )
                return
            per_ish = summa / maqsad
            qoshiladigan = per_ish * son
            nx.create_page(nx.DS_MOLIYA, {
                "Nomi": {"title": [{"text": {"content": f"{nomi} — {son} ta ish (o'zi qo'shdi)"}}]},
                "Turi": {"select": {"name": "Kirim"}},
                "Kategoriya": {"select": {"name": "Ish haqi"}},
                "Summa": {"number": qoshiladigan},
                "Sana": {"date": {"start": _tashkent_today().isoformat()}},
                "Xodim": {"relation": [{"id": pending_self_ish}]},
                "Izoh": {"rich_text": [{"text": {"content": f"{son} ta ish, {nomi} o'zi botga qo'shdi"}}]},
            })
            try:
                joriy_kredit = nx.get_number(employee, "Kredit") or 0
                nx.update_page_property(pending_self_ish, {"Kredit": {"number": joriy_kredit + qoshiladigan}})
            except Exception:
                logger.exception(f"{nomi} o'zi ish qo'shganda Kreditga qo'shishda xatolik")
            await update.message.reply_text(
                f"✅ Qabul qilindi: {son} ta ish uchun {_format_som(qoshiladigan)} hisoblandi.\n"
                f"/moliya orqali balansingizni ko'rishingiz mumkin."
            )
            if ADMIN_CHAT_ID and str(chat_id) != str(ADMIN_CHAT_ID):
                try:
                    await context.bot.send_message(
                        chat_id=ADMIN_CHAT_ID,
                        text=f"📌 {nomi} o'zi {son} ta ish qo'shdi (+{_format_som(qoshiladigan)}).",
                    )
                except Exception:
                    logger.exception("Adminga o'z-ish xabarini yuborib bo'lmadi")
        except Exception:
            logger.exception("O'z-ish sonini yozishda xatolik")
            await update.message.reply_text("⚠️ Qayd etib bo'lmadi.")
        return

    # 4) Maosh stavkasi o'zgartirilyaptimi?
    pending_rate_emp = context.user_data.get("pending_rate_employee_id")
    if pending_rate_emp:
        try:
            raqam = float(text_val.replace(" ", "").replace(",", ""))
        except ValueError:
            await update.message.reply_text("Iltimos, faqat raqam yuboring.")
            return

        turi = context.user_data.get("pending_rate_turi")

        if turi == "Vazifa boshiga" and "pending_rate_summa_temp" not in context.user_data:
            context.user_data["pending_rate_summa_temp"] = raqam
            await update.message.reply_text("Endi maqsad ish sonini yozing (masalan: 90):")
            return

        try:
            employee = nx.get_page(pending_rate_emp)
            nomi = nx.get_title(employee, "Ism") or "xodim"
        except Exception:
            logger.exception("Stavka yangilash uchun xodimni olishda xatolik")
            await update.message.reply_text("⚠️ Xodim topilmadi.")
            context.user_data.pop("pending_rate_employee_id", None)
            context.user_data.pop("pending_rate_turi", None)
            context.user_data.pop("pending_rate_summa_temp", None)
            return

        try:
            if turi == "Vazifa boshiga":
                summa = context.user_data.pop("pending_rate_summa_temp")
                maqsad = raqam
                nx.update_page_property(pending_rate_emp, {
                    "Maosh summasi": {"number": summa},
                    "Maosh maqsad soni": {"number": maqsad},
                })
                await update.message.reply_text(f"✅ {nomi}: yangi stavka — {_format_som(summa)} / {maqsad:g} ish.")
            else:
                nx.update_page_property(pending_rate_emp, {"Maosh summasi": {"number": raqam}})
                await update.message.reply_text(f"✅ {nomi}: yangi oylik stavka — {_format_som(raqam)}.")
        except Exception:
            logger.exception("Stavkani yangilashda xatolik")
            await update.message.reply_text("⚠️ Stavkani yangilab bo'lmadi.")

        context.user_data.pop("pending_rate_employee_id", None)
        context.user_data.pop("pending_rate_turi", None)
        return

    # 4b) Yangi loyiha qo'shish oqimi (nomi -> reels target -> video target -> post target -> kanal)?
    new_loyiha = context.user_data.get("new_loyiha")
    if new_loyiha:
        stage = new_loyiha.get("stage")

        if stage == "nomi":
            if not text_val:
                await update.message.reply_text("Loyiha nomi bo'sh bo'lmasin. Qaytadan yozing:")
                return
            new_loyiha["nomi"] = text_val
            new_loyiha["stage"] = "sana"
            await update.message.reply_text(
                "📅 Bu loyiha hisob-kitob davri qachondan boshlanadi?\n"
                "Sanani yozing (masalan: 15.07.2026) yoki 'bugun' deb yuboring:"
            )
            return

        if stage == "sana":
            sana = _parse_flexible_date(text_val)
            if not sana:
                await update.message.reply_text(
                    "Sanani tushunmadim. Masalan: 15.07.2026 yoki 'bugun' deb yozing:"
                )
                return
            new_loyiha["boshlanish_sanasi"] = sana.isoformat()
            new_loyiha["stage"] = "loyiha_turi"
            await update.message.reply_text(
                "📁 Bu qanday loyiha?\n\n"
                "📁 *Media loyiha* — mijoz uchun reels/video/TG post ishlab chiqarilib, soni kuzatiladi "
                "(masalan ARK Hospital, Shovkat aka).\n"
                "🎯 *Target loyiha* — shaxsiy target, reels/video/TG post kuzatuvi kerak emas, faqat to'lov.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=_new_loyiha_turi_keyboard(),
            )
            return

        if stage == "loyiha_turi":
            await update.message.reply_text("Iltimos, yuqoridagi tugmalardan loyiha turini tanlang.")
            return

        if stage in ("reels_video", "video_target", "post_target"):
            _skip_words = {"yo'q", "yoq", "yuq", "-", "skip", "kerak emas"}
            skip = text_val.strip().lower() in _skip_words
            son = None
            if not skip:
                try:
                    son = int(text_val.replace(" ", ""))
                except ValueError:
                    await update.message.reply_text("Iltimos, faqat butun son yuboring, yoki kerak bo'lmasa \"yo'q\" deb yozing:")
                    return

            if stage == "reels_video":
                new_loyiha["reels_target"] = son
                new_loyiha["stage"] = "video_target"
                await update.message.reply_text(
                    "🎬 Oylik TARGET VIDEO sonini yozing (masalan: 10), yoki kerak bo'lmasa \"yo'q\":"
                )
                return

            if stage == "video_target":
                new_loyiha["video_target"] = son
                new_loyiha["stage"] = "post_target"
                await update.message.reply_text(
                    "📝 Oylik TELEGRAM POST target sonini yozing (masalan: 30), yoki kerak bo'lmasa \"yo'q\":"
                )
                return

            # stage == "post_target"
            new_loyiha["post_target"] = son
            new_loyiha["stage"] = "kanal"
            await update.message.reply_text(
                "📢 Bu loyiha qaysi Telegram kanaliga bog'liq? (Telegram post sonini bot shu kanal orqali avtomatik hisoblaydi)\n"
                "Kanalga bog'liq bo'lmasa \"🚫 Yo'q\" tugmasini bosing.",
                reply_markup=_new_loyiha_channel_keyboard(),
            )
            return

        if stage == "kanal":
            await update.message.reply_text("Iltimos, yuqoridagi tugmalardan kanalni tanlang.")
            return

        if stage == "tolov_turi":
            await update.message.reply_text("Iltimos, yuqoridagi tugmalardan to'lov turini tanlang.")
            return

        if stage == "tolov_summasi":
            try:
                summa = float(text_val.replace(" ", "").replace(",", ""))
            except ValueError:
                await update.message.reply_text("Iltimos, faqat summa (raqam) yuboring, masalan: 150000")
                return
            new_loyiha["tolov_summasi"] = summa
            if new_loyiha.get("loyiha_turi") == "aralash":
                new_loyiha["stage"] = "target_narxi"
                await update.message.reply_text(
                    "✏️ Endi TARGET (reklama) uchun alohida narx: 1 ta target/reklama yoqish "
                    "necha so'm? (Bu reels narxidan mustaqil — chalkashmasin uchun alohida "
                    "hisoblanadi). Kerak bo'lmasa \"yo'q\" deb yozing:"
                )
                return
            await _finalize_new_loyiha(context.bot, chat_id, new_loyiha)
            context.user_data.pop("new_loyiha", None)
            return

        if stage == "target_narxi":
            if text_val.strip().lower() in {"yo'q", "yoq", "yuq", "-", "skip"}:
                new_loyiha["target_narxi"] = None
            else:
                try:
                    new_loyiha["target_narxi"] = float(text_val.replace(" ", "").replace(",", ""))
                except ValueError:
                    await update.message.reply_text("Iltimos, faqat summa (raqam) yuboring, masalan: 150000, yoki \"yo'q\" deb yozing.")
                    return
            await _finalize_new_loyiha(context.bot, chat_id, new_loyiha)
            context.user_data.pop("new_loyiha", None)
            return

    # 5) Vazifa matni kutilyaptimi (xodim va muddat allaqachon tanlangan)?
    pending_emp = context.user_data.get("pending_vazifa_employee_id")
    if pending_emp:
        pending_date = context.user_data.get("pending_vazifa_date")
        if not pending_date:
            await update.message.reply_text("Iltimos, avval muddatni yuqoridagi tugmalardan tanlang.")
            return
        if not text_val:
            await update.message.reply_text("Vazifa matni bo'sh bo'lmasin.")
            return

        context.user_data.pop("pending_vazifa_employee_id", None)
        context.user_data.pop("pending_vazifa_date", None)

        try:
            employee = nx.get_page(pending_emp)
        except Exception:
            logger.exception("Xodim sahifasini olishda xatolik")
            await update.message.reply_text("⚠️ Xodim ma'lumotini olib bo'lmadi, /vazifa deb qaytadan urinib ko'ring.")
            return

        ism = nx.get_title(employee, "Ism") or "xodim"
        vazifalar_royxati = _split_vazifa_lines(text_val)
        for bitta_vazifa in vazifalar_royxati:
            await _create_vazifa(context.bot, chat_id, employee, ism, bitta_vazifa, muddat=pending_date)
        return

    # Hech narsa kutilmayapti — oddiy xabar, e'tiborsiz qoldiramiz


# ----------------------------------------------------------------------------
# /kontent (tasdiqlash), /joylash (kanalga chiqarish)
# ----------------------------------------------------------------------------

def _normalize_br(text: str) -> str:
    """Notion'da rich-text ichida ba'zan literal "<br>"/"<br/>"/"<br />" belgilari qoladi
    (HTML emas, oddiy matn sifatida). Kanalga joylashdan oldin ularni haqiqiy qator
    ko'chirishga ("\\n") aylantiradi, aks holda Telegram xabarida "<br>" so'zi ko'rinib qoladi."""
    if not text:
        return text
    return re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)


def _build_publish_message(hook: str, body: str, footer: str, max_len: int | None = None) -> str:
    """Kanalga joylanadigan xabarni yig'adi: Hook va footer (imzo) QALIN (bold), tana esa
    oddiy matn sifatida. Telegram HTML parse_mode uchun xavfsiz (escape qilingan) natija
    qaytaradi — shuning uchun matn ichida "_" yoki "*" kabi belgilar bo'lsa ham hech narsa
    buzilmaydi (avvalgi Markdown muammosi shu tarzda butunlay bartaraf etilgan)."""
    segments: list[tuple[str, str]] = []
    if hook and hook.strip():
        segments.append(("bold", hook.strip()))
    if body and body.strip():
        segments.append(("plain", body.strip()))
    if footer and footer.strip():
        segments.append(("bold", footer.strip()))

    if max_len is not None:
        fixed_len = sum(len(s) for typ, s in segments if typ == "bold")
        fixed_len += 2 * max(len(segments) - 1, 0)  # "\n\n" ajratgichlar
        budget = max_len - fixed_len
        trimmed = []
        for typ, s in segments:
            if typ == "plain" and len(s) > budget:
                s = s[: max(budget - 3, 0)].rstrip() + "..."
            trimmed.append((typ, s))
        segments = trimmed

    parts = []
    for typ, s in segments:
        # quote=False: Telegram HTML rejimida faqat <, >, & ni escape qilish shart —
        # tirnoq/apostrofni ham escape qilish shart emas va matnni g'alati ko'rsatib yuboradi.
        escaped = html.escape(s, quote=False)
        parts.append(f"<b>{escaped}</b>" if typ == "bold" else escaped)
    return "\n\n".join(parts)


async def _publish_kontent_post(bot, page_id: str) -> tuple[bool, str]:
    """Bitta Kontent-Reja postini haqiqiy Telegram kanaliga joylaydi va Status'ni 'Joylandi'
    qiladi. (muvaffaqiyatmi, xabar matni) qaytaradi. Bir nechta joydan chaqiriladi: qo'lda
    "🚀 Kanalga joylash" tugmasi orqali, yoki Sana+Vaqt'i kelib yetganda avtomatik."""
    try:
        page = nx.get_page(page_id)
        nomi = nx.get_title(page, "Post nomi") or "Post"
        kanal = nx.get_select(page, "Kanal") or "?"
        channel_target = nx.CHANNEL_MAP.get(kanal)
        hook = _normalize_br(nx.get_rich_text(page, "Hook"))
        matn = _normalize_br(nx.get_rich_text(page, "Ssenariy/Matn"))
        rasm_url = nx.get_url(page, "Rasm/Video havolasi")

        if not channel_target:
            return False, f"⚠️ '{nomi}': bu kanal uchun Telegram manzili sozlanmagan, joylay olmadim."

        # Footer (imzo) odatda post matni ichiga allaqachon yozib qo'yilgan bo'ladi (masalan
        # ARK Hospital'ning "@ark_hospitalll..." qatori). Uni "Kanal Shablonlari"dagi asl
        # shablon bilan solishtirib, matn tanasidan ajratib olamiz — shunda faqat o'sha
        # qismini QALIN qilib qayta biriktirish mumkin bo'ladi.
        footer_shabloni = _normalize_br(nx.get_channel_footer(kanal))
        body = matn
        footer = ""
        if footer_shabloni and matn.rstrip().endswith(footer_shabloni.rstrip()):
            footer = footer_shabloni.rstrip()
            body = matn.rstrip()[: -len(footer)].rstrip()
        else:
            # Shablon aniq mos kelmasa ham (masalan telefon raqami/bo'shliqda kichik farq),
            # oxirgi paragraf (bo'sh qatordan keyingi so'nggi qism) har doim QALIN qilib
            # yuborilsin — bu odatda kanal imzosi/manzili bo'ladi.
            qismlar = re.split(r"\n\s*\n", matn.rstrip())
            if len(qismlar) > 1:
                footer = qismlar[-1].strip()
                body = "\n\n".join(qismlar[:-1]).rstrip()

        # Rasm manbasi: avval lokal (Gemini orqali yasalgan) rasm, bo'lmasa Notion'dagi URL.
        lokal_rasm = _local_image_path(page_id) if _has_local_image(page_id) else None

        if lokal_rasm:
            joylanadigan_matn = _build_publish_message(hook, body, footer, max_len=1024)
            with open(lokal_rasm, "rb") as f:
                await bot.send_photo(
                    chat_id=channel_target, photo=f, caption=joylanadigan_matn, parse_mode=ParseMode.HTML
                )
        elif rasm_url:
            joylanadigan_matn = _build_publish_message(hook, body, footer, max_len=1024)
            await bot.send_photo(
                chat_id=channel_target, photo=rasm_url, caption=joylanadigan_matn, parse_mode=ParseMode.HTML
            )
        else:
            joylanadigan_matn = _build_publish_message(hook, body, footer)
            await bot.send_message(chat_id=channel_target, text=joylanadigan_matn, parse_mode=ParseMode.HTML)

        nx.update_page_property(page_id, {"Status": {"select": {"name": "Joylandi"}}})
        return True, f"✅ '{nomi}' ({kanal}) kanalga joylandi!"
    except TelegramError as e:
        logger.exception("Kanalga joylashda Telegram xatoligi")
        return False, f"⚠️ Kanalga joylay olmadim: {e}\nBot shu kanalda admin (post huquqi bilan) ekanligini tekshiring."
    except Exception:
        logger.exception("Kanalga joylashda xatolik")
        return False, "⚠️ Xatolik yuz berdi."


def _kontent_channel_keyboard(channels: list[tuple[str, int]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"📢 {kanal} ({soni})", callback_data=f"kontent_kanal:{kanal}")]
        for kanal, soni in channels
    ]
    return InlineKeyboardMarkup(rows)


async def _do_kontent(bot, chat_id) -> None:
    """Avval qaysi kanal uchun tasdiqlash kerakligini so'raydi (har birida nechta post
    kutayotgani bilan). Kanal tanlangach, postlar birma-bir (bittadan) yuboriladi —
    ✅/❌ bosilgach, o'sha kanaldagi keyingi post avtomatik keladi."""
    try:
        postlar = nx.query_data_source(
            nx.DS_KONTENT_REJA, filter_obj={"property": "Status", "select": {"equals": "Yozildi"}}
        )
    except Exception:
        logger.exception("Kontent-rejani olishda xatolik")
        await bot.send_message(chat_id=chat_id, text="Xatolik yuz berdi, keyinroq urinib ko'ring.")
        return

    if not postlar:
        await bot.send_message(chat_id=chat_id, text="Tasdiqlash kutayotgan post yo'q. ✅")
        return

    counts: dict[str, int] = {}
    for p in postlar:
        kanal = nx.get_select(p, "Kanal") or "Noma'lum kanal"
        counts[kanal] = counts.get(kanal, 0) + 1

    channels = sorted(counts.items(), key=lambda item: item[0])
    await bot.send_message(
        chat_id=chat_id,
        text="📢 Qaysi kanal uchun tasdiqlaysiz?",
        reply_markup=_kontent_channel_keyboard(channels),
    )


# Rasm talab qiladigan post turlari (bularsiz "Rasm yasash" tugmasi ko'rsatilmaydi)
_RASM_KERAK_POST_TURLARI = {"Rasm", "Rasm+Matn", "Carousel"}


def _local_image_path(page_id: str) -> str:
    return os.path.join(GENERATED_IMAGES_DIR, f"{page_id}.png")


def _has_local_image(page_id: str) -> bool:
    return os.path.isfile(_local_image_path(page_id))


def _kontent_post_keyboard(page_id: str, rasm_kerakmi: bool = False, rasm_bormi: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve:{page_id}"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"reject:{page_id}"),
        ],
        [InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"edit_kontent:{page_id}")],
    ]
    if rasm_kerakmi:
        label = "🔄 Rasmni qayta yasash" if rasm_bormi else "🎨 Rasm yasash"
        rows.append([InlineKeyboardButton(label, callback_data=f"gen_image:{page_id}")])
    return InlineKeyboardMarkup(rows)


def _build_image_prompt(nomi: str, mavzu: str, matn: str, kanal: str) -> str:
    """Post mavzusi asosida Gemini uchun rasm generatsiya prompti tuzadi (ingliz tilida —
    uslub ko'rsatmalari uchun ancha ishonchli natija beradi)."""
    mavzu_yoki_nomi = (mavzu or nomi or "").strip()
    kontekst = (matn or "")[:300].strip()
    return (
        "Create a professional, high-quality, photograph-style image for a healthcare/hospital "
        f"social media post. Topic: {mavzu_yoki_nomi}. Post title (in Uzbek): {nomi}. "
        f"Context: {kontekst}. Style: clean, modern, trustworthy medical/clinical aesthetic, "
        "soft professional lighting, realistic, no visible text, no watermarks, no logos in the "
        f"image, suitable for a hospital brand's Telegram channel post ({kanal})."
    )


async def _send_kontent_post_message(bot, chat_id, page: dict) -> None:
    """Bitta Kontent-Reja postini (nomi, sana, kanal, matn) tugmalari bilan yuboradi.
    Agar shu post uchun lokal generatsiya qilingan rasm bo'lsa, uni ham (rasm sifatida) biriktiradi."""
    page_id = page["id"]
    nomi = nx.get_title(page, "Post nomi")
    kanal = nx.get_select(page, "Kanal") or "?"
    matn = nx.get_rich_text(page, "Ssenariy/Matn")
    sana = nx.get_date(page, "Sana") or "?"
    post_turi = nx.get_select(page, "Post turi") or ""

    rasm_url = nx.get_url(page, "Rasm/Video havolasi")
    rasm_bormi = _has_local_image(page_id) or bool(rasm_url)
    rasm_kerakmi = post_turi in _RASM_KERAK_POST_TURLARI

    preview = matn[:800] + ("..." if len(matn) > 800 else "")
    # MUHIM: parse_mode=Markdown ISHLATILMAYDI — post matni ichida "_" yoki "*" kabi
    # belgilar bo'lishi mumkin (masalan link ichidagi "urolog_shovkat"), bular Telegram'ning
    # Markdown parserini buzib, xabarni butunlay yuborilmay qoladigan qilib qo'yishi mumkin edi.
    text = f"📅 {sana} | 📢 {kanal}\n📌 {nomi}\n\n{preview}"
    keyboard = _kontent_post_keyboard(page_id, rasm_kerakmi=rasm_kerakmi, rasm_bormi=rasm_bormi)

    try:
        if _has_local_image(page_id):
            with open(_local_image_path(page_id), "rb") as f:
                await bot.send_photo(chat_id=chat_id, photo=f, caption=text[:1024], reply_markup=keyboard)
        else:
            await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
    except Exception:
        logger.exception(f"'{nomi}' postini ko'rsatishda xatolik")


async def _send_next_kontent_post(bot, chat_id, kanal: str) -> bool:
    """Berilgan kanal uchun navbatdagi tasdiqlanmagan (Yozildi) postni yuboradi.
    Post topilmasa False qaytaradi (chaqiruvchi shu orqali 'tugadi' xabarini beradi)."""
    try:
        postlar = nx.query_data_source(
            nx.DS_KONTENT_REJA,
            filter_obj={
                "and": [
                    {"property": "Status", "select": {"equals": "Yozildi"}},
                    {"property": "Kanal", "select": {"equals": kanal}},
                ]
            },
        )
    except Exception:
        logger.exception("Kontent-rejani olishda xatolik (kanal bo'yicha)")
        await bot.send_message(chat_id=chat_id, text="Xatolik yuz berdi.")
        return False

    if not postlar:
        return False

    await _send_kontent_post_message(bot, chat_id, postlar[0])
    return True


@require_auth
async def kontent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _do_kontent(context.bot, update.effective_chat.id)


async def _do_joylash(bot, chat_id) -> None:
    try:
        postlar = nx.query_data_source(
            nx.DS_KONTENT_REJA, filter_obj={"property": "Status", "select": {"equals": "Tasdiqlandi"}}
        )
    except Exception:
        logger.exception("Kontent-rejani olishda xatolik")
        await bot.send_message(chat_id=chat_id, text="Xatolik yuz berdi.")
        return

    if not postlar:
        await bot.send_message(chat_id=chat_id, text="Kanalga joylash uchun tasdiqlangan post yo'q.")
        return

    for p in postlar[:10]:
        page_id = p["id"]
        nomi = nx.get_title(p, "Post nomi")
        kanal = nx.get_select(p, "Kanal") or "?"
        channel_target = nx.CHANNEL_MAP.get(kanal)

        text = f"📅 📢 {kanal}\n📌 {nomi}\n\nStatus: Tasdiqlandi"
        if not channel_target:
            text += "\n\n⚠️ Bu kanal uchun Telegram manzili sozlanmagan (muhit o'zgaruvchisi yo'q)."
            try:
                await bot.send_message(chat_id=chat_id, text=text)
            except Exception:
                logger.exception(f"'{nomi}' postini ko'rsatishda xatolik")
            continue

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🚀 Kanalga joylash", callback_data=f"publish:{page_id}")]]
        )
        try:
            await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
        except Exception:
            logger.exception(f"'{nomi}' postini ko'rsatishda xatolik")


@require_auth
async def joylash(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _do_joylash(context.bot, update.effective_chat.id)


# ----------------------------------------------------------------------------
# /target
# ----------------------------------------------------------------------------

async def _do_target(bot, chat_id) -> None:
    lines = []

    # 1) Yo'nalishlar (umumiy biznes yo'nalishlari, agar kiritilgan bo'lsa)
    try:
        yonalishlar = nx.query_data_source(nx.DS_YONALISHLAR)
    except Exception:
        logger.exception("Yo'nalishlarni olishda xatolik")
        yonalishlar = []

    if yonalishlar:
        lines.append("🎯 *Yo'nalishlar bo'yicha progress*\n")
        for y in yonalishlar:
            nomi = nx.get_title(y, "Yo'nalish")
            oy = nx.get_rich_text(y, "Oy") or "-"
            tgt = nx.get_number(y, "Target (son)")
            bajarildi = nx.get_number(y, "Bajarildi (son)")
            if tgt:
                foiz = round((bajarildi or 0) / tgt * 100)
                lines.append(f"• {nomi} ({oy}): {bajarildi or 0}/{tgt} — *{foiz}%*")
            else:
                lines.append(f"• {nomi} ({oy}): target kiritilmagan")

    # 2) Loyihalar bo'yicha progress (joriy oy, har bir mijoz-loyiha uchun reels/video/post)
    loyiha_data = _compute_loyiha_dashboard_data()
    if loyiha_data:
        if lines:
            lines.append("")
        lines.append(f"📁 *Loyihalar bo'yicha progress* ({_current_month_str()})\n")
        for l in loyiha_data:
            parts = []
            for label, d, t in l["metrics"]:
                if t:
                    foiz = round((d or 0) / t * 100)
                    parts.append(f"{label} {d or 0}/{t} ({foiz}%)")
                else:
                    parts.append(f"{label} {d or 0}")
            lines.append(f"• *{l['name']}*: " + ", ".join(parts))

    if not lines:
        await bot.send_message(chat_id=chat_id, text="Hali hech qanday target/yo'nalish/loyiha kiritilmagan.")
        return

    await bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode=ParseMode.MARKDOWN)


@require_auth
async def target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _do_target(context.bot, update.effective_chat.id)


# ----------------------------------------------------------------------------
# /reels — har kuni qaysi loyihaga nechta reels joylanganini so'rash
# ----------------------------------------------------------------------------

def _loyiha_picker_keyboard():
    try:
        loyihalar = nx.query_data_source(
            nx.DS_LOYIHALAR,
            filter_obj={
                "and": [
                    {"property": "Holati", "select": {"does_not_equal": "Pauzada"}},
                    {"property": "Holati", "select": {"does_not_equal": "Arxivlangan"}},
                ]
            },
        )
    except Exception:
        logger.exception("Loyihalarni olishda xatolik (reels)")
        return None

    if not loyihalar:
        return None

    rows = []
    for l in loyihalar:
        nomi = nx.get_title(l, "Loyiha") or "?"
        rows.append([InlineKeyboardButton(f"🎬 {nomi}", callback_data=f"reels_proj:{l['id']}")])
    return InlineKeyboardMarkup(rows)


async def _do_reels_menu(bot, chat_id) -> None:
    keyboard = _loyiha_picker_keyboard()
    if not keyboard:
        await bot.send_message(chat_id=chat_id, text="⚠️ Faol loyiha topilmadi. Avval /yangiloyiha bilan qo'shing.")
        return
    await bot.send_message(chat_id=chat_id, text="🎬 Bugun qaysi loyihaga nechta reels joylandi?", reply_markup=keyboard)


@require_auth
async def reels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _do_reels_menu(context.bot, update.effective_chat.id)


# ----------------------------------------------------------------------------
# 🎯 Target hisobot — video sonini va obunachi (auditoriya) sonini kiritish
# ----------------------------------------------------------------------------

def _target_loyiha_picker_keyboard():
    """_loyiha_picker_keyboard bilan bir xil (Faol loyihalar), lekin 'target_hproj:' prefiksi bilan."""
    try:
        loyihalar = nx.query_data_source(
            nx.DS_LOYIHALAR,
            filter_obj={
                "and": [
                    {"property": "Holati", "select": {"does_not_equal": "Pauzada"}},
                    {"property": "Holati", "select": {"does_not_equal": "Arxivlangan"}},
                ]
            },
        )
    except Exception:
        logger.exception("Loyihalarni olishda xatolik (target hisobot)")
        return None

    if not loyihalar:
        return None

    rows = [
        [InlineKeyboardButton(f"📁 {nx.get_title(l, 'Loyiha') or '?'}", callback_data=f"target_hproj:{l['id']}")]
        for l in loyihalar
    ]
    return InlineKeyboardMarkup(rows)


async def _do_target_hisobot_menu(bot, chat_id) -> None:
    if not (ADMIN_CHAT_ID and str(chat_id) == str(ADMIN_CHAT_ID)):
        await bot.send_message(chat_id=chat_id, text="Bu bo'lim faqat admin uchun.")
        return
    keyboard = _target_loyiha_picker_keyboard()
    if not keyboard:
        await bot.send_message(chat_id=chat_id, text="⚠️ Faol loyiha topilmadi. Avval /yangiloyiha bilan qo'shing.")
        return
    await bot.send_message(
        chat_id=chat_id, text="🎯 Qaysi loyiha bo'yicha video yoki obunachi sonini yangilaysiz?", reply_markup=keyboard
    )


def _target_metric_keyboard(project_id: str, loyiha_turi: str = "Media") -> InlineKeyboardMarkup:
    video_label = "🎯 Target qo'shish" if loyiha_turi in ("Target", "Aralash") else "🎞 Video qo'shish"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(video_label, callback_data=f"target_video:{project_id}")],
        [InlineKeyboardButton("👥 Obunachi sonini yangilash", callback_data=f"target_obuna:{project_id}")],
    ])


# ----------------------------------------------------------------------------
# 💰 Moliya — xodim balansi, kunlik/vazifa-asosli maosh hisoblash, to'lovlar
# ----------------------------------------------------------------------------

def _format_som(n: float) -> str:
    return f"{n:,.0f}".replace(",", " ") + " so'm"


def _hisob_period(hisob_kuni: int, today: date) -> tuple[date, date]:
    """Xodimning shaxsiy 'Hisob kuni'siga asoslangan joriy hisob-kitob davrini qaytaradi.
    Davr har doim shu kunda TUGAYDI (masalan Hasan uchun har oyning 10-sanasida) va undan
    keyingi kundan boshlanadi. Masalan: bugun 31-iyul, hisob kuni 10 bo'lsa — joriy davr
    11-iyuldan 10-avgustgacha (hali tugamagan; faqat shu davr ichida o'tgan qismi hisoblanadi,
    to'liq summa faqat 10-avgustda — hisob kunining o'zida — yig'iladi)."""
    hisob_kuni = min(max(int(hisob_kuni), 1), 28)  # barcha oylarda mavjud bo'lgan xavfsiz kun

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
    """Xodimning JORIY HISOB-KITOB DAVRI bo'yicha (jamg'arilgan Kirim, to'langan Chiqim,
    davr boshi, davr oxiri).

    Davr xodimning shaxsiy "Hisob kuni"siga asoslanadi (masalan Hasan uchun har doim
    ...-11 dan ...-10 gacha) — taqvim oyiga (1-31) EMAS. Shu sabab, masalan, oyning
    oxirida (31-iyulda) hali "to'liq oy" hisoblanib ketmaydi, agar xodimning hisob kuni
    hali kelmagan bo'lsa (masalan Hasan uchun 10-avgustgacha). "Hisob kuni" belgilanmagan
    xodimlar uchun joriy taqvim oyi ishlatiladi.

    'Kunlik (oylik summadan)' turidagi xodimlar uchun jamg'arilgan summa REAL VAQTDA, davr
    ichida o'tgan kunlar ulushi asosida hisoblanadi (davr oxirida — hisob kunining o'zida —
    to'liq summa yig'iladi). 'Vazifa boshiga' turidagi xodimlar uchun Notion'da har bir
    bajarilgan vazifa uchun yozilgan Kirim yozuvlari shu davr ichida yig'iladi."""
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
            nx.DS_MOLIYA, filter_obj={"property": "Xodim", "relation": {"contains": employee_id}}
        )
    except Exception:
        logger.exception("Moliya yozuvlarini olishda xatolik")
        entries = []

    chiqim = 0
    kirim_recorded = 0
    for e in entries:
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
    """Butun biznes bo'yicha (barcha loyiha/xarajatlar) shu oydagi jami Kirim va Chiqim.

    MUHIM: xodimga (Xodim relationi bilan) tegishli "Kirim" yozuvlari bu yerga QO'SHILMAYDI.
    Ular xodimning JAMG'ARILGAN MAOSHI (masalan kunlik hisoblangan yoki bajargan ishi uchun
    tegishli summa) — bu biznesga real tushgan pul emas, aksincha kelajakda to'lanishi kerak
    bo'lgan xarajat (majburiyat). Shuning uchun bu "biznes kirimi"ga qo'shilsa, hisobot
    noto'g'ri, xodimning maoshi go'yo kompaniyaga tushgan daromadday ko'rinib qolar edi.
    Xodimga qilingan haqiqiy to'lov/avans ("Chiqim") esa — bu real xarajat, shuning uchun
    Xodim relationi bor-yo'qligidan qat'iy nazar Chiqim'ga qo'shiladi."""
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


async def _do_moliya(bot, chat_id) -> None:
    """Admin — biznesning umumiy holati (loyihalardan kirim, xarajatlar, sof foyda) + hamma xodimning
    balansini ko'radi. Oddiy xodim — faqat o'zining balansini ko'radi."""
    is_admin_view = bool(ADMIN_CHAT_ID) and str(chat_id) == str(ADMIN_CHAT_ID)
    month = _current_month_str()

    try:
        employees = nx.query_data_source(nx.DS_XODIMLAR)
    except Exception:
        logger.exception("Moliya uchun xodimlarni olishda xatolik")
        await bot.send_message(chat_id=chat_id, text="Xatolik yuz berdi.")
        return

    if is_admin_view:
        target_employees = [e for e in employees if nx.get_select(e, "Maosh turi")]
    else:
        target_employees = [
            e for e in employees
            if nx.get_select(e, "Maosh turi") and nx.get_rich_text(e, "Telegram") == str(chat_id)
        ]

    if not is_admin_view and not target_employees:
        await bot.send_message(
            chat_id=chat_id,
            text="Sizga maosh stavkasi belgilanmagan (yoki hali /men bilan ro'yxatdan o'tmagansiz).",
        )
        return

    lines = []
    action_rows = []

    if is_admin_view:
        biz_kirim, biz_chiqim = _business_month_totals(month)
        foyda = biz_kirim - biz_chiqim
        lines.append(f"💼 *Biznes — {month} umumiy holati*")
        lines.append(
            f"Kirim (loyihalar + boshqa): {_format_som(biz_kirim)}\n"
            f"Chiqim (ish haqi + boshqa): {_format_som(biz_chiqim)}\n"
            f"Sof foyda: {_format_som(foyda)}"
        )

        try:
            # Faqat FAOL loyihalar hisoblanadi — Pauzada/Arxivlangan loyihalar to'xtatilgan
            # bo'lgani uchun ularning eski Debiti umumiy "qancha qarzdormiz" ko'rinishini
            # chalkashtirmasligi kerak.
            loyihalar_debit = nx.query_data_source(
                nx.DS_LOYIHALAR, filter_obj={"property": "Holati", "select": {"equals": "Faol"}}
            )
            debit_qarzdorlar = [
                (nx.get_title(l, "Loyiha") or "?", nx.get_number(l, "Debit") or 0)
                for l in loyihalar_debit
                if (nx.get_number(l, "Debit") or 0) > 0
            ]
            jami_debit = sum(d for _, d in debit_qarzdorlar)
        except Exception:
            logger.exception("Loyihalar Debit'ini yig'ishda xatolik")
            jami_debit = 0
            debit_qarzdorlar = []
        if jami_debit:
            debit_qarzdorlar.sort(key=lambda x: x[1], reverse=True)
            qarzdorlar_matni = "\n".join(
                f"   • {nomi}: {_format_som(summa)}" for nomi, summa in debit_qarzdorlar
            )
            lines.append(
                f"\n💳 *Debit (mandan qarzdorlar):* {_format_som(jami_debit)} "
                f"(mijozlar bizga qarzdor, hali to'lanmagan, kirimga qo'shilmagan)\n"
                f"{qarzdorlar_matni}"
            )

        try:
            jami_kredit = 0
            for e in target_employees:
                e_turi = nx.get_select(e, "Maosh turi")
                e_kredit = nx.get_number(e, "Kredit") or 0
                if e_turi == "Kunlik (oylik summadan)":
                    e_kirim, _, _, _ = _moliya_period_totals(e)
                    e_kredit += e_kirim
                jami_kredit += e_kredit
        except Exception:
            logger.exception("Xodimlar Kreditini yig'ishda xatolik")
            jami_kredit = 0
        if jami_kredit:
            lines.append(
                f"💳 *Kredit (xodimlarga qarzimiz):* {_format_som(jami_kredit)} "
                f"(xodimlar ishlagan, biz hali to'lamagan haq)"
            )

        action_rows.append([InlineKeyboardButton("➕ Kirim qo'shish (loyihadan tushgan pul)", callback_data="menu:kirim")])
        lines.append(f"\n💰 *Xodimlar balansi — {month}*")
    else:
        lines.append(f"💰 *Moliya — {month} balansi*\n")

    pay_rows = []
    for e in target_employees:
        nomi = nx.get_title(e, "Ism") or "?"
        turi = nx.get_select(e, "Maosh turi")
        kirim, chiqim, davr_boshi, davr_oxiri = _moliya_period_totals(e)
        davr = f"{davr_boshi.strftime('%d.%m')} – {davr_oxiri.strftime('%d.%m')}"
        # "Kredit" — to'lanmagan, davrlar osha jamg'arilib boruvchi umumiy qarz. To'lovlar
        # allaqachon Kreditdan ayirilgan bo'ladi (to'lov qilingan zahoti), shuning uchun bu
        # yerda "chiqim"ni yana ayirish shart emas — faqat "Kunlik" turi uchun hali
        # bankvordan o'tmagan joriy davr jamg'armasi ustiga qo'shiladi (real vaqtli ko'rinish).
        kredit_hozir = nx.get_number(e, "Kredit") or 0
        balans = kredit_hozir + kirim if turi == "Kunlik (oylik summadan)" else kredit_hozir
        qoshimcha = ""
        if turi == "Vazifa boshiga":
            summa = nx.get_number(e, "Maosh summasi") or 0
            maqsad = nx.get_number(e, "Maosh maqsad soni") or 0
            if summa and maqsad:
                bajarilgan = round(kirim / (summa / maqsad))
                qoshimcha = f", {bajarilgan:g}/{maqsad:g} ish (bu davr)"
        lines.append(
            f"👤 *{nomi}*: {_format_som(balans)}\n"
            f"   (💳 Kredit: {_format_som(kredit_hozir)}, joriy davr ({davr}) jamg'armasi: {_format_som(kirim)}{qoshimcha})"
        )
        if is_admin_view:
            pay_rows.append([
                InlineKeyboardButton(f"💵 {nomi}ga to'lov", callback_data=f"pay_emp:{e['id']}"),
                InlineKeyboardButton("🪙 Avans", callback_data=f"advance_emp:{e['id']}"),
            ])
            if turi == "Vazifa boshiga":
                pay_rows.append([
                    InlineKeyboardButton(f"✅ {nomi}ga bajarilgan ish qo'shish", callback_data=f"work_emp:{e['id']}")
                ])

    pay_rows = action_rows + pay_rows

    if is_admin_view and pay_rows:
        pay_rows.append([InlineKeyboardButton("✏️ Stavkalarni o'zgartirish", callback_data="rate_change:yes")])

    keyboard = InlineKeyboardMarkup(pay_rows) if pay_rows else None
    await bot.send_message(chat_id=chat_id, text="\n\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)


@require_auth
async def moliya(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _do_moliya(context.bot, update.effective_chat.id)


# ----------------------------------------------------------------------------
# 📊 Faoliyat — tanlangan vaqt oralig'ida kim nima ish qilgani (admin)
# ----------------------------------------------------------------------------

def _faoliyat_range_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📅 Bugun", callback_data="faoliyat_range:bugun"),
            InlineKeyboardButton("📅 Kecha", callback_data="faoliyat_range:kecha"),
        ],
        [
            InlineKeyboardButton("📅 Bu hafta", callback_data="faoliyat_range:hafta"),
            InlineKeyboardButton("📅 Oxirgi 7 kun", callback_data="faoliyat_range:7kun"),
        ],
        [InlineKeyboardButton("📅 Bu oy", callback_data="faoliyat_range:oy")],
        [InlineKeyboardButton("✏️ Boshqa oraliq (sana kiritish)", callback_data="faoliyat_range:custom")],
    ])


async def _do_faoliyat_report(bot, chat_id, start: date, end: date) -> None:
    """[start, end] oralig'ida (ikkalasi ham kiritilgan) har bir xodim nima ish qilganini yig'ib chiqaradi:
    - DS_VAZIFALAR: "Bajarildi sanasi" shu oraliqda bo'lgan, Holati=Done vazifalar (Mas'ul bo'yicha guruhlangan).
    - DS_MOLIYA: "Kategoriya"=Ish haqi, "Sana" shu oraliqda bo'lgan kirim yozuvlari (Xodim bo'yicha guruhlangan;
      bu yerga "Vazifa boshiga" maoshli xodimlarning har bir bajargan ishi va admin qo'lda kiritgan ishlar kiradi)."""
    start_iso, end_iso = start.isoformat(), end.isoformat()

    try:
        employees = nx.query_data_source(nx.DS_XODIMLAR)
    except Exception:
        logger.exception("Faoliyat uchun xodimlarni olishda xatolik")
        employees = []
    emp_name = {e["id"]: (nx.get_title(e, "Ism") or "Noma'lum") for e in employees}

    try:
        vazifalar = nx.query_data_source(
            nx.DS_VAZIFALAR,
            filter_obj={
                "and": [
                    {"property": "Holati", "status": {"equals": "Done"}},
                    {"property": "Bajarildi sanasi", "date": {"on_or_after": start_iso}},
                    {"property": "Bajarildi sanasi", "date": {"on_or_before": end_iso}},
                ]
            },
            page_size=100,
        )
    except Exception:
        logger.exception("Faoliyat uchun vazifalarni olishda xatolik")
        vazifalar = []

    try:
        moliya_yozuvlari = nx.query_data_source(
            nx.DS_MOLIYA,
            filter_obj={
                "and": [
                    {"property": "Turi", "select": {"equals": "Kirim"}},
                    {"property": "Kategoriya", "select": {"equals": "Ish haqi"}},
                    {"property": "Sana", "date": {"on_or_after": start_iso}},
                    {"property": "Sana", "date": {"on_or_before": end_iso}},
                ]
            },
            page_size=100,
        )
    except Exception:
        logger.exception("Faoliyat uchun moliya yozuvlarini olishda xatolik")
        moliya_yozuvlari = []

    # emp_id -> {"vazifalar": [(sana, nomi)], "ishlar": [(sana, izoh, summa)]}
    by_emp: dict[str, dict] = {}

    for v in vazifalar:
        nomi = nx.get_title(v, "Vazifa") or "?"
        sana = nx.get_date(v, "Bajarildi sanasi") or ""
        for emp_id in nx.get_relation_ids(v, "Mas'ul"):
            by_emp.setdefault(emp_id, {"vazifalar": [], "ishlar": []})
            by_emp[emp_id]["vazifalar"].append((sana[:10], nomi))

    for m in moliya_yozuvlari:
        izoh = nx.get_rich_text(m, "Izoh") or nx.get_title(m, "Nomi") or "ish"
        sana = nx.get_date(m, "Sana") or ""
        summa = nx.get_number(m, "Summa") or 0
        for emp_id in nx.get_relation_ids(m, "Xodim"):
            by_emp.setdefault(emp_id, {"vazifalar": [], "ishlar": []})
            by_emp[emp_id]["ishlar"].append((sana[:10], izoh, summa))

    davr_str = f"{start.strftime('%d.%m.%Y')} – {end.strftime('%d.%m.%Y')}" if start != end else start.strftime("%d.%m.%Y")

    if not by_emp:
        await bot.send_message(
            chat_id=chat_id,
            text=f"📊 *Faoliyat: {davr_str}*\n\nBu oraliqda hech qanday bajarilgan ish qayd etilmagan.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    lines = [f"📊 *Faoliyat: {davr_str}*"]
    for emp_id, data in sorted(by_emp.items(), key=lambda kv: emp_name.get(kv[0], "")):
        nomi = emp_name.get(emp_id, "Noma'lum xodim")
        bo_lim = [f"\n👤 *{nomi}*"]
        if data["vazifalar"]:
            bo_lim.append(f"✅ Bajarilgan vazifalar ({len(data['vazifalar'])}):")
            for sana, vnomi in sorted(data["vazifalar"]):
                sana_disp = date.fromisoformat(sana).strftime("%d.%m") if sana else "?"
                bo_lim.append(f"   • {vnomi} — {sana_disp}")
        if data["ishlar"]:
            jami = sum(s for _, _, s in data["ishlar"])
            bo_lim.append(f"💰 Ish haqi yozuvlari ({len(data['ishlar'])} ta, jami {_format_som(jami)}):")
            for sana, izoh, summa in sorted(data["ishlar"]):
                sana_disp = date.fromisoformat(sana).strftime("%d.%m") if sana else "?"
                bo_lim.append(f"   • {sana_disp}: {izoh} — {_format_som(summa)}")
        lines.append("\n".join(bo_lim))

    matn = "\n".join(lines)
    # Telegram xabar uzunligi chegarasidan (4096) himoya
    for i in range(0, len(matn), 3500):
        await bot.send_message(chat_id=chat_id, text=matn[i:i + 3500], parse_mode=ParseMode.MARKDOWN)


@require_auth
async def faoliyat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not (ADMIN_CHAT_ID and str(chat_id) == str(ADMIN_CHAT_ID)):
        await update.message.reply_text("Bu bo'lim faqat admin uchun.")
        return
    await update.message.reply_text(
        "📊 Qaysi vaqt oralig'idagi faoliyatni ko'rmoqchisiz?",
        reply_markup=_faoliyat_range_keyboard(),
    )


# ----------------------------------------------------------------------------
# 📁 Loyihalar — ro'yxat, pauza/faollashtirish, o'chirish (arxivlash)
# ----------------------------------------------------------------------------

_HOLATI_EMOJI = {"Faol": "✅", "Pauzada": "⏸", "Arxivlangan": "🗑"}


async def _do_loyihalar_menu(bot, chat_id) -> None:
    if not (ADMIN_CHAT_ID and str(chat_id) == str(ADMIN_CHAT_ID)):
        await bot.send_message(chat_id=chat_id, text="Bu bo'lim faqat admin uchun.")
        return

    try:
        loyihalar = nx.query_data_source(nx.DS_LOYIHALAR, page_size=100)
    except Exception:
        logger.exception("Loyihalarni olishda xatolik (loyihalar menyu)")
        await bot.send_message(chat_id=chat_id, text="Xatolik yuz berdi.")
        return

    if not loyihalar:
        await bot.send_message(chat_id=chat_id, text="Hali hech qanday loyiha qo'shilmagan.")
        return

    # Faol/Pauzada/Arxivlangan loyihalar aralashib ketmasligi uchun ALOHIDA bo'limlarga
    # ajratib ko'rsatiladi — birinchi navbatda FAOL loyihalar chiqadi.
    guruhlar = {"Faol": [], "Pauzada": [], "Arxivlangan": []}
    for l in loyihalar:
        holati = nx.get_select(l, "Holati") or "Faol"
        guruhlar.setdefault(holati, []).append(l)

    rows = []
    sarlavhalar = {"Faol": "✅ Faol loyihalar", "Pauzada": "⏸ Pauzadagi loyihalar", "Arxivlangan": "🗑 To'xtatilgan (arxivlangan) loyihalar"}
    for holati in ("Faol", "Pauzada", "Arxivlangan"):
        guruh = guruhlar.get(holati, [])
        if not guruh:
            continue
        rows.append([InlineKeyboardButton(f"— {sarlavhalar[holati]} —", callback_data="noop")])
        for l in guruh:
            nomi = nx.get_title(l, "Loyiha") or "?"
            emoji = _HOLATI_EMOJI.get(holati, "•")
            rows.append([InlineKeyboardButton(f"{emoji} {nomi}", callback_data=f"loyiha_view:{l['id']}")])

    await bot.send_message(
        chat_id=chat_id, text="📁 Loyihalar — boshqarish uchun birini tanlang:", reply_markup=InlineKeyboardMarkup(rows)
    )


@require_auth
async def loyihalar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _do_loyihalar_menu(context.bot, update.effective_chat.id)


def _loyiha_detail_keyboard(page_id: str, holati: str) -> InlineKeyboardMarkup:
    rows = []
    if holati == "Pauzada":
        rows.append([InlineKeyboardButton("▶️ Qayta faollashtirish", callback_data=f"loyiha_resume:{page_id}")])
    else:
        rows.append([InlineKeyboardButton("⏸ Pauzaga qo'yish", callback_data=f"loyiha_pause:{page_id}")])
    rows.append([InlineKeyboardButton("🗑 O'chirish", callback_data=f"loyiha_delcheck:{page_id}")])
    rows.append([InlineKeyboardButton("⬅️ Loyihalar ro'yxatiga qaytish", callback_data="menu:loyihalar")])
    return InlineKeyboardMarkup(rows)


async def _send_loyiha_detail(bot, chat_id, page_id: str, edit_query=None) -> None:
    try:
        page = nx.get_page(page_id)
    except Exception:
        logger.exception("Loyihani olishda xatolik (detail)")
        await bot.send_message(chat_id=chat_id, text="⚠️ Loyihani topib bo'lmadi.")
        return

    nomi = nx.get_title(page, "Loyiha") or "?"
    holati = nx.get_select(page, "Holati") or "Faol"
    kanal = nx.get_select(page, "Bog'liq kanal") or "—"
    boshlanish = nx.get_date(page, "Boshlanish sanasi")
    reels_t = nx.get_number(page, "Reels target") or 0
    reels_d = nx.get_number(page, "Reels bajarildi") or 0
    video_t = nx.get_number(page, "Target video soni") or 0
    video_d = nx.get_number(page, "Target video bajarildi") or 0
    post_t = nx.get_number(page, "Telegram post target") or 0
    obuna_t = nx.get_number(page, "Obunachi target") or 0
    obuna_d = nx.get_number(page, "Obunachi hozirgi") or 0
    tolov_turi = nx.get_select(page, "To'lov turi") or "belgilanmagan"
    tolov_summasi = nx.get_number(page, "To'lov summasi") or 0
    joriy_debit = nx.get_number(page, "Debit") or 0

    post_d = 0
    if kanal and kanal != "—":
        try:
            joylangan_postlar = nx.query_data_source(
                nx.DS_KONTENT_REJA, filter_obj={"property": "Status", "select": {"equals": "Joylandi"}}
            )
            post_d = sum(1 for p in joylangan_postlar if nx.get_select(p, "Kanal") == kanal)
        except Exception:
            logger.exception("TG postlarni sanashda xatolik (loyiha detail)")

    if boshlanish:
        try:
            boshlanish_str = date.fromisoformat(boshlanish[:10]).strftime("%d.%m.%Y")
        except ValueError:
            boshlanish_str = boshlanish
    else:
        boshlanish_str = "belgilanmagan"

    text = (
        f"📁 *{nomi}*\n"
        f"Holati: {_HOLATI_EMOJI.get(holati, '')} {holati}\n"
        f"Kanal: {kanal}\n"
        f"📅 Boshlangan: {boshlanish_str}\n\n"
        f"🎬 Reels: {int(reels_d)}/{int(reels_t)}\n"
        f"🎯 Target: {int(video_d)}/{int(video_t)}\n"
        f"📝 TG post: {int(post_d)}/{int(post_t)}\n"
        f"👥 Obunachi: {int(obuna_d)}/{int(obuna_t) if obuna_t else '—'}\n\n"
        f"💰 To'lov: {tolov_turi}"
        + (f" — {_format_som(tolov_summasi)}" if tolov_summasi else "")
        + (f"\n💳 Debit (mandan qarzdor): {_format_som(joriy_debit)}" if joriy_debit else "")
    )
    keyboard = _loyiha_detail_keyboard(page_id, holati)

    if edit_query is not None:
        try:
            await edit_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
            return
        except Exception:
            pass
    await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)


_LOYIHA_TURI_LABELS = {"target": "Target", "media": "Media", "aralash": "Aralash"}


async def _finalize_new_loyiha(bot, chat_id, new_loyiha: dict) -> None:
    """/yangiloyiha oqimi oxirida (to'lov turi/summasi kiritilgan yoki o'tkazib yuborilgandan
    keyin) Loyihalar bazasiga yangi qatorni yozadi."""
    properties = {
        "Loyiha": {"title": [{"text": {"content": new_loyiha["nomi"]}}]},
        "Oy": {"rich_text": [{"text": {"content": _current_month_str()}}]},
        "Reels target": {"number": new_loyiha.get("reels_target")},
        "Reels bajarildi": {"number": 0},
        "Target video soni": {"number": new_loyiha.get("video_target")},
        "Target video bajarildi": {"number": 0},
        "Telegram post target": {"number": new_loyiha.get("post_target")},
        "Obunachi target": {"number": 0},
        "Obunachi hozirgi": {"number": 0},
        "Holati": {"select": {"name": "Faol"}},
        "Boshlanish sanasi": {"date": {"start": new_loyiha.get("boshlanish_sanasi") or _tashkent_today().isoformat()}},
        "Loyiha turi": {"select": {"name": _LOYIHA_TURI_LABELS.get(new_loyiha.get("loyiha_turi"), "Media")}},
    }
    kanal = new_loyiha.get("kanal")
    if kanal:
        properties["Bog'liq kanal"] = {"select": {"name": kanal}}
    target_narxi = new_loyiha.get("target_narxi")
    if target_narxi:
        properties["Target narxi"] = {"number": target_narxi}

    tolov_turi = new_loyiha.get("tolov_turi")
    tolov_summasi = new_loyiha.get("tolov_summasi")
    if tolov_turi:
        properties["To'lov turi"] = {"select": {"name": tolov_turi}}
    if tolov_summasi is not None:
        properties["To'lov summasi"] = {"number": tolov_summasi}

    tolov_izoh = ""
    if tolov_turi == "Video/Reels boshiga":
        tolov_izoh = f"\n💰 To'lov: har reels/video uchun {_format_som(tolov_summasi or 0)} (avtomatik hisoblanadi)"
    elif tolov_turi == "Oylik (fixed)":
        tolov_izoh = f"\n💰 To'lov: oyiga {_format_som(tolov_summasi or 0)} (fixed)"
        # MUHIM: agar shu oy uchun "Boshlanish sanasi" kuni ALLAQACHON O'TIB KETGAN bo'lsa
        # (masalan bugun 20-sana-yu, hisob kuni 10 bo'lsa), avtomatik oylik hisob-kitob
        # (scheduled_loyiha_billing) faqat KEYINGI oyning shu kunida ishga tushadi — birinchi
        # oy uchun Debit HECH QACHON qo'yilmay qolib ketadi (bu xatolik uchinchi marta
        # takrorlandi — ARK Hospital, dr.Uktam, NSH kurs). Shuning oldini olish uchun, agar
        # hisob kuni bugungidan oldin bo'lsa, birinchi oylik summa darhol Debitga qo'shiladi.
        # Agar hisob kuni bugun yoki keyinroq bo'lsa — bunga hojat yo'q, chunki avtomatik
        # job baribir shu oy ichida (ikki marta hisoblanmasin uchun) o'zi qo'shadi.
        try:
            boshlanish_str = new_loyiha.get("boshlanish_sanasi") or _tashkent_today().isoformat()
            boshlanish_kuni = date.fromisoformat(boshlanish_str[:10]).day
        except ValueError:
            boshlanish_kuni = _tashkent_today().day
        if boshlanish_kuni < _tashkent_today().day:
            properties["Debit"] = {"number": tolov_summasi}
            tolov_izoh += f"\n💳 Bu oy uchun hisob kuni allaqachon o'tgani sababli, Debitga darhol qo'shildi: {_format_som(tolov_summasi or 0)}"

    try:
        nx.create_page(nx.DS_LOYIHALAR, properties)
        await bot.send_message(
            chat_id=chat_id,
            text=f"✅ Yangi loyiha qo'shildi: *{new_loyiha['nomi']}* ({_current_month_str()}){tolov_izoh}",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:
        logger.exception("Yangi loyiha yaratishda xatolik")
        await bot.send_message(chat_id=chat_id, text="⚠️ Loyihani yaratib bo'lmadi.")


@require_auth
async def yangiloyiha(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Yangi mijoz-loyihani bosqichma-bosqich (nomi -> reels target -> video target ->
    telegram post target -> kanal -> to'lov turi/summasi) qo'shish oqimini boshlaydi. Faqat admin uchun."""
    chat_id = update.effective_chat.id
    if not (ADMIN_CHAT_ID and str(chat_id) == str(ADMIN_CHAT_ID)):
        await update.message.reply_text("⛔ Bu buyruq faqat admin uchun.")
        return
    context.user_data["new_loyiha"] = {"stage": "nomi"}
    await update.message.reply_text("🆕 Yangi loyiha nomini yozing (masalan: Yangi Klinika):")


def _income_project_picker_keyboard():
    """Loyihadan tushgan pulni qaysi loyihaga yozishni tanlash uchun tugmalar (+ 'Boshqa')."""
    month = _current_month_str()
    try:
        loyihalar = nx.query_data_source(
            nx.DS_LOYIHALAR, filter_obj={"property": "Oy", "rich_text": {"equals": month}}
        )
    except Exception:
        logger.exception("Loyihalarni olishda xatolik (kirim)")
        loyihalar = []

    rows = []
    for l in loyihalar:
        nomi = nx.get_title(l, "Loyiha") or "?"
        rows.append([InlineKeyboardButton(f"📁 {nomi}", callback_data=f"kirim_proj:{l['id']}")])
    rows.append([InlineKeyboardButton("🗂 Boshqa (loyihasiz)", callback_data="kirim_proj:none")])
    return InlineKeyboardMarkup(rows)


async def _do_kirim_menu(bot, chat_id) -> None:
    if not (ADMIN_CHAT_ID and str(chat_id) == str(ADMIN_CHAT_ID)):
        await bot.send_message(chat_id=chat_id, text="⛔ Bu bo'lim faqat admin uchun.")
        return
    await bot.send_message(
        chat_id=chat_id,
        text="➕ Bu tushgan pul qaysi loyihaga tegishli?",
        reply_markup=_income_project_picker_keyboard(),
    )


def _accrue_task_payment(task_page: dict) -> None:
    """'Vazifa boshiga' maosh turidagi xodimga, vazifa bajarilganda mos summani Moliya'ga Kirim sifatida yozadi."""
    emp_ids = nx.get_relation_ids(task_page, "Mas'ul")
    vazifa_nomi = nx.get_title(task_page, "Vazifa") or ""
    for emp_id in emp_ids:
        try:
            employee = nx.get_page(emp_id)
        except Exception:
            logger.exception("Vazifa haqi uchun xodimni olishda xatolik")
            continue

        turi = nx.get_select(employee, "Maosh turi")
        if turi != "Vazifa boshiga":
            continue

        summa = nx.get_number(employee, "Maosh summasi") or 0
        maqsad = nx.get_number(employee, "Maosh maqsad soni") or 0
        if not summa or not maqsad:
            continue

        per_task = summa / maqsad
        nomi = nx.get_title(employee, "Ism") or "Xodim"
        try:
            nx.create_page(nx.DS_MOLIYA, {
                "Nomi": {"title": [{"text": {"content": f"{nomi} — vazifa haqi"}}]},
                "Turi": {"select": {"name": "Kirim"}},
                "Kategoriya": {"select": {"name": "Ish haqi"}},
                "Summa": {"number": per_task},
                "Sana": {"date": {"start": _tashkent_today().isoformat()}},
                "Xodim": {"relation": [{"id": emp_id}]},
                "Izoh": {"rich_text": [{"text": {"content": vazifa_nomi}}]},
            })
        except Exception:
            logger.exception(f"{nomi} uchun vazifa haqini yozishda xatolik")
            continue

        # Ishlagan haqi to'lanmaguncha "Kredit" (biznesning xodimga qarzi) sifatida
        # jamg'arilib boradi — davr (Hisob kuni) o'zgarganda YO'QOLIB QOLMASIN.
        try:
            joriy_kredit = nx.get_number(employee, "Kredit") or 0
            nx.update_page_property(emp_id, {"Kredit": {"number": joriy_kredit + per_task}})
        except Exception:
            logger.exception(f"{nomi} uchun Kreditga qo'shishda xatolik")


# Eslatma: avval "Kunlik (oylik summadan)" turidagi xodimlarga har kuni tunda (00:05'da)
# alohida bir cron-job orqali Moliya'ga Kirim yozuvi qo'shilardi. Bu botning aynan o'sha
# daqiqada ishlab turishini talab qilardi (terminalda test qilinayotganda deyarli hech
# qachon to'g'ri kelmasdi — shuning uchun balans "yangilanmayotganday" ko'rinardi).
# Endi bu turdagi xodimlar uchun jamg'arilgan summa _moliya_period_totals() ichida REAL
# VAQTDA, xodimning shaxsiy "Hisob kuni" davri (masalan 11-dan 10-gacha) bo'yicha
# hisoblanadi, alohida cron-job shart emas.


def _salary_employee_picker_keyboard():
    try:
        employees = nx.query_data_source(nx.DS_XODIMLAR)
    except Exception:
        logger.exception("Xodimlarni olishda xatolik (stavka)")
        return None
    rows = []
    for e in employees:
        if not nx.get_select(e, "Maosh turi"):
            continue
        nomi = nx.get_title(e, "Ism") or "?"
        rows.append([InlineKeyboardButton(f"✏️ {nomi}", callback_data=f"rate_emp:{e['id']}")])
    return InlineKeyboardMarkup(rows) if rows else None


async def scheduled_settlement_check(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Har kuni ishlaydi: kimning shaxsiy 'Hisob kuni'si bugunga to'g'ri kelsa, o'sha xodim uchun
    adminga balans hisobotini yuboradi va stavkani o'zgartirish/to'lov/avans tugmalarini beradi.
    Masalan: Hasan — har oyning 10-sanasi, Mubina — har oyning 20-sanasi."""
    if not ADMIN_CHAT_ID:
        return
    try:
        employees = nx.query_data_source(nx.DS_XODIMLAR)
    except Exception:
        logger.exception("Hisob kuni tekshiruvi uchun xodimlarni olishda xatolik")
        return

    today = _tashkent_today()

    for e in employees:
        turi = nx.get_select(e, "Maosh turi")
        if not turi:
            continue
        hisob_kuni = nx.get_number(e, "Hisob kuni")
        if not hisob_kuni or int(hisob_kuni) != today.day:
            continue

        nomi = nx.get_title(e, "Ism") or "?"
        summa = nx.get_number(e, "Maosh summasi") or 0
        kirim, chiqim, davr_boshi, davr_oxiri = _moliya_period_totals(e, today)
        davr = f"{davr_boshi.strftime('%d.%m')} – {davr_oxiri.strftime('%d.%m')}"

        # "Kunlik (oylik summadan)" turida davr ichidagi jamg'arilgan summa Moliya'ga
        # alohida qator sifatida yozilmaydi (real vaqtda hisoblanadi) — shu sabab, agar
        # to'lanmasa, davr almashganda yo'qolib qolardi. Shu yerda uni doimiy "Kredit"ga
        # qo'shib qo'yamiz, shunda to'lanmaguncha hisobda qolaveradi. ("Vazifa boshiga"
        # turi buni allaqachon _accrue_task_payment orqali har bir bajarilgan ishda oladi.)
        if turi == "Kunlik (oylik summadan)" and kirim:
            try:
                joriy_kredit = nx.get_number(e, "Kredit") or 0
                nx.update_page_property(e["id"], {"Kredit": {"number": joriy_kredit + kirim}})
            except Exception:
                logger.exception(f"{nomi} uchun davr yakunida Kreditga qo'shishda xatolik")

        try:
            yangilangan_emp = nx.get_page(e["id"])
            umumiy_kredit = nx.get_number(yangilangan_emp, "Kredit") or 0
        except Exception:
            logger.exception(f"{nomi} uchun yangilangan Kreditni olishda xatolik")
            umumiy_kredit = kirim - chiqim

        lines = [f"🗓 Bugun *{nomi}* uchun hisob-kitob kuni ({int(hisob_kuni)}-sana).\n"]
        if turi == "Vazifa boshiga":
            maqsad = nx.get_number(e, "Maosh maqsad soni") or 0
            lines.append(f"Joriy stavka: {_format_som(summa)} / {maqsad:g} ish")
        else:
            lines.append(f"Joriy stavka: {_format_som(summa)} / oy")
        lines.append(f"\n💳 Jami Kredit (to'lanmagan, jamg'arilgan): {_format_som(umumiy_kredit)}")
        lines.append(f"(bu davr — {davr} — bo'yicha jamg'arilgan: {_format_som(kirim)}, to'langan: {_format_som(chiqim)})")

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💵 To'lov qildim", callback_data=f"pay_emp:{e['id']}"),
                InlineKeyboardButton("🪙 Avans berdim", callback_data=f"advance_emp:{e['id']}"),
            ],
            [
                InlineKeyboardButton("✏️ Stavkani o'zgartirish", callback_data=f"rate_emp:{e['id']}"),
            ],
        ])
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID, text="\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard
            )
        except Exception:
            logger.exception(f"{nomi} uchun hisob-kitob xabarini yuborishda xatolik")


# Bo'lib to'lanadigan loyihalarda (checkbox yoqilgan) ikkinchi 50% birinchi to'lov kunidan
# necha kun keyin hisoblanishi (masalan 21-sana + 5 kun = 26-sana).
SPLIT_BILLING_GAP_DAYS = int(os.environ.get("SPLIT_BILLING_GAP_DAYS", "5"))


async def scheduled_loyiha_billing(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Har kuni ishlaydi: "Oylik (fixed)" turidagi Faol loyihalar orasida, "Boshlanish sanasi"ning
    kun raqami bugunga to'g'ri kelsa, o'sha loyihaning "To'lov summasi"si avtomatik "Debit"ga
    qo'shiladi (yangi oy uchun mijoz qarzi) va adminga xabar beriladi.

    Agar "Bo'lib tolash 2x50%" belgilangan bo'lsa, to'lov 2 qismga bo'linadi: birinchi 50%
    "Boshlanish sanasi" kunida, qolgan 50% shu kundan SPLIT_BILLING_GAP_DAYS kun keyin."""
    if not ADMIN_CHAT_ID:
        return
    try:
        loyihalar = nx.query_data_source(
            nx.DS_LOYIHALAR, filter_obj={"property": "Holati", "select": {"equals": "Faol"}}
        )
    except Exception:
        logger.exception("Oylik hisob-kitob uchun loyihalarni olishda xatolik")
        return

    today = _tashkent_today()

    for page in loyihalar:
        tolov_turi = nx.get_select(page, "To'lov turi")
        if tolov_turi != "Oylik (fixed)":
            continue
        tolov_summasi = nx.get_number(page, "To'lov summasi") or 0
        if not tolov_summasi:
            continue
        boshlanish = nx.get_date(page, "Boshlanish sanasi")
        if not boshlanish:
            continue
        try:
            boshlanish_kuni = date.fromisoformat(boshlanish[:10]).day
        except ValueError:
            continue

        bolib_tolash = nx.get_checkbox(page, "Bolib tolash 2x50%")
        if bolib_tolash:
            ikkinchi_kuni = boshlanish_kuni + SPLIT_BILLING_GAP_DAYS
            if today.day == boshlanish_kuni:
                summa = round(tolov_summasi / 2)
                izoh = f"1-qism (50%), {today.day}-sana"
            elif today.day == ikkinchi_kuni:
                summa = tolov_summasi - round(tolov_summasi / 2)
                izoh = f"2-qism (50%), {today.day}-sana"
            else:
                continue
        else:
            if boshlanish_kuni != today.day:
                continue
            summa = tolov_summasi
            izoh = f"to'liq, {today.day}-sana"

        nomi = nx.get_title(page, "Loyiha") or "?"
        joriy_debit = nx.get_number(page, "Debit") or 0
        yangi_debit = joriy_debit + summa
        try:
            nx.update_page_property(page["id"], {"Debit": {"number": yangi_debit}})
        except Exception:
            logger.exception(f"{nomi} uchun oylik Debit qo'shishda xatolik")
            continue

        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    f"🗓 *{nomi}* — oylik hisob-kitob ({izoh}).\n"
                    f"💳 Debitga qo'shildi: {_format_som(summa)} (jami Debit: {_format_som(yangi_debit)}).\n"
                    f"Pul kelganda \"➕ Kirim qo'shish\" orqali qayd eting."
                ),
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            logger.exception(f"{nomi} uchun oylik hisob-kitob xabarini yuborishda xatolik")


# ----------------------------------------------------------------------------
# Tugma bosilganda (menu:..., vazifa_emp:..., vazifa_date:..., reels_proj:...,
# comment:..., pay_emp:..., rate_change:..., rate_emp:..., approve / reject / publish / done)
# ----------------------------------------------------------------------------

@require_auth
async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    action, payload = query.data.split(":", 1)
    chat_id = query.message.chat_id

    if action == "noop":
        return

    if action == "debit_confirm":
        data = context.user_data.pop("pending_debit_confirm", None)
        if not data:
            await query.edit_message_text(query.message.text + "\n\n⚠️ Sessiya eskirgan, o'zgarish qilinmadi.")
            return
        if payload == "no":
            await query.edit_message_text(query.message.text + "\n\n👍 Tushunarli, Debit o'zgarishsiz qoldi.")
            return
        try:
            proj_page = nx.get_page(data["project_id"])
            joriy_debit = nx.get_number(proj_page, "Debit") or 0
            yangi_debit = max(0, joriy_debit - data["summa"])
            nx.update_page_property(data["project_id"], {"Debit": {"number": yangi_debit}})
            await query.edit_message_text(
                query.message.text + f"\n\n💳 Debitdan ayirildi. Qolgan Debit: {_format_som(yangi_debit)}"
            )
        except Exception:
            logger.exception("Debit tasdiqlashda xatolik")
            await query.edit_message_text(query.message.text + "\n\n⚠️ Debitni yangilab bo'lmadi.")
        return

    if action == "faoliyat_range":
        if not (ADMIN_CHAT_ID and str(chat_id) == str(ADMIN_CHAT_ID)):
            await context.bot.send_message(chat_id=chat_id, text="⛔ Bu bo'lim faqat admin uchun.")
            return
        today = _tashkent_today()
        if payload == "bugun":
            start = end = today
        elif payload == "kecha":
            start = end = today - timedelta(days=1)
        elif payload == "hafta":
            start = today - timedelta(days=today.weekday())
            end = today
        elif payload == "7kun":
            start = today - timedelta(days=6)
            end = today
        elif payload == "oy":
            start = today.replace(day=1)
            end = today
        elif payload == "custom":
            context.user_data["pending_faoliyat_range"] = True
            await query.edit_message_text(
                "✏️ Sanalarni kiriting: BOSHLANISH-SANASI TUGASH-SANASI\n"
                "Masalan: 01.08.2026 15.08.2026"
            )
            return
        else:
            return
        await query.edit_message_text(f"⏳ {start.strftime('%d.%m.%Y')} – {end.strftime('%d.%m.%Y')} uchun yig'ilmoqda...")
        await _do_faoliyat_report(context.bot, chat_id, start, end)
        return

    if action == "menu" and payload == "yangiloyiha":
        if not (ADMIN_CHAT_ID and str(chat_id) == str(ADMIN_CHAT_ID)):
            await context.bot.send_message(chat_id=chat_id, text="⛔ Bu bo'lim faqat admin uchun.")
            return
        context.user_data["new_loyiha"] = {"stage": "nomi"}
        await context.bot.send_message(chat_id=chat_id, text="🆕 Yangi loyiha nomini yozing (masalan: Yangi Klinika):")
        return

    if action == "menu":
        dispatch = {
            "vazifa": _do_vazifa_menu,
            "vazifalarim": _do_vazifalarim,
            "jamoa": _do_jamoa_vazifalar,
            "hisobot": _do_hisobot,
            "oylik": _do_oylik,
            "kontent": _do_kontent,
            "joylash": _do_joylash,
            "target": _do_target,
            "reels": _do_reels_menu,
            "moliya": _do_moliya,
            "kirim": _do_kirim_menu,
            "loyihalar": _do_loyihalar_menu,
            "target_hisobot": _do_target_hisobot_menu,
        }
        handler = dispatch.get(payload)
        if handler:
            await handler(context.bot, chat_id)
        return

    if action == "vazifa_emp":
        employee_id = payload
        try:
            employee = nx.get_page(employee_id)
            ism = nx.get_title(employee, "Ism") or "xodim"
        except Exception:
            logger.exception("Xodimni olishda xatolik")
            await query.edit_message_text("⚠️ Xodimni topib bo'lmadi.")
            return
        context.user_data["pending_vazifa_employee_id"] = employee_id
        context.user_data.pop("pending_vazifa_date", None)
        await query.edit_message_text(
            f"🗓 {ism} uchun vazifa muddatini tanlang:",
            reply_markup=_date_picker_keyboard(),
        )
        return

    if action == "vazifa_date":
        iso_date = payload
        employee_id = context.user_data.get("pending_vazifa_employee_id")
        if not employee_id:
            await query.edit_message_text("⚠️ Sessiya eskirgan. /vazifa deb qaytadan boshlang.")
            return
        context.user_data["pending_vazifa_date"] = iso_date
        sana_str = date.fromisoformat(iso_date).strftime("%d.%m.%Y")
        await query.edit_message_text(f"✏️ Endi vazifa matnini yozib yuboring (muddat: {sana_str}):")
        return

    if action == "reels_proj":
        project_id = payload
        try:
            proj = nx.get_page(project_id)
            nomi = nx.get_title(proj, "Loyiha") or "loyiha"
        except Exception:
            logger.exception("Loyihani olishda xatolik")
            await query.edit_message_text("⚠️ Loyihani topib bo'lmadi.")
            return
        context.user_data["pending_reels_project_id"] = project_id
        await query.edit_message_text(f"✏️ {nomi} uchun bugun nechta reels joylanganini raqam bilan yozing:")
        return

    if action == "target_hproj":
        if not (ADMIN_CHAT_ID and str(chat_id) == str(ADMIN_CHAT_ID)):
            await context.bot.send_message(chat_id=chat_id, text="Bu bo'lim faqat admin uchun.")
            return
        project_id = payload
        try:
            proj = nx.get_page(project_id)
            nomi = nx.get_title(proj, "Loyiha") or "loyiha"
            proj_turi = nx.get_select(proj, "Loyiha turi") or "Media"
        except Exception:
            logger.exception("Loyihani olishda xatolik (target hisobot)")
            await query.edit_message_text("⚠️ Loyihani topib bo'lmadi.")
            return
        await query.edit_message_text(
            f"🎯 {nomi} — nimani yangilaysiz?", reply_markup=_target_metric_keyboard(project_id, proj_turi)
        )
        return

    if action == "target_video":
        project_id = payload
        try:
            proj = nx.get_page(project_id)
            nomi = nx.get_title(proj, "Loyiha") or "loyiha"
            proj_turi = nx.get_select(proj, "Loyiha turi") or "Media"
        except Exception:
            logger.exception("Loyihani olishda xatolik (target video)")
            await query.edit_message_text("⚠️ Loyihani topib bo'lmadi.")
            return
        context.user_data["pending_target_video_project_id"] = project_id
        if proj_turi in ("Target", "Aralash"):
            await query.edit_message_text(f"✏️ {nomi} uchun bugun nechta target bajarilganini/yoqilganini raqam bilan yozing:")
        else:
            await query.edit_message_text(f"✏️ {nomi} uchun bugun nechta yangi video joylanganini raqam bilan yozing:")
        return

    if action == "target_obuna":
        project_id = payload
        try:
            proj = nx.get_page(project_id)
            nomi = nx.get_title(proj, "Loyiha") or "loyiha"
            joriy = nx.get_number(proj, "Obunachi hozirgi") or 0
        except Exception:
            logger.exception("Loyihani olishda xatolik (target obuna)")
            await query.edit_message_text("⚠️ Loyihani topib bo'lmadi.")
            return
        context.user_data["pending_target_obuna_project_id"] = project_id
        await query.edit_message_text(
            f"✏️ {nomi} uchun HOZIRGI JAMI obunachi/follower sonini yozing (hozircha: {int(joriy)}):"
        )
        return

    if action == "loyiha_view":
        if not (ADMIN_CHAT_ID and str(chat_id) == str(ADMIN_CHAT_ID)):
            await context.bot.send_message(chat_id=chat_id, text="Bu bo'lim faqat admin uchun.")
            return
        await _send_loyiha_detail(context.bot, chat_id, payload, edit_query=query)
        return

    if action == "loyiha_pause":
        if not (ADMIN_CHAT_ID and str(chat_id) == str(ADMIN_CHAT_ID)):
            await context.bot.send_message(chat_id=chat_id, text="Bu bo'lim faqat admin uchun.")
            return
        try:
            nx.update_page_property(payload, {"Holati": {"select": {"name": "Pauzada"}}})
        except Exception:
            logger.exception("Loyihani pauzaga qo'yishda xatolik")
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Pauzaga qo'yib bo'lmadi.")
            return
        await _send_loyiha_detail(context.bot, chat_id, payload, edit_query=query)
        return

    if action == "loyiha_resume":
        if not (ADMIN_CHAT_ID and str(chat_id) == str(ADMIN_CHAT_ID)):
            await context.bot.send_message(chat_id=chat_id, text="Bu bo'lim faqat admin uchun.")
            return
        try:
            nx.update_page_property(payload, {"Holati": {"select": {"name": "Faol"}}})
        except Exception:
            logger.exception("Loyihani faollashtirishda xatolik")
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Faollashtirib bo'lmadi.")
            return
        await _send_loyiha_detail(context.bot, chat_id, payload, edit_query=query)
        return

    if action == "loyiha_delcheck":
        if not (ADMIN_CHAT_ID and str(chat_id) == str(ADMIN_CHAT_ID)):
            await context.bot.send_message(chat_id=chat_id, text="Bu bo'lim faqat admin uchun.")
            return
        try:
            proj = nx.get_page(payload)
            nomi = nx.get_title(proj, "Loyiha") or "loyiha"
        except Exception:
            logger.exception("Loyihani olishda xatolik (delcheck)")
            await query.edit_message_text("⚠️ Loyihani topib bo'lmadi.")
            return
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Ha, o'chir", callback_data=f"loyiha_delconfirm:{payload}"),
            InlineKeyboardButton("❌ Bekor qilish", callback_data=f"loyiha_view:{payload}"),
        ]])
        await query.edit_message_text(
            f"❗️ *{nomi}* loyihasini butunlay o'chirmoqchimisiz?\n"
            f"(Notion'da arxivga ko'chiriladi — kerak bo'lsa u yerdan qaytarish mumkin)",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )
        return

    if action == "loyiha_delconfirm":
        if not (ADMIN_CHAT_ID and str(chat_id) == str(ADMIN_CHAT_ID)):
            await context.bot.send_message(chat_id=chat_id, text="Bu bo'lim faqat admin uchun.")
            return
        try:
            proj = nx.get_page(payload)
            nomi = nx.get_title(proj, "Loyiha") or "loyiha"
            nx.archive_page(payload)
        except Exception:
            logger.exception("Loyihani o'chirishda xatolik")
            await query.edit_message_text("⚠️ Loyihani o'chirib bo'lmadi.")
            return
        await query.edit_message_text(f"🗑 *{nomi}* o'chirildi (Notion arxiviga ko'chirildi).", parse_mode=ParseMode.MARKDOWN)
        return

    if action == "kontent_kanal":
        kanal = payload
        context.user_data["kontent_kanal"] = kanal
        try:
            await query.edit_message_text(f"📢 Kanal: {kanal}")
        except Exception:
            pass
        has_more = await _send_next_kontent_post(context.bot, chat_id, kanal)
        if not has_more:
            await context.bot.send_message(chat_id=chat_id, text=f"'{kanal}' uchun tasdiqlash kutayotgan post yo'q.")
            context.user_data.pop("kontent_kanal", None)
        return

    if action == "edit_kontent":
        page_id = payload
        context.user_data["pending_kontent_edit_page_id"] = page_id
        try:
            await context.bot.send_message(
                chat_id=chat_id, text="✏️ Post uchun yangi matnni yozing (butun 'Ssenariy/Matn' shu bilan almashtiriladi):"
            )
        except Exception:
            logger.exception("Tahrirlash so'rovini yuborishda xatolik")
        return

    if action == "gen_image":
        page_id = payload
        try:
            page = nx.get_page(page_id)
            nomi = nx.get_title(page, "Post nomi") or "Post"
            mavzu = nx.get_rich_text(page, "Mavzu")
            matn = nx.get_rich_text(page, "Ssenariy/Matn")
            kanal = nx.get_select(page, "Kanal") or "?"
        except Exception:
            logger.exception("Rasm yasash uchun postni olishda xatolik")
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Postni topib bo'lmadi.")
            return

        await context.bot.send_message(chat_id=chat_id, text=f"🎨 '{nomi}' uchun rasm yasalmoqda, biroz kuting...")
        try:
            prompt = _build_image_prompt(nomi, mavzu, matn, kanal)
            rasm_bytes = ox.generate_image(prompt)
            with open(_local_image_path(page_id), "wb") as f:
                f.write(rasm_bytes)
        except ox.OpenAINotConfigured:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Rasm generatsiyasi sozlanmagan — OPENAI_API_KEY muhit o'zgaruvchisi yo'q.",
            )
            return
        except Exception:
            logger.exception("OpenAI orqali rasm yasashda xatolik")
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Rasmni yasab bo'lmadi. Birozdan so'ng qayta urinib ko'ring.")
            return

        await context.bot.send_message(chat_id=chat_id, text="✅ Rasm tayyor:")
        await _send_kontent_post_message(context.bot, chat_id, page)
        return

    if action == "kirim_proj":
        if payload == "none":
            context.user_data["pending_income_project_id"] = "none"
            context.user_data["pending_income_project_name"] = "Boshqa"
            await query.edit_message_text("✏️ Summani raqam bilan yozing (masalan: 2000000):")
            return
        project_id = payload
        try:
            proj = nx.get_page(project_id)
            nomi = nx.get_title(proj, "Loyiha") or "loyiha"
        except Exception:
            logger.exception("Loyihani olishda xatolik (kirim)")
            await query.edit_message_text("⚠️ Loyihani topib bo'lmadi.")
            return
        context.user_data["pending_income_project_id"] = project_id
        context.user_data["pending_income_project_name"] = nomi
        await query.edit_message_text(f"✏️ {nomi} uchun tushgan summani raqam bilan yozing (masalan: 2000000):")
        return

    if action == "newloyiha_turi":
        new_loyiha = context.user_data.get("new_loyiha")
        if not new_loyiha or new_loyiha.get("stage") != "loyiha_turi":
            await query.edit_message_text("⚠️ Sessiya eskirgan. /yangiloyiha deb qaytadan boshlang.")
            return

        if payload == "target":
            new_loyiha["loyiha_turi"] = "target"
            new_loyiha["stage"] = "tolov_turi"
            await query.edit_message_text(
                "🎯 Target loyiha — reels/video/TG post/kanal so'ralmaydi.\n\n"
                "💰 Bu qanday to'lov qiladi? (\"Donasiga\" tanlasangiz, keyinchalik \"🎯 Target hisobot\" "
                "orqali har bajarilgan birlik uchun avtomatik hisoblanadi)",
                reply_markup=_new_loyiha_tolov_keyboard(),
            )
            return

        if payload == "aralash":
            new_loyiha["loyiha_turi"] = "aralash"
            new_loyiha["stage"] = "reels_video"
            await query.edit_message_text(
                "🔀 Aralash loyiha — ham video/reels, ham target (reklama) alohida-alohida "
                "kuzatiladi va alohida narxda hisoblanadi (chalkashib ketmasligi uchun).\n\n"
                "📹 Oylik nechta REELS VIDEO chiqishi kerak? Sonini yozing (masalan: 20).\n"
                "Kerak bo'lmasa — \"yo'q\" deb yozing:"
            )
            return

        # payload == "media"
        new_loyiha["loyiha_turi"] = "media"
        new_loyiha["stage"] = "reels_video"
        await query.edit_message_text(
            "📹 Oylik nechta REELS VIDEO chiqishi kerak? Sonini yozing (masalan: 20).\n"
            "Bu loyihada reels/video kuzatuvi kerak bo'lmasa — \"yo'q\" deb yozing:"
        )
        return

    if action == "newloyiha_kanal":
        new_loyiha = context.user_data.get("new_loyiha")
        if not new_loyiha or new_loyiha.get("stage") != "kanal":
            await query.edit_message_text("⚠️ Sessiya eskirgan. /yangiloyiha deb qaytadan boshlang.")
            return

        kanal = None
        if payload != "none":
            try:
                kanal = NEW_LOYIHA_CHANNELS[int(payload)]
            except (ValueError, IndexError):
                kanal = None
        if kanal:
            new_loyiha["kanal"] = kanal

        new_loyiha["stage"] = "tolov_turi"
        await query.edit_message_text(
            "💰 Bu loyiha qanday to'lov qiladi?",
            reply_markup=_new_loyiha_tolov_keyboard(),
        )
        return

    if action == "newloyiha_tolov":
        new_loyiha = context.user_data.get("new_loyiha")
        if not new_loyiha or new_loyiha.get("stage") != "tolov_turi":
            await query.edit_message_text("⚠️ Sessiya eskirgan. /yangiloyiha deb qaytadan boshlang.")
            return

        if payload == "yoq":
            await query.edit_message_text("💰 To'lov turi belgilanmadi (keyinroq Notion'dan qo'shishingiz mumkin).")
            await _finalize_new_loyiha(context.bot, chat_id, new_loyiha)
            context.user_data.pop("new_loyiha", None)
            return

        if payload == "video":
            new_loyiha["tolov_turi"] = "Video/Reels boshiga"
            new_loyiha["stage"] = "tolov_summasi"
            if new_loyiha.get("loyiha_turi") == "target":
                await query.edit_message_text("✏️ 1 ta target uchun necha so'm? Raqam bilan yozing (masalan: 150000):")
            else:
                await query.edit_message_text("✏️ Bitta reels/video uchun necha so'm? Raqam bilan yozing (masalan: 150000):")
            return

        if payload == "oylik":
            new_loyiha["tolov_turi"] = "Oylik (fixed)"
            new_loyiha["stage"] = "tolov_summasi"
            await query.edit_message_text("✏️ Oyiga jami necha so'm? Raqam bilan yozing (masalan: 3000000):")
            return
        return

    if action == "comment":
        page_id = payload
        context.user_data["pending_comment_page_id"] = page_id
        await context.bot.send_message(chat_id=chat_id, text="✏️ Izohingizni shu yerga oddiy xabar sifatida yozib yuboring:")
        return

    if action == "pay_emp":
        employee_id = payload
        try:
            employee = nx.get_page(employee_id)
            ism = nx.get_title(employee, "Ism") or "xodim"
        except Exception:
            logger.exception("To'lov uchun xodimni olishda xatolik")
            await query.edit_message_text("⚠️ Xodimni topib bo'lmadi.")
            return
        context.user_data["pending_payment_employee_id"] = employee_id
        await context.bot.send_message(
            chat_id=chat_id, text=f"✏️ {ism}ga to'langan summani raqam bilan yozing (masalan: 3000000):"
        )
        return

    if action == "advance_emp":
        employee_id = payload
        try:
            employee = nx.get_page(employee_id)
            ism = nx.get_title(employee, "Ism") or "xodim"
        except Exception:
            logger.exception("Avans uchun xodimni olishda xatolik")
            await query.edit_message_text("⚠️ Xodimni topib bo'lmadi.")
            return
        context.user_data["pending_advance_employee_id"] = employee_id
        await context.bot.send_message(
            chat_id=chat_id, text=f"✏️ {ism}ga bergan avans summasini raqam bilan yozing (masalan: 1000000):"
        )
        return

    if action == "work_emp":
        employee_id = payload
        try:
            employee = nx.get_page(employee_id)
            ism = nx.get_title(employee, "Ism") or "xodim"
        except Exception:
            logger.exception("Ish qo'shish uchun xodimni olishda xatolik")
            await query.edit_message_text("⚠️ Xodimni topib bo'lmadi.")
            return
        context.user_data["pending_work_employee_id"] = employee_id
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✏️ {ism} (botda vazifa sifatida qayd etilmagan, qo'lda hisoblanadigan ishlar uchun) "
            "necha ta YANGI ish (video) bajarganini raqam bilan yozing (masalan: 29):",
        )
        return

    if action == "rate_change":
        if payload == "no":
            await query.edit_message_text(query.message.text + "\n\n✅ Stavkalar o'zgarishsiz qoladi.")
            return
        keyboard = _salary_employee_picker_keyboard()
        if not keyboard:
            await query.edit_message_text("⚠️ Maosh stavkasi belgilangan xodim topilmadi.")
            return
        await query.edit_message_text("Kimning stavkasini o'zgartirasiz?", reply_markup=keyboard)
        return

    if action == "rate_emp":
        employee_id = payload
        try:
            employee = nx.get_page(employee_id)
            ism = nx.get_title(employee, "Ism") or "xodim"
            turi = nx.get_select(employee, "Maosh turi")
        except Exception:
            logger.exception("Stavka uchun xodimni olishda xatolik")
            await query.edit_message_text("⚠️ Xodimni topib bo'lmadi.")
            return
        context.user_data["pending_rate_employee_id"] = employee_id
        context.user_data["pending_rate_turi"] = turi
        context.user_data.pop("pending_rate_summa_temp", None)
        if turi == "Vazifa boshiga":
            await query.edit_message_text(f"✏️ {ism} uchun yangi umumiy summani raqam bilan yozing (masalan: 5000000):")
        else:
            await query.edit_message_text(f"✏️ {ism} uchun yangi oylik summani raqam bilan yozing (masalan: 6000000):")
        return

    if action == "mood":
        mood_labels = {"yomon": "😞 Yomon", "orta": "😐 O'rta", "zor": "🔥 Zo'r"}
        label = mood_labels.get(payload, payload)
        await query.edit_message_text(f"Bugungi kayfiyatingiz: {label}\nRahmat! 🙏")
        if ADMIN_CHAT_ID and str(chat_id) != str(ADMIN_CHAT_ID):
            uname = _sender_display_name(chat_id, update.effective_user, fallback="Foydalanuvchi")
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=f"🌙 {uname}: bugungi kayfiyati — {label}",
                )
            except Exception:
                logger.exception("Adminga kayfiyat haqida xabar berib bo'lmadi")
        return

    # Qolgan holatlar: "approve:<page_id>", "reject:<page_id>", "publish:<page_id>", "done:<page_id>"
    page_id = payload

    if action in ("approve", "reject"):
        new_status = "Tasdiqlandi" if action == "approve" else "Reja"
        try:
            nx.update_page_property(page_id, {"Status": {"select": {"name": new_status}}})
        except Exception:
            logger.exception("Statusni yangilashda xatolik")
            await query.edit_message_text(query.message.text + "\n\n⚠️ Statusni yangilab bo'lmadi.")
            return

        # Post matnida (masalan izohdagi "urolog_shovkat" kabi) Markdown'ni buzadigan belgilar
        # bo'lishi mumkin edi — shu sabab avval "✅ tasdiqlandi" deb Notion'da yozilsa ham, Telegram
        # xabarini formatlab tahrirlashda xatolik chiqib, foydalanuvchiga "ishlamayapti"day ko'rinardi.
        # Endi eski xabar matni umuman qayta ishlatilmaydi va parse_mode qo'llanilmaydi.
        try:
            nomi = nx.get_title(nx.get_page(page_id), "Post nomi") or "Post"
        except Exception:
            nomi = "Post"
        try:
            await query.edit_message_text(f"{'✅' if action == 'approve' else '❌'} {nomi}\n\n➡️ Status: {new_status}")
        except Exception:
            logger.exception("Xabarni tahrirlashda xatolik (status baribir yangilandi)")

        # /kontent oqimida bo'lsa (kanal tanlangan bo'lsa) — shu kanaldagi keyingi postni
        # avtomatik, birma-bir yuboramiz, admin har safar /kontent yozib o'tirmasin.
        kontent_kanal = context.user_data.get("kontent_kanal")
        if kontent_kanal:
            has_more = await _send_next_kontent_post(context.bot, chat_id, kontent_kanal)
            if not has_more:
                await context.bot.send_message(
                    chat_id=chat_id, text=f"✅ '{kontent_kanal}' uchun barcha postlar ko'rib chiqildi."
                )
                context.user_data.pop("kontent_kanal", None)
        return

    if action == "publish":
        ok, xabar = await _publish_kontent_post(context.bot, page_id)
        try:
            await query.edit_message_text(query.message.text + f"\n\n{xabar}")
        except Exception:
            logger.exception("Xabarni tahrirlashda xatolik (joylash baribir amalga oshdi/oshmadi)")
        return

    if action == "done":
        try:
            page = nx.get_page(page_id)
            vazifa_nomi = nx.get_title(page, "Vazifa")
            nx.update_page_property(page_id, {
                "Holati": {"status": {"name": "Done"}},
                "Bajarildi sanasi": {"date": {"start": _tashkent_today().isoformat()}},
            })
            await query.edit_message_text(query.message.text + "\n\n✅ Bajarildi deb belgilandi!")

            try:
                _accrue_task_payment(page)
            except Exception:
                logger.exception("Vazifa haqini hisoblashda xatolik")

            if ADMIN_CHAT_ID:
                bajaruvchi = _sender_display_name(chat_id, update.effective_user)
                await context.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=f"✅ {bajaruvchi} vazifani bajardi: {vazifa_nomi}",
                )
        except Exception:
            logger.exception("Vazifa holatini yangilashda xatolik")
            await query.edit_message_text(query.message.text + "\n\n⚠️ Xatolik yuz berdi.")
        return


# ----------------------------------------------------------------------------
# Kanal ID'ini aniqlash yordamchisi:
# Botni maxfiy (private) kanalga admin qilib qo'shing, keyin o'sha kanaldagi istalgan
# postni shu botga forward qiling — bot sizga o'sha kanalning raqamli chat_id'ini yuboradi,
# uni CHANNEL_18_NATIJALAR kabi muhit o'zgaruvchisiga qo'yasiz.
# ----------------------------------------------------------------------------

@require_auth
async def on_forwarded(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    origin = update.message.forward_origin
    if origin is None or not hasattr(origin, "chat"):
        await update.message.reply_text(
            "Bu forward qilingan post emas yoki kanal manbasi aniqlanmadi. "
            "Iltimos, kanaldagi postni to'g'ridan-to'g'ri shu botga forward qiling."
        )
        return

    chat = origin.chat
    await update.message.reply_text(
        f"📢 Kanal: {chat.title}\nID: `{chat.id}`\n\n"
        f"Shu ID'ni tegishli CHANNEL_... muhit o'zgaruvchisiga qo'ying.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ----------------------------------------------------------------------------

BOT_COMMANDS = [
    BotCommand("start", "Botni ishga tushirish / asosiy menyu"),
    BotCommand("menu", "Asosiy menyu (tugmalar)"),
    BotCommand("men", "Xodim sifatida ro'yxatdan o'tish"),
    BotCommand("hisobot", "Kunlik dashboard (rasm)"),
    BotCommand("oylik", "Oylik target dashboard (rasm)"),
    BotCommand("vazifalarim", "Menga tayinlangan vazifalar"),
    BotCommand("qildim", "Donasiga to'lanadigan ishni o'zim yozib qo'yaman (masalan montaj)"),
    BotCommand("jamoa", "Kimda nima vazifa bor (admin)"),
    BotCommand("vazifa", "Yangi TZ berish (tugmalar orqali)"),
    BotCommand("kontent", "Tasdiqlash kutayotgan postlar"),
    BotCommand("joylash", "Tasdiqlangan postlarni kanalga joylash"),
    BotCommand("target", "Yo'nalishlar bo'yicha progress"),
    BotCommand("reels", "Bugungi reels sonini kiritish"),
    BotCommand("moliya", "Moliya — balansni ko'rish"),
    BotCommand("faoliyat", "Kim nima ish qilgani (vaqt oralig'i tanlab, admin)"),
    BotCommand("loyihalar", "Loyihalarni boshqarish: pauza/faollashtirish/o'chirish (admin)"),
    BotCommand("yangiloyiha", "Yangi mijoz-loyiha qo'shish (admin)"),
]


async def _post_init(app: Application) -> None:
    await app.bot.set_my_commands(BOT_COMMANDS)
    logger.info("Bot buyruqlar menyusi ('/') sozlandi.")


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).post_init(_post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CommandHandler("men", men))
    app.add_handler(CommandHandler("hisobot", hisobot))
    app.add_handler(CommandHandler("oylik", oylik))
    app.add_handler(CommandHandler("vazifalarim", vazifalarim))
    app.add_handler(CommandHandler("qildim", qildim))
    app.add_handler(CommandHandler("jamoa", jamoa))
    app.add_handler(CommandHandler("vazifa", vazifa))
    app.add_handler(CommandHandler("kontent", kontent))
    app.add_handler(CommandHandler("joylash", joylash))
    app.add_handler(CommandHandler("target", target))
    app.add_handler(CommandHandler("reels", reels))
    app.add_handler(CommandHandler("moliya", moliya))
    app.add_handler(CommandHandler("faoliyat", faoliyat))
    app.add_handler(CommandHandler("loyihalar", loyihalar_cmd))
    app.add_handler(CommandHandler("yangiloyiha", yangiloyiha))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.FORWARDED, on_forwarded))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.FORWARDED, on_plain_text))

    if app.job_queue is not None:
        if ADMIN_CHAT_ID:
            app.job_queue.run_daily(
                scheduled_daily_report,
                time=dtime(hour=REPORT_HOUR, minute=REPORT_MINUTE, tzinfo=TASHKENT_TZ),
            )
            app.job_queue.run_daily(
                scheduled_reels_prompt,
                time=dtime(hour=REELS_HOUR, minute=REELS_MINUTE, tzinfo=TASHKENT_TZ),
            )
            logger.info(
                f"Kunlik avtomatik hisobot: {REPORT_HOUR:02d}:{REPORT_MINUTE:02d}, "
                f"reels so'rovi: {REELS_HOUR:02d}:{REELS_MINUTE:02d} (ADMIN_CHAT_ID={ADMIN_CHAT_ID})"
            )
        else:
            logger.warning("ADMIN_CHAT_ID o'rnatilmagan — kunlik hisobot va reels so'rovi avtomatik ishlamaydi.")

        for h in REMINDER_HOURS:
            app.job_queue.run_daily(scheduled_task_reminders, time=dtime(hour=h, minute=0, tzinfo=TASHKENT_TZ))
        app.job_queue.run_daily(
            scheduled_motivation, time=dtime(hour=MOTIVATION_HOUR, minute=MOTIVATION_MINUTE, tzinfo=TASHKENT_TZ)
        )
        app.job_queue.run_daily(scheduled_mood_checkin, time=dtime(hour=MOOD_HOUR, minute=MOOD_MINUTE, tzinfo=TASHKENT_TZ))
        app.job_queue.run_daily(
            scheduled_settlement_check, time=dtime(hour=SETTLEMENT_HOUR, minute=SETTLEMENT_MINUTE, tzinfo=TASHKENT_TZ)
        )
        app.job_queue.run_daily(
            scheduled_loyiha_billing, time=dtime(hour=LOYIHA_BILLING_HOUR, minute=LOYIHA_BILLING_MINUTE, tzinfo=TASHKENT_TZ)
        )
        app.job_queue.run_daily(
            scheduled_morning_task_notify, time=dtime(hour=QUIET_HOURS_END, minute=0, tzinfo=TASHKENT_TZ)
        )
        app.job_queue.run_daily(
            scheduled_publish_watchdog,
            time=dtime(hour=DAILY_PUBLISH_CHECK_HOUR, minute=DAILY_PUBLISH_CHECK_MINUTE, tzinfo=TASHKENT_TZ),
        )
        app.job_queue.run_repeating(
            scheduled_auto_publish, interval=AUTO_PUBLISH_INTERVAL_MINUTES * 60, first=15
        )
        logger.info(
            f"Vazifa eslatmalari: {REMINDER_HOURS}, motivatsiya: {MOTIVATION_HOUR:02d}:{MOTIVATION_MINUTE:02d}, "
            f"kayfiyat so'rovi: {MOOD_HOUR:02d}:{MOOD_MINUTE:02d}, "
            f"hisob-kitob tekshiruvi: har kuni {SETTLEMENT_HOUR:02d}:{SETTLEMENT_MINUTE:02d} (har xodimning o'z 'Hisob kuni'sida), "
            f"loyiha oylik hisob-kitobi: har kuni {LOYIHA_BILLING_HOUR:02d}:{LOYIHA_BILLING_MINUTE:02d} (har loyihaning 'Boshlanish sanasi' kunida), "
            f"tungi tinchlik: {QUIET_HOURS_START:02d}:00–{QUIET_HOURS_END:02d}:00 (xodimlarga avtomatik xabar yo'q), "
            f"avtomatik joylash: har {AUTO_PUBLISH_INTERVAL_MINUTES} daqiqada"
        )
    else:
        logger.warning("job_queue mavjud emas — 'pip install python-telegram-bot[job-queue]' qilinganini tekshiring.")

    logger.info("Jarvis bot ishga tushdi (polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
