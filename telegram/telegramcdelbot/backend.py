import os
import signal
import subprocess
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel, model_validator
import uvicorn
import asyncio
import sys
import db_manager
from typing import Optional, List
from fastapi import Query
from fastapi.middleware.cors import CORSMiddleware
import pytz
from crontab import CronTab
from datetime import datetime
import telegram
from telegram import Update, Message
from telegram.ext import ContextTypes, Application
from telegram.helpers import escape_markdown
from dotenv import load_dotenv 
import logging
from telegram.error import RetryAfter, TimedOut, TelegramError, NetworkError
import json 
from asyncio import to_thread
from datetime import timezone
from asyncio import Lock
from telegram import InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio
from zoneinfo import ZoneInfo
from collections import OrderedDict
import time
import socket
load_dotenv()  # ← add this line BEFORE using os.getenv("BOT_TOKEN")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# --- Application Setup ---
app = FastAPI(
    title="Telegram Bot Backend",
    description="An API to start, stop, and manage the Telegram deletion bot.",
    version="1.0.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


CRON_JOB_COMMENT = "TELEGRAM_AUTOPURGE_JOB"
CHECK_GROUPS_CRON_COMMENT = "TELEGRAM_CHECK_GROUPS_JOB"
application = Application.builder().token(os.getenv("BOT_TOKEN")).connection_pool_size(100).connect_timeout(10).read_timeout(120).write_timeout(120).pool_timeout(60).build()
bot = application.bot
GROUP_LOOKUP = {}
BOT_ID = int(os.getenv("BOT_TOKEN").split(":")[0])
PROCESSED_UPDATES = OrderedDict()
MAX_CACHE_SIZE = 5000
MEDIA_GROUP_BUFFER = {}
MEDIA_GROUP_LOCK = Lock()
ACTIVE_TASKS = set()
LAST_ACTIVE_TIMESTAMP = 0.0
QUIET_COOLDOWN_SECONDS = 90

class WebhookRequest(BaseModel):
    # The public URL of your PHP script, e.g., "https://senti.royalpepperbanquets.in/webhook/"
    url: str


class GroupMapping(BaseModel):
    main_group_name: str
    main_group_id: int
    lesser_group_id: int
    archive_group_id: int
    
class PurgeRequest(BaseModel):
    group_id: Optional[int] = None
    group_ids: Optional[List[int]] = None
    @model_validator(mode='after')
    def check_exclusive_fields(self):
        if self.group_id is not None and self.group_ids is not None:
            raise ValueError('Provide either "group_id" or "group_ids", not both.')
        if self.group_id is None and self.group_ids is None:
            raise ValueError('You must provide either "group_id" or "group_ids".')
        return self

class ScheduleCheckRequest(BaseModel):
    enabled: bool
    minute_interval: Optional[int] = 120 # minutes
    @model_validator(mode='after')
    def check_interval(self):
        if self.enabled and (self.minute_interval is None or self.minute_interval <= 0):
            raise ValueError('When enabling, "minute_interval" must be a positive number.')
        return self

class ScheduleRequest(BaseModel):
    enabled: bool
    time_ist: Optional[str] = None  # e.g., "02:30" or "16:50"
    group_id: int
    spare_minutes: Optional[int] = 0
    @model_validator(mode='after')
    def check_required_fields(self):
        # If the schedule is being enabled, time and groups must be provided.
        if self.enabled and (self.time_ist is None or self.group_id is None):
            raise ValueError('When enabling a schedule, "time_ist" and "group_id" are required.')
        return self

async def process_media_group_after_delay(media_group_id: str, destinations: dict, initial_message: Message):
    """
    Waits for all messages in a media group, then sends them as a single batch.
    """
    from zoneinfo import ZoneInfo 
    await asyncio.sleep(60) 
    lesser_group_id = destinations['lesser']
    archive_group_id = destinations['archive']
    async with MEDIA_GROUP_LOCK:
        messages = MEDIA_GROUP_BUFFER.pop(media_group_id, [])
    messages.sort(key=lambda m: m.message_id)

    if not messages:
        logging.warning(f"Media group {media_group_id} processed but no messages were found in buffer.")
        return
    first_msg = messages[0] 
    sender_name = escape_markdown(first_msg.from_user.full_name, version=2)
    utc_time = first_msg.date.replace(tzinfo=timezone.utc)
    ist_time = utc_time.astimezone(ZoneInfo("Asia/Kolkata"))
    timestamp = ist_time.strftime("%Y-%m-%d %H:%M:%S IST")
    header = f"*Original Sender:* `{sender_name}`\n*Time Sent:* `{timestamp}`\n\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\n\n"
    caption = ""
    for msg in messages:
        if msg.caption:
            caption = msg.caption
            break # Found it
    footer = ""
    final_caption = header + escape_markdown(caption or "", version=2) + footer
    media_list = []
    for i, msg in enumerate(messages):
        item_caption = final_caption if i == 0 else None
        if msg.photo:
            media_list.append(InputMediaPhoto(media=msg.photo[-1].file_id, caption=item_caption, parse_mode='MarkdownV2'))
        elif msg.video:
            media_list.append(InputMediaVideo(media=msg.video.file_id, caption=item_caption, parse_mode='MarkdownV2'))
        elif msg.document:
            media_list.append(InputMediaDocument(media=msg.document.file_id, caption=item_caption, parse_mode='MarkdownV2'))
        elif msg.audio:
             media_list.append(InputMediaAudio(media=msg.audio.file_id, caption=item_caption, parse_mode='MarkdownV2'))
    if not media_list:
        logging.error(f"Failed to build any media for group {media_group_id}")
        return
    for group_id in [lesser_group_id, archive_group_id]:
        try:
            await bot.send_media_group(
                chat_id=group_id, 
                media=media_list, 
                read_timeout=120, 
                write_timeout=120
            )
            logging.info(f"Successfully sent media group {media_group_id} to Group {group_id}.")
            
        except (RetryAfter, TimedOut, NetworkError) as e:
            reason = f"Temporary Error on media group: {e.__class__.__name__} ({e})"
            logging.warning(f"Group {group_id} failed media group ({reason}). Logging ENTIRE ALBUM to DB.")
            await to_thread(db_manager.log_missed_media_group, messages, group_id, reason)
            
        except Exception as e:
            reason = f"Unrecoverable (MediaGroup Error): {e}"
            logging.error(f"Failed to send media group to Group {group_id}. Error: {e}")
            await to_thread(db_manager.log_missed_media_group, messages, group_id, reason)

async def custom_forward_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:    
        message = update.message
        if not message or message.chat.id not in GROUP_LOOKUP:
            return
        if message.from_user and message.from_user.id == BOT_ID:
            return
        destinations = GROUP_LOOKUP[message.chat.id]
        if message.media_group_id:
            async with MEDIA_GROUP_LOCK:
                if message.media_group_id not in MEDIA_GROUP_BUFFER:
                    MEDIA_GROUP_BUFFER[message.media_group_id] = [message]
                    task = asyncio.create_task(
                        process_media_group_after_delay(
                            message.media_group_id, 
                            destinations,
                            initial_message=message 
                        )
                    )
                    ACTIVE_TASKS.add(task)
                    task.add_done_callback(ACTIVE_TASKS.discard)
                else:
                    MEDIA_GROUP_BUFFER[message.media_group_id].append(message)
            return  
        lesser_group_id = destinations['lesser']
        archive_group_id = destinations['archive']
        sender_name = escape_markdown(message.from_user.full_name, version=2)
        from datetime import timezone
        from zoneinfo import ZoneInfo
        utc_time = message.date.replace(tzinfo=timezone.utc)
        ist_time = utc_time.astimezone(ZoneInfo("Asia/Kolkata"))
        timestamp = ist_time.strftime("%Y-%m-%d %H:%M:%S IST")
        header = f"*Original Sender:* `{sender_name}`\n*Time Sent:* `{timestamp}`\n\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\n\n"
        logging.info(f"Processing message {message.message_id} from '{sender_name}'.")
        for group_id in [lesser_group_id, archive_group_id]:   
            try:
                if message.text and not (message.photo or message.document or message.video or message.audio or message.voice or message.sticker or message.animation):
                    content = escape_markdown(message.text, version=2)
                    await bot.send_message(chat_id=group_id, text=header + content, parse_mode='MarkdownV2')
                else:
                    caption_with_header = header + escape_markdown(message.caption or "", version=2)
                    if message.photo:
                        await bot.send_photo(chat_id=group_id, photo=message.photo[-1].file_id, caption=caption_with_header, parse_mode='MarkdownV2', read_timeout=120, write_timeout=120)
                    elif message.document:
                        await bot.send_document(chat_id=group_id, document=message.document.file_id, caption=caption_with_header, parse_mode='MarkdownV2', read_timeout=120, write_timeout=120)
                    elif message.video:
                        await bot.send_video(chat_id=group_id, video=message.video.file_id, caption=caption_with_header, parse_mode='MarkdownV2', read_timeout=120, write_timeout=120)
                    elif message.audio:
                        await bot.send_audio(chat_id=group_id, audio=message.audio.file_id, caption=caption_with_header, parse_mode='MarkdownV2', read_timeout=120, write_timeout=120)
                    elif message.voice:
                        await bot.send_voice(chat_id=group_id, voice=message.voice.file_id, caption=caption_with_header, parse_mode='MarkdownV2', read_timeout=120, write_timeout=120)
                    elif message.sticker:
                        await bot.send_message(chat_id=group_id, text=header, parse_mode='MarkdownV2', read_timeout=120, write_timeout=120)
                        await bot.send_sticker(chat_id=group_id, sticker=message.sticker.file_id, read_timeout=120, write_timeout=120)
                    elif message.animation:
                        await bot.send_animation(chat_id=group_id, animation=message.animation.file_id, caption=caption_with_header, parse_mode='MarkdownV2', read_timeout=120, write_timeout=120)
                logging.info(f"Successfully sent message to Group {group_id} in one attempt.")
            
            except (RetryAfter, TimedOut, NetworkError) as e:
                reason = f"Temporary Error on first attempt: {e.__class__.__name__} ({e})"
                logging.warning(f"Group {group_id} failed first attempt ({reason}). Logging to DB.")
                await to_thread(db_manager.log_missed_message, message, group_id, reason)
            
            except TelegramError as e:
                reason = f"Unrecoverable (TelegramError): {e}"
                logging.error(f"Failed to send message to Group {group_id}. Unrecoverable Telegram Error: {e}")
                await to_thread(db_manager.log_missed_message, message, group_id, reason)
                
            except Exception as e:
                reason = f"Unrecoverable (TelegramError): {e}"
                logging.error(f"Failed to send message to Group {group_id}. Unexpected System Error: {e}")
                await to_thread(db_manager.log_missed_message, message, group_id, reason)
        
    except Exception as e:
        logging.error(f"CRITICAL ERROR in custom_forward_handler: {e}", exc_info=True)

async def _resend_message_helper(message: Message, group_id: int, delay_reason: str = None):
    """
    A helper to re-send a message, duplicating the logic from the main handler.
    This will try to send ONCE and will raise an exception on failure.
    """
    sender_name = escape_markdown(message.from_user.full_name, version=2)
    utc_time = message.date.replace(tzinfo=timezone.utc)
    ist_time = utc_time.astimezone(ZoneInfo("Asia/Kolkata"))
    timestamp = ist_time.strftime("%Y-%m-%d %H:%M:%S IST")
    header = f"*Original Sender:* `{sender_name}`\n*Time Sent:* `{timestamp}`\n\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\n\n"
    footer = ""
    if delay_reason:
        escaped_reason = escape_markdown(delay_reason, version=2)
        footer = f"\n\n\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\n*⚠️ Delayed Due To:* `{escaped_reason}`"
    if message.text and not (message.photo or message.document or message.video or message.audio or message.voice or message.sticker or message.animation):
        content = escape_markdown(message.text, version=2)
        await bot.send_message(chat_id=group_id, text=header + content +footer, parse_mode='MarkdownV2')
    else:
        caption_with_header = header + escape_markdown(message.caption or "", version=2)+ footer
        if message.photo:
            await bot.send_photo(chat_id=group_id, photo=message.photo[-1].file_id, caption=caption_with_header, parse_mode='MarkdownV2')
        elif message.document:
            await bot.send_document(chat_id=group_id, document=message.document.file_id, caption=caption_with_header, parse_mode='MarkdownV2')
        elif message.video:
            await bot.send_video(chat_id=group_id, video=message.video.file_id, caption=caption_with_header, parse_mode='MarkdownV2')
        elif message.audio:
            await bot.send_audio(chat_id=group_id, audio=message.audio.file_id, caption=caption_with_header, parse_mode='MarkdownV2')
        elif message.voice:
            await bot.send_voice(chat_id=group_id, voice=message.voice.file_id, caption=caption_with_header, parse_mode='MarkdownV2')
        elif message.sticker:
            await bot.send_message(chat_id=group_id, text=header, parse_mode='MarkdownV2')
            await bot.send_sticker(chat_id=group_id, sticker=message.sticker.file_id)
        elif message.animation:
            await bot.send_animation(chat_id=group_id, animation=message.animation.file_id, caption=caption_with_header, parse_mode='MarkdownV2')
GROUP_COOLDOWNS = {}

async def _resend_media_group_retry_helper(messages: list, group_id: int, delay_reason: str = None):
    """Helper to re-send an entire media group at once."""
    first_msg = messages[0]
    sender_name = escape_markdown(first_msg.from_user.full_name, version=2)
    utc_time = first_msg.date.replace(tzinfo=timezone.utc)
    ist_time = utc_time.astimezone(ZoneInfo("Asia/Kolkata"))
    timestamp = ist_time.strftime("%Y-%m-%d %H:%M:%S IST")
    header = f"*Original Sender:* `{sender_name}`\n*Time Sent:* `{timestamp}`\n\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\n\n"
    footer = ""
    if delay_reason:
        escaped_reason = escape_markdown(delay_reason, version=2)
        footer = f"\n\n\\-\\-\\-\\-\\-\\-\\-\\-\\-\\-\n*⚠️ Delayed Due To:* `{escaped_reason}`"
    
    caption = ""
    for msg in messages:
        if msg.caption:
            caption = msg.caption
            break
    footer = ""        
    
    final_caption = header + escape_markdown(caption or "", version=2) + footer 
    
    media_list = []
    for i, msg in enumerate(messages):
        item_caption = final_caption if i == 0 else None
        if msg.photo:
            media_list.append(InputMediaPhoto(media=msg.photo[-1].file_id, caption=item_caption, parse_mode='MarkdownV2'))
        elif msg.video:
            media_list.append(InputMediaVideo(media=msg.video.file_id, caption=item_caption, parse_mode='MarkdownV2'))
        elif msg.document:
            media_list.append(InputMediaDocument(media=msg.document.file_id, caption=item_caption, parse_mode='MarkdownV2'))
        elif msg.audio:
             media_list.append(InputMediaAudio(media=msg.audio.file_id, caption=item_caption, parse_mode='MarkdownV2'))
             
    if not media_list:
        raise ValueError("Failed to build any media for retry.")
        
    await bot.send_media_group(chat_id=group_id, media=media_list, read_timeout=120, write_timeout=120)
    
    
async def process_single_retry(item):
    """Handles the retry logic for a SINGLE message concurrently."""
    group_id = item['failed_group_id']
    if time.time() < GROUP_COOLDOWNS.get(group_id, 0):
        logging.info(f"Retryer: Group {group_id} is on cooldown. Skipping message {item['id']}.")
        return
    try:
        message_data = json.loads(item['message_json'])
        delay_reason = item.get('reason', 'Unknown network delay')
        if isinstance(message_data, list):
            messages = [Message.de_json(m, bot) for m in message_data]
            await _resend_media_group_retry_helper(messages, group_id, delay_reason)
        else:
            message = Message.de_json(message_data, bot)
            await _resend_message_helper(message, group_id, delay_reason)
        await to_thread(db_manager.delete_missed_message, item['id'])
        logging.info(f"Retryer: Successfully resent and deleted message ID {item['id']}")

    except RetryAfter as e:
        cooldown_until = time.time() + e.retry_after + 1.0 # Add 1 sec buffer
        GROUP_COOLDOWNS[group_id] = cooldown_until
        logging.warning(f"Retryer: Flood control on Group {group_id}. Pausing this group for {e.retry_after}s.")
        await to_thread(db_manager.update_missed_message_status, item['id'], 'pending', reason=f"Paused by Flood Control")

    except (TimedOut, NetworkError) as e:
        logging.warning(f"Retryer: TimedOut on message ID {item['id']}. Network glitch.")
        await to_thread(db_manager.increment_missed_message_attempt, item['id'])
        
    except TelegramError as e:
        logging.error(f"Retryer: Permanent error on message ID {item['id']}: {e}. Abandoning.")
        await to_thread(db_manager.update_missed_message_status, item['id'], 'abandoned', reason=str(e))
        
    except Exception as e:
        logging.error(f"Retryer: Unknown error on message ID {item['id']}: {e}.")
        await to_thread(db_manager.increment_missed_message_attempt, item['id'])

async def retry_missed_messages_task():
    """
    This task runs in the background for the app's entire lifecycle.
    It wakes up periodically to check for pending messages and retry them.
    """
    cleanup_counter = 0 
    global LAST_ACTIVE_TIMESTAMP
    global GROUP_COOLDOWNS
    while True:
        await asyncio.sleep(60) 
        current_time = time.time()
        expired_groups = [g_id for g_id, exp_time in GROUP_COOLDOWNS.items() if current_time > exp_time]
        for g_id in expired_groups:
            del GROUP_COOLDOWNS[g_id]
        time_since_last_message = time.time() - LAST_ACTIVE_TIMESTAMP
        if time_since_last_message < QUIET_COOLDOWN_SECONDS:
            logging.info(f"Retryer: Bot is busy (last message {int(time_since_last_message)}s ago). Pausing retries.")
            continue
        try:
            socket.gethostbyname("api.telegram.org")
        except socket.gaierror:
            logging.warning("Retryer: Server DNS is currently down. Pausing queue to save strikes.")
            continue
        try:
            pending_messages = await to_thread(db_manager.get_pending_missed_messages, limit=5)
            if not pending_messages:
                pass
            else:
                logging.info(f"Retryer: Found {len(pending_messages)} pending messages. Trickling sequentially...")
                for item in pending_messages:
                    await process_single_retry(item)
                    await asyncio.sleep(2.0)  # Give the network a 2-second breather between heavy uploads
            cleanup_counter += 1
            if cleanup_counter >= 1440:
                logging.info("Retryer: Running daily cleanup of old resolved messages...")
                await to_thread(db_manager.delete_old_resolved_messages, days_old=10)
                cleanup_counter = 0

        except Exception as e:
            logging.error(f"CRITICAL: The retry_missed_messages_task has crashed: {e}")
            await asyncio.sleep(300)

# --- API Endpoints ---
@app.on_event("startup")
async def on_startup():
    """
    Runs when the FastAPI application starts.
    """
    await bot.initialize()
    task = asyncio.create_task(retry_missed_messages_task())
    ACTIVE_TASKS.add(task)
    task.add_done_callback(ACTIVE_TASKS.discard)
    logging.info("Background retryer task has been started.")
    
@app.on_event("shutdown")
async def on_shutdown():
    """
    Catches the server kill signal and rescues any albums 
    currently sitting in the 15-second RAM buffer.
    """
    logging.info("🛑 Shutting down! Rescuing media buffer from RAM...")
    async with MEDIA_GROUP_LOCK:
        if not MEDIA_GROUP_BUFFER:
            logging.info("Buffer is empty. Safe to shut down.")
            return
    rescued_count = 0
    reason = "Server Graceful Shutdown (Rescued from RAM)"
    async with MEDIA_GROUP_LOCK:
        for media_group_id, messages in MEDIA_GROUP_BUFFER.items():
            if not messages:
                continue
            first_msg = messages[0]
            chat_id = first_msg.chat.id
            destinations = GROUP_LOOKUP.get(chat_id)
            if not destinations:
                continue
            for group_id in [destinations['lesser'], destinations['archive']]:
                for msg in messages:
                    await to_thread(db_manager.log_missed_message, msg, group_id, reason)
                    rescued_count += 1
        MEDIA_GROUP_BUFFER.clear()
    await bot.shutdown()
    logging.info(f"✅ Successfully rescued {rescued_count} pending files to the database. Server can now safely exit.")

@app.post("/bot/set_webhook", summary="Set the bot's webhook URL with Telegram")
async def set_webhook(request: WebhookRequest):
    """
    Tells Telegram where to send message updates. This only needs to be
    done once, or if your domain changes.
    """
    try:
        bot = telegram.Bot(token=os.getenv("BOT_TOKEN"))
        await bot.set_webhook(request.url)
        return {"status": "success", "message": f"Webhook set to {request.url}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to set webhook: {e}")

@app.post("/schedule/purge", summary="Set or update the daily auto-del schedule")
async def schedule_purge(request: ScheduleRequest):
    """
    Creates or updates a single cron job to run the auto_del.py script daily.
    The time is provided in IST 24 hr format (eg, 16:24 or 05:06) and is converted to the server's UTC for scheduling.
    Only works for one group at a time.
    """
    group_id = request.group_id 
    cron_comment = f"TELEGRAM_AUTOPURGE_JOB_{group_id}"
    cron = CronTab(user=True)
    if request.enabled:    
        try:
            ist_time = datetime.strptime(request.time_ist, "%H:%M").time()
            today_ist = datetime.now(pytz.timezone('Asia/Kolkata')).replace(hour=ist_time.hour, minute=ist_time.minute)
            time_utc = today_ist.astimezone(pytz.utc)
            python_executable = sys.executable
            script_path = os.path.realpath('auto_del.py')
            command = f"{python_executable} {script_path} --group-id {group_id} --spare-minutes {request.spare_minutes}"
            job = cron.new(command=command, comment=cron_comment)
            job.setall(time_utc.minute, time_utc.hour, '*', '*', '*')
            success, message = db_manager.set_del_schedule(group_id, request.time_ist, request.spare_minutes)
            if not success:
                raise HTTPException(status_code=404, detail=message)
            cron.write()
            return {"status": "success", "message": f"Auto-del job scheduled for group {group_id}."}
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid time format. Please use 'HH:MM'.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to set cron job: {e}") 
        
    else:
        cron.remove_all(comment=f"TELEGRAM_AUTOPURGE_JOB_{request.group_id}")
        cron.write()
        db_manager.delete_del_schedule(request.group_id)
        return {"status": "success", "message": "Auto-del job has been disabled."}       

@app.get("/schedule/purge", summary="Get the current auto-del schedule")
async def get_schedule():
    """Retrieves the saved schedule state from the database."""
    schedule = db_manager.get_all_del_schedules()
    if schedule:
        return schedule
    return {"enabled": False, "message": "No active schedule found."}
    
@app.get("/groups", summary="List group mappings, optionally filtered by tag")
async def list_groups(tag: Optional[str] = Query(None, enum=["A", "B", "C"])):
    """
    Retrieves group mappings.
    - No tag: returns all complete mappings.
    - ?tag=A: returns all Main groups.
    - ?tag=B: returns all Lesser groups.
    - ?tag=C: returns all Archive groups.
    """
    if tag:
        return db_manager.get_groups_by_tag(tag)
    else:
        return db_manager.get_all_mappings()

@app.post("/actions/purge", summary="Purge one or more groups")
async def purge_group(request: PurgeRequest):
    """
    Triggers the purge script for one or more group IDs.
    """
    ids_to_purge = []
    if request.group_id is not None:
        ids_to_purge.append(request.group_id)
    elif request.group_ids is not None:
        ids_to_purge = request.group_ids
    initiated_count = 0
    for group_id in ids_to_purge:
        try:
            subprocess.Popen([sys.executable, 'purge_group.py', str(group_id)])
            initiated_count += 1
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail="'purge_group.py' not found.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to start purge for group {group_id}: {e}")
    return {"status": "success", "message": f"Purge process initiated for {initiated_count} group(s)."}


