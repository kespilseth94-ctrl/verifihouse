import streamlit as st
import requests
import datetime

# --- 1. CONFIGURATION ---
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

# --- 2. STATE INITIALIZATION ---
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
    st.session_state.house_permits = []
    st.session_state.rc_data = None

# --- 3. CORE LOGIC (Defined as functions) ---
def get_sf_permits(street_num, street_name):
    url = "https://data.sfgov.org/resource/i98e-djp9.json"
    params = {
        'street_name': street_name.strip().title(), 
        '$limit': 2000, 
        '$order': 'permit_creation_date DESC'
    }
    try:
        r = requests.get(url, params=params)
        data = r.json()
        # Filter by street number manually to be safe
        return [p for p in data if street_num.strip() in str(p.get('street_number', ''))]
    except Exception as e:
        st.error(f"Connection Error (SF Gov): {e}")
        return []

def get_rentcast_data(street_num, street_name, key):
    if not key: return None
    url = "https://api.rentcast.io/v1/properties"
    params = {'address': f"{street_num} {street_name}, San Francisco, CA"}
    headers = {'X-Api-Key': key}
    try:
        r = requests.get(url, headers=headers, params=params)
        data = r.json()
        if isinstance(data, list) and len(data) > 0: return data[0]
    except Exception as e:
        # Don't crash, just return None
        return None
    return None

def run_audit():
    """This runs immediately when button is clicked"""
    with st.spinner("Connecting to City Database..."):
        # 1. Fetch Permits
        permits = get_sf_permits(st.session_state.input_num, st.session_state.input_name)
        st.session_state.house_permits = permits
        
        # 2. Fetch RentCast
        key = "3a69e2134c654a4d95e7e7d506b76feb"
        rc = get_rentcast_data(st.session_state.input_num, st.session_state.input_name, key)
        st.session_state.rc_data = rc
        
        # 3. Mark as loaded
        st.session_state.data_loaded = True

def analyze_risks(permits):
    score = 100
    findings = []
    
    # VERTICAL LISTS (Safe from copy-paste errors)
    risk_map = [
        {
            "keywords": ["KNOB", "TUBE"],
            "deduction": 25,
            "cat": "fire",
            "msg": "Major Electrical Risk: Knob & Tube Wiring detected."
        },
        {
            "keywords": ["ALUMINUM WIRING"],
            "deduction": 15,
            "cat": "fire",
            "msg": "Fire Risk: Aluminum branch wiring detected."
        },
        {
            "keywords": ["UNPERMITTED", "ILLEGAL WIRING"],
            "deduction": 20,
            "cat": "legal",
            "msg": "Compliance Risk: History of unpermitted work."
        },
        {
            "keywords": ["UNDERPIN", "SHORING", "FOUNDATION"],
            "deduction": 30,
            "cat": "structure",
            "msg": "Major Structural Risk: Foundation movement detected."
        },
        {
            "keywords": ["SISTERING", "JOIST", "DRY ROT", "TERMITE"],
            "deduction": 15,
            "cat": "structure",
            "msg": "Structural Decay: Frame damage (rot/termites) noted."
        },
        {
            "keywords": ["FIRE DAMAGE", "CHARRED", "SCORCH", "BURNING"],
            "deduction": 30,
            "cat": "fire",
            "msg": "Structural Risk: Evidence of past fire/burning."
        },
        {
            "keywords": ["WATER DAMAGE", "LEAK", "MOLD", "FUNGAL"],
            "deduction": 20,
            "cat": "water",
            "msg": "Health Risk: History of water intrusion or mold."
        },
        {
            "keywords": ["REMEDIATION", "ASBESTOS", "LEAD PAINT"],
            "deduction": 10,
            "cat": "health",
            "msg": "Toxic Material: History of hazmat remediation."
        },
        {
            "keywords": ["NOV ", "NOTICE OF VIOLATION", "ABATEMENT"],
            "deduction": 25,
            "cat": "legal",
            "msg": "Legal Risk: Property has received City Violations."
        },
        {
            "keywords": ["SOLAR", "LEASE", "PPA", "SUNRUN"],
            "match_all": True,
            "deduction": 15,
            "cat": "finance",
            "msg": "Financial Encumbrance: Solar Lease detected."
        }
    ]
    
    for p in permits:
        desc = str(p.get('description', '')).upper()
        date = p.get('permit_creation_date', 'N/A')[:4]
        
        for risk in risk_map:
            if risk.get("match_all"):
                if "SOLAR" in desc and any(term in desc for term in ["LEASE", "PPA"]):
                    score -= risk["deduction"]
                    findings.append({"type": "risk", "msg": f"{risk['msg']} ({date})", "cat": risk['cat']})
            elif any(k in desc for k in risk["keywords"]):
                if "BURNING" in desc and any(safe in desc for safe in ["STOVE", "INSERT", "LOG"]): continue
                score -= risk["deduction"]
                findings.append({"type": "risk", "msg": f"{risk['msg']} ({date})", "cat": risk['cat']})

    return max(score, 0), findings

