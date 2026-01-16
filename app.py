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
        # We use the 'q' parameter which searches ALL columns for the text
        # This is much stronger than filtering specific columns
        url = "https://data.sfgov.org/resource/p4e4-a5a7.json"
        
        # We construct a simple query string "301 MISSION"
        full_query = f"{st_num} {st_name}"
        params = {'q': full_query, '$limit': 50, '$order': 'permit_creation_date DESC'}
        
        try:
            r = requests.get(url, params=params)
            data = r.json()
            
            if len(data) == 0:
                st.error("No records found.")
                st.info(f"Database searched for text: '{full_query}'")
            else:
                st.success(f"Found {len(data)} permits!")
                
                # Simple Risk Logic
                risk_found = False
                for p in data:
                    desc = str(p.get('description', '')).upper()
                    date = p.get('permit_creation_date', 'N/A')[:10]
                    
                    if "SOLAR" in desc:
                        st.warning(f"☀️ SOLAR DETECTED: {date}")
                        risk_found = True
                    if "KNOB" in desc:
                        st.error(f"⚡ KNOB & TUBE WIRING: {date}")
                        risk_found = True
                
                if not risk_found:
                    st.info("No major risks flagged in recent history.")
                    
                # Show Raw Data for Proof
                st.dataframe(data)

        except Exception as e:
            st.error(f"Connection Error: {e}")
