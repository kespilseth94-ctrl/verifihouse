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
    with st.spinner("Scanning Modern Permit Database..."):
        # 1. USE THE MODERN DATABASE (i98e)
        url = "https://data.sfgov.org/resource/i98e-djp9.json"
        
        # 2. BROAD SEARCH: Fetch everything on the street, then filter locally
        # This prevents "Exact Match" errors on the street number
        clean_name = st_name.strip().upper()
        query = f"street_name like '{clean_name}%'"
        
        params = {
            '$where': query,
            '$limit': 2000, # Fetch a large batch to ensure we catch the number
            '$order': 'permit_creation_date DESC'
        }
        
        try:
            r = requests.get(url, params=params)
            data = r.json()
            
            # 3. FILTER LOCALLY (Robust Matching)
            # We look for the user's number inside the results
            exact_matches = []
            nearby_matches = []
            
            for p in data:
                p_num = str(p.get('street_number', ''))
                # Exact Match
                if p_num == st_num.strip():
                    exact_matches.append(p)
                # Save first 5 others for debugging
                elif len(nearby_matches) < 5:
                    nearby_matches.append(p)

            # 4. DISPLAY RESULTS
            if len(exact_matches) > 0:
                st.success(f"✅ Found {len(exact_matches)} permits for {st_num} {clean_name}!")
                
                # RISK SCANNER
                risks = []
                for p in exact_matches:
                    desc = str(p.get('description', '')).upper()
                    date = p.get('permit_creation_date', 'N/A')[:10]
                    if "SOLAR" in desc and "LEASE" in desc:
                        risks.append(f"⚠️ SOLAR LEASE: {date}")
                    if "KNOB" in desc:
                        risks.append(f"⚡ KNOB & TUBE WIRING: {date}")
                
                if risks:
                    for r in risks: st.error(r)
                else:
                    st.info("No immediate Red Flags detected in recent history.")
                
                with st.expander("View Raw Permit Log"):
                    st.dataframe(exact_matches)
            
            else:
                st.warning(f"No exact matches for #{st_num}.")
                if len(nearby_matches) > 0:
                    st.info(f"However, we DID find permits for these nearby buildings on {clean_name}:")
                    # Show nearby addresses so you KNOW the app is working
                    debug_data = [{"Number": m.get('street_number'), "Date": m.get('permit_creation_date')} for m in nearby_matches]
                    st.table(debug_data)
                else:
                    st.error(f"Zero records found for street name '{clean_name}'. Check spelling.")

        except Exception as e:
            st.error(f"Connection Error: {e}")
