import streamlit as st
import requests
import datetime

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="VeriHouse | Certified Home History", page_icon="🛡️", layout="wide")

# --- BRANDING CSS ---
st.markdown("""
    <style>
    .main-header { font-family: 'Helvetica Neue', sans-serif; color: #2C3E50; }
    .score-card { 
        padding: 25px; 
        border-radius: 12px; 
        background-color: #ffffff; 
        border: 1px solid #e1e4e8;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        text-align: center;
    }
    .metric-value { font-size: 2.5em; font-weight: 800; color: #2C3E50; }
    .metric-label { font-size: 0.9em; color: #586069; text-transform: uppercase; letter-spacing: 1.5px; }
    .badge-verified { background-color: #d1fae5; color: #065f46; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 0.9em; }
    .badge-warning { background-color: #fee2e2; color: #991b1b; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 0.9em; }
    </style>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
with st.sidebar:
    st.title("🛡️ VeriHouse")
    st.markdown("**The Standard for Home Verification.**")
    st.divider()
    st.caption("Coverage: San Francisco, CA")
    st.warning("Disclaimer: Not a professional inspection. Verify with city.")

# --- MAIN HERO SECTION ---
st.markdown("<h1 style='text-align: center; color: #2C3E50;'>VeriHouse Property Audit</h1>", unsafe_allow_html=True)
st.write("")

# --- INPUT SECTION ---
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    with st.container():
        c1, c2 = st.columns(2)
        street_num = c1.text_input("Street Number", value="301")
        street_name = c2.text_input("Street Name", value="MISSION")
        run_btn = st.button("Verify Property", type="primary", use_container_width=True)

# --- LOGIC ENGINE ---
def calculate_verihouse_score(permits):
    score = 100
    findings = []
    deductions = {"SOLAR LEASE": -15, "KNOB & TUBE": -25, "UNPERMITTED ROOF": -10}
    solar_lease_terms = ["SUNRUN", "SOLARCITY", "TESLA", "LEASE", "PPA"]
    elec_risk = ["KNOB", "TUBE", "UNGROUNDED"]
    
    for p in permits:
        desc = str(p.get('description', '')).upper()
        date = p.get('permit_creation_date', 'N/A')[:4]
        
        if "SOLAR" in desc:
            is_lease = any(term in desc for term in solar_lease_terms)
            if is_lease:
                score += deductions["SOLAR LEASE"]
                findings.append({"type": "warning", "msg": f"Encumbered Asset: Solar Lease detected ({date})"})
            else:
                findings.append({"type": "verified", "msg": f"Clean Asset: Owned Solar System detected ({date})"})
        
        if any(k in desc for k in elec_risk):
            score += deductions["KNOB & TUBE"]
            findings.append({"type": "warning", "msg": f"Safety Risk: Evidence of Knob & Tube wiring ({date})"})

    return max(score, 0), findings

# --- REPORT DISPLAY ---
if run_btn:
    with st.spinner(f"Searching Master Database for {street_num} {street_name}..."):
        # SWITCHING BACK TO MASTER DATABASE (p4e4)
        url = "https://data.sfgov.org/resource/p4e4-a5a7.json"
        
        # KEEPING THE SMART SEARCH (Starts With...)
        query_string = f"street_number = '{street_num}' AND street_name like '{street_name.upper()}%'"
        params = {'$where': query_string, "$limit": 50, "$order": "permit_creation_date DESC"}
        
        try:
            r = requests.get(url, params=params)
            data = r.json()
            
            if len(data) == 0:
                st.error(f"DEBUG: Master Database (p4e4) returned 0 records.")
                st.info(f"Query: {query_string}")
            
            final_score, notes = calculate_verihouse_score(data)
            
            st.divider()
            m1, m2, m3 = st.columns(3)
            with m1: st.metric("VeriHouse Score", final_score)
            with m2: st.metric("Asset Tier", "Standard" if final_score < 80 else "Gold")
            with m3: st.metric("Records Found", len(data))

            st.write("")
            st.subheader("📋 Verification Log")
            if len(data) > 0:
                st.dataframe(data) # Show the raw data table to PROVE it found them

        except Exception as e:
            st.error(f"Connection Error: {e}")
