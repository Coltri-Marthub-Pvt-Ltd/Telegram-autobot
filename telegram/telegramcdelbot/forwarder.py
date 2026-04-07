import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
from telegram.helpers import escape_markdown
import db_manager
import requests  # Added for webhook setup
from datetime import timezone, datetime
from zoneinfo import ZoneInfo  # Python 3.9+
# --- Basic Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_LOOKUP = {}

# ---- Forwarding Handler ----
async def custom_forward_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or message.chat.id not in GROUP_LOOKUP:
        return

    destinations = GROUP_LOOKUP[message.chat.id]
    lesser_group_id = destinations['lesser']
    archive_group_id = destinations['archive']

    sender_name = escape_markdown(message.from_user.full_name, version=2)
    utc_time = message.date.replace(tzinfo=timezone.utc)
    ist_time = utc_time.astimezone(ZoneInfo("Asia/Kolkata"))
    timestamp = ist_time.strftime("%Y-%m-%d %H:%M:%S IST")
    header = f"*Original Sender:* `{sender_name}`\n*Time Sent:* `{timestamp}`\n\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\n\n"

    logging.info(f"Processing message {message.message_id} from '{sender_name}'.")

    for group_id in [lesser_group_id, archive_group_id]:
        try:
            if message.text and not (message.photo or message.document or message.video or message.audio or message.voice or message.sticker or message.animation):
                content = escape_markdown(message.text, version=2)
                await context.bot.send_message(chat_id=group_id, text=header + content, parse_mode='MarkdownV2')
            else:
                caption_with_header = header + escape_markdown(message.caption or "", version=2)
                if message.photo:
                    await context.bot.send_photo(chat_id=group_id, photo=message.photo[-1].file_id, caption=caption_with_header, parse_mode='MarkdownV2')
                elif message.document:
                    await context.bot.send_document(chat_id=group_id, document=message.document.file_id, caption=caption_with_header, parse_mode='MarkdownV2')
                elif message.video:
                    await context.bot.send_video(chat_id=group_id, video=message.video.file_id, caption=caption_with_header, parse_mode='MarkdownV2')
                elif message.audio:
                    await context.bot.send_audio(chat_id=group_id, audio=message.audio.file_id, caption=caption_with_header, parse_mode='MarkdownV2')
                elif message.voice:
                    await context.bot.send_voice(chat_id=group_id, voice=message.voice.file_id, caption=caption_with_header, parse_mode='MarkdownV2')
                elif message.sticker:
                    await context.bot.send_message(chat_id=group_id, text=header, parse_mode='MarkdownV2')
                    await context.bot.send_sticker(chat_id=group_id, sticker=message.sticker.file_id)
                elif message.animation:
                    await context.bot.send_animation(chat_id=group_id, animation=message.animation.file_id, caption=caption_with_header, parse_mode='MarkdownV2')

            logging.info(f"Successfully sent message to Group {group_id}.")
        except Exception as e:
            logging.error(f"Failed to send message to Group {group_id}. Error: {e}")

# ---- Webhook Setup Function (Step 2) ----
def set_webhook():
    # Step 1: Define webhook URL (replace YOUR_DOMAIN with your actual domain)
    YOUR_DOMAIN = "https://senti.royalpepperbanquets.in/webhook"  # <-- ⚠️ Replace this with your real domain
    URL_PATH = BOT_TOKEN.split(':')[-1]
    webhook_url = f"{YOUR_DOMAIN.rstrip('/')}/{URL_PATH}"

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}"
    response = requests.post(url)
    if response.status_code == 200:
        logging.info("Webhook set successfully.")
    else:
        logging.error(f"Failed to set webhook: {response.text}")

# ---- Main Function ----
def main():
    global GROUP_LOOKUP

    db_manager.initialize_database()
    all_mappings = db_manager.get_all_mappings()
    if not all_mappings:
        logging.warning("No group mappings found. The bot will not forward any messages.")

    main_group_ids = []
    for mapping in all_mappings:
        main_id = mapping['main_group_id']
        main_group_ids.append(main_id)
        GROUP_LOOKUP[main_id] = {
            'lesser': mapping['lesser_group_id'],
            'archive': mapping['archive_group_id']
        }
    logging.info(f"Loaded {len(main_group_ids)} group mappings.")

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    message_filters = (filters.TEXT | filters.ATTACHMENT) & (~filters.COMMAND) & filters.Chat(chat_id=main_group_ids)
    application.add_handler(MessageHandler(message_filters, custom_forward_handler))

    PORT = 8001
    URL_PATH = BOT_TOKEN.split(':')[-1]

    # Step 2: Call set_webhook before starting
    set_webhook()

    # Step 4: Start bot in webhook mode
    logging.info(f"Bot starting in webhook mode on port {PORT} with URL path: /{URL_PATH}")
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=URL_PATH
    )

if __name__ == '__main__':
    main()