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
    .badge-warn { background-color: #fffbeb; color: #b45309; padding: 4px 10px; border-radius: 15px; font-size: 0.8em; font-weight: bold; border: 1px solid #fcd34d; }
    </style>
""", unsafe_allow_html=True)

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🛡️ VeriHouse")
    st.markdown("**Residential Risk Intelligence**")
    
    # --- HARDCODED KEY (Clean Demo Mode) ---
    rentcast_key = "3a69e2134c654a4d95e7e7d506b76feb"
    
    st.divider()
    st.info("System Status: Online 🟢")
    st.caption("1. SF Active Permits (Forensics)")
    st.caption("2. RentCast (Age & Predictive)")
    st.caption("3. MLS Semantic Analysis (New)")
    st.divider()
    st.warning("Disclaimer: Estimates are for planning only. Not a contractor quote.")

# --- 4. MAIN INTERFACE ---
st.markdown("<h1 style='text-align: center;'>VeriHouse Property Audit</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #666;'>Forensic Analysis + Predictive Maintenance + Listing Truth Check</p>", unsafe_allow_html=True)
st.write("")

# --- INITIALIZE SESSION STATE ---
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
    st.session_state.house_permits = []
    st.session_state.rc_data = None
    st.session_state.current_address = ""

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    with st.container():
        c1, c2 = st.columns(2)
        st_num = c1.text_input("Street Number", value="301")
        st_name = c2.text_input("Street Name", value="Mission") 
        run_btn = st.button("Generate Full Audit", type="primary", use_container_width=True)

# --- 5. ENGINE FUNCTIONS ---
def analyze_risks(permits):
    score = 100
    findings = []
    
    risk_map = [
        {"keywords": ["KNOB", "TUBE"], "deduction": 25, "msg": "Major Electrical Risk: Knob & Tube Wiring detected.", "cat": "fire"},
        {"keywords": ["ALUMINUM WIRING"], "deduction": 15, "msg": "Fire Risk: Aluminum branch wiring detected.", "cat": "fire"},
        {"keywords": ["UNPERMITTED", "ILLEGAL WIRING"], "deduction": 20, "msg": "Compliance Risk: History of unpermitted work.", "cat": "legal"},
        {"keywords": ["UNDERPIN", "SHORING", "FOUNDATION REPAIR", "SETTLEMENT"], "deduction": 30, "msg": "Major Structural Risk: Foundation movement detected.", "cat": "structure"},
        {"keywords": ["SISTERING", "JOIST REPAIR", "DRY ROT", "TERMITE"], "deduction": 15, "msg": "Structural Decay: Frame damage (rot/termites) noted.", "cat": "structure"},
        {"keywords": ["FIRE DAMAGE", "FIRE REPAIR", "CHARRED", "SCORCH", "BURNING"], "deduction": 30,