@app.post("/groups", summary="Add a new group mapping")
async def add_group(mapping: GroupMapping):
    success, message = db_manager.add_group_mapping(
        mapping.main_group_name,
        mapping.main_group_id,
        mapping.lesser_group_id,
        mapping.archive_group_id
    )
    if not success:
        raise HTTPException(status_code=409, detail=message) # 409 Conflict for duplicates
    GROUP_LOOKUP[mapping.main_group_id] = {
        'lesser': mapping.lesser_group_id,
        'archive': mapping.archive_group_id
    }
    print(f"✅ Cache updated: Added mapping for {mapping.main_group_id}")
    return {"status": "success", "message": message}

@app.delete("/groups/{mapping_id}", summary="Delete a group mapping")
async def delete_group(mapping_id: int):
    mapping_to_delete = db_manager.get_mapping_by_id(mapping_id)
    if not mapping_to_delete:
        raise HTTPException(status_code=404, detail="Mapping ID not found.")
    if not db_manager.delete_mapping(mapping_id):
        raise HTTPException(status_code=500, detail="Failed to delete mapping from database.")
    main_id_to_remove = mapping_to_delete['main_group_id']
    if main_id_to_remove in GROUP_LOOKUP:
        GROUP_LOOKUP.pop(main_id_to_remove)
        print(f"✅ Cache updated: Removed mapping for {main_id_to_remove}")
    return {"status": "success", "message": "Mapping deleted."}

