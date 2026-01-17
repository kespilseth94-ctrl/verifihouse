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

# --- 2. STATE ---
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
    st.session_state.house_permits = []
    st.session_state.rc_data = None

# --- 3. FUNCTIONS ---
def run_audit():
    with st.spinner("Connecting to City Database..."):
        # Fetch Permits
        url = "https://data.sfgov.org/resource/i98e-djp9.json"
        p_params = {'street_name': st.session_state.input_name.strip().title(), '$limit': 2000, '$order': 'permit_creation_date DESC'}
        try:
            r = requests.get(url, params=p_params)
            data = r.json()
            st.session_state.house_permits = [p for p in data if st.session_state.input_num.strip() in str(p.get('street_number', ''))]
        except: st.session_state.house_permits = []
        
        # Fetch RentCast
        try:
            rc_url = "https://api.rentcast.io/v1/properties"
            rc_head = {'X-Api-Key': "3a69e2134c654a4d95e7e7d506b76feb"}
            rc_r = requests.get(rc_url, headers=rc_head, params={'address': f"{st.session_state.input_num} {st.session_state.input_name}, San Francisco, CA"})
            st.session_state.rc_data = rc_r.json()[0] if isinstance(rc_r.json(), list) and len(rc_r.json()) > 0 else None
        except: st.session_state.rc_data = None
        
        st.session_state.data_loaded = True

def analyze_risks(permits):
    score = 100
    findings = []
    # Compact Risk Map
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
    ]
    
    for p in permits:
        d = str(p.get('description', '')).upper()
        yr = p.get('permit_creation_date', 'N/A')[:4]
        # Check Standard Risks
        for r in risks:
            if any(key in d for key in r["k"]):
                if "BURNING" in d and "STOVE" in d: continue # False positive check
                score -= r["d"]
                findings.append({"type": "risk", "msg": f"{r['m']} ({yr})", "cat": r['c']})
        # Check Solar
        if "SOLAR" in d and ("LEASE" in d or "PPA" in d):
            score -= 15
            findings.append({"type": "risk", "msg": f"Financial Encumbrance: Solar Lease. ({yr})", "cat": "finance"})
            
    return max(score, 0), findings

def check_listing(text, permits):
    text = text.upper()
    issues = []
    cy = datetime.datetime.now().year
    
    # Kitchen Check
    if any(x in text for x in ["NEW KITCHEN", "REMODELED KITCHEN", "CHEF"]):
        if not any("KITCHEN" in str(p.get('description','')).upper() and int(p.get('permit_creation_date','1900')[:4]) > (cy-10) for p in permits):
            issues.append("Claim: 'Remodeled Kitchen' - No permits found in last 10 yrs.")
    
    # Bath Check
    if any(x in text for x in ["NEW BATH", "UPDATED BATH", "SPA-LIKE"]):
        if not any(("BATH" in str(p.get('description','')).upper() or "SHOWER" in str(p.get('description','')).upper()) and int(p.get('permit_creation_date','1900')[:4]) > (cy-10) for p in permits):
            issues.append("Claim: 'Updated Bathroom' - No permits found in last 10 yrs.")
            
    return issues

# --- 4. UI LAYOUT ---
with st.sidebar:
    st.title("🛡️ VeriHouse")
    st.info("System Online 🟢")

st.markdown("<h1 style='text-align: center;'>VeriHouse Property Audit</h1>", unsafe_allow_html=True)
c1, c2 = st.columns([1, 2])
with c2:
    sc1, sc2 = st.columns(2)
    sc1.text_input("Street Number", value="301", key="input_num")
    sc2.text_input("Street Name", value="Mission", key="input_name") 
    st.button("Generate Full Audit", type="primary", use_container_width=True, on_click=run_audit)

# --- 5. REPORT ---
if st.session_state.data_loaded:
    permits = st.session_state.house_permits
    
    if len(permits) > 0:
        score, findings = analyze_risks(permits)
        tier = "PLATINUM" if score >= 90 else "GOLD" if score >= 80 else "SILVER" if score >= 70 else "STANDARD"
        
        st.divider()
        m1, m2, m3 = st.columns(3)
        m1.markdown(f"<div class='score-card'><div class='metric-label'>Score</div><div class='metric-value'>{score}</div></div>", unsafe_allow_html=True)
        m2.markdown(f"<div class='score-card'><div class='metric-label'>Tier</div><div class='metric-value'>{tier}</div></div>", unsafe_allow_html=True)
        m3.markdown(f"<div class='score-card'><div class='metric-label'>Permits</div><div class='metric-value'>{len(permits)}</div></div>", unsafe_allow_html=True)
        
        st.subheader("📋 Forensic Log")
        if not findings: st.success("No major risks found.")
        for f in findings:
            st.markdown(f"<div style='margin:5px'><span class='badge-risk'>⚠ {f['cat'].upper()}</span> {f['msg']}</div>", unsafe_allow_html=True)
            
        st.divider()
        st.subheader("🕵️ Listing Truth Check")
        with st.form("check_form"):
            user_text = st.text_area("Paste Listing Description:")
            if st.form_submit_button("Analyze"):
                discrepancies = check_listing(user_text, permits)
                if discrepancies:
                    st.error(f"Found {len(discrepancies)} Potential Discrepancies:")
                    for d in discrepancies: st.write(f"- {d}")
                else: st.success("✅ Claims verified against history.")
        
        with st.expander("Raw Permit Data"): st.dataframe(permits)
    else:
        st.warning(f"No permits found for {st.session_state.input_num} {st.session_state.input_name}. Check spelling.")
