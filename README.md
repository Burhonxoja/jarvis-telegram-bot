# Jarvis Telegram Bot

Notion bilan ulangan, sizning barcha jarayonlaringizni (vazifalar, kontent-reja, hisobotlar) boshqaradigan Telegram bot.

## Nima qila oladi (hozirgi versiya)

- `/start` — botni ishga tushirish, chat ID'ni ko'rsatadi
- `/hisobot` — bugungi vazifalar va kontent-reja holati bo'yicha qisqa hisobot
- `/kontent` — "Yozildi" statusidagi postlarni ko'rsatadi, tugma orqali Tasdiqlash/Rad etish imkonini beradi (bosilganda Notion'dagi Status avtomatik yangilanadi)
- `/vazifa <matn>` — Vazifalar bazasiga yangi vazifa qo'shadi

## Nima uchun bu yerda (Cowork ichida) ishlamaydi

Bu muhit xavfsizlik devori orqasida ishlaydi va tashqi API'larga (Telegram, Notion) to'g'ridan-to'g'ri ulanishga ruxsat bermaydi. Shuning uchun botni **tashqi hostingda** ishga tushirish kerak. Quyida eng oson variant — Railway orqali.

## O'rnatish (Railway orqali, bepul boshlash mumkin)

1. **GitHub'ga yuklang** (yoki Railway'ga to'g'ridan-to'g'ri fayllarni tashlang):
   - Shu papkadagi barcha fayllarni (`bot.py`, `notion_api.py`, `requirements.txt`) yangi GitHub repo'ga yuklang.
   - `.env` faylini **HECH QACHON** repo'ga qo'shmang (u faqat namuna — `.env.example`).

2. **railway.app** ga kiring → "New Project" → "Deploy from GitHub repo" → repo'ni tanlang.

3. **Environment Variables** bo'limiga o'ting va ikkita o'zgaruvchi qo'shing:
   - `TELEGRAM_BOT_TOKEN` = BotFather bergan tokeningiz
   - `NOTION_TOKEN` = notion.so/my-integrations dan olingan Internal Integration Secret

4. **Start command**'ni sozlang: `python bot.py`

5. Deploy qilgach, Telegram'da botingizga `/start` yozing — javob bersa, tayyor.

## Muhim: Notion integratsiyasini bazalarga ulash

Token olish yetarli emas — integratsiyani har bir Notion sahifasiga **alohida ulash** kerak:

1. Notion'da "🧠 Jarvis — Boshqaruv Markazi" sahifasini oching.
2. Yuqori o'ng burchakdagi "..." (uch nuqta) tugmasini bosing.
3. "Connections" (yoki "Ulanishlar") → yaratgan integratsiyangizni (masalan "Jarvis Bot") tanlang va ulang.
4. Bu sahifa ostidagi barcha bazalar (Xodimlar, Vazifalar, Kontent-Reja va h.k.) avtomatik shu ruxsatni meros qilib oladi.

Agar bu qadam bajarilmasa, bot Notion'dan ma'lumot ololmaydi (403 xatolik chiqadi).

## Keyingi qadamlar (rejalashtirilgan)

- Kunlik hisobotni avtomatik, belgilangan vaqtda yuborish (masalan har kuni kechqurun)
- Xodimlarga TZ (vazifa) tayinlash va ular tomonidan "bajardim" deb belgilash
- Lead/target progressini `/target` buyrug'i orqali ko'rsatish
- Rasm/video fayllarni to'g'ridan-to'g'ri botga yuborib, Kontent-Reja'ga biriktirish

Savol yoki xatolik chiqsa — screenshot bilan yuboring, birga hal qilamiz.
