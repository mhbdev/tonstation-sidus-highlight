import logging
import signal
import threading
import time

import telebot

from tonstation.config import settings
from tonstation.storage import MessageStore, message_from_telegram

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

if not settings.bot_token or not settings.source_chat_id:
    raise ValueError('TG_BOT_TOKEN and SOURCE_CHAT_ID are required to run the collector service.')

bot = telebot.TeleBot(settings.bot_token, parse_mode=None, threaded=False)
store = MessageStore(settings.db_path)
stop_event = threading.Event()


def _is_source_chat(message) -> bool:
    try:
        return str(message.chat.id) == str(settings.source_chat_id)
    except Exception:
        return False


def _is_chatid_command(message) -> bool:
    text = message.text or getattr(message, 'caption', None)
    return bool(text) and str(text).strip().lower().startswith('/chatid')


@bot.channel_post_handler(func=lambda m: True)
def handle_channel_post(message):
    if _is_chatid_command(message):
        bot.send_message(message.chat.id, f'Channel chat_id: {message.chat.id}', parse_mode=None)
        return
    if not _is_source_chat(message):
        return
    record = message_from_telegram(message, settings.source_chat_id)
    if record:
        store.upsert_message(record)
        logger.info('Stored channel post %s', record.message_id)


@bot.message_handler(content_types=['text'])
def handle_text(message):
    if _is_chatid_command(message):
        bot.send_message(message.chat.id, f'Chat chat_id: {message.chat.id}', parse_mode=None)
        return
    if not _is_source_chat(message):
        return
    record = message_from_telegram(message, settings.source_chat_id)
    if record:
        store.upsert_message(record)
        logger.info('Stored message %s', record.message_id)


def run_collector():
    logger.info('Starting collector for chat %s', settings.source_chat_id)

    def _shutdown(signum=None, frame=None):
        if stop_event.is_set():
            return
        logger.info('Shutting down collector...')
        stop_event.set()
        try:
            bot.stop_polling()
        except Exception:
            pass

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    def _polling_loop():
        while not stop_event.is_set():
            try:
                bot.infinity_polling(
                    timeout=settings.polling_timeout,
                    interval=settings.polling_interval,
                    allowed_updates=['message', 'channel_post'],
                    skip_pending=True,
                )
            except Exception as exc:
                if stop_event.is_set():
                    break
                logger.exception('Collector error, retrying in 5s: %s', exc)
                time.sleep(5)
            else:
                if not stop_event.is_set():
                    logger.info('Polling stopped unexpectedly, restarting in 2s')
                    time.sleep(2)

    polling_thread = threading.Thread(target=_polling_loop, daemon=True)
    polling_thread.start()

    try:
        while polling_thread.is_alive():
            polling_thread.join(timeout=1)
    except KeyboardInterrupt:
        _shutdown()
    finally:
        _shutdown()
        polling_thread.join(timeout=5)
        store.close()
        logger.info('Collector stopped.')


if __name__ == '__main__':
    run_collector()
