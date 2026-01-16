import streamlit as st
import requests

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="VeriHouse", page_icon="🛡️")

st.title("🛡️ VeriHouse Property Audit")
st.markdown("Coverage: San Francisco, CA")

# --- INPUTS ---
col1, col2 = st.columns(2)
st_num = col1.text_input("Street Number", value="301")
st_name = col2.text_input("Street Name", value="MISSION")
run_btn = st.button("Verify Property", type="primary")

# --- ENGINE ---
if run_btn:
    with st.spinner("Searching City Database..."):
        # We use the OLD reliable database (p4e4)
        url = "https://data.sfgov.org/resource/p4e4-a5a7.json"
        
        # 1. CLEAN THE INPUTS
        # We strip spaces to avoid " 301 " errors
        clean_num = st_num.strip()
        clean_name = st_name.strip().upper()
        
        # 2. BUILD THE QUERY (The "Goldilocks" Filter)
        # This SQL logic says: "Number matches exactly" AND "Name starts with user input"
        query = f"street_number = '{clean_num}' AND street_name like '{clean_name}%'"
        
        params = {
            '$where': query,
            '$limit': 50,
            '$order': 'permit_creation_date DESC'
        }
        
        try:
            r = requests.get(url, params=params)
            data = r.json()
            
            # ERROR TRAP: Check if the API sent back an error message (Dict) instead of a list
            if isinstance(data, dict):
                st.error("City Database Error")
                st.json(data) # Show the error to the user
            elif len(data) == 0:
                st.warning("No records found.")
                st.info(f"The app looked for: Street #{clean_num} on {clean_name}...")
            else:
                st.success(f"Found {len(data)} permits!")
                
                # RISK LOGIC
                risks = []
                for p in data:
                    desc = str(p.get('description', '')).upper()
                    date = p.get('permit_creation_date', 'N/A')[:10]
                    
                    if "SOLAR" in desc and "LEASE" in desc:
                        risks.append(f"⚠️ SOLAR LEASE: {date}")
                    if "KNOB" in desc:
                        risks.append(f"⚡ KNOB & TUBE WIRING: {date}")
                
                if risks:
                    for r in risks: st.error(r)
                else:
                    st.info("No major 'Red Flag' keywords found in recent history.")
                    
                # Show Raw Data (So you know it's real)
                st.dataframe(data)

        except Exception as e:
            st.error(f"Connection Error: {e}")
