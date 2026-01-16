import streamlit as st
import requests

st.set_page_config(page_title="VeriHouse", page_icon="🛡️")
st.title("🛡️ VeriHouse Property Audit")
st.markdown("Coverage: San Francisco, CA")

# --- INPUTS ---
col1, col2 = st.columns(2)
st_num = col1.text_input("Street Number", value="301")
st_name = col2.text_input("Street Name", value="Mission") 
run_btn = st.button("Verify Property", type="primary")

# --- ENGINE ---
if run_btn:
    with st.spinner("Searching City Database..."):
        url = "https://data.sfgov.org/resource/i98e-djp9.json"
        
        # 1. CAPITALIZATION FIX (The Secret Sauce)
        # The city uses "Mission", not "MISSION" or "mission"
        clean_name = st_name.strip().title() 
        clean_num = st_num.strip()
        
        # 2. TARGETED SEARCH
        # We ask for the specific street name in the correct format
        params = {
            'street_name': clean_name,
            '$limit': 2000,
            '$order': 'permit_creation_date DESC'
        }
        
        try:
            r = requests.get(url, params=params)
            data = r.json()
            
            # 3. FILTER FOR NUMBER
            matches = []
            if isinstance(data, list):
                for p in data:
                    p_num = str(p.get('street_number', ''))
                    # Check if "301" is in "301" or "301-303"
                    if clean_num in p_num:
                        matches.append(p)

            # 4. RESULTS
            if len(matches) > 0:
                st.success(f"✅ VERIFIED: Found {len(matches)} permits for {clean_num} {clean_name}!")
                
                # Risk Logic
                risks = []
                for p in matches:
                    desc = str(p.get('description', '')).lower()
                    date = p.get('permit_creation_date', 'N/A')[:10]
                    if "solar" in desc and "lease" in desc:
                        risks.append(f"⚠️ SOLAR LEASE: {date}")
                    if "knob" in desc:
                        risks.append(f"⚡ KNOB & TUBE WIRING: {date}")
                
                if risks:
                    for r in risks: st.error(r)
                else:
                    st.info("No major 'Red Flag' keywords found in recent history.")
                
                # Show Data
                st.dataframe(matches)
            
            else:
                st.warning(f"We found permits on '{clean_name}', but none matched #{clean_num}.")
                st.write("Tip: Do NOT add 'Street' or 'St' to the name box. Just 'Mission'.")

        except Exception as e:
            st.error(f"Error: {e}")