def predict_maintenance(age_year, permits):
    preds = []
    text = " ".join([str(p.get('description', '')).upper() for p in permits])
    curr_year = datetime.datetime.now().year
    
    if age_year < 1960 and "REWIRE" not in text and "PANEL" not in text:
        preds.append({"item": "Full Rewire", "prob": "HIGH", "cost": "$15k-$30k", "reason": f"Built {age_year}, no rewiring found."})
    
    if age_year < 1975 and "COPPER" not in text and "REPIPE" not in text:
        preds.append({"item": "Galvanized Pipe Swap", "prob": "MEDIUM", "cost": "$8k-$15k", "reason": f"Built {age_year}, original pipes likely."})

    recent_roof = False
    for p in permits:
        if "ROOF" in str(p.get('description', '')).upper():
            try:
                if int(p.get('permit_creation_date', '1900')[:4]) > (curr_year - 20): recent_roof = True
            except: pass
            
    if not recent_roof:
         preds.append({"item": "Roof Replacement", "prob": "HIGH", "cost": "$12k-$25k", "reason": "No roof permits in 20 years."})
            
    return preds

def check_listing_claims(text, permits):
    text = text.upper()
    issues = []
    curr_year = datetime.datetime.now().year
    
    # Kitchen Logic
    if any(x in text for x in ["NEW KITCHEN", "REMODELED KITCHEN", "CHEF'S KITCHEN"]):
        found = False
        for p in permits:
            d = str(p.get('description','')).upper()
            try:
                if "KITCHEN" in d and int(p.get('permit_creation_date','1900')[:4]) > (curr_year - 10): found = True
            except: pass
        if not found: issues.append({"claim": "Remodeled Kitchen", "msg": "No kitchen permits found in last 10 years."})

    # Bath Logic
    if any(x in text for x in ["NEW BATH", "REMODELED BATH", "UPDATED BATH", "WHIRLPOOL", "SPA-LIKE"]):
        found = False
        for p in permits:
            d = str(p.get('description','')).upper()
            try:
                if ("BATH" in d or "SHOWER" in d) and int(p.get('permit_creation_date','1900')[:4]) > (curr_year - 10): found = True
            except: pass
        if not found: issues.append({"claim": "Updated Bathroom", "msg": "No bath permits found in last 10 years."})

    return issues

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("🛡️ VeriHouse")
    st.caption("Residential Risk Intelligence")
    st.divider()
    st.info("System Online 🟢")

# --- 5. MAIN INTERFACE ---
st.markdown("<h1 style='text-align: center;'>VeriHouse Property Audit</h1>", unsafe_allow_html=True)
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    with st.container():
        c1, c2 = st.columns(2)
        # We attach the inputs to session_state keys so the callback can find them
        c1.text_input("Street Number", value="301", key="input_num")
        c2.text_input("Street Name", value="Mission", key="input_name") 
        # BUTTON WITH CALLBACK (The Fix)
        st.button("Generate Full Audit", type="primary", use_container_width=True, on_click=run_audit)

# --- 6. REPORT DISPLAY ---
if st.session_state.data_loaded:
    permits = st.session_state.house_permits
    rc = st.session_state.rc_data
    
    if len(permits) > 0:
        score,
