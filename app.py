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
        # 1. USE THE ACTIVE DATABASE
        url = "https://data.sfgov.org/resource/i98e-djp9.json"
        
        # 2. WILDCARD SEARCH PARAMETERS
        clean_name = st_name.strip().upper()
        clean_num = st_num.strip()
        
        # We ask for anything starting with the street name (e.g. "MISSION%")
        params = {
            '$where': f"street_name like '{clean_name}%'",
            '$limit': 2000,
            '$order': 'permit_creation_date DESC'
        }
        
        # 3. EXECUTE SEARCH (With Correct Error Handling)
        try:
            r = requests.get(url, params=params)
            data = r.json()
            
            # Filter the results locally in Python
            matches = []
            nearby_numbers = set()
            
            if isinstance(data, list):
                for p in data:
                    p_num = str(p.get('street_number', ''))
                    p_name = str(p.get('street_name', ''))
                    
                    # Debugging: Collect all numbers we find
                    nearby_numbers.add(f"{p_num} {p_name}")
                    
                    # Check if "301" is in the number (e.g. finds "301" and "301-305")
                    if clean_num in p_num:
                        matches.append(p)
            
            # 4. DISPLAY RESULTS
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
                    st.write("Here are the addresses we DID find on this street (check for typos):")
                    # Convert set to list and show first 10
                    st.write(list(nearby_numbers)[:10])
                else:
                    st.error("Zero results. The city might list this street under a completely different name.")

        except Exception as e:
            # This is the block that was missing/broken before
            st.error(f"System Error: {e}")
