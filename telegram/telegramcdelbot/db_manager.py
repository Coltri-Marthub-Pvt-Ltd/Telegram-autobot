import sqlite3
from pathlib import Path
import json

# --- Configuration ---
DB_DIRECTORY = Path(__file__).parent / "temp" / "db"
DB_PATH = DB_DIRECTORY / 'group_mappings.db'

def initialize_database():
    """Creates the database and the group_mappings table if they don't exist."""
    DB_DIRECTORY.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
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
    print("Database initialized successfully.")
    print("Group mappings database initialized successfully.")

def add_group_mapping(name, main_id, lesser_id, archive_id):
    """Adds a new set of group mappings to the database."""
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
    """Retrieves all group mappings from the database."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, main_group_name, main_group_id, lesser_group_id, archive_group_id FROM group_mappings ORDER BY main_group_name")
        rows = cursor.fetchall()
        # Convert row objects to plain dictionaries for API responses
        return [dict(row) for row in rows]

def get_mapping_by_id(mapping_id: int):
    """Retrieves a single group mapping by its primary key ID."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM group_mappings WHERE id = ?", (mapping_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def delete_mapping(mapping_id: int):
    """Deletes a group mapping by its unique database ID."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM group_mappings WHERE id = ?", (mapping_id,))
        return cursor.rowcount > 0 # Returns True if a row was deleted

def _find_group_name(conn, group_id: int):
    """Internal helper to find the constructed group name from a group ID."""
    cursor = conn.cursor()
    # Check Main groups
    cursor.execute("SELECT main_group_name FROM group_mappings WHERE main_group_id = ?", (group_id,))
    row = cursor.fetchone()
    if row: return f"{row[0]}_A"
    # Check Lesser groups
    cursor.execute("SELECT main_group_name FROM group_mappings WHERE lesser_group_id = ?", (group_id,))
    row = cursor.fetchone()
    if row: return f"{row[0]}_B"
    # Check Archive groups
    cursor.execute("SELECT main_group_name FROM group_mappings WHERE archive_group_id = ?", (group_id,))
    row = cursor.fetchone()
    if row: return f"{row[0]}_C"
    return None

def set_del_schedule(group_id: int, time_ist: str, spare_minutes: int):
    """Creates or updates a purge schedule, finding the group name automatically."""
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
    """Deletes a purge schedule for a single group."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM del_schedules WHERE group_id = ?", (group_id,))
        return cursor.rowcount > 0

def get_all_del_schedules():
    """Retrieves all active schedules from the del_schedules table."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        rows = cursor.execute("SELECT group_id, group_name, time_ist, spare_minutes FROM del_schedules ORDER BY group_name").fetchall()
        return [dict(row) for row in rows]



def set_bot_status(group_id: int, pid: int):
    """Saves a running PID for a specific group. If pid is None, deletes the entry."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        if pid is None:
            cursor.execute("DELETE FROM system_state WHERE key = ?", (f"bot_pid_{group_id}",))
        else:
            cursor.execute("REPLACE INTO system_state (key, value) VALUES (?, ?)", (f"bot_pid_{group_id}", str(pid)))

def get_bot_status(group_id: int):
    """Retrieves the PID for a specific group."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM system_state WHERE key = ?", (f"bot_pid_{group_id}",))
            result = cursor.fetchone()
            return int(result[0]) if result else None
    except (sqlite3.Error, ValueError):
        return None

def clear_bot_status(group_id: int):
    """Removes the PID for a specific group."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM system_state WHERE key = ?", (f"bot_pid_{group_id}",))

def get_all_active_pids():
    """Retrieves all stored PIDs for crash recovery."""
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
                # Skip malformed entries
                continue
        return result
        
def get_groups_by_tag(tag: str):
    """
    Retrieves a list of groups based on a tag (A, B, or C).
    'A': Main groups
    'B': Lesser groups
    'C': Archive groups
    """
    tag = tag.upper()
    if tag not in ['A', 'B', 'C']:
        return []

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        rows = cursor.execute("SELECT id, main_group_name, main_group_id, lesser_group_id, archive_group_id FROM group_mappings").fetchall()

        # --- NEW: Transform the data based on the tag ---
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

# Initialize the DB when the module is first imported or run
if __name__ == '__main__':
    initialize_database()