import os
import sys
import asyncio
from dotenv import load_dotenv
import telegram

# --- Configuration ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- Constants ---
# How many "Message not found" errors in a row before we assume we're done.
CONSECUTIVE_FAILURE_LIMIT = 5 

async def purge(group_id_to_purge: int):
    """
    Deletes all messages possible from a group by iterating backwards from the latest message.
    """
    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN is not set in the .env file. Cannot run.")
        return

    print("--- ⚠️ DANGER ZONE: MESSAGE PURGE SCRIPT ---")
    print(f"Attempting to purge all recent messages from Group ID: {group_id_to_purge}")
    
    bot = telegram.Bot(token=BOT_TOKEN)

    try:
        # --- 1. Get a starting point (the ID of the most recent message) ---
        # We do this by sending a temporary message and grabbing its ID.
        temp_msg = await bot.send_message(chat_id=group_id_to_purge, text="Starting purge...")
        start_id = temp_msg.message_id
        await bot.delete_message(chat_id=group_id_to_purge, message_id=start_id)
        print(f"Starting purge from message ID {start_id} and working backwards.")

    except telegram.error.Forbidden as e:
        print(f"❌ FATAL ERROR: The bot does not have permission to send or delete messages in this group.")
        print(f"   Make sure the bot is an admin with 'Delete Messages' permission. Error: {e}")
        return
    except Exception as e:
        print(f"❌ FATAL ERROR: Could not get a starting message ID. Error: {e}")
        return

    # --- 2. Initialize counters ---
    deleted_count = 0
    failed_count = 0
    consecutive_failures = 0

    # --- 3. Loop backwards from the starting ID and attempt to delete ---
    for message_id in range(start_id, 0, -1):
        try:
            await bot.delete_message(
                chat_id=group_id_to_purge,
                message_id=message_id
            )
            print(f"✅ Deleted message {message_id}")
            deleted_count += 1
            consecutive_failures = 0  # Reset counter on success

        except telegram.error.BadRequest as e:
            # These are expected errors for messages that are too old or already gone.
            # We treat them as non-fatal failures and continue.
            error_message = str(e).lower()
            if 'message to delete not found' in error_message or "message can't be deleted" in error_message:
                print(f"INFO: Could not delete message {message_id} (likely too old or already gone).")
                failed_count += 1
                consecutive_failures += 1
            else:
                # A different kind of bad request we didn't expect
                print(f"⚠️ An unexpected BadRequest occurred for message {message_id}: {e}")
                failed_count += 1
                consecutive_failures += 1
        except telegram.error.RetryAfter as e:
            # Telegram is telling us to slow down.
            wait_time = 2
            print(f"⚠️ Rate limit hit. Waiting for {wait_time} seconds as requested by Telegram.")
            await asyncio.sleep(wait_time)
            # We don't increment failure counters here because this is a recoverable event.

        except Exception as e:
            # Any other error
            print(f"❌ An unexpected error occurred for message {message_id}: {e}")
            failed_count += 1
            consecutive_failures += 1
        
        # --- 4. Check if we should stop ---
        if consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
            print(f"\nStopping after {CONSECUTIVE_FAILURE_LIMIT} consecutive failures. This likely means we've hit the 48-hour limit.")
            break
        
        # --- 5. Be kind to the API ---
        await asyncio.sleep(0.2) 

    print("\n--- Purge Complete ---")
    print(f"Successfully deleted: {deleted_count}")
    print(f"Failed to delete (or skipped): {failed_count}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python purge_group.py <GROUP_ID>")
    else:
        try:
            target_group_id = int(sys.argv[1])
            asyncio.run(purge(target_group_id))
        except ValueError:
            print("Error: Group ID must be an integer.")