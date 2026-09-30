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
