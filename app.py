import streamlit as st
import requests
import datetime

# --- 1. CONFIGURATION & STYLING ---
st.set_page_config(page_title="VeriHouse", page_icon="🛡️", layout="wide")

st.markdown("""
    <style>
    .score-card { 
        padding: 20px; 
        border-radius: 10px; 
        background-color: #f8f9fa; 
        border: 1px solid #e9ecef; 
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .metric-value { 
        font-size: 2.2em; 
        font-weight: 800; 
        color: #2C3E50; 
    }
    .metric-label { 
        font-size: 0.85em; 
        color: #6c757d; 
        text-transform: uppercase; 
        letter-spacing: 1px; 
    }
    .badge-risk { 
        background-color: #fee2e2; 
        color: #991b1b; 
        padding: 4px 10px; 
        border-radius: 15px; 
        font-size: 0.8em; 
        font-weight: bold; 
    }
    .badge-safe { 
        background-color: #d1fae5; 
        color: #065f46; 
        padding: 4px 10px; 
        border-radius: 15px; 
        font-size: 0.8em; 
        font-weight: bold; 
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. SESSION STATE ---
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
    st.session_state.house_permits = []
    st.session_state.rc_data = None
    st.session_state.input_num = "301"
    st.session_state.input_name = "Mission"

# --- 3. DATA FUNCTIONS ---
def run_audit():
    with st.spinner("Connecting to City Database..."):
        # 1. Fetch SF Permits
        url = "https://data.sfgov.org/resource/i98e-djp9.json"
        # We clean the input here to ensure matches
        clean_name = st.session_state.input_name.strip().title()
        clean_num = st.session_state.input_num.strip()
        
        params = {
            'street_name': clean_name, 
            '$limit': 2000, 
            '$order': 'permit_creation_date DESC'
        }
        
        try:
            r = requests.get(url, params=params)
            data = r.json()
            # Filter specifically for the street number
            matches = [p for p in data if clean_num in str(p.get('street_number', ''))]
            st.session_state.house_permits = matches
        except:
            st.session_state.house_permits = []
        
        # 2. Fetch RentCast Data
        try:
            rc_key = "3a69e2134c654a4d95e7e7d506b76feb"
            rc_url = "https://api.rentcast.io/v1/properties"
            rc_params = {'address': f"{clean_num} {clean_name}, San Francisco, CA"}
            rc_head = {'X-Api-Key': rc_key}
            
            r_rc = requests.get(rc_url, headers=rc_head, params=rc_params)
            rc_json = r_rc.json()
            
            # RentCast returns a list, we need the first item
            if isinstance(rc_json, list) and len(rc_json) > 0:
                st.session_state.rc_data = rc_json[0]
            else:
                st.session_state.rc_data = None
        except:
            st.session_state.rc_data = None
            
        st.session_state.data_loaded = True

def analyze_risks(permits):
    score = 100
    findings = []
    
    # VERTICAL DEFINITIONS (Safe from cut-offs)
    risks = [
        {"k": ["KNOB", "TUBE"], "d": 25, "c": "fire", "m": "Major Electrical Risk: Knob & Tube Wiring."},
        {"k": ["ALUMINUM WIRING"], "d": 15, "c": "fire", "m": "Fire Risk: Aluminum branch wiring."},
        {"k": ["UNPERMITTED", "ILLEGAL WIRING"], "d": 20, "c": "legal", "m": "Compliance Risk: Unpermitted work."},
        {"k": ["UNDERPIN", "SHORING", "FOUNDATION"], "d": 30, "c": "structure", "m": "Structural Risk: Foundation movement."},
        {"k": ["SISTERING", "JOIST", "TERMITE"], "d": 15, "c": "structure", "m": "Structural Decay: Frame damage/rot."},
        {"k": ["FIRE DAMAGE", "CHARRED", "BURNING"], "d": 30, "c": "fire", "m": "Structural Risk: Past fire evidence."},
        {"k": ["WATER DAMAGE", "MOLD", "FUNGAL"], "d": 20, "c": "water", "m": "Health Risk: Water intrusion/mold."},
        {"k": ["REMEDIATION", "ASBESTOS", "LEAD"], "d": 10, "c": "health", "m": "Toxic Material: Hazmat remediation."},
        {"k": ["NOV ", "NOTICE OF VIOLATION"], "d": 25, "c": "legal", "m": "Legal Risk: City Violations found."},
        {"k": ["SOLAR", "LEASE", "PPA"], "d": 15, "c": "finance", "m": "Financial Encumbrance: Solar Lease."}
    ]
    
    for p in permits:
        d = str(p.get('description', '')).upper()
        yr = p.get('permit_creation_date', 'N/A')[:4]
        
        for r in risks:
            # Check keywords
            if any(key in d for key in r["k"]):
                # Safety check for 'burning' stoves
                if "BURNING" in d and "STOVE" in d: continue 
                
                score -= r["d"]
                findings.append({
                    "type": "risk", 
                    "msg": f"{r['m']} ({yr})", 
                    "cat": r['c']
                })
                
    return max(score, 0), findings

def predict_maintenance(age_year, permits):
    preds = []
    text = " ".join([str(p.get('description', '')).upper() for p in permits])
    
    if age_year < 1960 and "REWIRE" not in text and "PANEL" not in text:
        preds.append({"item": "Full Rewire", "prob": "HIGH", "cost": "$15k-$30k", "reason": f"Built {age_year}, no rewiring found."})
    
    if age_year < 1975 and "COPPER" not in text and "REPIPE" not in text:
        preds.append({"item": "Galvanized Pipe Swap", "prob": "MEDIUM", "cost": "$8k-$15k", "reason": f"Built {age_year}, original pipes likely."})

    recent_roof = False
    for p in permits:
        d = str(p.get('description', '')).upper()
        if "ROOF" in d:
             # simple date check
             try:
                 yr = int(p.get('permit_creation_date', '1900')[:4])
                 if yr > (datetime.datetime.now().year - 20): recent_roof = True
             except: pass
             
    if not recent_roof:
         preds.append({"item": "Roof Replacement", "prob": "HIGH", "cost": "$12k-$25k", "reason": "No roof permits in 20 years."})
            
    return preds

def check_listing(text, permits):
    text = text.upper()
    issues = []
    cy = datetime.datetime.now().year
    
    # Kitchen
    if any(x in text for x in ["NEW KITCHEN", "REMODELED KITCHEN", "CHEF"]):
        found = False
        for p in permits:
            d
