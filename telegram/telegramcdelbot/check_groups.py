import asyncio
import os
import sys
import logging
from dotenv import load_dotenv
import telegram
from telegram.error import TelegramError
import db_manager

load_dotenv()
# ---------------------
try:
    ADMIN_CHAT_ID = int(os.getenv("Japesh_telegram_id"))
except (ValueError, TypeError):
    logging.critical("Could not find or parse ADMIN_CHAT_ID from .env file.")
    ADMIN_CHAT_ID = None
# ---------------------

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def check_one_group(bot: telegram.Bot, mapping: dict):
    """
    Checks a single group ID to see if it has migrated.
    """
    old_id = int(mapping['main_group_id'])
    group_name = mapping['main_group_name']

    # If it's already a supergroup, do nothing.
    # Supergroup IDs are longer (start with -100...)
    if old_id < -1000000000000:
        return

    logging.info(f"Checking non-supergroup: {group_name} ({old_id})")

    try:
        # Send a "typing..." action. This is invisible to users
        # but will trigger the migration error if the group upgraded.
        await bot.send_chat_action(chat_id=old_id, action="typing")

    except TelegramError as e:
        # This is the magic!
        # If the group migrated, the error object contains the new ID.
        if e.parameters and 'migrate_to_chat_id' in e.parameters:
            new_id = e.parameters['migrate_to_chat_id']
            logging.warning(f"MIGRATION DETECTED: '{group_name}' ({old_id}) has moved to {new_id}")
            
            # Send an alert to your admin chat
            alert_text = (
                f"🚨 **Group Migration Detected** 🚨\n\n"
                f"The group **{group_name}** has upgraded.\n"
                f"The bot will not work for this group until you update the mapping.\n\n"
                f"**Old ID:** `{old_id}`\n"
                f"**New ID:** `{new_id}`\n\n"
                f"**Full Error Details:**\n"
                f"```\n{e}\n```"
            )
            try:
                await bot.send_message(chat_id=ADMIN_CHAT_ID, text=alert_text, parse_mode="MarkdownV2")
            except Exception as alert_e:
                logging.error(f"Failed to send migration alert to admin: {alert_e}")
        
        else:
            # A different error (e.g., bot was kicked)
            logging.error(f"Error checking group {group_name} ({old_id}): {e.message}")
            
    except Exception as e:
        logging.error(f"Unexpected error checking {group_name}: {e}")


async def main():
    logging.info("--- Starting Group Migration Check ---")
    
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        logging.critical("BOT_TOKEN or ADMIN_CHAT_ID is not set. Exiting.")
        return

    bot = telegram.Bot(token=BOT_TOKEN)
    db_manager.initialize_database() # Make sure DB is ready
    
    all_mappings = db_manager.get_all_mappings()
    
    tasks = []
    for mapping in all_mappings:
        tasks.append(check_one_group(bot, mapping))
        
    await asyncio.gather(*tasks) # Run all checks in parallel
    logging.info("--- Group Migration Check Finished ---")


if __name__ == "__main__":
    asyncio.run(main())