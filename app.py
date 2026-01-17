import streamlit as st
import requests
import datetime

# --- 1. CONFIGURATION & STYLING ---
st.set_page_config(page_title="VeriHouse", page_icon="🛡️", layout="wide")
st.markdown("""
    <style>
    .score-card { padding: 20px; border-radius: 10px; background-color: #f8f9fa; border: 1px solid #e9ecef; text-align: center; }
    .metric-value { font-size: 2.2em; font-weight: 800; color: #2C3E50; }
    .metric-label { font-size: 0.85em; color: #6c757d; text-transform: uppercase; letter-spacing: 1px; }
    .badge-risk { background-color: #fee2e2; color: #991b1b; padding: 4px 10px; border-radius: 15px; font-size: 0.8em; font-weight: bold; }
    .badge-safe { background-color: #d1fae5; color: #065f46; padding: 4px 10px; border-radius: 15px; font-size: 0.8em; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- 2. SIDEBAR ---
with st.sidebar:
    st.title("🛡️ VeriHouse")
    st.caption("Residential Risk Intelligence")
    rentcast_key = "3a69e2134c654a4d95e7e7d506b76feb"
    st.divider()
    st.info("System Online 🟢")

# --- 3. STATE MANAGEMENT ---
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
    st.session_state.house_permits = []
    st.session_state.rc_data = None
    st.session_state.current_address = ""

# --- 4. MAIN INTERFACE ---
st.markdown("<h1 style='text-align: center;'>VeriHouse Property Audit</h1>", unsafe_allow_html=True)
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    with st.container():
        c1, c2 = st.columns(2)
        st_num = c1.text_input("Street Number", value="301")
        st_name = c2.text_input("Street Name", value="Mission") 
        run_btn = st.button("Generate Full Audit", type="primary", use_container_width=True)

# --- 5. LOGIC ENGINES ---
def analyze_risks(permits):
    score = 100
    findings = []
    
    # COMPRESSED RISK MAP (To prevent copy-paste errors)
    risk_map = [
        {"keywords": ["KNOB", "TUBE"], "deduction": 25, "msg": "Major Electrical Risk: Knob & Tube Wiring detected.", "cat": "fire"},
        {"keywords": ["ALUMINUM WIRING"], "deduction": 15, "msg": "Fire Risk: Aluminum branch wiring detected.", "cat": "fire"},
        {"keywords": ["UNPERMITTED", "ILLEGAL WIRING"], "deduction": 20, "msg": "Compliance Risk: History of unpermitted work.", "cat": "legal"},
        {"keywords": ["UNDERPIN", "SHORING", "FOUNDATION"], "deduction": 30, "msg": "Major Structural Risk: Foundation movement detected.", "cat": "structure"},
        {"keywords": ["SISTERING", "JOIST", "DRY ROT", "TERMITE"], "deduction": 15, "msg": "Structural Decay: Frame damage (rot/termites) noted.", "cat": "structure"},
        {"keywords": ["FIRE DAMAGE", "CHARRED", "SCORCH", "BURNING"], "deduction": 30, "msg": "Structural Risk: Evidence of past fire/burning.", "cat": "fire"},
        {"keywords": ["WATER DAMAGE", "LEAK", "MOLD", "FUNGAL"], "deduction": 20, "msg": "Health Risk: History of water intrusion or mold.", "cat": "water"},
        {"keywords": ["REMEDIATION", "ASBESTOS", "LEAD PAINT"], "deduction": 10, "msg": "Toxic Material: History of hazmat remediation.", "cat": "health"},
        {"keywords": ["NOV ", "NOTICE OF VIOLATION", "ABATEMENT"], "deduction": 25, "msg": "Legal Risk: Property has received City Violations.", "cat": "legal"},
        {"keywords": ["SOLAR", "LEASE", "PPA", "SUNRUN", "TESLA"], "match_all": True, "deduction": 15, "msg": "Financial Encumbrance: Solar Lease detected.", "cat": "finance"},
    ]
    
    assets = [
        {"keywords": ["REROOF", "RE-ROOF", "NEW ROOF"], "msg":
