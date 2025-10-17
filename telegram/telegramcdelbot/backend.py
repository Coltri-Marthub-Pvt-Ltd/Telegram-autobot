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
from telegram import Update
from telegram.ext import ContextTypes, Application
from telegram.helpers import escape_markdown
# backend.py — add these lines near the top
import os
from dotenv import load_dotenv 
import logging

load_dotenv()  # ← add this line BEFORE using os.getenv("BOT_TOKEN")
# ✅ Allow your frontend domain to access this API

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
#application = telegram.Bot(token=os.getenv("BOT_TOKEN")).connection_pool_size(50).build()
application = Application.builder().token(os.getenv("BOT_TOKEN")).connection_pool_size(50).build()
bot = application.bot
GROUP_LOOKUP = {}
# This global variable will hold the running bot process object
"""ACTIVE_BOTS = {}
"""
# --- Pydantic Models for Request Bodies --- 
class WebhookRequest(BaseModel):
    # The public URL of your PHP script, e.g., "https://senti.royalpepperbanquets.in/webhook/"
    url: str

"""class BotControlRequest(BaseModel):
    group_id: Optional[int] = None
    group_ids: Optional[List[int]] = None

    @model_validator(mode='after')
    def check_exclusive_fields(self):
        if self.group_id is not None and self.group_ids is not None:
            raise ValueError('Provide either "group_id" or "group_ids", not both.')
        if self.group_id is None and self.group_ids is None:
            raise ValueError('You must provide either "group_id" or "group_ids".')
        return self"""

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

"""def is_process_running(pid: int):
    ""Checks if a process with the given PID is currently running.""
    if pid is None:
        return False
    try:
        # Sending signal 0 to a process checks for its existence without harming it
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True"""

async def custom_forward_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or message.chat.id not in GROUP_LOOKUP:
        return

    destinations = GROUP_LOOKUP[message.chat.id]
    lesser_group_id = destinations['lesser']
    archive_group_id = destinations['archive']

    sender_name = escape_markdown(message.from_user.full_name, version=2)
    timestamp = message.date.strftime("%Y-%m-%d %H:%M:%S %Z")
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

            logging.info(f"Successfully sent message to Group {group_id}.")
        except Exception as e:
            logging.error(f"Failed to send message to Group {group_id}. Error: {e}")

# --- API Endpoints ---
"""@app.post("/bot/start", summary="Start the bot for a specific group")
async def start_bot(request: BotControlRequest):
    group_id = request.group_id
    if is_process_running(ACTIVE_BOTS.get(group_id)):
        raise HTTPException(status_code=400, detail=f"Bot is already running for group {group_id}.")

    try:
        process = subprocess.Popen([sys.executable, 'forwarder.py', str(group_id)])
        await asyncio.sleep(0.5)
        if process.poll() is not None:
            raise HTTPException(status_code=500, detail=f"Bot for group {group_id} failed to start. Check its logs.")
        pid = process.pid
        db_manager.set_bot_status(group_id, pid)
        ACTIVE_BOTS[group_id] = pid
        return {"status": "success", "message": f"Bot started for group {group_id}.", "pid": pid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start bot: {e}")"""

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

"""@app.post("/bot/start", summary="Start bot for one or more groups")
async def start_bot(request: BotControlRequest):
    ids_to_start = request.group_ids if request.group_ids is not None else [request.group_id]

    started_bots = []
    failed_bots = []

    for group_id in ids_to_start:
        if is_process_running(ACTIVE_BOTS.get(group_id)):
            failed_bots.append({"group_id": group_id, "reason": "Already running."})
            continue
        try:
            process = subprocess.Popen([sys.executable, 'forwarder.py', str(group_id)])
            await asyncio.sleep(0.5) # Give the process a moment to start
            if process.poll() is not None:
                failed_bots.append({"group_id": group_id, "reason": "Failed to start. Check logs."})
            else:
                pid = process.pid
                db_manager.set_bot_status(group_id, pid)
                ACTIVE_BOTS[group_id] = pid
                started_bots.append({"group_id": group_id, "pid": pid})
        except Exception as e:
            failed_bots.append({"group_id": group_id, "reason": str(e)})

    return {
        "status": "completed",
        "message": f"Attempted to start {len(ids_to_start)} bot(s).",
        "started": started_bots,
        "failed": failed_bots
    }"""

"""@app.post("/bot/stop", summary="Stop the bot for a specific group")
async def stop_bot(request: BotControlRequest):
    group_id = request.group_id
    pid = ACTIVE_BOTS.get(group_id)
    if not is_process_running(pid):
        raise HTTPException(status_code=400, detail=f"Bot is not running for group {group_id}.")

    try:
        try:
            os.kill(pid, signal.SIGINT)
        except OSError:
            print(f"Process {pid} was already gone before stop was called.")
        db_manager.clear_bot_status(group_id)
        ACTIVE_BOTS.pop(group_id, None)
        return {"status": "success", "message": f"Bot stopped for group {group_id}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop bot: {e}")"""
        
