import os
import threading
from datetime import datetime

import psycopg
from flask import Flask
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
# RENDER WEB SERVER
# =========================================================

web_app = Flask(__name__)


@web_app.route("/")
def home():
    return "Takim Yildizi Operasyon Bot aktif."


def run_web():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)


# =========================================================
# POSTGRESQL
# =========================================================

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL bulunamadi.")


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

        conn.commit()


veritabani_hazirla()


# =========================================================
# TELEGRAM
# =========================================================

SIPARIS_METNI = 1


ana_menu = ReplyKeyboardMarkup(
    [
        ["➕ Sipariş Ekle"],
        ["📦 Açık İşler"],
        ["🚚 Alınan İşler"],
    ],
    resize_keyboard=True
)


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
# SIPARIS EKLE
# =========================================================

async def siparis_baslat(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "📦 Sipariş bilgisini yazınız.\n\n"
        "Örnek:\n"
        "VARMAKSAN ERZURUM\n\n"
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
                    siparis_metni,
                    eklenme_tarihi
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

    for siparis_id, siparis_metni, tarih in kayitlar:
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
# ALINAN ISLER - SIMDILIK BOS
# =========================================================

async def alinan_isler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "🚚 Alınan işler sistemi bir sonraki "
        "adımda aktif edilecek.",
        reply_markup=ana_menu
    )


# =========================================================
# IPTAL
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
    token = os.environ.get("BOT_TOKEN")

    if not token:
        raise RuntimeError("BOT_TOKEN bulunamadi.")

    application = (
        Application.builder()
        .token(token)
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

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        siparis_conversation
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

    print(
        "Takim Yildizi Operasyon Bot baslatiliyor..."
    )

    application.run_polling()


if __name__ == "__main__":
    web_thread = threading.Thread(
        target=run_web,
        daemon=True
    )

    web_thread.start()

    main()
