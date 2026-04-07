#./db_manager.py
import sqlite3
from pathlib import Path
import json
from datetime import datetime, timedelta

DB_DIRECTORY = Path(__file__).parent / "temp" / "db"
DB_PATH = DB_DIRECTORY / 'group_mappings.db'

def initialize_database():
    DB_DIRECTORY.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS group_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                main_group_name TEXT NOT NULL,
                main_group_id INTEGER NOT NULL UNIQUE,
                lesser_group_id INTEGER NOT NULL UNIQUE,
                archive_group_id INTEGER NOT NULL UNIQUE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS del_schedules (
                group_id INTEGER PRIMARY KEY,
                group_name TEXT NOT NULL,
                time_ist TEXT NOT NULL,
                spare_minutes INTEGER NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS missed_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                logged_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                source_chat_id INTEGER NOT NULL,
                source_message_id INTEGER NOT NULL,
                failed_group_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                message_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempt_count INTEGER DEFAULT 0
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_missed_messages_status
            ON missed_messages (status)
        ''')
        cursor.execute("UPDATE missed_messages SET status = 'pending' WHERE status = 'processing'")
    print("Database initialized successfully.")
    print("Group mappings database initialized successfully.")

def add_group_mapping(name, main_id, lesser_id, archive_id):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO group_mappings (main_group_name, main_group_id, lesser_group_id, archive_group_id) VALUES (?, ?, ?, ?)",
                (name, main_id, lesser_id, archive_id)
            )
        return True, "Mapping added successfully."
    except sqlite3.IntegrityError:
        return False, "Error: One or more of the provided Group IDs already exist in the database."

def get_all_mappings():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, main_group_name, main_group_id, lesser_group_id, archive_group_id FROM group_mappings ORDER BY main_group_name")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_mapping_by_id(mapping_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM group_mappings WHERE id = ?", (mapping_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def delete_mapping(mapping_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM group_mappings WHERE id = ?", (mapping_id,))
        return cursor.rowcount > 0 # Returns True if a row was deleted

def _find_group_name(conn, group_id: int):
    cursor = conn.cursor()
    cursor.execute("SELECT main_group_name FROM group_mappings WHERE main_group_id = ?", (group_id,))
    row = cursor.fetchone()
    if row: return f"{row[0]}_A"
    cursor.execute("SELECT main_group_name FROM group_mappings WHERE lesser_group_id = ?", (group_id,))
    row = cursor.fetchone()
    if row: return f"{row[0]}_B"
    cursor.execute("SELECT main_group_name FROM group_mappings WHERE archive_group_id = ?", (group_id,))
    row = cursor.fetchone()
    if row: return f"{row[0]}_C"
    return None

def set_del_schedule(group_id: int, time_ist: str, spare_minutes: int):
    with sqlite3.connect(DB_PATH) as conn:
        group_name = _find_group_name(conn, group_id)
        if not group_name:
            return False, f"Group ID {group_id} not found in any mapping."
        cursor = conn.cursor()
        cursor.execute(
            "REPLACE INTO del_schedules (group_id, group_name, time_ist, spare_minutes, enabled) VALUES (?, ?, ?, ?, 1)",
            (group_id, group_name, time_ist, spare_minutes)
        )
    return True, "Schedule set successfully."

def delete_del_schedule(group_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM del_schedules WHERE group_id = ?", (group_id,))
        return cursor.rowcount > 0

def get_all_del_schedules():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        rows = cursor.execute("SELECT group_id, group_name, time_ist, spare_minutes FROM del_schedules ORDER BY group_name").fetchall()
        return [dict(row) for row in rows]

def set_bot_status(group_id: int, pid: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        if pid is None:
            cursor.execute("DELETE FROM system_state WHERE key = ?", (f"bot_pid_{group_id}",))
        else:
            cursor.execute("REPLACE INTO system_state (key, value) VALUES (?, ?)", (f"bot_pid_{group_id}", str(pid)))

def get_bot_status(group_id: int):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM system_state WHERE key = ?", (f"bot_pid_{group_id}",))
            result = cursor.fetchone()
            return int(result[0]) if result else None
    except (sqlite3.Error, ValueError):
        return None

def clear_bot_status(group_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM system_state WHERE key = ?", (f"bot_pid_{group_id}",))

def get_all_active_pids():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM system_state WHERE key LIKE 'bot_pid_%'")
        result = {}
        for row in cursor.fetchall():
            key = row['key']
            value = row['value']
            if not value or value == 'None':  # extra safety
                continue
            try:
                group_id = int(key.split('_')[-1])
                pid = int(value)
                result[group_id] = pid
            except (ValueError, IndexError):
                continue
        return result
        
def get_groups_by_tag(tag: str):
    tag = tag.upper()
    if tag not in ['A', 'B', 'C']:
        return []
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        rows = cursor.execute("SELECT id, main_group_name, main_group_id, lesser_group_id, archive_group_id FROM group_mappings").fetchall()
        results = []
        for row in rows:
            if tag == 'A':
                results.append({
                    "id": row["id"],
                    "group_name": f"{row["main_group_name"]}_A",
                    "group_id": row["main_group_id"]
                })
            elif tag == 'B':
                results.append({
                    "id": row["id"],
                    "group_name": f"{row['main_group_name']}_B",
                    "group_id": row["lesser_group_id"]
                })
            elif tag == 'C':
                results.append({
                    "id": row["id"],
                    "group_name": f"{row['main_group_name']}_C",
                    "group_id": row["archive_group_id"]
                })
        return sorted(results, key=lambda x: x['group_name'])

def log_missed_message(message_obj, failed_group_id: int, reason: str):
    message_json = message_obj.to_json()
    source_chat_id = message_obj.chat.id
    source_message_id = message_obj.message_id
    try:
        with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO missed_messages 
                (source_chat_id, source_message_id, failed_group_id, reason, message_json, status) 
                VALUES (?, ?, ?, ?, ?, 'pending')
                """,
                (source_chat_id, source_message_id, failed_group_id, reason, message_json)
            )
        return True
    except Exception as e:
        print(f"CRITICAL: FAILED TO LOG MISSED MESSAGE TO DATABASE. Error: {e}")
        return False

def log_missed_media_group(messages_list, failed_group_id: int, reason: str):
    messages_data = [json.loads(m.to_json()) for m in messages_list]
    message_json = json.dumps(messages_data)
    source_chat_id = messages_list[0].chat.id
    source_message_id = messages_list[0].message_id
    try:
        with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO missed_messages 
                (source_chat_id, source_message_id, failed_group_id, reason, message_json, status) 
                VALUES (?, ?, ?, ?, ?, 'pending')
                """,
                (source_chat_id, source_message_id, failed_group_id, reason, message_json)
            )
        return True
    except Exception as e:
        print(f"CRITICAL: FAILED TO LOG MISSED MEDIA GROUP. Error: {e}")
        return False

def get_pending_missed_messages(limit: int = 10):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM missed_messages WHERE status = 'pending' ORDER BY logged_at ASC LIMIT ?", 
            (limit,)
        )
        rows = cursor.fetchall()
        if rows:
            ids = [row['id'] for row in rows]
            placeholders = ','.join(['?'] * len(ids))
            cursor.execute(f"UPDATE missed_messages SET status = 'processing' WHERE id IN ({placeholders})", ids)
        return [dict(row) for row in rows]

def update_missed_message_status(missed_message_id: int, status: str, reason: str = None):
    if status not in ['success', 'abandoned', 'pending']:
        raise ValueError("Status must be 'success', 'abandoned', or 'pending'")
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            if reason:
                cursor.execute(
                    "UPDATE missed_messages SET status = ?, reason = ? WHERE id = ?",
                    (status, reason, missed_message_id)
                )
            else:
                cursor.execute(
                    "UPDATE missed_messages SET status = ? WHERE id = ?",
                    (status, missed_message_id)
                )
            return cursor.rowcount > 0
    except Exception as e:
        print(f"ERROR: Failed to update missed message status for ID {missed_message_id}. Error: {e}")
        return False

def get_all_missed_messages_for_api():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, logged_at, source_chat_id, source_message_id, failed_group_id, reason, status FROM missed_messages ORDER BY logged_at DESC"
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def delete_old_resolved_messages(days_old: int = 7):
    cutoff_date = (datetime.now() - timedelta(days=days_old)).isoformat()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM missed_messages WHERE logged_at <= ? AND (status = 'success' OR status = 'abandoned')",
                (cutoff_date,)
            )
            deleted_count = cursor.rowcount
            if deleted_count > 0:
                print(f"Cleanup: Deleted {deleted_count} resolved missed messages older than {days_old} days.")
            return deleted_count
    except Exception as e:
        print(f"ERROR: Failed to clean up old missed messages. Error: {e}")
        return 0

def delete_missed_message(missed_message_id: int):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM missed_messages WHERE id = ?", (missed_message_id,))
            return cursor.rowcount > 0
    except Exception as e:
        print(f"ERROR: Failed to delete missed message ID {missed_message_id}. Error: {e}")
        return False

def increment_missed_message_attempt(missed_message_id: int):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE missed_messages SET attempt_count = attempt_count + 1, status = 'pending' WHERE id = ?", 
                (missed_message_id,)
            )
            cursor.execute(
                "UPDATE missed_messages SET status = 'abandoned', reason = reason || ' (Max 10 Retries Reached)' WHERE id = ? AND attempt_count >= 10", 
                (missed_message_id,)
            )
            return cursor.rowcount > 0
    except Exception as e:
        print(f"ERROR: Failed to increment attempt count. Error: {e}")
        return False
if __name__ == '__main__':
    initialize_database()
