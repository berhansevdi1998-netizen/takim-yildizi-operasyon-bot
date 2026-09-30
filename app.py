import os
import threading

from flask import Flask
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# =========================
# RENDER WEB SERVER
# =========================

web_app = Flask(__name__)


@web_app.route("/")
def home():
    return "Takim Yildizi Operasyon Bot aktif."


def run_web():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)


# =========================
# TELEGRAM
# =========================

ana_menu = ReplyKeyboardMarkup(
    [
        ["➕ Sipariş Ekle"],
        ["📦 Açık İşler"],
        ["🚚 Alınan İşler"],
    ],
    resize_keyboard=True
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚚 TAKIM YILDIZI OPERASYON\n\n"
        "Gündüz kargo operasyon sistemi hazır.\n\n"
        "Yapmak istediğiniz işlemi seçiniz:",
        reply_markup=ana_menu
    )


# =========================
# BOTU BASLAT
# =========================

def main():
    token = os.environ.get("BOT_TOKEN")

    if not token:
        raise RuntimeError("BOT_TOKEN bulunamadi.")

    application = (
        Application.builder()
        .token(token)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    print("Takim Yildizi Operasyon Bot baslatiliyor...")

    application.run_polling()


if __name__ == "__main__":
    web_thread = threading.Thread(
        target=run_web,
        daemon=True
    )

    web_thread.start()

    main()
