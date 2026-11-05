# Kino Bot

Python + aiogram 3 + SQLite asosida Telegram kino boti. Foydalanuvchi kino kodini yuboradi; bot majburiy obunani tekshiradi va videoni yetkazadi. Boshqaruv Telegram ichidagi tugmali admin panel orqali bajariladi.

**Holat:** kod va avtomatlashtirilgan testlar tayyor. Haqiqiy botda ishga tushirish uchun sizning `BOT_TOKEN` va `OWNER_IDS` qiymatlaringiz kerak. Token kiritilmagani sababli jonli Telegram akkaunti va haqiqiy kino fayllari bilan yakuniy tekshiruv hali bajarilmagan.

## 1. Windows’da ishga tushirish

Python 3.11 yoki 3.12 o‘rnating. PowerShell’da:

```powershell
git clone https://github.com/Abdulkhak1mov/kinobot.git
cd kinobot
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

`.env` ni to‘ldiring:

```dotenv
BOT_TOKEN=BOTFATHER_BERGAN_TOKEN
OWNER_IDS=SIZNING_RAQAMLI_TELEGRAM_ID
DATABASE_PATH=data/kino.db
BOT_TITLE=Kino Bot
TIMEZONE=Asia/Tashkent
```

- `BOT_TOKEN` — [@BotFather](https://t.me/BotFather) orqali olingan **Telegram bot tokeni**. GitHub tokeni bu yerga yozilmaydi.
- `OWNER_IDS` — egasining Telegram raqamli ID raqami; bir nechta bo‘lsa vergul bilan ajrating. Telefon raqami yoki `@username` emas. Botdagi `/id` komandasi foydalanuvchining ID raqamini ko‘rsatadi.
- `.env` va `data/` Git’ga yuborilmaydi. Bot tokeni kodda saqlanmaydi.

Ishga tushirish:

```powershell
.\.venv\Scripts\python.exe bot.py
```

Telegram’da botni oching: `/start`, keyin `/admin`. Konsol yopilsa, mahalliy bot ham to‘xtaydi.

## 2. Linux / server

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# .env qiymatlarini to‘ldiring
.venv/bin/python bot.py
```

Docker o‘rnatilgan serverda:

```bash
docker compose up -d --build
docker compose logs -f bot
```

`./data` doimiy saqlanadi. Cloud hosting’da `DATABASE_PATH` doimiy disk/volume ichida bo‘lsin. Bitta bot tokeni uchun **bitta polling jarayoni va bitta replica** ishlating. Mahalliy process lock bir bazaga ikkita jarayon ulanishini to‘xtatadi; turli serverlar orasida umumiy lock mavjud emas. Webhook faol bo‘lsa bot izoh bilan to‘xtaydi; avval oldingi xizmatni to‘xtatib webhookni olib tashlash kerak. Bot pullik xizmat yoki hostingni avtomatik yaratmaydi.

## 3. Birinchi kino va serial

`/admin` → **Kino / serial qo‘shish**:

1. Kod: masalan `101` yoki `KINO_101`. 1–32 ta lotin harfi, raqam, `_`, `-`.
2. Nomi.
3. Turi: `movie` / `kino` yoki `series` / `serial`.
4. Janr, yil, davlat, tavsif, davomiylik. Majburiy bo‘lmagan joyda `/skip`.
5. Poster: rasm yuboring, HTTPS havola yozing yoki `/skip`.
6. Treyler: HTTPS havola yoki `/skip`.
7. Til va sifat: masalan `O‘zbekcha`, `720p`.
8. Serial uchun fasl va qism raqami.
9. Videoni yuboring. Shu bosqichda katalog va birinchi video birga saqlanadi.

`/cancel` jarayonni bekor qiladi. Qolgan draftlar bazada saqlanadi, restartdan keyin davom ettirish mumkin. `/start` yoki admin bosh menyusi draftni bekor qiladi.

Yana til/sifat yoki serial qismi: **Katalogni boshqarish → kino → Video variant**. Bitta til + sifat + fasl + qism kombinatsiyasi takrorlanmaydi. Mavjud faylni **Videolarni boshqarish → Videoni almashtirish** orqali yangilang. Janr va davlat har bir kino uchun bitta qiymat; nomlarni bir xil yozish tavsiya qilinadi.