@app.get("/missed-messages", summary="View all messages in the retry queue")
async def get_missed_messages():
    """
    Retrieves a list of all messages that have failed and are
    in the 'pending', 'success', or 'abandoned' state.
    """
    try:
        items = await to_thread(db_manager.get_all_missed_messages_for_api)
        pending_count = sum(1 for item in items if item['status'] == 'pending')
        return {
            "total_count": len(items),
            "pending_count": pending_count,
            "messages": items
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve messages: {e}")

@app.post("/schedule/check-groups", summary="Set or update the group migration check schedule")
async def schedule_group_check(request: ScheduleCheckRequest):
    """
    Creates, updates, or deletes a cron job to run the check_groups.py script
    at a specified hourly interval.
    """
    cron = CronTab(user=True)
    cron.remove_all(comment=CHECK_GROUPS_CRON_COMMENT)
    if request.enabled:
        try:
            python_executable = sys.executable
            script_path = os.path.realpath('check_groups.py')
            command = f"{python_executable} {script_path}"
            job = cron.new(command=command, comment=CHECK_GROUPS_CRON_COMMENT)
            interval = request.minute_interval
            if interval < 60:
                job.setall(f"*/{interval} * * * *")
            else:
                minutes = interval % 60
                hours = interval // 60
                job.setall(f"{minutes} */{hours} * * *")
            cron.write()
            return {
                "status": "success",
                "message": f"Group check job scheduled to run every {request.minute_interval} minute(s)."
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to set cron job: {e}") 
    else:
        cron.write()
        return {"status": "success", "message": "Group check job has been disabled."}
db_manager.initialize_database()

print("Loading group mappings into memory...")
all_mappings = db_manager.get_all_mappings()
for mapping in all_mappings:
    main_id = int(mapping['main_group_id'])
    GROUP_LOOKUP[main_id] = {
        'lesser': int(mapping['lesser_group_id']),
        'archive': int(mapping['archive_group_id'])
    }
print(f"Loaded {len(GROUP_LOOKUP)} group mappings.")
from fastapi import Request, BackgroundTasks
from fastapi.responses import JSONResponse
import requests
import asyncio

# --- Telegram Bot Config ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

@app.post("/webhook", summary="Telegram webhook endpoint")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receives updates from Telegram via webhook.
    """
    try:
        body = await request.body()
        if not body:
            logging.warning("⚠️ Received an empty webhook update. Ignoring.")
            return {"status": "ok", "message": "Empty update ignored."}
        update = await request.json()
        update_id = update.get("update_id")
        if update_id:
            if update_id in PROCESSED_UPDATES:
                logging.warning(f"⚠️ Duplicate webhook received from Telegram: {update_id}. Ignoring.")
                return {"status": "ok"}
            PROCESSED_UPDATES[update_id] = True
            if len(PROCESSED_UPDATES) > MAX_CACHE_SIZE:
                PROCESSED_UPDATES.popitem(last=False)
            global LAST_ACTIVE_TIMESTAMP
            LAST_ACTIVE_TIMESTAMP = time.time()
        logging.info(f"📩 Telegram update received:{update}")
        update_obj = Update.de_json(update, bot)
        context = ContextTypes.DEFAULT_TYPE(application=application)
        #context._bot = bot
        background_tasks.add_task(custom_forward_handler, update_obj, context)
        return {"status": "ok"}
    except Exception as e:
        logging.error(f"❌ Error in webhook: {e}")
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)
async def send_message(chat_id: int, text: str):
    try:
        payload = {"chat_id": chat_id, "text": text}
        response = requests.post(f"{API_URL}/sendMessage", json=payload)
        print("➡️ Sent:", response.text)
    except Exception as e:
        print("❌ Send error:", e)
