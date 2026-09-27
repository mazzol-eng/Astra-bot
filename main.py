"""Astra: polling por padrão, webhook nativo opcional."""
import logging

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from config import load_settings
from handlers import start, help_command, cancel, whoami, callback, text_message, unknown_command, error_handler


def build_application(settings):
    # Processamento sequencial evita confirmações concorrentes na mesma sessão.
    application = Application.builder().token(settings.token).concurrent_updates(False).build()
    application.bot_data['settings'] = settings
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('cancelar', cancel))
    application.add_handler(CommandHandler('meuid', whoami))
    application.add_handler(CallbackQueryHandler(callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    application.add_error_handler(error_handler)
    return application


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    # URLs HTTP incluem o token: não habilite logs de transporte em produção.
    for name in ('httpx', 'httpcore', 'telegram', 'tornado.access'):
        logging.getLogger(name).setLevel(logging.WARNING)
    try:
        settings = load_settings()
    except ValueError as exc:
        logging.error('Configuração inválida: %s', exc)
        raise SystemExit(1) from None
    app = build_application(settings)
    logging.info('Iniciando Astra em %s', 'webhook' if settings.use_webhook else 'polling')
    if settings.use_webhook:
        # Webhook: serviço web público com HTTPS; proxy termina TLS e repassa HTTP.
        # O servidor embutido do PTB usa o extra [webhooks]; não precisa de Flask.
        app.run_webhook(listen='0.0.0.0', port=settings.port, url_path='telegram',
                        webhook_url=settings.webhook_url + '/telegram',
                        secret_token=settings.webhook_secret,
                        allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY],
                        drop_pending_updates=False, bootstrap_retries=3)
    else:
        # Polling: ideal para local, VM ou worker sempre ativo. Sem domínio/porta pública.
        app.run_polling(allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY],
                        drop_pending_updates=False, bootstrap_retries=3)


if __name__ == '__main__':
    main()
