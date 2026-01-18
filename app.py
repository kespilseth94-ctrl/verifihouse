import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# --- CONFIGURATION & SECRETS ---
st.set_page_config(page_title="VerifiHouse", layout="wide")

# Safe loading of secrets
try:
    rentcast_key = st.secrets["rentcast_key"]
except FileNotFoundError:
    st.error("Secrets file missing. Please check .streamlit/secrets.toml")
    st.stop()
except KeyError:
    st.error("Key 'rentcast_key' not found in secrets.toml")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.title("🛡️ VeriHouse")
    st.markdown("**The Standard for Home Verification.**")
    st.write("We analyze municipal data to certify the safety and quality of residential assets.")
    st.divider()
    st.success("System Online 🟢")
    st.caption("Coverage: San Francisco, CA")
    st.caption("v2.0 restored")
    
    # --- RESTORED DISCLAIMER ---
    st.divider()
    st.warning("""
    **Disclaimer:**
    This tool is for informational purposes only and does not constitute a professional home inspection. 
    VerifiHouse is not affiliated with the City of San Francisco. 
    Always verify public records with an official city clerk.
    """)

# --- FUNCTIONS ---

def fetch_rentcast_data(address_full):
    """Gets age, sqft, and tax data from RentCast."""
    url = "https://api.rentcast.io/v1/properties"
    params = {"address": address_full}
    headers = {"accept": "application/json", "X-Api-Key": rentcast_key}
    
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        return data[0] if data else None
    return None

def fetch_sf_permits(street_num, street_name):
    """
    Queries DataSF (Socrata API) for permits at this address.
    No API key required for basic queries.
    """
    # San Francisco Open Data Endpoint for Building Permits
    url = "https://data.sfgov.org/resource/i98e-djp9.json"
    
    # Query for exact address match
    # We use a SQL-like query (SoQL)
    street_name_upper = street_name.upper()
    query = f"street_number='{street_number}' AND street_name like '%{street_name_upper}%'"
    
    params = {
        "$where": query,
        "$order": "filed_date DESC",
        "$limit": 20
    }
    
    try:
        r = requests.get(url, params=params)
        if r.status_code == 200:
            return r.json()
    except:
        return []
    return []

def run_comparative_engine(rentcast_data, permits):
    """
    The Brain: Compares Age vs. Permits to find risks.
    """
    risks = []
    current_year = datetime.now().year
    
    # 1. Get Age
    year_built = rentcast_data.get("yearBuilt")
    if year_built:
        age = current_year - year_built
    else:
        age = 0
        
    # 2. Analyze Permit Recency
    has_recent_permit = False
    if permits:
        last_permit_date = permits[0].get("filed_date", "")
        if "202" in last_permit_date: # Rough check for post-2020
            has_recent_permit = True
            
    # 3. GENERATE RISKS (The Logic)
    
    # Risk A: Old Home, No Recent Work (Deferred Maintenance)
    if age > 40 and not has_recent_permit:
        risks.append({
            "type": "STRUCTURAL",
            "msg": f"High Risk: Home is {age} years old with no recent major permits found."
        })
        
    # Risk B: Unpermitted Renovations (Flip Risk)
    last_sale_date = rentcast_data.get("lastSaleDate", "")
    if last_sale_date and "202" in last_sale_date and not has_recent_permit:
        risks.append({
            "type": "LEGAL",
            "msg": "Flip Risk: Property sold recently but no permits filed for renovation."
        })

    # Risk C: Specific keywords in permit history
    for p in permits:
        desc = str(p.get("description", "")).lower()
        if "compliance" in desc or "violation" in desc:
            risks.append({
                "type": "LEGAL",
                "msg": f"Violation Found: {p.get('filed_date')} - {desc[:50]}..."
            })
            
    return age, risks

# --- MAIN UI ---
st.markdown("<h1 style='text-align: center;'>VerifiHouse Property Audit</h1>", unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    street_number = st.text_input("Street Number", placeholder="301")
with col2:
    street_name = st.text_input("Street Name", placeholder="Mission")

if st.button("Generate Full Audit", type="primary"):
    if not street_number or not street_name:
        st.warning("Please enter both a street number and name.")
    else:
        full_address = f"{street_number} {street_name}, San Francisco, CA"
        
        with st.spinner(f"Auditing {full_address}..."):
            
            # 1. FETCH DATA
            rc_data = fetch_rentcast_data(full_address)
            sf_data = fetch_sf_permits(street_number, street_name)
            
            if rc_data:
                # 2. RUN ANALYSIS
                age, detected_risks = run_comparative_engine(rc_data, sf_data)
                
                # 3. DISPLAY HEADER METRICS
                st.success("Audit Complete.")
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Year Built", rc_data.get("yearBuilt", "N/A"))
                m2.metric("Sq Ft", rc_data.get("squareFootage", "N/A"))
                m3.metric("Permit Count", len(sf_data))
                
                # Dynamic Score (Simple Logic)
                base_score = 100
                base_score -= (len(detected_risks) * 15)
                m4.metric("VeriHouse Score", base_score)

                # 4. FORENSIC LOG (The Risk Engine Output)
                st.subheader("📋 Forensic Log")
                if detected_risks:
                    for risk in detected_risks:
                        if risk['type'] == 'LEGAL':
                            st.error(f"⚖️ **LEGAL RISK:** {risk['msg']}")
                        else:
                            st.warning(f"🏗️ **STRUCTURE RISK:** {risk['msg']}")
                else:
                    st.success("No major forensic risks detected based on available data.")

                # 5. PERMIT HISTORY TABLE
                st.subheader("Permit History (City of SF)")
                if sf_data:
                    # Clean up data for display
                    df = pd.DataFrame(sf_data)
                    display_cols = ['filed_date', 'permit_number', 'description', 'status', 'cost']
                    # Only show cols that actually exist in the data
                    final_cols = [c for c in display_cols if c in df.columns]
                    st.dataframe(df[final_cols], use_container_width=True)
                else:
                    st.info("No permit history found in San Francisco Open Data.")

                # 6. RENTCAST RAW DATA (Optional)
                with st.expander("View Raw Property Data"):
                    st.json(rc_data)

            else:
                st.error("Property not found in RentCast database. Please check the address.")
