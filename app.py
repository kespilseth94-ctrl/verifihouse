import streamlit as st
import requests

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="VeriHouse", page_icon="🛡️")
st.title("🛡️ VeriHouse Property Audit")
st.markdown("Coverage: San Francisco, CA (Master DB)")

# --- INPUTS ---
col1, col2 = st.columns(2)
st_num = col1.text_input("Street Number", value="301")
st_name = col2.text_input("Street Name", value="MISSION")
run_btn = st.button("Verify Property", type="primary")

# --- ENGINE ---
if run_btn:
    with st.spinner("Accessing Master Records..."):
        # 1. CONNECT TO THE MASTER DATABASE (p4e4)
        url = "https://data.sfgov.org/resource/p4e4-a5a7.json"
        
        # 2. BROAD QUERY
        # We only ask for the street name. We do NOT ask for the number.
        # This avoids "301" vs "301-305" mismatch errors.
        clean_name = st_name.strip().upper()
        
        # This asks for ANY street that starts with your input
        params = {
            '$where': f"street_name like '{clean_name}%'",
            '$limit': 2000, 
            '$order': 'permit_creation_date DESC'
        }
        
        try:
            r = requests.get(url, params=params)
            data = r.json()
            
            # 3. DEBUGGER: Did we at least find the street?
            if len(data) == 0:
                st.error(f"CRITICAL: The city returned 0 permits for '{clean_name}'.")
                st.info("Try a simpler street name (e.g., type 'MISSION' instead of 'MISSION ST')")
            else:
                # 4. PYTHON FILTERING (The smart part)
                # Now we look for '301' inside the pile we just downloaded
                matches = []
                nearby = []
                
                clean_num = st_num.strip()
                
                for p in data:
                    p_num = str(p.get('street_number', ''))
                    # Check if our number is exactly the permit number
                    if p_num == clean_num:
                        matches.append(p)
                    elif len(nearby) < 10:
                        nearby.append(p)

                # 5. RESULTS
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
                        st.info("No major keywords detected in history.")
                        
                    st.dataframe(matches)
                
                else:
                    st.warning(f"We found {len(data)} permits on {clean_name}, but none matched #{clean_num}.")
                    st.write("Here are the addresses we DID find on this street (check for typos):")
                    # Show the user what the database ACTUALLY has
                    debug_table = [{"Number": m.get('street_number'), "Street": m.get('street_name'), "Date": m.get('permit_creation_date')} for m in nearby]
                    st.table(debug_table)

        except Exception as e:
            st.error(f"Connection Error: {e}")