Oddiy kino yagona videoga ega bo‘lsa, kod yuborilgach kartochka va video avtomatik keladi. Bir nechta variant bo‘lsa foydalanuvchi til/sifatni tanlaydi. Seriallarda fasl → qism → til/sifat tartibi ishlaydi. Bot sifatni o‘zi o‘zgartirmaydi yoki tarjima qilmaydi: kerakli variantlarni admin yuklaydi.

## 4. Majburiy obuna va kanallar

Botni har bir tegishli kanalga administrator qiling. `/admin → Kanallar → Kanal qo‘shish` da 3 qatorda yuboring:

```text
@kanal_username
https://t.me/kanal_username
Kanal nomi
```

Yopiq kanal uchun birinchi qatorda `-100...` raqamli chat ID va ikkinchisida haqiqiy taklif havolasi bo‘lsin. Bot kanal ID va o‘zining administratorligini tekshiradi. Taklif havolasining aynan shu kanalga tegishli ekanini admin tekshiradi.

Kanal sozlamasidan **Majburiy obuna** ni yoqing. Bir nechta kanal qo‘shish mumkin. Foydalanuvchi barcha kanallarga a’zo bo‘lib **Obunani tekshirish** ni bossa, saqlangan kino so‘rovi avtomatik davom etadi. Tekshiruv API xatosi bilan tugasa bot kirishni ochmaydi. Join request yuborishning o‘zi a’zolik hisoblanmaydi — so‘rov qabul qilinishi kerak.

## 5. Kanaldan avtomatik import

Faqat admin panelda qo‘shilgan va **Avtoimport** yoqilgan kanaldagi **yangi** video postlar o‘qiladi. Obuna kanali va import kanali bir xil yoki turlicha bo‘lishi mumkin.

Bitta postda bitta video, uning caption’i quyidagicha bo‘lsin (kalitlar aynan inglizcha):

```text
#kino
code: 101
title: Namuna kino
kind: movie
genre: Komediya
year: 2024
country: O‘zbekiston
description: Qisqa tavsif
duration: 95
language: O‘zbekcha
quality: 720p
```

Serial misoli:

```text
#kino
code: S101
title: Namuna serial
kind: series
genre: Drama
year: 2024
country: Turkiya
language: O‘zbekcha
quality: 720p
season: 1
episode: 2
```

`code`, `title`, `kind`, `language`, `quality` majburiy. Serial uchun `season`, `episode` ham majburiy. Ixtiyoriy `poster` va `trailer` maydonlariga HTTPS havola berish mumkin. Keyingi variant/qismda ayni kod, nom va tur yoziladi; mavjud kartochka ma’lumotlari avtomatik almashtirilmaydi. Bir xil post qayta kelganda qayta import qilinmaydi. Takroriy variant yoki boshqa nomga band kod bo‘lsa egaga xato xabari yuboriladi.

Eski kanal tarixini avtomatik o‘qish va postni tahrirlab katalogni yangilash kiritilmagan. Eski videoni yangi post qilib e’lon qilish yoki botga yuborish mumkin. `#kino` bo‘lmagan postlar e’tiborga olinmaydi. Xizmat videolarni yuklab olmaydi; shu botga tegishli Telegram `file_id` orqali qayta yuboradi. Telegram qabul qilmaydigan hajm/fayl yoki himoyalangan kontent cheklovlarini aylanib o‘tmaydi.

## 6. Admin rollari

| Imkoniyat | owner | manager | editor |
|---|---|---|---|
| Kino/video qo‘shish, tahrirlash, yashirish, o‘chirish, xatoliklarni ko‘rish | Ha | Ha | Ha |
| Kanallarni boshqarish | Ha | Ha | Yo‘q |
| Umumiy va kino statistikasi | Ha | Ha | Yo‘q |
| Ommaviy xabar va foydalanuvchini bloklash | Ha | Ha | Yo‘q |
| Adminlarni qo‘shish/rolini o‘zgartirish | Ha | Yo‘q | Yo‘q |
| Bot ichidan zaxira olish | Ha | Yo‘q | Yo‘q |

