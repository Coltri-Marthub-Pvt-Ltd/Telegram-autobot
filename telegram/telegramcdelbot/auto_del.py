import os
import sys
import asyncio
import argparse
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import telegram

# --- Configuration ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- Constants ---
# How many "Message not found" or "can't be deleted" errors in a row before stopping.
CONSECUTIVE_FAILURE_LIMIT = 5

async def purge_group(bot: telegram.Bot, group_id: int, spare_minutes: int):
    """
    Deletes messages in a single group, sparing those newer than the cutoff time.
    """
    print(f"\n--- Starting purge for Group ID: {group_id} ---")
    
    try:
        # Get the most recent message ID to start iterating backwards
        temp_msg = await bot.send_message(chat_id=group_id, text="Initiating automated purge...")
        start_id = temp_msg.message_id
        await bot.delete_message(chat_id=group_id, message_id=start_id)
        print(f"Starting purge from message ID {start_id} and working backwards.")
    except telegram.error.Forbidden:
        print(f"❌ FATAL ERROR: Bot lacks admin permission in group {group_id}. Skipping.")
        return 0, 0 # Return 0 deleted, 0 failed
    except Exception as e:
        print(f"❌ FATAL ERROR: Could not get starting message ID for group {group_id}. Error: {e}")
        return 0, 0

    # Calculate the exact cutoff time in UTC for reliable comparison
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=spare_minutes)
    
    deleted_count = 0
    failed_count = 0
    consecutive_failures = 0

    for message_id in range(start_id, 0, -1):
        try:
            # For each message, we must check its timestamp *before* deleting.
            # This is done by checking the 'date' property of the message object.
            # We can get this from the message ID itself without an extra API call.
            # The first 32 bits of a message ID are a Unix timestamp.
            message_timestamp = datetime.fromtimestamp(message_id >> 32, tz=timezone.utc)

            if message_timestamp >= cutoff_time:
                # This message is within the spare time, so we skip it and stop.
                # Because we are iterating backwards, all previous messages are also safe.
                print(f"INFO: Reached message {message_id} which is within the spare time limit. Stopping purge for this group.")
                break

            # If the message is old enough, delete it.
            await bot.delete_message(chat_id=group_id, message_id=message_id)
            print(f"✅ Deleted message {message_id}")
            deleted_count += 1
            consecutive_failures = 0

        except telegram.error.BadRequest as e:
            error_message = str(e).lower()
            if 'message to delete not found' in error_message or "message can't be deleted" in error_message:
                print(f"INFO: Could not delete message {message_id} (likely >48h old or already gone).")
                failed_count += 1
                consecutive_failures += 1
            else:
                print(f"⚠️ Unexpected BadRequest for message {message_id}: {e}")
                failed_count += 1
        
        if consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
            print(f"INFO: Stopping after {CONSECUTIVE_FAILURE_LIMIT} consecutive failures (hit 48h limit).")
            break
        
        await asyncio.sleep(0.2) # Avoid hitting API rate limits
    
    print(f"--- Purge finished for Group ID: {group_id} ---")
    return deleted_count, failed_count


async def main():
    """Main function to parse arguments and orchestrate the purge."""
    parser = argparse.ArgumentParser(description="Automated Telegram message purge script for cron jobs.")
    parser.add_argument('--group-id', required=True, nargs='+', type=int, help="A list of group IDs to purge.")
    parser.add_argument('--spare-minutes', type=int, default=0, help="Optional: Spare messages from the last X minutes. Default is 0.")
    
    args = parser.parse_args()
    
    if not BOT_TOKEN:
        print("❌ FATAL: BOT_TOKEN not found in .env file.")
        return

    bot = telegram.Bot(token=BOT_TOKEN)
    total_deleted = 0
    total_failed = 0
    
    for group_id in args.group_ids:
        deleted, failed = await purge_group(bot, group_id, args.spare_minutes)
        total_deleted += deleted
        total_failed += failed
    
    print("\n---  Cron Job Summary ---")
    print(f"Total messages deleted: {total_deleted}")
    print(f"Total messages failed/skipped: {total_failed}")


if __name__ == '__main__':
    asyncio.run(main())