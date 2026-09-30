import os
from datetime import datetime

import psycopg
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)


# =========================================================
# AYARLAR
# =========================================================

DATABASE_URL = os.environ.get("DATABASE_URL")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

WEBHOOK_URL = (
    "https://takim-yildizi-operasyon-bot.onrender.com"
)

PORT = int(os.environ.get("PORT", "10000"))

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL bulunamadi.")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN bulunamadi.")


# =========================================================
# POSTGRESQL
# =========================================================

def get_db():
    return psycopg.connect(DATABASE_URL)


def veritabani_hazirla():
    with get_db() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                CREATE TABLE IF NOT EXISTS siparisler (
                    id BIGSERIAL PRIMARY KEY,
                    siparis_metni TEXT NOT NULL,
                    durum TEXT NOT NULL DEFAULT 'ACIK',
                    eklenme_tarihi TIMESTAMP NOT NULL
                        DEFAULT CURRENT_TIMESTAMP,
                    alan_personel TEXT,
                    alinma_tarihi TIMESTAMP,
                    kargo_ucreti NUMERIC(15,2)
                )
            """)

            cur.execute("""
                ALTER TABLE siparisler
                ADD COLUMN IF NOT EXISTS odeme_tipi TEXT
            """)

            cur.execute("""
                ALTER TABLE siparisler
                ADD COLUMN IF NOT EXISTS iptal_tarihi TIMESTAMP
            """)

            cur.execute("""
                ALTER TABLE siparisler
                ADD COLUMN IF NOT EXISTS iptal_eden TEXT
            """)

            cur.execute("""
                ALTER TABLE siparisler
                ADD COLUMN IF NOT EXISTS karsi_odeme_telefon TEXT
            """)

            cur.execute("""
                ALTER TABLE siparisler
                ADD COLUMN IF NOT EXISTS tahsilat_durumu TEXT
            """)

            cur.execute("""
                ALTER TABLE siparisler
                ADD COLUMN IF NOT EXISTS tahsilat_tarihi TIMESTAMP
            """)

            cur.execute("""
                ALTER TABLE siparisler
                ADD COLUMN IF NOT EXISTS tahsil_eden TEXT
            """)


            cur.execute("""
                ALTER TABLE siparisler
                ADD COLUMN IF NOT EXISTS dekont_file_id TEXT
            """)

            cur.execute("""
                ALTER TABLE siparisler
                ADD COLUMN IF NOT EXISTS dekont_tipi TEXT
            """)

            cur.execute("""
                ALTER TABLE siparisler
                ADD COLUMN IF NOT EXISTS tahsilat_iban TEXT
            """)


            cur.execute("""
                CREATE TABLE IF NOT EXISTS toplu_gonderiler (
                    id BIGSERIAL PRIMARY KEY,
                    siparis_id BIGINT NOT NULL,
                    sehir TEXT NOT NULL,
                    kargo_ucreti NUMERIC(15,2) NOT NULL,
                    odeme_tipi TEXT NOT NULL,
                    eklenme_tarihi TIMESTAMP NOT NULL
                )
            """)

        conn.commit()


veritabani_hazirla()


# =========================================================
# DURUMLAR
# =========================================================

SIPARIS_METNI = 1

IS_ID = 10
KARGO_UCRETI = 12
GONDERI_TIPI = 13
TOPLU_GONDERILER = 14
KARSI_ODEME_TUTAR = 15
KARSI_ODEME_TELEFON = 16
TAHSILAT_ID = 17
TAHSILAT_ONAY = 18
TAHSILAT_DEKONT = 19
TAHSILAT_IBAN = 22

IPTAL_ID = 20
IPTAL_ONAY = 21


# =========================================================
# MENULER
# =========================================================

ana_menu = ReplyKeyboardMarkup(
    [
        ["➕ Sipariş Ekle"],
        ["📦 Açık İşler", "📥 İş Al"],
        ["🚚 Alınan İşler", "🗑 Sipariş İptal"],
        ["📲 Karşı Ödemeliler"],
        ["❓ Nasıl Kullanılır?"],
    ],
    resize_keyboard=True
)



iptal_onay_menu = ReplyKeyboardMarkup(
    [
        ["✅ İptal Et"],
        ["❌ Vazgeç"],
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)


islem_iptal_menu = ReplyKeyboardMarkup(
    [
        ["❌ İşlemden Vazgeç"],
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)


gonderi_tipi_menu = ReplyKeyboardMarkup(
    [
        ["📦 Tek Gönderi", "📦 Toplu Gönderi"],
        ["❌ İşlemden Vazgeç"],
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)


tek_gonderi_odeme_menu = ReplyKeyboardMarkup(
    [
        ["📲 Karşı Ödemeli"],
        ["❌ İşlemden Vazgeç"],
    ],
    resize_keyboard=True
)


tahsilat_onay_menu = ReplyKeyboardMarkup(
    [
        ["✅ Tahsil Edildi"],
        ["❌ İşlemden Vazgeç"],
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)


tahsilat_iban_menu = ReplyKeyboardMarkup(
    [
        ["Esma", "Hasan", "Berhan"],
        ["❌ İşlemden Vazgeç"],
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)


# =========================================================
# YARDIMCI FONKSIYONLAR
# =========================================================

def tutar_cevir(text):
    text = (
        text.strip()
        .replace("₺", "")
        .replace("TL", "")
        .replace("tl", "")
        .replace(" ", "")
    )

    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")

    elif "," in text:
        text = text.replace(",", ".")

    elif "." in text:
        parcalar = text.split(".")

        if len(parcalar[-1]) == 3:
            text = text.replace(".", "")

    tutar = float(text)

    if tutar == 0:
        raise ValueError

    return tutar


def acik_siparis_getir(siparis_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    siparis_metni,
                    eklenme_tarihi
                FROM siparisler
                WHERE id = %s
                  AND durum = 'ACIK'
                """,
                (siparis_id,)
            )

            return cur.fetchone()