"""@app.post("/bot/stop", summary="Stop bot for one or more groups")
async def stop_bot(request: BotControlRequest):
    ids_to_stop = request.group_ids if request.group_ids is not None else [request.group_id]

    stopped_bots = []
    failed_bots = []

    for group_id in ids_to_stop:
        pid = ACTIVE_BOTS.get(group_id)
        if not is_process_running(pid):
            failed_bots.append({"group_id": group_id, "reason": "Not running."})
            continue
        try:
            try:
                os.kill(pid, signal.SIGINT)
            except OSError:
                print(f"Process {pid} was already gone before stop was called.")
            db_manager.clear_bot_status(group_id)
            ACTIVE_BOTS.pop(group_id, None)
            stopped_bots.append({"group_id": group_id, "pid": pid})
        except Exception as e:
            failed_bots.append({"group_id": group_id, "reason": str(e)})

    return {
        "status": "completed",
        "message": f"Attempted to stop {len(ids_to_stop)} bot(s).",
        "stopped": stopped_bots,
        "failed": failed_bots
    }"""

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

            # Use the new db_manager function to save the state
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
        # Logic to STOP and CLEAR the cron job
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
    
    
"""@app.get("/bot/status", summary="Check status for all monitored groups")
async def get_status():
    all_main_groups = db_manager.get_groups_by_tag('A')
    status_list = []
    for group in all_main_groups:
        group_id = group['group_id']
        pid = ACTIVE_BOTS.get(group_id)
        is_running = is_process_running(pid)

        status_list.append({
            "group_name": group['group_name'],
            "group_id": group_id,
            "status": "running" if is_running else "stopped",
            "pid": pid if is_running else None
        })
    return status_list"""

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
            # Recursively call the purge script for each ID
            subprocess.Popen([sys.executable, 'purge_group.py', str(group_id)])
            initiated_count += 1
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail="'purge_group.py' not found.")
        except Exception as e:
            # If one fails, stop and report the error
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
    # Step 1: Find the mapping details BEFORE deleting from the database
    mapping_to_delete = db_manager.get_mapping_by_id(mapping_id)
    if not mapping_to_delete:
        raise HTTPException(status_code=404, detail="Mapping ID not found.")

    # Step 2: Delete the mapping from the database
    if not db_manager.delete_mapping(mapping_id):
        # This is unlikely if the above check passed, but good for safety
        raise HTTPException(status_code=500, detail="Failed to delete mapping from database.")

    # Step 3: 🗑️ Delete the entry from the in-memory cache
    main_id_to_remove = mapping_to_delete['main_group_id']
    if main_id_to_remove in GROUP_LOOKUP:
        GROUP_LOOKUP.pop(main_id_to_remove)
        print(f"✅ Cache updated: Removed mapping for {main_id_to_remove}")

    return {"status": "success", "message": "Mapping deleted."}


db_manager.initialize_database()

print("Loading group mappings into memory...")
all_mappings = db_manager.get_all_mappings()
for mapping in all_mappings:
    main_id = mapping['main_group_id']
    GROUP_LOOKUP[main_id] = {
        'lesser': mapping['lesser_group_id'],
        'archive': mapping['archive_group_id']
    }
print(f"Loaded {len(GROUP_LOOKUP)} group mappings.")
from fastapi import Request
from fastapi.responses import JSONResponse
import requests
import asyncio

# --- Telegram Bot Config ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

@app.post("/webhook", summary="Telegram webhook endpoint")
async def telegram_webhook(request: Request):
    """
    Receives updates from Telegram via webhook.
    """
    try:
        body = await request.body()
        if not body:
            print("⚠️ Received an empty webhook update. Ignoring.")
            return {"status": "ok", "message": "Empty update ignored."}
        update = await request.json()
        print("📩 Telegram update received:", update)
        update_obj = Update.de_json(update, bot)
        context = ContextTypes.DEFAULT_TYPE(application=application)
        #context._bot = bot
        # Run the forwarding logic in the background so the API can respond instantly
        asyncio.create_task(custom_forward_handler(update_obj, context))

        # Immediately tell Telegram "we got it"
        return {"status": "ok"}

        """# Extract message info if available
        message = update.get("message") or update.get("edited_message") or {}
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")

        # Example simple command handling
        if text == "/start":
            reply = "👋 Hello! Telegram webhook is working!"
        else:
            reply = f"You said: {text}"

        # Send reply asynchronously
        if chat_id:
            asyncio.create_task(send_message(chat_id, reply))

        return JSONResponse({"status": "ok"})"""

    except Exception as e:
        print("❌ Error in webhook:", e)
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)


# ---- Helper function to send Telegram message ----
async def send_message(chat_id: int, text: str):
    try:
        payload = {"chat_id": chat_id, "text": text}
        response = requests.post(f"{API_URL}/sendMessage", json=payload)
        print("➡️ Sent:", response.text)
    except Exception as e:
        print("❌ Send error:", e)
