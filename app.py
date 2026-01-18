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

# --- 2. INITIALIZE STATE ---
if 'house_permits' not in st.session_state:
    st.session_state.house_permits = []
if 'rc_data' not in st.session_state:
    st.session_state.rc_data = None
if 'has_run' not in st.session_state:
    st.session_state.has_run = False

# --- 3. LOGIC FUNCTIONS ---
def get_sf_data(number, street):
    # Safety clean
    clean_num = str(number).strip()
    clean_street = str(street).strip().title()
    
    url = "https://data.sfgov.org/resource/i98e-djp9.json"
    params = {'street_name': clean_street, '$limit': 2000, '$order': 'permit_creation_date DESC'}
    
    try:
        r = requests.get(url, params=params)
        data = r.json()
        # Filter for exact street number match
        return [p for p in data if clean_num in str(p.get('street_number', ''))]
    except:
        return []

def get_rentcast_data(number, street):
    # --- SECURE KEY CHANGE ---
    try:
        key = st.secrets["rentcast_key"]
    except:
        return None
    # -------------------------
    
    url = "https://api.rentcast.io/v1/properties"
    params = {'address': f"{number} {street}, San Francisco, CA"}
    headers = {'X-Api-Key': key}
    
    try:
        r = requests.get(url, headers=headers, params=params)
        data = r.json()
        if isinstance(data, list) and len(data) > 0:
            return data[0]
    except:
        return None
    return None

def analyze_history(permits):
    score = 100
    log = []
    
    # RISK DEFINITIONS
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
        desc = str(p.get('description', '')).upper()
        date = p.get('permit_creation_date', 'N/A')[:4]
        
        for r in risks:
            if any(k in desc for k in r['k']):
                if "BURNING" in desc and "STOVE" in desc: continue
                score -= r['d']
                log.append({"cat": r['c'], "msg": f"{r['m']} ({date})", "type": "risk"})
                
    return max(score, 0), log

def predict_future(age, permits):
    preds = []
    text = " ".join([str(p.get('description', '')).upper() for p in permits])
    
    if age < 1960 and "REWIRE" not in text and "PANEL" not in text:
        preds.append({"item": "Full Rewire", "cost": "$15k-$30k", "prob": "HIGH", "why": f"Built {age}, no rewiring found."})
        
    if age < 1975 and "COPPER" not in text and "REPIPE" not in text:
        preds.append({"item": "Galvanized Pipe Swap", "cost": "$8k-$15k", "prob": "MEDIUM", "why": f"Built {age}, original pipes likely."})
        
    # Roof Check
    recent_roof = False
    current_year = datetime.datetime.now().year
    for p in permits:
        if "ROOF" in str(p.get('description', '')).upper():
            try:
                if int(p.get('permit_creation_date', '1900')[:4]) > (current_year - 20): recent_roof = True
            except: pass
            
    if not recent_roof:
        preds.append({"item": "Roof Replacement", "cost": "$12k-$25k", "prob": "HIGH", "why": "No roof permits in 20 years."})
        
    return preds

def check_truth(claims, permits):
    claims = claims.upper()
    issues = []
    cy = datetime.datetime.now().year
    
    # Kitchen
    if any(x in claims for x in ["NEW KITCHEN", "REMODELED KITCHEN", "CHEF"]):
        found = False
        for p in permits:
            d = str(p.get('description', '')).upper()
            try:
                if "KITCHEN" in d and int(p.get('permit_creation_date', '1900')[:4]) > (cy - 10): found = True
            except: pass
        if not found: issues.append("Claim: 'Remodeled Kitchen' - No recent permits found.")

    # Bath
    if any(x in claims for x in ["NEW BATH", "UPDATED BATH", "SPA-LIKE"]):
        found = False
        for p in permits:
            d = str(p.get('description', '')).upper()
            try:
                if ("BATH" in d or "SHOWER" in d) and int(p.get('permit_creation_date', '1900')[:4]) > (cy - 10): found = True
            except: pass
        if not found: issues.append("Claim: 'Updated Bathroom' - No recent permits found.")
        
    return issues

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("🛡️ VeriHouse")
    st.info("System Online 🟢")

# --- 5. MAIN UI ---
st.markdown("<h1 style='text-align: center;'>VeriHouse Property Audit</h1>", unsafe_allow_html=True)

# Search Bar
c1, c2 = st.columns([1, 2])
with c2:
    col_a, col_b = st.columns(2)
    s_num = col_a.text_input("Street Number", value="301")
    s_name = col_b.text_input("Street Name", value="Mission")
    
    if st.button("Generate Full Audit", type="primary", use_container_width=True):
        with st.spinner("Analyzing..."):
            st.session_state.house_permits = get_sf_data(s_num, s_name)
            st.session_state.rc_data = get_rentcast_data(s_num, s_name)
            st.session_state.has_run = True

# Results
if st.session_state.has_run:
    permits = st.session_state.house_permits
    rc = st.session_state.rc_data
    
    if len(permits) > 0 or rc:
        score, findings = analyze_history(permits)
        
        # Tier Logic
        if score >= 90: tier = "PLATINUM"
        elif score >= 80: tier = "GOLD"
        elif score >= 70: tier = "SILVER"
        else: tier = "STANDARD"
        
        st.divider()
        
        # Metrics
        m1, m2, m3 = st.columns(3)
        m1.markdown(f"<div class='score-card'><div class='metric-label'>Score</div><div class='metric-value'>{score}</div></div>", unsafe_allow_html=True)
        m2.markdown(f"<div class='score-card'><div class='metric-label'>Tier</div><div class='metric-value'>{tier}</div></div>", unsafe_allow_html=True)
        
        val = rc['yearBuilt'] if (rc and 'yearBuilt' in rc) else len(permits)
        lbl = "Year Built" if (rc and 'yearBuilt' in rc) else "Permits"
        m3.markdown(f"<div class='score-card'><div class='metric-label'>{lbl}</div><div class='metric-value'>{val}</div></div>", unsafe_allow_html=True)
        
        st.write("")
        st.subheader("📋 Forensic Log")
        if not findings:
            st.success("No major risks found in permit history.")
        else:
            for f in findings:
                st.markdown(f"<div style='margin-bottom:5px'><span class='badge-risk'>⚠ {f['cat'].upper()}</span> {f['msg']}</div>", unsafe_allow_html=True)
                
        if rc:
            st.write("")
            st.subheader("🔮 Predictive Maintenance")
            preds = predict_future(rc.get('yearBuilt', 0), permits)
            if not preds:
                st.info("No anomalies predicted.")
            else:
                for p in preds:
                    bg = "#fef2f2" if p['prob'] == "HIGH" else "#fffbeb"
                    st.markdown(f"<div style='background-color:{bg}; padding:10px; border-radius:5px; margin-bottom:5px;'><strong>{p['item']}</strong> ({p['cost']})<br><small>{p['why']}</small></div>", unsafe_allow_html=True)
                    
        st.write("")
        st.divider()
        st.subheader("🕵️ Listing Truth Check")
        with st.form("truth_checker"):
            txt = st.text_area("Paste Listing Description:")
            if st.form_submit_button("Analyze"):
                issues = check_truth(txt, permits)
                if issues:
                    st.error(f"Found {len(issues)} Discrepancies:")
                    for i in issues: st.write(f"- {i}")
                else:
                    st.success("Claims verified.")
                    
        with st.expander("Raw Data"):
            st.dataframe(permits)
    else:
        st.warning("No data found for this address.")
