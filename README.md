# Jarvis Telegram Bot

Notion bilan ulangan, sizning barcha jarayonlaringizni (vazifalar, kontent-reja, hisobotlar, target) boshqaradigan Telegram bot.

## Buyruqlar

- `/start` — botni ishga tushirish, chat ID'ni ko'rsatadi
- `/men <Ism>` — o'zingizni (yoki xodimni, agar u shu botdan foydalanayotgan bo'lsa) Xodimlar bazasidagi ism bilan bog'lab, ro'yxatdan o'tkazadi. Bundan keyin unga TZ va bildirishnomalar shu chatga keladi.
- `/hisobot` — bugungi vazifalar va kontent-reja holati bo'yicha qisqa hisobot
- `/vazifalarim` — sizga (ro'yxatdan o'tgan xodimga) tayinlangan, hali bajarilmagan vazifalar, har birida "✅ Bajardim" tugmasi. Agar vazifaga izoh qoldirilgan bo'lsa, o'sha izoh(lar) har safar vazifa ko'rsatilganda pastida doim ko'rinadi.
- `/jamoa` (faqat admin) — har bir xodimda hozir qanday ochiq vazifalar borligini bittalab ko'rsatadi (kim, nima ish, muddati, izohlari bilan) — "kimda nima vazifa bor" savoliga javob
- `/vazifa <Ism> | <matn>` — xodimga yangi TZ beradi (masalan: `/vazifa Hasan | 3 ta reels suratga oling`). Agar xodim ro'yxatdan o'tgan bo'lsa, unga darhol xabar va "✅ Bajardim" tugmasi yuboriladi. Agar vazifa matni ro'yxat shaklida yozilsa (masalan `1. birinchi ish` `2. ikkinchi ish` — bir nechta qatorda yoki bittasida ketma-ket), bot har bir bandni **alohida vazifa** sifatida ajratib yaratadi (har biriga alohida xabar va "✅ Bajardim" tugmasi bilan).
- `/kontent` — avval qaysi kanal uchun tasdiqlaysiz deb so'raydi (har bir kanalda nechta post kutayotgani bilan), so'ng shu kanaldagi "Yozildi" postlarni birma-bir (bittadan) ko'rsatadi, tugmalar bilan: "✅ Tasdiqlash", "❌ Rad etish", "✏️ Tahrirlash" (yangi matn so'raladi va Notion'dagi "Ssenariy/Matn" shu bilan almashtiriladi, so'ng post qayta ko'rsatiladi). Agar postning turi rasm talab qilsa (Rasm / Rasm+Matn / Carousel) va hali rasm biriktirilmagan bo'lsa, "🎨 Rasm yasash" tugmasi ham chiqadi — bosilsa, OpenAI GPT Image (`OPENAI_API_KEY` orqali) post mavzusiga mos rasmni avtomatik generatsiya qilib, sizga ko'rsatadi (keyin qayta yasash ham mumkin). Tasdiqlash yoki rad etishdan so'ng o'sha kanaldagi keyingi post avtomatik keladi, hech qolmaguncha
- `/joylash` — "Tasdiqlandi" statusidagi postlarni ko'rsatadi, "🚀 Kanalga joylash" tugmasi bosilganda postni haqiqiy Telegram kanaliga yuboradi va Status'ni "Joylandi" qiladi. Kontent-Reja'dagi "Hook" maydoni (agar to'ldirilgan bo'lsa) postning boshida **qalin (bold)** qilib chiqadi; postning oxiridagi imzo/footer (masalan ARK Hospital uchun "📝 Kanal Shablonlari"dagi "Post oxiri shabloni" bilan mos qism) ham avtomatik **qalin** qilib joylanadi. **Bundan tashqari — qo'lda bosish shart emas**: post "Tasdiqlandi" bo'lgach, uning Kontent-Reja'dagi "Sana"+"Vaqt"i kelib yetganda bot uni avtomatik ravishda o'zi kanalga joylaydi (har `AUTO_PUBLISH_INTERVAL_MINUTES` daqiqada tekshiriladi) va adminga xabar beradi.
- `/target` (menyuda "📊 Progress" tugmasi) — target/bajarildi progressi (o'qish uchun): avval Yo'nalishlar bazasi (agar to'ldirilgan bo'lsa), keyin **har bir FAOL Loyiha** uchun Reels/🎯 Target (video)/Obunachi progressi + Telegram post progressi. Hech biri oy bo'yicha filtrlanmaydi — bir marta qo'shilgan loyiha va uning barcha "Joylandi" postlari doim to'liq hisoblanadi, qaytadan har oy qo'shish shart emas.
- "🎯 Target hisobot" (menyu tugmasi, faqat admin) — loyiha tanlangach, "🎞 Video qo'shish" (bugun nechta yangi video joylangani — reels kabi qo'shiladi; hisobot/progressda bu "🎯 Target" deb chiqadi) yoki "👥 Obunachi sonini yangilash" (hozirgi JAMI obunachi/follower sonini kiritasiz — o'rniga yoziladi, oldingi qiymat ustiga qo'shilmaydi) tanlanadi. Bu orqali oylik auditoriya hisobotini ham yuritish mumkin.
- **Debit / Kredit**: `Debit` = mandan qarzdorlar (mijozlar bizga qarzdor bo'lgan summa). Agar loyihaning to'lov turi "Video/Reels boshiga" bo'lsa, `/reels` yoki "🎞 Video qo'shish" orqali kiritilgan har bir son uchun hisoblangan summa **darhol Kirimga emas, loyihaning "Debit"iga qo'shiladi** (chunki pul hali kelmagan). Pul haqiqatda kelganda admin "➕ Kirim qo'shish" orqali qayd etadi — o'sha summa avtomatik shu Debit'dan ayiriladi va faqat SHU payt haqiqiy Kirim sifatida biznes hisobotiga qo'shiladi. Debit `/loyihalar` tafsilotida va admin `/moliya`sida ("💳 Debit — mandan qarzdorlar") ko'rinadi. (`Kredit` = man qarzman, ya'ni biznes boshqalarga qarzdor bo'lgan summa — hozircha alohida moliyaviy bo'lim sifatida joriy qilinmagan, kerak bo'lsa xodimlar balansi shu tushuncha bilan ham kengaytirilishi mumkin.)
- `/menu` — asosiy menyu (barcha buyruqlar tugma shaklida)
- `/reels` — bugun qaysi loyihaga nechta reels joylanganini kiritish (Loyihalar bazasidagi "Reels bajarildi"ga qo'shiladi). Faqat FAOL (Pauzada/Arxivlangan bo'lmagan) loyihalar tanlov ro'yxatida chiqadi. Agar loyihaning "To'lov turi" — "Video/Reels boshiga" bo'lsa, kiritilgan son × "To'lov summasi" avtomatik loyihaning "Debit"iga qo'shiladi (haqiqiy Kirim emas — yuqoridagi "Debit / Kredit" bo'limiga qarang).
- Har bir vazifa xabarida "💬 Izoh" tugmasi bor — xodim vazifaga izoh qoldirishi mumkin (Notion sahifa kommentariyasi sifatida saqlanadi)
- `/vazifa` argumentsiz yozilsa, tugma orqali xodim va muddat (bugun/keyingi kunlar) tanlanadi, so'ng vazifa matni yoziladi
- `/moliya` — moliya bo'limi. Admin uchun: 💼 butun biznesning shu oylik holati (loyihalardan tushgan kirim − barcha xarajat = sof foyda) + hamma xodimning balansi. Oddiy xodim uchun: faqat o'zining balansi. Xodimlar bazasida "Maosh turi" ("Kunlik (oylik summadan)" yoki "Vazifa boshiga"), "Maosh summasi", (vazifa-asosli uchun) "Maosh maqsad soni" va "Hisob kuni" (oyning qaysi sanasida hisob-kitob qilinishi, masalan Hasan=10, Mubina=20) bilan sozlanadi. Balans TAQVIM OYIGA emas, balki xodimning shaxsiy "Hisob kuni" davriga asoslanadi — masalan Hasan uchun har doim 11-sanadan keyingi oyning 10-sanasigacha. "Kunlik" turidagi xodimning jamg'arilgan summasi shu davr ichida REAL VAQTDA (o'tgan kunlar ulushi bo'yicha) hisoblanadi va faqat davr oxirida — hisob kunining o'zida — to'liq summaga yetadi. "Vazifa boshiga" turi har "✅ Bajardim" bosilganda Notion'ga yoziladi va shu davr ichida yig'iladi. Admin "💵 to'lov" yoki "🪙 avans" tugmasi bilan Chiqim qayd etadi. Har bir xodimning o'z "Hisob kuni"da adminga balans + to'lov/avans/stavka-o'zgartirish tugmalari yuboriladi.
- "➕ Kirim qo'shish" (faqat admin) — loyihadan tushgan pulni loyiha bo'yicha (yoki "Boshqa") Moliya'ga Kirim sifatida yozadi; shu orqali `/moliya`dagi umumiy biznes hisobotiga qo'shiladi.
- "✅ ...ga bajarilgan ish qo'shish" (faqat admin, "Vazifa boshiga" xodimlar uchun, masalan Mubina) — bot orqali alohida vazifa sifatida tayinlanmagan ishlar (masalan tashqarida qilingan montaj/video) uchun, admin necha ta YANGI ish bajarilganini kiritadi; mos summa (stavka ÷ maqsad soni × son) avtomatik Kirim sifatida yoziladi va balansga qo'shiladi.
- `/loyihalar` (faqat admin) — joriy oydagi (Arxivlangandan boshqa) loyihalar ro'yxatini ko'rsatadi; birini tanlasangiz — targetlar, to'lov turi va holati bilan tafsilot ochiladi, tugmalar: "⏸ Pauzaga qo'yish" / "▶️ Qayta faollashtirish" va "🗑 O'chirish" (tasdiqlash so'raladi, o'chirilganda Notion arxiviga ko'chiriladi — butunlay yo'qolmaydi, kerak bo'lsa Notion'dan qaytarish mumkin). Pauzadagi yoki o'chirilgan loyihalar `/reels` tanlovida va `/target`dagi progress hisobotida ko'rinmaydi.
- `/yangiloyiha` (faqat admin) — yangi mijoz-loyihani bosqichma-bosqich qo'shadi: loyiha nomi → **hisob-kitob davri boshlanish sanasi** (qo'lda kiritiladi, masalan "15.07.2026", yoki "bugun" deb yozish mumkin — shu orqali eski loyihalarni ham haqiqiy boshlangan sanasi bilan kiritish mumkin) → oylik reels video target → oylik video target → oylik telegram post target → bog'liq kanal (tugma orqali, yoki "keyinroq belgilayman") → **to'lov turi** ("🎬 Video/Reels donasiga" yoki "📅 Oylik (fixed)", yoki "hozircha belgilamayman") → to'lov summasi. Oxirida Notion'dagi "📁 Loyihalar" bazasiga joriy oy uchun yangi qator yaratiladi (barcha "bajarildi" sonlari 0'dan boshlanadi). Agar to'lov turi "Video/Reels boshiga" bo'lsa, `/reels` orqali kiritilgan har bir son uchun daromad avtomatik hisoblab, Moliya'ga yoziladi.

## Avtomatik kunlik hisobot

`ADMIN_CHAT_ID` muhit o'zgaruvchisi o'rnatilgan bo'lsa, bot har kuni belgilangan vaqtda (standart 20:00, `REPORT_HOUR`/`REPORT_MINUTE` orqali sozlanadi) avtomatik hisobotni shu chatga yuboradi.

## Muhit o'zgaruvchilari

| O'zgaruvchi | Majburiymi | Tavsif |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Ha | BotFather bergan token |
| `NOTION_TOKEN` | Ha | Notion Internal Integration Secret |
| `ADMIN_CHAT_ID` | Yo'q, lekin tavsiya etiladi | Kunlik hisobot va xodim bildirishnomalari shu ID'ga yuboriladi. `/start` yozib, chiqqan raqamni shu yerga qo'ying. |
| `REPORT_HOUR`, `REPORT_MINUTE` | Yo'q | Kunlik hisobot vaqti (standart 20:00) |
| `REELS_HOUR`, `REELS_MINUTE` | Yo'q | Kunlik reels so'rovi vaqti (standart 19:30) — ADMIN_CHAT_ID'ga yuboriladi |
| `REMINDER_HOURS` | Yo'q | Vergul bilan ajratilgan soatlar (standart `9,11,13,15,17,19`) — shu soatlarda kimda ochiq vazifa bo'lsa, o'sha xodimga eslatma boradi |
| `MOTIVATION_HOUR`, `MOTIVATION_MINUTE` | Yo'q | Har tongi motivatsion xabar vaqti (standart 08:00), ALLOWED_CHAT_IDS'dagi hammaga yuboriladi |
| `MOOD_HOUR`, `MOOD_MINUTE` | Yo'q | Kechki "kuningiz qanday o'tdi?" so'rovi vaqti (standart 21:00), ALLOWED_CHAT_IDS'dagi hammaga yuboriladi |
| `SETTLEMENT_HOUR`, `SETTLEMENT_MINUTE` | Yo'q | Har kuni tekshiriladigan vaqt (standart 09:00) — kimning Xodimlar bazasidagi "Hisob kuni"si bugunga to'g'ri kelsa, o'sha xodim uchun adminga balans va to'lov/avans/stavka tugmalari yuboriladi |
| `AUTO_PUBLISH_INTERVAL_MINUTES` | Yo'q | Necha daqiqada bir "Tasdiqlandi" postlarning Sana+Vaqt'i tekshirilib, kelib yetganlari avtomatik kanalga joylanadi (standart 5) |
| `OPENAI_API_KEY` | Yo'q, faqat "🎨 Rasm yasash" uchun | OpenAI Platform'dan olinadigan API kaliti (platform.openai.com/api-keys). Bo'lmasa, "Rasm yasash" tugmasi bosilganda tushunarli xato xabari chiqadi, boshqa hech narsaga ta'sir qilmaydi. |
| `OPENAI_IMAGE_MODEL` | Yo'q | Rasm generatsiyasi uchun model nomi (standart `gpt-image-1`) |
| `GEMINI_API_KEY` | Yo'q, ishlatilmayapti | Eski Gemini integratsiyasi qoldirilgan, lekin hozir "Rasm yasash" OpenAI orqali ishlaydi. |
| `CHANNEL_UROLOG_SHOVKAT` | Yo'q, faqat `/joylash` uchun | "Telegram - Urolog Shovkat" kanaliga mos Telegram manzil (masalan `@urolog_shovkat` yoki `-100xxxxxxxxxx`) |
| `CHANNEL_ARK_HOSPITAL` | Yo'q, faqat `/joylash` uchun | "Telegram - ARK Hospital" kanaliga mos manzil |
| `CHANNEL_18_NATIJALAR` | Yo'q, faqat `/joylash` uchun | "Telegram - 18+ Natijalar" kanaliga mos manzil |
| `ALLOWED_CHAT_IDS` | Yo'q, lekin **kuchli tavsiya** | Vergul bilan ajratilgan ruxsat berilgan chat_id'lar (masalan `1890595434,7388057342`). Shu ro'yxatda va `ADMIN_CHAT_ID`da bo'lmagan hech kim botdan foydalana olmaydi — `/start` bossa ham faqat o'z chat_id'ini ko'radi, boshqa hech narsa ishlamaydi. |

## Maxfiy kanalning raqamli ID'ini topish (masalan "18+ Natijalar")

Agar kanal faqat taklif havolasi (invite link) orqali bo'lsa, `@username` yo'q — bunday holda:
1. Botni o'sha kanalga **admin** qilib qo'shing.
2. Kanaldagi istalgan postni shu botga **forward** qiling (shaxsiy chatda).
3. Bot sizga kanalning raqamli ID'sini (masalan `-1001234567890`) yuboradi — shuni `CHANNEL_18_NATIJALAR` ga qo'ying.

**Muhim:** `/joylash` ishlashi uchun bot shu kanallarda **admin** va **post yuborish huquqiga** ega bo'lishi kerak (Telegram kanal sozlamalaridan qo'shiladi).

## Lokal ishga tushirish (hozirgi holat — terminal test)

```
cd jarvis_bot
pip3 install -r requirements.txt
export TELEGRAM_BOT_TOKEN="..."
export NOTION_TOKEN="..."
export ADMIN_CHAT_ID="..."      # ixtiyoriy, lekin tavsiya etiladi
export CHANNEL_UROLOG_SHOVKAT="@sizning_kanal_username"   # ixtiyoriy
export OPENAI_API_KEY="..."     # ixtiyoriy, faqat "🎨 Rasm yasash" uchun
python3 bot.py
```

## Notion integratsiyasini ulash (majburiy)

1. Notion'da "🧠 Jarvis — Boshqaruv Markazi" sahifasini oching.
2. "..." (uch nuqta) → Connections → integratsiyangizni tanlang.
3. Bu sahifa ostidagi barcha bazalar avtomatik ruxsatni meros oladi.

## Doimiy (24/7) hostingga joylash

Bot hozircha faqat siz terminalni ochib turgan vaqtda ishlaydi. Doimiy ishlashi uchun tashqi hosting kerak (Railway, Render va h.k.) — kod tayyor, faqat shu yerdagi muhit o'zgaruvchilarini hosting platformasining "Environment Variables" bo'limiga kiritish kifoya.

## Hali qilinmagan / keyingi qadamlar

- Obsidian integratsiyasi (siz so'rovingiz bilan hozircha o'tkazib yuborilgan)
- Video generatsiyasini avtomatlashtirish (hozircha qo'lda). Rasm generatsiyasi endi `/kontent`dagi "🎨 Rasm yasash" tugmasi orqali avtomatlashtirilgan (Gemini/Nano Banana).
