import streamlit as st
import requests

st.set_page_config(page_title="VeriHouse", page_icon="🛡️")
st.title("🛡️ VeriHouse Property Audit")
st.markdown("Coverage: San Francisco, CA (Smart Search)")

# --- INPUTS ---
col1, col2 = st.columns(2)
st_num = col1.text_input("Street Number", value="301")
st_name = col2.text_input("Street Name", value="MISSION")
run_btn = st.button("Verify Property", type="primary")

# --- ENGINE ---
if run_btn:
    with st.spinner("Searching City Archives..."):
        # We use the Active Database (i98e)
        url = "https://data.sfgov.org/resource/i98e-djp9.json"
        
        clean_num = st_num.strip()
        base_name = st_name.strip().upper()
        
        # THE SMART RETRY LOGIC
        # We define 3 variations of the street name to try
        variations = [base_name] # 1. Try "MISSION"
        if "ST" not in base_name:
            variations.append(f"{base_name} ST")      # 2. Try "MISSION ST"
            variations.append(f"{base_name} STREET")  # 3. Try "MISSION STREET"
            variations.append(f"{base_name} AVE")     # 4. Try "MISSION AVE"
        
        found_data = []
        used_name = ""
        
        for name_try in variations:
            params = {
                'street_number': clean_num,
                'street_name': name_try,
                '$limit': 50,
                '$order': 'permit_creation_date DESC'
            }
            try:
                r = requests.get(url, params=params)
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
                    found_data = data
                    used_name = name_try
                    break # Stop looking, we found it!
            except:
                pass

        # --- RESULTS ---
        if len(found_data) > 0:
            st.success(f"✅ Found {len(found_data)} permits using name: '{used_name}'")
            
            # Simple Risk Scan
            risks = []
            for p in found_data:
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
                
            st.dataframe(found_data)
            
        else:
            st.warning(f"Could not find address #{clean_num} on {base_name}.")
            st.info(f"We tried searching: {', '.join(variations)}")
            st.write("Tip: Verify the street number is correct for this specific building.")
