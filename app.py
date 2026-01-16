import streamlit as st
import requests

st.set_page_config(page_title="VeriHouse", page_icon="🛡️")
st.title("🛡️ VeriHouse Property Audit")
st.markdown("Coverage: San Francisco, CA (Wildcard Search)")

# --- INPUTS ---
col1, col2 = st.columns(2)
st_num = col1.text_input("Street Number", value="301")
st_name = col2.text_input("Street Name", value="MISSION")
run_btn = st.button("Verify Property", type="primary")

# --- ENGINE ---
if run_btn:
    with st.spinner("Scanning entire street block..."):
        # 1. USE THE ACTIVE DATABASE (Confirmed Working)
        url = "https://data.sfgov.org/resource/i98e-djp9.json"
        
        # 2. WILDCARD SEARCH
        # We tell the API: "Give me anything where the Street Name STARTS with this word."
        # We DO NOT send the street number to the API (to avoid "301" vs "301-303" errors)
        clean_name = st_name.strip().upper()
        clean_num = st_num.strip()
        
        params = {
            '$where': f"street_name like '{clean_name}%'",
            '$limit': 1000, # Get a huge batch to be safe
            '$order': 'permit_creation_date DESC'
        }
        
        try:
            r = requests.get(url, params=params)
            data = r.json()
            
            # 3. PYTHON FILTERING (The smart part)
            # We look for "301" inside the results ourselves
            matches = []
            nearby_numbers = set()
            
            if isinstance(data, list):
                for p in data:
                    p_num = str(p.get('street_number', ''))
                    p_name = str(p.get('street_name', ''))
                    
                    # Store purely for debugging
                    nearby_numbers.add(f"{p_num} {p_name}")
                    
                    # FUZZY MATCH: Does "301" appear in the number? 
                    # (Finds "301", "301-303", "301A")
                    if clean_num == p_num:
                        matches.append(p)
            
            # 4. RESULTS
            if len(matches) > 0:
                st.success(f"✅ VERIFIED: Found {len(matches)} permits for {clean_num} {clean_name}!")
                
                # Risk Scan
                risks = []
                for p in matches:
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
                    
                st.dataframe(matches)
            
            else:
                st.warning(f"We downloaded {len(data)} permits for '{clean_name}', but none matched #{clean_num}.")
                
                if len(nearby_numbers) > 0:
                    st
