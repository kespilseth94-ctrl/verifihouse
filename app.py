import streamlit as st
import requests

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="VeriHouse", page_icon="🛡️")
st.title("🛡️ VeriHouse Property Audit")
st.markdown("Coverage: San Francisco, CA (Active Permits)")

# --- INPUTS ---
col1, col2 = st.columns(2)
st_num = col1.text_input("Street Number", value="301")
st_name = col2.text_input("Street Name", value="MISSION")
run_btn = st.button("Verify Property", type="primary")

# --- ENGINE ---
if run_btn:
    with st.spinner("Connecting to Active Database..."):
        # 1. USE THE ACTIVE DATABASE (The one that found 2 records earlier)
        url = "https://data.sfgov.org/resource/i98e-djp9.json"
        
        # 2. SIMPLE QUERY
        # "Find permits where the street number is X and street name starts with Y"
        clean_name = st_name.strip().upper()
        clean_num = st_num.strip()
        
        params = {
            '$where': f"street_number = '{clean_num}' AND street_name like '{clean_name}%'",
            '$limit': 50,
            '$order': 'permit_creation_date DESC'
        }
        
        try:
            r = requests.get(url, params=params)
            data = r.json()
            
            # 3. RESULTS DISPLAY (No Risk Logic, just Raw Data)
            if len(data) > 0:
                st.success(f"✅ SUCCESS: Found {len(data)} permits!")
                st.write("Here is the raw data from the city:")
                st.dataframe(data) 
            else:
                st.warning("Connected, but found 0 records matching that specific number.")
                st.info(f"Try searching for just the street name '{clean_name}' to see if the building uses a different number.")

        except Exception as e:
            st.error(f"Connection Error: {e}")
