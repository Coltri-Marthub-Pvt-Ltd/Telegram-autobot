import os
import time
import requests
from dotenv import load_dotenv
import db_manager
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    print("❌ Error: BOT_TOKEN not found in .env")
    exit(1)

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/getChat"

def get_actual_group_name(chat_id):
    if not chat_id:
        return "No ID provided"
    try:
        response = requests.get(f"{API_URL}?chat_id={chat_id}", timeout=10)
        data = response.json()
        if data.get("ok"):
            result = data.get("result", {})
            return result.get("title", "Unknown Name (Could be a private user ID)")
        else:
            return f"⚠️ API Error: {data.get('description', 'Unknown')}"
    except Exception as e:
        return f"❌ Request Failed: {e}"

def main():
    print("Initiating database connection...")
    db_manager.initialize_database() 
    print("Fetching mappings from the database...\n")
    mappings = db_manager.get_all_mappings()
    if not mappings:
        print("No mappings found in the database.")
        return
    for mapping in mappings:
        mapping_id = mapping['id'] if 'id' in mapping else 'N/A'
        db_name = mapping['main_group_name']
        main_id = mapping['main_group_id']
        lesser_id = mapping['lesser_group_id']
        archive_id = mapping['archive_group_id']
        print("="*70)
        print(f"Mapping Database ID: {mapping_id} | Base Name: {db_name}")
        print("-" * 70)
        # Check Group A
        actual_a = get_actual_group_name(main_id)
        print(f"ID: {main_id}")
        print(f" -> DB Expects:  {db_name}_A")
        print(f" -> TG Actual:   {actual_a}")
        time.sleep(3)
        # Check Group B
        actual_b = get_actual_group_name(lesser_id)
        print(f"\nID: {lesser_id}")
        print(f" -> DB Expects:  {db_name}_B")
        print(f" -> TG Actual:   {actual_b}")
        time.sleep(3)
        # Check Group C
        actual_c = get_actual_group_name(archive_id)
        print(f"\nID: {archive_id}")
        print(f" -> DB Expects:  {db_name}_C")
        print(f" -> TG Actual:   {actual_c}")
        time.sleep(3)
        print("="*70 + "\n")
    print("✅ Scan Complete.")

if __name__ == "__main__":
    main()


