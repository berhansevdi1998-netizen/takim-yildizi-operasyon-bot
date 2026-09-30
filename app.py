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

        conn.commit()


veritabani_hazirla()


# =========================================================
# DURUMLAR
# =========================================================

SIPARIS_METNI = 1

IS_ID = 10
IS_ONAY = 11
KARGO_UCRETI = 12

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
        ["❓ Nasıl Kullanılır?"],
    ],
    resize_keyboard=True
)


is_onay_menu = ReplyKeyboardMarkup(
    [
        ["✅ Bu İşi Aldım"],
        ["❌ Vazgeç"],
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)


iptal_onay_menu = ReplyKeyboardMarkup(
    [
        ["✅ İptal Et"],
        ["❌ Vazgeç"],
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
        
        "3️⃣ ✅ Bu İşi Aldım butonuna basın.\n"
        "4️⃣ Kargo ücretini yazın.\n\n"

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
        "bilgileri aynı mesajın içine ekleyebilirsiniz."
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
        "Bu işi siz mi aldınız?",
        reply_markup=is_onay_menu
    )

    return IS_ONAY


async def is_onayla(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    secim = update.message.text.strip()

    if secim == "❌ Vazgeç":
        context.user_data.clear()

         await update.message.reply_text(
            "İşlem iptal edildi.",
            reply_markup=ana_menu
        )

        return ConversationHandler.END

    if secim != "✅ Bu İşi Aldım":
        await update.message.reply_text(
            "Lütfen butonlardan seçim yapınız.",
            reply_markup=is_onay_menu
        )
        return IS_ONAY

    await update.message.reply_text(
        "💰 Kargo ücretini yazınız.\n\n"
        "💵 Nakit ise tutarı normal yazın.\n"
        "📒 Vadeli / cari ise tutarı eksi olarak yazın."
    )

    return KARGO_UCRETI
async def kargo_ucreti_al(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
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
                    alinma_tarihi
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

    for (
        siparis_id,
        siparis_metni,
        personel,
        kargo_ucreti,
        odeme_tipi,
        alinma_tarihi
    ) in kayitlar:

        ucret = abs(float(kargo_ucreti or 0))
        toplam += ucret

        if odeme_tipi == "NAKİT":
            nakit_toplam += ucret
        elif odeme_tipi == "VADELİ":
            vadeli_toplam += ucret

        mesaj += (
            f"🆔 #{siparis_id}\n"
            f"📦 {siparis_metni}\n"
            f"👤 {personel or '-'}\n"
            f"💳 {odeme_tipi or '-'}\n"
            f"💰 {ucret:,.2f} ₺\n"
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
        "❌ İşlem iptal edildi.",
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
                    filters.TEXT & ~filters.COMMAND,
                    siparis_kaydet
                )
            ],
        },

        fallbacks=[
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
                    filters.TEXT & ~filters.COMMAND,
                    is_id_al
                )
            ],

            IS_ONAY: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    is_onayla
                )
            ],

            KARGO_UCRETI: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    kargo_ucreti_al
                )
            ],
        },

        fallbacks=[
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
                    filters.TEXT & ~filters.COMMAND,
                    siparis_iptal_id_al
                )
            ],

            IPTAL_ONAY: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    siparis_iptal_onayla
                )
            ],
        },

        fallbacks=[
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