`owner` faqat `OWNER_IDS` orqali belgilanadi. `/admin → Administratorlar` orqali `123456789 editor` yoki `123456789 manager` yuboring. Admin botga `/start` yuborgan bo‘lishi kerak. Huquqlar har amalda qayta tekshiriladi; oddiy foydalanuvchi callback matnini o‘zgartirib admin huquqini ololmaydi.

## 7. Xabarnoma, e’lon va statistika

- Serial kartochkasidagi **Yangi qismlarni kuzatish** tugmasi kuzatuvni yoqadi/o‘chiradi. Yangi qism birinchi marta qo‘shilganda kuzatuvchilarga xabar navbatga tushadi. Shu qismga ikkinchi sifat qo‘shilsa yana xabar ketmaydi.
- Foydalanuvchi **Sozlamalar** dan ommaviy xabar va serial xabarnomalarini o‘chirishi mumkin. Oddiy kino so‘rovlari ishlashda davom etadi.
- **Ommaviy xabar**: bitta xabar yuboring → nusxasini ko‘ring → **Yuborish** tugmasini bosing. Tasdiqlashsiz tarqatilmaydi. Albom o‘rniga bitta xabar ishlating.
- Navbat SQLite’da saqlanadi; restartdan keyin davom etadi. Telegram `retry_after` ko‘rsatmasi bajariladi; vaqtinchalik xatolar ko‘pi bilan 5 urinishgacha qayta sinaladi. Har yuborishdan oldin blok, opt-out va admin vakolati yana tekshiriladi.
- Crash aynan Telegram xabarni qabul qilgan, lekin bazaga natija yozilmagan lahzada yuz bersa, bitta xabar qayta yuborilishi mumkin (at-least-once). Telegram’da bu holat uchun idempotency kaliti yo‘q.
- Yashirilgan/o‘chirilgan kinolar ochiq katalogdan va yuborishdan chiqadi; tegishli kutilayotgan serial xabarlari tashlab ketiladi. Oldin yuborilgan Telegram videolari qaytarib olinmaydi.
- “Ko‘rishlar” — **bot orqali muvaffaqiyatli video olishlar soni**, filmni oxirigacha tomosha qilish analitikasi emas. Umumiy son, noyob oluvchilar, baholar va kunlik faollik ko‘rsatiladi. Kunlik chegara `TIMEZONE` bo‘yicha.
- Spam limiti: har foydalanuvchi uchun 5 soniyada 8 amal. Limit bitta jarayon xotirasida saqlanadi.

## 8. Zaxira va tiklash

`/admin → Zaxira nusxa` — baza faylini egaga yuboradi. Katalog, Telegram file_id’lari, foydalanuvchilar, sozlamalar va tarix kiradi. Video baytlari va `.env` kirmaydi. Zaxira ayni bot tokeni bilan ishlatiladi; boshqa botga almashtirilsa file_id’larni qayta olish talab qilinishi mumkin.

Konsolda:

```bash
python backup.py backup kino-backup.db
# Botni to‘xtating, so‘ng:
python backup.py restore kino-backup.db
```

Tiklashdan oldin baza yaxlitligi va kerakli jadvallar tekshiriladi. Eski holat avtomatik `.before-restore-...db` fayliga saqlanadi. Ishlayotgan bot bor bo‘lsa tiklash bloklanadi. Tiklanganda eski e’lonlar qayta tarqalmasligi uchun kutilayotgan navbat va tugallanmagan draftlar bekor qilinadi. Bir xil botning bir xil sxemadagi zaxirasi uchun mo‘ljallangan.

## 9. Tanlangan 41 funksiyaning qamrovi

