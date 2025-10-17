import streamlit as st
import requests
import time
import pandas as pd

# --- Configuration ---
st.set_page_config(page_title="Bot Control Panel", layout="wide") # Use wide layout
BASE_URL = "http://127.0.0.1:8000"

# --- Main UI ---
st.title("🤖 Telegram Bot Control Panel")

# --- Main Layout (2 columns) ---
col1, col2 = st.columns(2)

with col1:
    # --- Status and Controls ---
    st.header("Bot Status & Controls")
    
    # Status display logic... (no changes needed)
    
    # Start/Stop buttons... (no changes needed)

    st.divider()

    # --- Group Configuration ---
    st.header("Group Configuration")
    
    with st.form("add_group_form"):
        st.subheader("Add New Group Mapping")
        main_group_name = st.text_input("Friendly Name (e.g., 'Project Alpha')")
        main_group_id = st.text_input("Main Group ID")
        lesser_group_id = st.text_input("Lesser Group ID")
        archive_group_id = st.text_input("Archive Group ID")
        submitted = st.form_submit_button("Add Mapping")
        if submitted:
            try:
                payload = {
                    "main_group_name": main_group_name,
                    "main_group_id": int(main_group_id),
                    "lesser_group_id": int(lesser_group_id),
                    "archive_group_id": int(archive_group_id)
                }
                response = requests.post(f"{BASE_URL}/groups", json=payload)
                if response.status_code == 200:
                    st.success("Group mapping added! Restart the bot to apply changes.")
                else:
                    st.error(f"Error: {response.json().get('detail')}")
            except (ValueError, TypeError):
                st.error("Please ensure all IDs are valid integers.")
            except requests.exceptions.ConnectionError:
                st.error("API Connection Error.")


with col2:
    # --- Danger Zone ---
    st.header("⚠️ Danger Zone")
    st.subheader("Purge Group Messages")
    
    # Fetch groups for the dropdown
    try:
        groups_response = requests.get(f"{BASE_URL}/groups")
        if groups_response.status_code == 200:
            all_groups = groups_response.json()
            # Create a user-friendly list for the selectbox
            group_options = {f"{g['main_group_name']} ({g['main_group_id']})": g['main_group_id'] for g in all_groups}
            
            if group_options:
                selected_group_str = st.selectbox("Select a Main Group to Purge:", options=group_options.keys())
                group_id_to_purge = group_options[selected_group_str]

                confirm_purge = st.checkbox("I understand this is irreversible and I want to proceed.")
                if st.button("🔥 Purge Selected Group", type="primary", disabled=not confirm_purge):
                    response = requests.post(f"{BASE_URL}/actions/purge", json={"group_id": group_id_to_purge})
                    if response.status_code == 200:
                        st.success(f"Purge command sent for {selected_group_str}. Check backend console.")
                    else:
                        st.error(f"Error: {response.json().get('detail')}")
            else:
                st.info("No groups configured. Add a group mapping to enable purging.")
        else:
            st.error("Could not fetch group list from API.")
    except requests.exceptions.ConnectionError:
        st.error("API Connection Error.")

    st.divider()
    
    # --- Display Current Mappings ---
    st.subheader("Current Group Mappings")
    try:
        groups_response = requests.get(f"{BASE_URL}/groups")
        if groups_response.status_code == 200:
            df = pd.DataFrame(groups_response.json())
            # Add a delete button column
            df['Delete'] = [False] * len(df)
            edited_df = st.data_editor(df, disabled=['id', 'main_group_name', 'main_group_id', 'lesser_group_id', 'archive_group_id'])
            
            rows_to_delete = edited_df[edited_df['Delete'] == True]
            if not rows_to_delete.empty:
                for index, row in rows_to_delete.iterrows():
                    if st.button(f"Confirm Delete for '{row['main_group_name']}'"):
                        response = requests.delete(f"{BASE_URL}/groups/{row['id']}")
                        if response.status_code == 200:
                            st.success(f"Deleted '{row['main_group_name']}'. Restart bot to apply.")
                            st.rerun()
                        else:
                            st.error("Failed to delete.")
    except Exception:
        st.error("Could not display group mappings.")