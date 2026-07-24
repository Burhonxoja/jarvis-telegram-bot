"""
Jarvis Telegram Bot — Notion bilan ishlaydigan yagona boshqaruv boti.

Buyruqlar:
  /start     - botni ishga tushirish, chat_id'ni ro'yxatdan o'tkazish
  /hisobot   - bugungi vazifalar va kontent-reja holati bo'yicha qisqa hisobot
  /kontent   - "Yozildi" statusidagi postlarni ko'rish va tasdiqlash/rad etish
  /vazifa    - yangi vazifa yaratish: /vazifa <matn>

Ishga tushirish:
  1) requirements.txt dagi paketlarni o'rnating: pip install -r requirements.txt
  2) Muhit o'zgaruvchilarini sozlang: TELEGRAM_BOT_TOKEN, NOTION_TOKEN, ADMIN_CHAT_ID (ixtiyoriy)
  3) python bot.py
"""
import logging
import os
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

import notion_api as nx

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("jarvis-bot")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

STATUS_ORDER = ["Reja", "Yozildi", "Tasdiqlandi", "Joylandi"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        "Salom! Men Jarvis — sizning Notion bilan ulangan yordamchingizman.\n\n"
        f"Sizning chat ID'ingiz: {chat_id}\n"
        "(Buni ADMIN_CHAT_ID sifatida saqlab qo'ying — kunlik hisobotlar shu ID'ga yuboriladi.)\n\n"
        "Buyruqlar:\n"
        "/hisobot — bugungi holat\n"
        "/kontent — tasdiqlash kutayotgan postlar\n"
        "/vazifa <matn> — yangi vazifa yaratish"
    )


async def hisobot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Hisobot tayyorlanmoqda...")

    today = date.today().isoformat()

    # Bugungi muddatli vazifalar
    try:
        vazifalar = nx.query_data_source(
            nx.DS_VAZIFALAR,
            filter_obj={"property": "Muddat", "date": {"equals": today}},
        )
    except Exception as e:
        logger.exception("Vazifalarni olishda xatolik")
        vazifalar = []

    # Bugungi kontent-reja postlari
    try:
        postlar = nx.query_data_source(
            nx.DS_KONTENT_REJA,
            filter_obj={"property": "Sana", "date": {"equals": today}},
        )
    except Exception:
        logger.exception("Kontent-rejani olishda xatolik")
        postlar = []

    lines = [f"📊 *Kunlik hisobot* — {today}\n"]

    lines.append(f"*Bugungi vazifalar:* {len(vazifalar)} ta")
    for v in vazifalar[:15]:
        nomi = nx.get_title(v, "Vazifa")
        holati = nx.get_status(v, "Holati") or "?"
        lines.append(f"  • {nomi} — _{holati}_")

    lines.append(f"\n*Bugungi postlar:* {len(postlar)} ta")
    for p in postlar[:15]:
        nomi = nx.get_title(p, "Post nomi")
        kanal = nx.get_select(p, "Kanal") or "?"
        status = nx.get_select(p, "Status") or "?"
        lines.append(f"  • [{kanal}] {nomi} — _{status}_")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def kontent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        postlar = nx.query_data_source(
            nx.DS_KONTENT_REJA,
            filter_obj={"property": "Status", "select": {"equals": "Yozildi"}},
        )
    except Exception:
        logger.exception("Kontent-rejani olishda xatolik")
        await update.message.reply_text("Xatolik yuz berdi, keyinroq urinib ko'ring.")
        return

    if not postlar:
        await update.message.reply_text("Tasdiqlash kutayotgan post yo'q. ✅")
        return

    for p in postlar[:10]:
        page_id = p["id"]
        nomi = nx.get_title(p, "Post nomi")
        kanal = nx.get_select(p, "Kanal") or "?"
        matn = nx.get_rich_text(p, "Ssenariy/Matn")
        sana = nx.get_date(p, "Sana") or "?"

        preview = matn[:500] + ("..." if len(matn) > 500 else "")
        text = f"📅 {sana} | 📢 {kanal}\n*{nomi}*\n\n{preview}"

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve:{page_id}"),
                InlineKeyboardButton("❌ Rad etish", callback_data=f"reject:{page_id}"),
            ]
        ])
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    action, page_id = query.data.split(":", 1)
    new_status = "Tasdiqlandi" if action == "approve" else "Reja"

    try:
        nx.update_page_property(page_id, {"Status": {"select": {"name": new_status}}})
        await query.edit_message_text(
            query.message.text + f"\n\n➡️ Status: *{new_status}*",
            parse_mode="Markdown",
        )
    except Exception:
        logger.exception("Statusni yangilashda xatolik")
        await query.edit_message_text(query.message.text + "\n\n⚠️ Xatolik yuz berdi.")


async def vazifa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    matn = " ".join(context.args)
    if not matn:
        await update.message.reply_text("Foydalanish: /vazifa <vazifa matni>")
        return

    try:
        nx.create_page(
            nx.DS_VAZIFALAR,
            {
                "Vazifa": {"title": [{"text": {"content": matn}}]},
                "Holati": {"status": {"name": "Not started"}},
            },
        )
        await update.message.reply_text(f"✅ Vazifa yaratildi: {matn}")
    except Exception:
        logger.exception("Vazifa yaratishda xatolik")
        await update.message.reply_text("⚠️ Vazifani yaratib bo'lmadi.")


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("hisobot", hisobot))
    app.add_handler(CommandHandler("kontent", kontent))
    app.add_handler(CommandHandler("vazifa", vazifa))
    app.add_handler(CallbackQueryHandler(on_button))

    logger.info("Jarvis bot ishga tushdi (polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