| № | Funksiya | Qayerda / ishlashi |
|---|---|---|
| 1 | Kod orqali kino | Oddiy matn yoki `/start film_KOD` |
| 4 | Janr | Bosh menyu → Janr |
| 6 | Ommabop | Muvaffaqiyatli yuborishlar bo‘yicha saralash |
| 8 | Yil | Bosh menyu → Yil |
| 9 | Davlat | Bosh menyu → Davlat |
| 10 | Til | Kino/qismning mavjud variantlari |
| 11 | Majburiy obuna | Kino va fayl yuborishdan oldin tekshiruv |
| 12 | Bir nechta kanal | Barcha required kanallar tekshiriladi |
| 13 | Qayta tekshirish | Obunani tekshirish tugmasi |
| 14 | Kanal boshqarish | Admin → Kanallar |
| 15 | Obunadan keyin davom | Bazadagi pending so‘rov |
| 16 | Kino havolasi | `https://t.me/BOT?start=film_KOD` |
| 17 | Do‘stga ulashish | Kartochkadagi ulashish tugmasi |
| 18 | Sevimlilar | Kartochka va bosh menyu |
| 19 | Tarix | Oxirgi olingan kino oldinda |
| 20 | Keyin ko‘raman | Kartochka va bosh menyu |
| 21 | Tugmali admin panel | `/admin` |
| 22 | Botga video yuklash | Ketma-ket qo‘shish jarayoni |
| 24 | Kanal avtoimporti | Ruxsatli kanaldagi yangi `#kino` postlari |
| 25 | Tahrirlash | Kod, nom, tavsif, janr, yil, davlat, poster, treyler va video |
| 26 | O‘chirish | Tasdiqlash bilan kino/video o‘chirish |
| 27 | Yashirish | Admin → kino → Yashirish/Ochish |
| 28 | Takroriy koddan himoya | SQLite UNIQUE va oldindan tekshiruv |
| 30 | Bir nechta admin | Ega panelidan |
| 31 | Admin huquqlari | owner / manager / editor |
| 32 | Seriallar | Alohida bo‘lim |
| 33 | Fasl va qism | Tugmalar va sahifalash |
| 34 | Yangi qism xabari | Kuzatuv + doimiy navbat |
| 35 | Sifat | Admin yuklagan video variantlari |
| 36 | Kartochka | Poster, nom, tavsif, yil, davomiylik |
| 37 | Treyler | HTTPS havolali tugma |
| 38 | Baho | 1–5; har user uchun bitta yangilanadigan baho |
| 40 | Xatolik yuborish | Kartochka → Xatolik, admin ro‘yxati |
| 42 | Umumiy statistika | Admin → Statistika |
| 43 | Kunlik faollik | Sana bo‘yicha noyob foydalanuvchilar |
| 44 | Kino statistikasi | Admin → kino → Statistika |
| 46 | Ommaviy xabar | Preview, tasdiqlash, navbat |
| 47 | Xabarlarni o‘chirish | Foydalanuvchi sozlamalari |
| 48 | Spamdan himoya | Message va callback middleware |
| 49 | Bloklash | Admin → Bloklash / ochish |
| 50 | Zaxira va tiklash | Admin backup + `backup.py restore` |

## 10. Tekshirish

```bash
python -m unittest discover -s tests -v
python -m compileall -q .
```

Testlar haqiqiy Telegram so‘rovlarini yubormaydi: Bot API javoblari test adapteri bilan almashtirilgan. Haqiqiy aiogram Dispatcher orqali deep-link va admin marshrutlari ham tekshiriladi. Qamrov: UNIQUE cheklovlar, tranzaksiya rollback, huquqlarni chetlab o‘tishga qarshi himoya, obuna statuslari/API xatosi, yashirilgan video, serial va sifatlar, avtoimport, navbatdagi opt-out/retry, zaxira/tiklash, spam va e’lonni ikki marta tasdiqlash.

Jonli tekshiruv: botni ishga tushiring → kichik sinov video qo‘shing → boshqa akkauntdan kod yuboring → obunasiz/obunali holatni tekshiring → 2 til/sifat qo‘shing → serialga kuzatuv qo‘yib yangi qism qo‘shing → restartdan so‘ng katalog saqlanganini tekshiring.

## Manbalar

- [aiogram rasmiy hujjatlari](https://docs.aiogram.dev/en/latest/)
- [Telegram getChatMember: boshqa foydalanuvchi a’zoligini tekshirish uchun bot administrator bo‘lishi kerak](https://core.telegram.org/bots/api#getchatmember)
- [Telegram Bot API: file_id va xabar yuborish](https://core.telegram.org/bots/api)