def kullanici_adi_getir(update):
    kullanici = update.effective_user

    if kullanici.full_name:
        return kullanici.full_name

    if kullanici.username:
        return f"@{kullanici.username}"

    return str(kullanici.id)


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    context.user_data.clear()

    await update.message.reply_text(
        "🚚 TAKIM YILDIZI OPERASYON\n\n"
        "Gündüz kargo operasyon sistemi\n\n"
        "Yapmak istediğiniz işlemi seçiniz:",
        reply_markup=ana_menu
    )


# =========================================================
# NASIL KULLANILIR
# =========================================================

async def nasil_kullanilir(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    mesaj = (
        "❓ TAKIM YILDIZI OPERASYON — KULLANIM\n\n"

        "📦 AÇIK İŞLER\n"
        "Henüz alınmamış işleri görmek için "
        "📦 Açık İşler butonuna basın.\n\n"

        "📥 İŞ ALMA\n"
        "1️⃣ 📥 İş Al butonuna basın.\n"
        "2️⃣ Aldığınız işin ID numarasını yazın.\n"
        "3️⃣ Tek Gönderi veya Toplu Gönderi seçin.\n"
        "4️⃣ Tek gönderide nakit/vadeli tutarı yazın veya 📲 Karşı Ödemeli seçin.\n"
        "5️⃣ Toplu gönderide şehir ve ücretleri alt alta yazın.\n\n"

        "💰 KARGO ÜCRETİ\n"
        "💵 Nakit aldıysanız tutarı normal yazın.\n\n"
        "📒 Vadeli / cari ise tutarı eksi olarak yazın.\n\n"

        "✅ İş alındığında otomatik olarak "
        "Açık İşler listesinden çıkar.\n\n"

        "🚚 ALINAN İŞLER\n"
        "Alınan işleri, alan personeli, ödeme tipini "
        "ve kargo ücretini buradan görebilirsiniz.\n\n"

        "🗑 SİPARİŞ İPTAL\n"
        "Müşteri siparişten vazgeçtiyse "
        "🗑 Sipariş İptal butonunu kullanın.\n\n"

        "⚠️ Bir işi almadan önce doğru ID numarasını "
        "seçtiğinizden emin olun.\n\n"

        "TAKIM YILDIZI LOJİSTİK 🚚"
    )

    await update.message.reply_text(
        mesaj,
        reply_markup=ana_menu
    )


# =========================================================
# SIPARIS EKLE
# =========================================================

async def siparis_baslat(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    context.user_data.clear()

    await update.message.reply_text(
        "📦 Sipariş bilgisini yazınız.\n\n"
        
        "Yeni müşteriyse adres ve telefon gibi "
        "bilgileri aynı mesajın içine ekleyebilirsiniz.",
        reply_markup=islem_iptal_menu
    )

    return SIPARIS_METNI


async def siparis_kaydet(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    siparis_metni = update.message.text.strip()

    if not siparis_metni:
        await update.message.reply_text(
            "❌ Sipariş bilgisi boş olamaz."
        )
        return SIPARIS_METNI

    tarih = datetime.now()

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO siparisler
                (
                    siparis_metni,
                    durum,
                    eklenme_tarihi
                )
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (
                    siparis_metni,
                    "ACIK",
                    tarih
                )
            )

            siparis_id = cur.fetchone()[0]

        conn.commit()

    await update.message.reply_text(
        "✅ SİPARİŞ EKLENDİ\n\n"
        f"🆔 #{siparis_id}\n"
        f"📦 {siparis_metni}",
        reply_markup=ana_menu
    )

    context.user_data.clear()

    return ConversationHandler.END


# =========================================================
# ACIK ISLER
# =========================================================

async def acik_isler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    siparis_metni
                FROM siparisler
                WHERE durum = 'ACIK'
                ORDER BY id ASC
            """)

            kayitlar = cur.fetchall()

    if not kayitlar:
        await update.message.reply_text(
            "✅ Şu anda bekleyen açık iş yok.",
            reply_markup=ana_menu
        )
        return

    mesaj = (
        f"📦 AÇIK İŞLER — {len(kayitlar)} ADET\n\n"
    )

    for siparis_id, siparis_metni in kayitlar:
        mesaj += (
            f"🆔 #{siparis_id}\n"
            f"📦 {siparis_metni}\n"
            "────────────\n"
        )

    await update.message.reply_text(
        mesaj,
        reply_markup=ana_menu
    )


# =========================================================
# IS AL
# =========================================================

async def is_al_baslat(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    context.user_data.clear()

    await update.message.reply_text(
        "📥 ALINACAK İŞ\n\n"
        "Aldığınız siparişin 🆔 numarasını yazınız.\n\n"
        
    )

    return IS_ID


async def is_id_al(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        siparis_id = int(update.message.text.strip())

    except ValueError:
        await update.message.reply_text(
            "❌ Geçerli bir sipariş numarası yazınız.\n"
            
        )
        return IS_ID

    siparis = acik_siparis_getir(siparis_id)

    if not siparis:
        await update.message.reply_text(
            "❌ Bu numarada açık bir iş bulunamadı.\n\n"
            "Sipariş alınmış, iptal edilmiş veya "
            "numara yanlış olabilir.",
            reply_markup=ana_menu
        )

        context.user_data.clear()

        return ConversationHandler.END

    context.user_data["siparis_id"] = siparis_id
    _, siparis_metni, _ = siparis

    await update.message.reply_text(
        "📦 SEÇİLEN İŞ\n\n"
        f"🆔 #{siparis_id}\n"
        f"📦 {siparis_metni}\n\n"
        "Gönderi tipini seçiniz.",
        reply_markup=gonderi_tipi_menu
    )

    return GONDERI_TIPI


async def gonderi_tipi_sec(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    secim = update.message.text.strip()

    if secim == "📦 Tek Gönderi":
        await update.message.reply_text(
            "💰 Kargo ücretini yazınız.\n\n"
            "💵 Nakit ise tutarı normal yazın.\n"
            "📒 Vadeli / cari ise tutarı eksi olarak yazın.\n\n"
            "📲 Karşı ödemeli ise aşağıdaki butona basın.",
            reply_markup=tek_gonderi_odeme_menu
        )
        return KARGO_UCRETI

    if secim == "📦 Toplu Gönderi":
        await update.message.reply_text(
            "📦 TOPLU GÖNDERİ\n\n"
            "Şehir ve ücretleri alt alta yazınız.\n"
            "Her satırda önce şehir, sonra tutar olmalıdır.\n\n"
            "💵 Nakit tutarı normal yazın.\n"
            "📒 Vadeli / cari tutarı eksi olarak yazın.",
            reply_markup=islem_iptal_menu
        )
        return TOPLU_GONDERILER

    await update.message.reply_text(
        "Lütfen gönderi tipini butonlardan seçiniz.",
        reply_markup=gonderi_tipi_menu
    )
    return GONDERI_TIPI


async def kargo_ucreti_al(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if update.message.text.strip() == "📲 Karşı Ödemeli":
        await update.message.reply_text(
            "📲 KARŞI ÖDEMELİ\n\n"
            "💰 Kargo ücretini yazınız.",
            reply_markup=islem_iptal_menu
        )
        return KARSI_ODEME_TUTAR

    try:
        kargo_ucreti = tutar_cevir(
            update.message.text
        )

    except ValueError:
        await update.message.reply_text(
            "❌ Kargo ücretini anlayamadım.\n\n"
            
        )
        return KARGO_UCRETI

    if kargo_ucreti > 0:
        odeme_tipi = "NAKİT"
    else:
        odeme_tipi = "VADELİ"

    siparis_id = context.user_data["siparis_id"]

    personel = kullanici_adi_getir(update)
    alinma_tarihi = datetime.now()

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE siparisler
                SET
                    durum = 'ALINDI',
                    alan_personel = %s,
                    alinma_tarihi = %s,
                    kargo_ucreti = %s,
                    odeme_tipi = %s
                WHERE id = %s
                  AND durum = 'ACIK'
                RETURNING siparis_metni
                """,
                (
                    personel,
                    alinma_tarihi,
                    kargo_ucreti,
                    odeme_tipi,
                    siparis_id
                )
            )

            sonuc = cur.fetchone()

        conn.commit()

    if not sonuc:
        context.user_data.clear()

        await update.message.reply_text(
            "⚠️ Bu iş siz işlem yaparken başka bir "
            "personel tarafından alınmış veya iptal edilmiş.\n\n"
            "📦 Açık İşler listesini tekrar kontrol edin.",
            reply_markup=ana_menu
        )

        return ConversationHandler.END

    siparis_metni = sonuc[0]

    await update.message.reply_text(
        "✅ İŞ ALINDI\n\n"
        f"🆔 #{siparis_id}\n"
        f"📦 {siparis_metni}\n"
        f"👤 Alan: {personel}\n"
        f"💳 Ödeme Tipi: {odeme_tipi}\n"
        f"💰 Kargo Ücreti: {abs(kargo_ucreti):,.2f} ₺\n"
        f"🕐 Saat: {alinma_tarihi.strftime('%H:%M')}\n\n"
        "Bu iş artık Açık İşler listesinden çıkarıldı.",
        reply_markup=ana_menu
    )

    context.user_data.clear()

    return ConversationHandler.END


async def karsi_odeme_tutar_al(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        tutar = abs(tutar_cevir(update.message.text))
    except ValueError:
        await update.message.reply_text(
            "❌ Kargo ücretini anlayamadım.\n\n"
            "Lütfen sadece tutarı yazınız.",
            reply_markup=islem_iptal_menu
        )
        return KARSI_ODEME_TUTAR

    context.user_data["karsi_odeme_tutar"] = tutar

    await update.message.reply_text(
        "📞 Karşı taraftan ödeme alınacak telefon numarasını yazınız.",
        reply_markup=islem_iptal_menu
    )

    return KARSI_ODEME_TELEFON


async def karsi_odeme_telefon_al(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    telefon = update.message.text.strip()

    rakamlar = "".join(ch for ch in telefon if ch.isdigit())

    if len(rakamlar) < 10 or len(rakamlar) > 13:
        await update.message.reply_text(
            "❌ Telefon numarasını anlayamadım.\n\n"
            "Lütfen telefon numarasını tekrar yazınız.",
            reply_markup=islem_iptal_menu
        )
        return KARSI_ODEME_TELEFON

    siparis_id = context.user_data["siparis_id"]
    tutar = context.user_data["karsi_odeme_tutar"]
    personel = kullanici_adi_getir(update)
    alinma_tarihi = datetime.now()

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE siparisler
                SET
                    durum = 'ALINDI',
                    alan_personel = %s,
                    alinma_tarihi = %s,
                    kargo_ucreti = %s,
                    odeme_tipi = 'KARŞI ÖDEMELİ',
                    karsi_odeme_telefon = %s,
                    tahsilat_durumu = 'BEKLİYOR'
                WHERE id = %s
                  AND durum = 'ACIK'
                RETURNING siparis_metni
                """,
                (
                    personel,
                    alinma_tarihi,
                    tutar,
                    telefon,
                    siparis_id
                )
            )
            sonuc = cur.fetchone()

        conn.commit()

    if not sonuc:
        context.user_data.clear()
        await update.message.reply_text(
            "⚠️ Bu iş siz işlem yaparken başka bir personel "
            "tarafından alınmış veya iptal edilmiş.\n\n"
            "📦 Açık İşler listesini tekrar kontrol edin.",
            reply_markup=ana_menu
        )
        return ConversationHandler.END

    siparis_metni = sonuc[0]

    await update.message.reply_text(
        "✅ İŞ ALINDI\n\n"
        f"🆔 #{siparis_id}\n"
        f"📦 {siparis_metni}\n"
        f"👤 Alan: {personel}\n"
        "💳 Ödeme Tipi: KARŞI ÖDEMELİ\n"
        f"💰 Kargo Ücreti: {tutar:,.2f} ₺\n"
        f"📞 Telefon: {telefon}\n"
        "⏳ Tahsilat Durumu: BEKLİYOR\n"
        f"🕐 Saat: {alinma_tarihi.strftime('%H:%M')}\n\n"
        "Bu iş artık Açık İşler listesinden çıkarıldı.",
        reply_markup=ana_menu
    )

    context.user_data.clear()
    return ConversationHandler.END


async def toplu_gonderiler_al(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    satirlar = [
        satir.strip()
        for satir in update.message.text.splitlines()
        if satir.strip()
    ]

    if not satirlar:
        await update.message.reply_text(
            "❌ Gönderi bilgisi boş olamaz.",
            reply_markup=islem_iptal_menu
        )
        return TOPLU_GONDERILER

    gonderiler = []

    for satir in satirlar:
        parcalar = satir.rsplit(maxsplit=1)

        if len(parcalar) != 2:
            await update.message.reply_text(
                f"❌ Bu satırı anlayamadım:\n{satir}\n\n"
                "Her satırda önce şehir, sonra tutar yazınız.",
                reply_markup=islem_iptal_menu
            )
            return TOPLU_GONDERILER

        sehir, tutar_metni = parcalar

        try:
            tutar = tutar_cevir(tutar_metni)
        except ValueError:
            await update.message.reply_text(
                f"❌ Bu satırdaki tutarı anlayamadım:\n{satir}",
                reply_markup=islem_iptal_menu
            )
            return TOPLU_GONDERILER

        odeme_tipi = "NAKİT" if tutar > 0 else "VADELİ"
        gonderiler.append((sehir, tutar, odeme_tipi))

    siparis_id = context.user_data["siparis_id"]
    personel = kullanici_adi_getir(update)
    alinma_tarihi = datetime.now()

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE siparisler
                SET
                    durum = 'ALINDI',
                    alan_personel = %s,
                    alinma_tarihi = %s,
                    kargo_ucreti = %s,
                    odeme_tipi = %s
                WHERE id = %s
                  AND durum = 'ACIK'
                RETURNING siparis_metni
                """,
                (
                    personel,
                    alinma_tarihi,
                    sum(tutar for _, tutar, _ in gonderiler),
                    "TOPLU",
                    siparis_id
                )
            )
            sonuc = cur.fetchone()

            if sonuc:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS toplu_gonderiler (
                        id BIGSERIAL PRIMARY KEY,
                        siparis_id BIGINT NOT NULL,
                        sehir TEXT NOT NULL,
                        kargo_ucreti NUMERIC(15,2) NOT NULL,
                        odeme_tipi TEXT NOT NULL,
                        eklenme_tarihi TIMESTAMP NOT NULL
                    )
                """)

                for sehir, tutar, odeme_tipi in gonderiler:
                    cur.execute(
                        """
                        INSERT INTO toplu_gonderiler
                        (
                            siparis_id,
                            sehir,
                            kargo_ucreti,
                            odeme_tipi,
                            eklenme_tarihi
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            siparis_id,
                            sehir,
                            tutar,
                            odeme_tipi,
                            alinma_tarihi
                        )
                    )

        conn.commit()

    if not sonuc:
        context.user_data.clear()
        await update.message.reply_text(
            "⚠️ Bu iş siz işlem yaparken başka bir personel "
            "tarafından alınmış veya iptal edilmiş.",
            reply_markup=ana_menu
        )
        return ConversationHandler.END

    siparis_metni = sonuc[0]
    nakit_toplam = sum(
        abs(tutar) for _, tutar, tip in gonderiler if tip == "NAKİT"
    )
    vadeli_toplam = sum(
        abs(tutar) for _, tutar, tip in gonderiler if tip == "VADELİ"
    )

    mesaj = (
        "✅ TOPLU İŞ ALINDI\n\n"
        f"🆔 #{siparis_id}\n"
        f"📦 {siparis_metni}\n"
        f"👤 Alan: {personel}\n\n"
    )

    for sehir, tutar, odeme_tipi in gonderiler:
        mesaj += (
            f"📍 {sehir} — {abs(tutar):,.2f} ₺ — {odeme_tipi}\n"
        )

    mesaj += (
        f"\n📦 {len(gonderiler)} gönderi\n"
        f"💵 Nakit Toplam: {nakit_toplam:,.2f} ₺\n"
        f"📒 Vadeli Toplam: {vadeli_toplam:,.2f} ₺\n"
        f"💰 Genel Toplam: {nakit_toplam + vadeli_toplam:,.2f} ₺"
    )

    context.user_data.clear()

    await update.message.reply_text(
        mesaj,
        reply_markup=ana_menu
    )

    return ConversationHandler.END


async def karsi_odemeliler_baslat(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    context.user_data.clear()

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    siparis_metni,
                    kargo_ucreti,
                    karsi_odeme_telefon,
                    alan_personel,
                    alinma_tarihi
                FROM siparisler
                WHERE odeme_tipi = 'KARŞI ÖDEMELİ'
                  AND COALESCE(tahsilat_durumu, 'BEKLİYOR') = 'BEKLİYOR'
                ORDER BY id ASC
                """
            )
            kayitlar = cur.fetchall()

    if not kayitlar:
        await update.message.reply_text(
            "✅ Bekleyen karşı ödemeli tahsilat bulunmuyor.",
            reply_markup=ana_menu
        )
        return ConversationHandler.END

    mesaj = "📲 BEKLEYEN KARŞI ÖDEMELİLER\n\n"

    for (
        siparis_id,
        siparis_metni,
        kargo_ucreti,
        telefon,
        personel,
        alinma_tarihi
    ) in kayitlar:
        mesaj += (
            f"🆔 #{siparis_id}\n"
            f"📦 {siparis_metni}\n"
            f"💰 {abs(float(kargo_ucreti or 0)):,.2f} ₺\n"
            f"📞 {telefon or '-'}\n"
            f"👤 İşi alan: {personel or '-'}\n"
            "⏳ Tahsilat: BEKLİYOR\n"
        )

        if alinma_tarihi:
            mesaj += f"🕐 {alinma_tarihi.strftime('%d.%m.%Y %H:%M')}\n"

        mesaj += "\n"

    mesaj += "Tahsil edilen siparişin ID numarasını yazınız."

    await update.message.reply_text(
        mesaj,
        reply_markup=islem_iptal_menu
    )

    return TAHSILAT_ID


async def tahsilat_id_al(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        siparis_id = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(
            "❌ Geçerli bir sipariş ID numarası yazınız.",
            reply_markup=islem_iptal_menu
        )
        return TAHSILAT_ID

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    siparis_metni,
                    kargo_ucreti,
                    karsi_odeme_telefon
                FROM siparisler
                WHERE id = %s
                  AND odeme_tipi = 'KARŞI ÖDEMELİ'
                  AND COALESCE(tahsilat_durumu, 'BEKLİYOR') = 'BEKLİYOR'
                """,
                (siparis_id,)
            )
            kayit = cur.fetchone()

    if not kayit:
        await update.message.reply_text(
            "❌ Bu ID ile bekleyen karşı ödemeli kayıt bulunamadı.",
            reply_markup=islem_iptal_menu
        )
        return TAHSILAT_ID

    siparis_metni, tutar, telefon = kayit
    context.user_data["tahsilat_siparis_id"] = siparis_id

    await update.message.reply_text(
        "📲 TAHSİLAT ONAYI\n\n"
        f"🆔 #{siparis_id}\n"
        f"📦 {siparis_metni}\n"
        f"💰 {abs(float(tutar or 0)):,.2f} ₺\n"
        f"📞 {telefon or '-'}\n\n"
        "Para IBAN'a geldiyse aşağıdaki butona basınız.",
        reply_markup=tahsilat_onay_menu
    )

    return TAHSILAT_ONAY


async def tahsilat_onayla(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if update.message.text.strip() != "✅ Tahsil Edildi":
        await update.message.reply_text(
            "Lütfen işlemi butondan onaylayınız.",
            reply_markup=tahsilat_onay_menu
        )
        return TAHSILAT_ONAY

    siparis_id = context.user_data.get("tahsilat_siparis_id")

    if not siparis_id:
        context.user_data.clear()
        await update.message.reply_text(
            "❌ Tahsilat kaydı bulunamadı. İşlemi yeniden başlatın.",
            reply_markup=ana_menu
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "🧾 DEKONT GEREKLİ\n\n"
        "Ödemenin dekontunu şimdi gönderiniz.\n\n"
        "📷 Fotoğraf veya 📄 PDF kabul edilir.\n"
        "Dekont yüklenmeden tahsilat tamamlanmaz.",
        reply_markup=islem_iptal_menu
    )

    return TAHSILAT_DEKONT


async def tahsilat_dekont_al(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    mesaj = update.message

    if mesaj.photo:
        file_id = mesaj.photo[-1].file_id
        dekont_tipi = "FOTOĞRAF"

    elif (
        mesaj.document
        and mesaj.document.mime_type == "application/pdf"
    ):
        file_id = mesaj.document.file_id
        dekont_tipi = "PDF"

    else:
        await mesaj.reply_text(
            "❌ Lütfen dekontu fotoğraf veya PDF olarak gönderiniz.",
            reply_markup=islem_iptal_menu
        )
        return TAHSILAT_DEKONT

    context.user_data["dekont_file_id"] = file_id
    context.user_data["dekont_tipi"] = dekont_tipi

    await mesaj.reply_text(
        "🏦 Ödeme hangi IBAN'a geldi?",
        reply_markup=tahsilat_iban_menu
    )

    return TAHSILAT_IBAN


async def tahsilat_iban_sec(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    iban_sahibi = update.message.text.strip()

    if iban_sahibi not in {"Esma", "Hasan", "Berhan"}:
        await update.message.reply_text(
            "Lütfen IBAN sahibini butonlardan seçiniz.",
            reply_markup=tahsilat_iban_menu
        )
        return TAHSILAT_IBAN

    siparis_id = context.user_data.get("tahsilat_siparis_id")
    file_id = context.user_data.get("dekont_file_id")
    dekont_tipi = context.user_data.get("dekont_tipi")

    if not siparis_id or not file_id or not dekont_tipi:
        context.user_data.clear()
        await update.message.reply_text(
            "❌ Tahsilat bilgileri eksik. İşlemi yeniden başlatın.",
            reply_markup=ana_menu
        )
        return ConversationHandler.END

    tahsil_eden = kullanici_adi_getir(update)
    tahsilat_tarihi = datetime.now()

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE siparisler
                SET
                    tahsilat_durumu = 'TAHSİL EDİLDİ',
                    tahsilat_tarihi = %s,
                    tahsil_eden = %s,
                    dekont_file_id = %s,
                    dekont_tipi = %s,
                    tahsilat_iban = %s
                WHERE id = %s
                  AND odeme_tipi = 'KARŞI ÖDEMELİ'
                  AND COALESCE(tahsilat_durumu, 'BEKLİYOR') = 'BEKLİYOR'
                RETURNING
                    siparis_metni,
                    kargo_ucreti,
                    karsi_odeme_telefon
                """,
                (
                    tahsilat_tarihi,
                    tahsil_eden,
                    file_id,
                    dekont_tipi,
                    iban_sahibi,
                    siparis_id
                )
            )
            sonuc = cur.fetchone()

        conn.commit()

    if not sonuc:
        context.user_data.clear()
        await update.message.reply_text(
            "⚠️ Bu tahsilat daha önce tamamlanmış olabilir. "
            "Bekleyen listeyi tekrar kontrol edin.",
            reply_markup=ana_menu
        )
        return ConversationHandler.END

    siparis_metni, tutar, telefon = sonuc

    await update.message.reply_text(
        "✅ TAHSİLAT TAMAMLANDI\n\n"
        f"🆔 #{siparis_id}\n"
        f"📦 {siparis_metni}\n"
        f"💰 {abs(float(tutar or 0)):,.2f} ₺\n"
        f"📞 {telefon or '-'}\n"
        f"🏦 IBAN: {iban_sahibi}\n"
        f"🧾 Dekont: {dekont_tipi} kaydedildi\n"
        f"👤 İşlemi yapan: {tahsil_eden}\n"
        f"🕐 {tahsilat_tarihi.strftime('%d.%m.%Y %H:%M')}\n\n"
        "Kayıt bekleyen karşı ödemeliler listesinden çıkarıldı.",
        reply_markup=ana_menu
    )

    context.user_data.clear()
    return ConversationHandler.END


# =========================================================
# SIPARIS IPTAL
# =========================================================

async def siparis_iptal_baslat(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    context.user_data.clear()

    await update.message.reply_text(
        "🗑 SİPARİŞ İPTAL\n\n"
        "İptal edilecek açık siparişin 🆔 "
        "numarasını yazınız.\n\n"
        
    )

    return IPTAL_ID


async def siparis_iptal_id_al(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        siparis_id = int(update.message.text.strip())

    except ValueError:
        await update.message.reply_text(
            "❌ Geçerli bir sipariş numarası yazınız.\n"
            
        )
        return IPTAL_ID

    siparis = acik_siparis_getir(siparis_id)

    if not siparis:
        await update.message.reply_text(
            "❌ Bu numarada açık bir sipariş bulunamadı.\n\n"
            "Sipariş daha önce alınmış, iptal edilmiş "
            "veya numara yanlış olabilir.",
            reply_markup=ana_menu
        )

        context.user_data.clear()

        return ConversationHandler.END

    context.user_data["iptal_siparis_id"] = siparis_id

    _, siparis_metni, _ = siparis

    await update.message.reply_text(
        "⚠️ İPTAL ONAYI\n\n"
        f"🆔 #{siparis_id}\n"
        f"📦 {siparis_metni}\n\n"
        "Bu siparişi iptal etmek istediğinize emin misiniz?",
        reply_markup=iptal_onay_menu
    )

    return IPTAL_ONAY


async def siparis_iptal_onayla(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    secim = update.message.text.strip()

    if secim == "❌ Vazgeç":
        context.user_data.clear()

        await update.message.reply_text(
            "✅ Sipariş iptal edilmedi.",
            reply_markup=ana_menu
        )

        return ConversationHandler.END

    if secim != "✅ İptal Et":
        await update.message.reply_text(
            "Lütfen butonlardan seçim yapınız.",
            reply_markup=iptal_onay_menu
        )
        return IPTAL_ONAY

    siparis_id = context.user_data["iptal_siparis_id"]
    iptal_eden = kullanici_adi_getir(update)
    iptal_tarihi = datetime.now()

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE siparisler
                SET
                    durum = 'IPTAL',
                    iptal_tarihi = %s,
                    iptal_eden = %s
                WHERE id = %s
                  AND durum = 'ACIK'
                RETURNING siparis_metni
                """,
                (
                    iptal_tarihi,
                    iptal_eden,
                    siparis_id
                )
            )

            sonuc = cur.fetchone()

        conn.commit()

    context.user_data.clear()

    if not sonuc:
        await update.message.reply_text(
            "⚠️ Bu sipariş siz işlem yaparken başka bir "
            "personel tarafından alınmış veya iptal edilmiş.\n\n"
            "📦 Açık İşler listesini tekrar kontrol edin.",
            reply_markup=ana_menu
        )

        return ConversationHandler.END

    siparis_metni = sonuc[0]

    await update.message.reply_text(
        "🗑 SİPARİŞ İPTAL EDİLDİ\n\n"
        f"🆔 #{siparis_id}\n"
        f"📦 {siparis_metni}\n\n"
        "Sipariş Açık İşler listesinden çıkarıldı.",
        reply_markup=ana_menu
    )

    return ConversationHandler.END


# =========================================================
# ALINAN ISLER
# =========================================================

async def alinan_isler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    siparis_metni,
                    alan_personel,
                    kargo_ucreti,
                    odeme_tipi,
                    alinma_tarihi,
                    karsi_odeme_telefon,
                    tahsilat_durumu
                FROM siparisler
                WHERE durum = 'ALINDI'
                ORDER BY alinma_tarihi DESC
                LIMIT 50
            """)

            kayitlar = cur.fetchall()

    if not kayitlar:
        await update.message.reply_text(
            "🚚 Henüz alınan iş bulunmuyor.",
            reply_markup=ana_menu
        )
        return

    mesaj = (
        f"🚚 ALINAN İŞLER — {len(kayitlar)} ADET\n\n"
    )

    toplam = 0
    nakit_toplam = 0
    vadeli_toplam = 0
    karsi_odeme_toplam = 0

    for (
        siparis_id,
        siparis_metni,
        personel,
        kargo_ucreti,
        odeme_tipi,
        alinma_tarihi,
        karsi_odeme_telefon,
        tahsilat_durumu
    ) in kayitlar:

        ucret = abs(float(kargo_ucreti or 0))

        if odeme_tipi != "TOPLU":
            toplam += ucret

            if odeme_tipi == "NAKİT":
                nakit_toplam += ucret
            elif odeme_tipi == "VADELİ":
                vadeli_toplam += ucret
            elif odeme_tipi == "KARŞI ÖDEMELİ":
                karsi_odeme_toplam += ucret

        mesaj += (
            f"🆔 #{siparis_id}\n"
            f"📦 {siparis_metni}\n"
            f"👤 {personel or '-'}\n"
        )

        if odeme_tipi == "TOPLU":
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT sehir, kargo_ucreti, odeme_tipi
                        FROM toplu_gonderiler
                        WHERE siparis_id = %s
                        ORDER BY id ASC
                        """,
                        (siparis_id,)
                    )
                    alt_gonderiler = cur.fetchall()

            for sehir, alt_tutar, alt_tip in alt_gonderiler:
                mesaj += (
                    f"📍 {sehir} — {abs(float(alt_tutar)):,.2f} ₺ "
                    f"— {alt_tip}\n"
                )

            ucret = sum(abs(float(x[1])) for x in alt_gonderiler)
            nakit_toplam += sum(
                abs(float(x[1])) for x in alt_gonderiler
                if x[2] == "NAKİT"
            )
            vadeli_toplam += sum(
                abs(float(x[1])) for x in alt_gonderiler
                if x[2] == "VADELİ"
            )
            toplam += ucret
        else:
            mesaj += (
                f"💳 {odeme_tipi or '-'}\n"
                f"💰 {ucret:,.2f} ₺\n"
            )

            if odeme_tipi == "KARŞI ÖDEMELİ":
                mesaj += (
                    f"📞 {karsi_odeme_telefon or '-'}\n"
                    f"⏳ Tahsilat: {tahsilat_durumu or 'BEKLİYOR'}\n"
                )

        if alinma_tarihi:
            mesaj += (
                f"🕐 {alinma_tarihi.strftime('%H:%M')}\n"
            )

        mesaj += "────────────\n"

    mesaj += (
        "\n💰 GÜN SONU TOPLAMLARI\n\n"
        f"💵 NAKİT: {nakit_toplam:,.2f} ₺\n"
        f"📒 VADELİ: {vadeli_toplam:,.2f} ₺\n"
        f"📲 KARŞI ÖDEMELİ: {karsi_odeme_toplam:,.2f} ₺\n"
        f"💰 TOPLAM: {toplam:,.2f} ₺"
    )

    await update.message.reply_text(
        mesaj,
        reply_markup=ana_menu
    )


# =========================================================
# GENEL IPTAL
# =========================================================

async def iptal(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    context.user_data.clear()

    await update.message.reply_text(
        "❌ İşlem iptal edildi. Ana menüye dönüldü.",
        reply_markup=ana_menu
    )

    return ConversationHandler.END


# =========================================================
# MAIN
# =========================================================

def main():
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    siparis_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("^➕ Sipariş Ekle$"),
                siparis_baslat
            )
        ],

        states={
            SIPARIS_METNI: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ İşlemden Vazgeç$"),
                    siparis_kaydet
                )
            ],
        },

        fallbacks=[
            MessageHandler(
                filters.Regex("^❌ İşlemden Vazgeç$"),
                iptal
            ),
            CommandHandler("iptal", iptal)
        ],
    )

    is_al_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("^📥 İş Al$"),
                is_al_baslat
            )
        ],

        states={
            IS_ID: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ İşlemden Vazgeç$"),
                    is_id_al
                )
            ],


            GONDERI_TIPI: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ İşlemden Vazgeç$"),
                    gonderi_tipi_sec
                )
            ],

            KARGO_UCRETI: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ İşlemden Vazgeç$"),
                    kargo_ucreti_al
                )
            ],

            KARSI_ODEME_TUTAR: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ İşlemden Vazgeç$"),
                    karsi_odeme_tutar_al
                )
            ],

            KARSI_ODEME_TELEFON: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ İşlemden Vazgeç$"),
                    karsi_odeme_telefon_al
                )
            ],

            TOPLU_GONDERILER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ İşlemden Vazgeç$"),
                    toplu_gonderiler_al
                )
            ],
        },

        fallbacks=[
            MessageHandler(
                filters.Regex("^❌ İşlemden Vazgeç$"),
                iptal
            ),
            CommandHandler("iptal", iptal)
        ],
    )

    tahsilat_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("^📲 Karşı Ödemeliler$"),
                karsi_odemeliler_baslat
            )
        ],

        states={
            TAHSILAT_ID: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ İşlemden Vazgeç$"),
                    tahsilat_id_al
                )
            ],

            TAHSILAT_ONAY: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ İşlemden Vazgeç$"),
                    tahsilat_onayla
                )
            ],


            TAHSILAT_DEKONT: [
                MessageHandler(
                    (filters.PHOTO | filters.Document.PDF),
                    tahsilat_dekont_al
                )
            ],

            TAHSILAT_IBAN: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ İşlemden Vazgeç$"),
                    tahsilat_iban_sec
                )
            ],
        },

        fallbacks=[
            MessageHandler(
                filters.Regex("^❌ İşlemden Vazgeç$"),
                iptal
            ),
            CommandHandler("iptal", iptal)
        ],
    )

    siparis_iptal_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("^🗑 Sipariş İptal$"),
                siparis_iptal_baslat
            )
        ],

        states={
            IPTAL_ID: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ İşlemden Vazgeç$"),
                    siparis_iptal_id_al
                )
            ],

            IPTAL_ONAY: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ İşlemden Vazgeç$"),
                    siparis_iptal_onayla
                )
            ],
        },

        fallbacks=[
            MessageHandler(
                filters.Regex("^❌ İşlemden Vazgeç$"),
                iptal
            ),
            CommandHandler("iptal", iptal)
        ],
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        siparis_conversation
    )

    application.add_handler(
        is_al_conversation
    )

    application.add_handler(
        tahsilat_conversation
    )

    application.add_handler(
        siparis_iptal_conversation
    )

    application.add_handler(
        MessageHandler(
            filters.Regex("^📦 Açık İşler$"),
            acik_isler
        )
    )

    application.add_handler(
        MessageHandler(
            filters.Regex("^🚚 Alınan İşler$"),
            alinan_isler
        )
    )

    application.add_handler(
        MessageHandler(
            filters.Regex("^❓ Nasıl Kullanılır\\?$"),
            nasil_kullanilir
        )
    )

    print(
        "Takim Yildizi Operasyon Bot webhook ile baslatiliyor..."
    )

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="telegram",
        webhook_url=f"{WEBHOOK_URL}/telegram",
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    main()
