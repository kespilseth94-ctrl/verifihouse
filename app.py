import streamlit as st
import requests

st.set_page_config(page_title="VeriHouse Debugger", page_icon="🐞")
st.title("🐞 VeriHouse: Connection Debugger")

# --- INPUTS ---
col1, col2 = st.columns(2)
st_num = col1.text_input("Street Number", value="301")
st_name = col2.text_input("Street Name", value="MISSION")
run_btn = st.button("Run Diagnostic Test", type="primary")

if run_btn:
    # 1. TARGET THE ACTIVE DATABASE (i98e)
    url = "https://data.sfgov.org/resource/i98e-djp9.json"
    
    # 2. SIMPLEST POSSIBLE QUERY (No complex logic)
    # We ask for records where the Street Name is EXACTLY what you typed (UPPERCASE)
    clean_name = st_name.strip().upper()
    
    st.info(f"Connecting to: {url}")
    st.info(f"Asking for: street_name = '{clean_name}'")
    
    params = {
        'street_name': clean_name,  # Simple column filter (Safest method)
        '$limit': 10 
    }
    
    try:
        r = requests.get(url, params=params)
        data = r.json()
        
        st.divider()
        st.subheader("📡 Server Response")
        
        # 3. TRUTH SERUM (Show exactly what we got)
        if isinstance(data, dict):
            # If it's a Dictionary, IT IS AN ERROR.
            st.error("❌ DATABASE ERROR:")
            st.json(data)
        elif isinstance(data, list):
            # If it's a List, IT IS DATA.
            st.success(f"✅ Success! Received a list of {len(data)} items.")
            
            if len(data) == 0:
                st.warning("The list is empty. (0 Results)")
            else:
                st.write("First item in the list:")
                st.json(data[0]) # Show the first permit so we can see the column names
                
                # Check if our number exists
                found = False
                st.write("---")
                st.write(f"Scanning {len(data)} downloads for Number '{st_num}'...")
                for p in data:
                    # Check 'street_number' column (it might be '301' or '301-303')
                    if st_num in str(p.get('street_number', '')):
                        st.success(f"🎯 FOUND IT: {p.get('street_number')} {p.get('street_name')}")
                        st.json(p)
                        found = True
                
                if not found:
                    st.warning(f"Address number '{st_num}' not found in this batch.")
                    st.write("Numbers found in this batch:", [p.get('street_number') for p in data])

    except Exception as e:
        st.error(f"System Crash: {e}")
