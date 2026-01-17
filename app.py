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
        for risk in risk_map:
            if risk.get("match_all"):
                if "SOLAR" in desc and any(term in desc for term in ["LEASE", "PPA"]):
                    score -= risk["deduction"]
                    findings.append({"type": "risk", "msg": f"{risk['msg']} ({date})", "cat": risk['cat']})
            elif any(k in desc for k in risk["keywords"]):
                if "BURNING" in desc and any(safe in desc for safe in ["STOVE", "INSERT", "LOG"]): continue
                score -= risk["deduction"]
                findings.append({"type": "risk", "msg": f"{risk['msg']} ({date})", "cat": risk['cat']})
        for asset in assets:
             if any(k in desc for k in asset["keywords"]):
                 findings.append({"type": "safe", "msg": f"{asset['msg']} ({date})"})
    return max(score, 0), findings

def get_property_details(number, street, api_key):
    if not api_key: return None
    url = "https://api.rentcast.io/v1/properties"
    address_query = f"{number} {street}, San Francisco, CA"
    params = {'address': address_query}
    headers = {'X-Api-Key': api_key}
    try:
        r = requests.get(url, headers=headers, params=params)
        data = r.json()
        if isinstance(data, list) and len(data) > 0: return data[0]
    except: return None
    return None

def predict_maintenance(age_year, permits):
    predictions = []
    current_year = datetime.datetime.now().year
    all_desc = " ".join([str(p.get('description', '')).upper() for p in permits])
    
    if age_year < 1960:
        if "REWIRE" not in all_desc and "PANEL" not in all_desc:
            predictions.append({"item": "Full Rewire (Knob & Tube Risk)", "prob": "HIGH", "cost": "$15,000 - $30,000", "time": "Immediate", "reason": f"Home built {age_year} with no record of rewiring."})

    if age_year < 1975:
        if "COPPER" not in all_desc and "REPIPE" not in all_desc:
            predictions.append({"item": "Galvanized Pipe Replacement", "prob": "MEDIUM", "cost": "$8,000 - $15,000", "time": "2-5 Years", "reason": f"Home built {age_year} likely has galvanized steel pipes."})

    recent_roof = False
    for p in permits:
        d = str(p.get('description', '')).upper()
        date_str = p.get('permit_creation_date', '1900')[:4]
        if "ROOF" in d and int(date_str) > (current_year - 20): recent_roof = True
    
    if not recent_roof:
         predictions.append({"item": "Roof Replacement", "prob": "HIGH", "cost": "$12,000 - $25,000", "time": "1-3 Years", "reason": "No roofing permits found in last 20 years."})
            
    if age_year < 1980:
        if "SEWER" not in all_desc and "LATERAL" not in all_desc:
            predictions.append({"item": "Sewer Lateral Replacement", "prob": "MEDIUM", "cost": "$10,000 - $20,000", "time": "On Sale", "reason": "SF requires sewer lateral compliance on sale."})

    return predictions

def check_listing_claims(listing_text, permits):
    text = listing_text.upper()
    discrepancies = []
    current_year = datetime.datetime.now().year
    
    # Check 1: KITCHEN
    # "SPA" removed to avoid false triggers on "SPACE"
    if any(x in text for x in ["NEW KITCHEN", "REMODELED KITCHEN", "CHEF'S KITCHEN", "MODERN KITCHEN"]):
        recent_kitchen = False
        for p in permits:
            d = str(p.get('description', '')).upper()
            date = int(p.get('permit_creation_date', '1900')[:4])
            if "KITCHEN" in d and date > (current_year - 10): recent_kitchen = True
        
        if not recent_kitchen:
            discrepancies.append({
                "claim": "Remodeled Kitchen",
                "status": "UNVERIFIED",
                "msg": "Listing claims a new/remodeled kitchen, but no kitchen permits were found in the last 10 years."
            })

    # Check 2: BATHROOM
    # REFINED KEYWORDS: Removed "SPA", added "SPA-LIKE" and "WHIRLPOOL"
    bath_keywords = ["NEW BATH", "REMODELED BATH", "UPDATED BATH", "MODERN BATH", "SPA-LIKE", "WHIRLPOOL"]
    
    if any(x in text for x in bath_keywords):
        recent_bath = False
        for p in permits:
            d = str(p.get('description', '')).upper()
            date = int(p.get('permit_creation_date', '1900')[:4])
            if ("BATH" in d or "SHOWER" in d) and date > (current_year - 10): recent_bath = True
        
        if not recent_bath:
            discrepancies.append({
                "claim": "Updated Bathroom",
                "status": "UNVERIFIED",
                "msg": "Listing claims updated baths, but no bathroom/plumbing permits found in the last 10 years."
            })

    # Check 3: ROOF
    if "NEW ROOF" in text:
        recent_roof = False
        for p in permits:
            d = str(p.get('description', '')).upper()
            date = int(p.get('permit_creation_date', '1900')[:4])
            if "ROOF" in d and date > (current_year - 10): recent_roof = True
            
        if not recent_roof:
            discrepancies.append({
                "claim": "New Roof",
                "status": "UNVERIFIED",
                "msg": "Listing claims 'New Roof', but no roofing permits found in the last 10 years."
            })

    # Check 4: ADU
    if any(x in text for x in ["ADU", "IN-LAW", "GUEST UNIT", "LEGAL UNIT"]):
        has_adu = False
        for p in permits:
            d = str(p.get('description', '')).upper()
            if any(k in d for k in ["ADU", "DWELLING UNIT", "SECONDARY"]): has_adu = True
            
        if not has_adu:
            discrepancies.append({
                "claim": "ADU / In-Law Unit",
                "status": "ILLEGAL RISK",
                "msg": "Listing mentions an ADU/Unit, but no permits for 'Dwelling Unit' or 'ADU' were found."
            })

    return discrepancies

# --- 6. DATA FETCHING LOGIC (Run only when button is clicked) ---
if run_btn:
    with st.spinner(f"Running comprehensive audit for {st_num} {st_name}..."):
        
        # A. GET DATA
        url = "https://data.sfgov.org/resource/i98e-djp9.json"
        clean_name = st_name.strip().title()
        clean_num = st_num.strip()
        params = {'street_name': clean_name, '$limit': 2000, '$order': 'permit_creation_date DESC'}
        
        house_permits = []
        try:
            r = requests.get(url, params=params)
            data = r.json()
            if isinstance(data, list):
                for p in data:
                    if clean_num in str(p.get('street_number', '')):
                        house_permits.append(p)
        except: pass

        rc_data = get_property_details(clean_num, clean_name, rentcast_key)
        
        # SAVE TO SESSION STATE
        st.session_state.house_permits = house_permits
        st.session_state.rc_data = rc_data
        st.session_state.data_loaded = True
        st.session_state.current_address = f"{clean_num} {clean_name}"

# --- 7. DISPLAY LOGIC (Run whenever data exists in memory) ---
if st.session_state.data_loaded:
    
    house_permits = st.session_state.house_permits
    rc_data = st.session_state.rc_data
    
    if len(house_permits) > 0:
        final_score, notes = analyze_risks(house_permits)
        
        # Tier Logic
        if final_score >=
