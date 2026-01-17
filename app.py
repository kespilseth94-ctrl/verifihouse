import streamlit as st
import requests
import datetime

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="VeriHouse | Predictive Asset History", 
    page_icon="🛡️", 
    layout="wide"
)

# --- 2. CUSTOM STYLING ---
st.markdown("""
    <style>
    .main-header { font-family: 'Helvetica Neue', sans-serif; color: #2C3E50; }
    .score-card { 
        padding: 20px; 
        border-radius: 10px; 
        background-color: #f8f9fa; 
        border: 1px solid #e9ecef;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .metric-value { font-size: 2.2em; font-weight: 800; color: #2C3E50; }
    .metric-label { font-size: 0.85em; color: #6c757d; text-transform: uppercase; letter-spacing: 1px; }
    .badge-risk { background-color: #fee2e2; color: #991b1b; padding: 4px 10px; border-radius: 15px; font-size: 0.8em; font-weight: bold; }
    .badge-safe { background-color: #d1fae5; color: #065f46; padding: 4px 10px; border-radius: 15px; font-size: 0.8em; font-weight: bold; }
    .badge-pred { background-color: #e0f2fe; color: #0369a1; padding: 4px 10px; border-radius: 15px; font-size: 0.8em; font-weight: bold; border: 1px solid #bae6fd; }
    </style>
""", unsafe_allow_html=True)

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🛡️ VeriHouse")
    st.markdown("**Residential Risk Intelligence**")
    
    # SILENT AUTHENTICATION
    # If key is in secrets, load it without showing ANY UI
    rentcast_key = None
    if 'rentcast_api_key' in st.secrets:
        rentcast_key = st.secrets['rentcast_api_key']
    else:
        # Only show input if secrets are missing (Fallback)
        st.markdown("### 🔑 Data Connections")
        rentcast_key = st.text_input("RentCast API Key", type="password")
    
    st.divider()
    st.info("System Status: Online 🟢")
    st.caption("1. SF Active Permits (Forensics)")
    st.caption("2. RentCast (Age & Predictive)")
    st.divider()
    st.warning("Disclaimer: Estimates are for planning only. Not a contractor quote.")

# --- 4. MAIN INTERFACE ---
st.markdown("<h1 style='text-align: center;'>VeriHouse Property Audit</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #666;'>Forensic Analysis + Predictive Maintenance Costing</p>", unsafe_allow_html=True)
st.write("")

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    with st.container():
        c1, c2 = st.columns(2)
        st_num = c1.text_input("Street Number", value="301")
        st_name = c2.text_input("Street Name", value="Mission") 
        run_btn = st.button("Generate Full Audit", type="primary", use_container_width=True)

# --- 5. ENGINE A: FORENSIC RISK (Gold Master Logic) ---
def analyze_risks(permits):
    score = 100
    findings = []
    
    # FORENSIC DICTIONARY
    risk_map = [
        {"keywords": ["KNOB", "TUBE"], "deduction": 25, "msg": "Major Electrical Risk: Knob & Tube Wiring detected.", "cat": "fire"},
        {"keywords": ["ALUMINUM WIRING"], "deduction": 15, "msg": "Fire Risk: Aluminum branch wiring detected.", "cat": "fire"},
        {"keywords": ["UNPERMITTED", "ILLEGAL WIRING"], "deduction": 20, "msg": "Compliance Risk: History of unpermitted work.", "cat": "legal"},
        {"keywords": ["UNDERPIN", "SHORING", "FOUNDATION REPAIR", "SETTLEMENT"], "deduction": 30, "msg": "Major Structural Risk: Foundation movement detected.", "cat": "structure"},
        {"keywords": ["SISTERING", "JOIST REPAIR", "DRY ROT", "TERMITE"], "deduction": 15, "msg": "Structural Decay: Frame damage (rot/termites) noted.", "cat": "structure"},
        {"keywords": ["FIRE DAMAGE", "FIRE REPAIR", "CHARRED", "SCORCH", "BURNING"], "deduction": 30, "msg": "Structural Risk: Evidence of past fire/burning.", "cat": "fire"},
        {"keywords": ["WATER DAMAGE", "LEAK", "MOLD", "FUNGAL"], "deduction": 20, "msg": "Health Risk: History of water intrusion or mold.", "cat": "water"},
        {"keywords": ["REMEDIATION", "ABATEMENT", "ASBESTOS", "LEAD PAINT"], "deduction": 10, "msg": "Toxic Material: History of hazmat remediation.", "cat": "health"},
        {"keywords": ["NOV ", "NOTICE OF VIOLATION", "ORDER OF ABATEMENT"], "deduction": 25, "msg": "Legal Risk: Property has received City Violations.", "cat": "legal"},
        {"keywords": ["SOLAR", "LEASE", "PPA", "SUNRUN", "TESLA"], "match_all": True, "deduction": 15, "msg": "Financial Encumbrance: Solar Lease detected.", "cat": "finance"},
    ]
    
    assets = [
        {"keywords": ["REROOF", "RE-ROOF", "NEW ROOF"], "msg": "Capital Improvement: Roof replaced recently."},
        {"keywords": ["SEISMIC", "RETROFIT", "BOLT"], "msg": "Safety Asset: Seismic retrofitting completed."},
        {"keywords": ["COPPER", "REPIPE"], "msg": "Plumbing Asset: Copper repiping detected."},
        {"keywords": ["100 AMP", "200 AMP", "PANEL UPGRADE"], "msg": "Electrical Asset: Main service panel upgraded."},
    ]

    for p in permits:
        desc = str(p.get('description', '')).upper()
        date = p.get('permit_creation_date', 'N/A')[:4]
        
        # Risks
        for risk in risk_map:
            if risk.get("match_all"):
                if "SOLAR" in desc and any(term in desc for term in ["LEASE", "PPA"]):
                    score -= risk["deduction"]
                    findings.append({"type": "risk", "msg": f"{risk['msg']} ({date})", "cat": risk['cat']})
            elif any(k in desc for k in risk["keywords"]):
                if "BURNING" in desc and any(safe in desc for safe in ["STOVE", "INSERT", "LOG"]): continue
                score -= risk["deduction"]
                findings.append({"type": "risk", "msg": f"{risk['msg']} ({date})", "cat": risk['cat']})
        
        # Assets
        for asset in assets:
             if any(k in desc for k in asset["keywords"]):
                 findings.append({"type": "safe", "msg": f"{asset['msg']} ({date})"})

    return max(score, 0), findings

# --- 6. ENGINE B: RENTCAST & PREDICTION ---
def get_property_details(number, street, api_key):
    if not api_key: return None
    url = "https://api.rentcast.io/v1/properties"
    address_query = f"{number} {street}, San Francisco, CA"
    params = {'address': address_query}
    headers = {'X-Api-Key': api_key}
