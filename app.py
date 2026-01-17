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
    
    # RENTCAST KEY INPUT (SECURE METHOD)
    st.markdown("### 🔑 Data Connections")
    
    # Try to get key from secrets, otherwise ask user
    if 'rentcast_api_key' in st.secrets:
        rentcast_key = st.secrets['rentcast_api_key']
        st.success("API Key Loaded Securely 🔒")
    else:
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
    try:
        r = requests.get(url, headers=headers, params=params)
        data = r.json()
        if isinstance(data, list) and len(data) > 0: return data[0]
    except: return None
    return None

def predict_maintenance(age_year, permits):
    predictions = []
    current_year = datetime.datetime.now().year
    
    # Create searchable text blob
    all_desc = " ".join([str(p.get('description', '')).upper() for p in permits])
    
    # 1. ELECTRICAL PREDICTION
    if age_year < 1960:
        if "REWIRE" not in all_desc and "PANEL" not in all_desc:
            predictions.append({
                "item": "Full Rewire (Knob & Tube Risk)",
                "prob": "HIGH",
                "cost": "$15,000 - $30,000",
                "time": "Immediate (Safety)",
                "reason": f"Home built {age_year} with no record of rewiring. High risk of ungrounded or Knob & Tube wiring."
            })

    # 2. PLUMBING PREDICTION
    if age_year < 1975:
        if "COPPER" not in all_desc and "REPIPE" not in all_desc:
            predictions.append({
                "item": "Galvanized Pipe Replacement",
                "prob": "MEDIUM",
                "cost": "$8,000 - $15,000",
                "time": "Within 2-5 Years",
                "reason": f"Home built {age_year} likely has galvanized steel pipes reaching end-of-life (corrosion risk)."
            })

    # 3. ROOF PREDICTION
    recent_roof = False
    for p in permits:
        d = str(p.get('description', '')).upper()
        date_str = p.get('permit_creation_date', '1900')[:4]
        if "ROOF" in d and int(date_str) > (current_year - 20):
            recent_roof = True
    
    if not recent_roof:
         predictions.append({
                "item": "Roof Replacement",
                "prob": "HIGH",
                "cost": "$12,000 - $25,000",
                "time": "Within 1-3 Years",
                "reason": "No roofing permits found in the last 20 years. Asphalt shingles typically last 20-25 years."
            })
            
    # 4. SEWER LATERAL (SF Specific)
    if age_year < 1980:
        if "SEWER" not in all_desc and "LATERAL" not in all_desc:
            predictions.append({
                "item": "Sewer Lateral Replacement",
                "prob": "MEDIUM",
                "cost": "$10,000 - $20,000",
                "time": "On Sale/Transfer",
                "reason": "SF requires sewer lateral compliance on sale. No record of replacement found."
            })

    return predictions

# --- 7. EXECUTION LOGIC ---
if run_btn:
    with st.spinner(f"Running comprehensive audit for {st_num} {st_name}..."):
        
        # A. GET SF PERMITS
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
        except Exception as e:
            st.error(f"SF Database Error: {e}")

        # B. GET RENTCAST DATA
        rc_data = get_property_details(clean_num, clean_name, rentcast_key)
        
        # --- DISPLAY SECTION ---
        
        # 1. HEADER METRICS
        if len(house_permits) > 0:
            final_score, notes = analyze_risks(house_permits)
            if final_score >= 90: tier = "PLATINUM"
            elif final_score >= 80: tier = "GOLD"
            elif final_score >= 70: tier = "SILVER"
            else: tier = "STANDARD"
            
            st.divider()
            m1, m2, m3 = st.columns(3)
            with m1: st.markdown(f"<div class='score-card'><div class='metric-label'>VeriHouse Score</div><div class='metric-value'>{final_score}</div></div>", unsafe_allow_html=True)
            with m2: st.markdown(f"<div class='score-card'><div class='metric-label'>Asset Tier</div><div class='metric-value'>{tier}</div></div>", unsafe_allow_html=True)
            with m3: 
                # If we have age, show it, otherwise show permit count
                if rc_data:
                    age = rc_data.get('yearBuilt', 'N/A')
                    st.markdown(f"<div class='score-card'><div class='metric-label'>Year Built</div><div class='metric-value'>{age}</div></div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div class='score-card'><div class='metric-label'>Permits Found</div><div class='metric-value'>{len(house_permits)}</div></div>", unsafe_allow_html=True)

            st.write("")
            
            # 2. FORENSIC FINDINGS (The "What Happened" Section)
            st.subheader("📋 Forensic Verification Log")
            if len(notes) == 0:
                st.success("No significant risk keywords found in recent history.")
            notes.sort(key=lambda x: x['type']) 
            for note in notes:
                if note['type'] == 'risk':
                    st.markdown(f"<div style='margin-bottom:10px;'><span class='badge-risk'>⚠ {note['cat'].upper()} RISK</span> &nbsp; {note['msg']}</div>", unsafe_allow_html=True)
                elif note['type'] == 'safe':
                    st.markdown(f"<div style='margin-bottom:10px;'><span class='badge-safe'>✓ VERIFIED</span> &nbsp; {note['msg']}</div>", unsafe_allow_html=True)

            # 3. PREDICTIVE MAINTENANCE (The "What Will Happen" Section)
            if rc_data:
                year_built = rc_data.get('yearBuilt', 0)
                if year_built > 0:
                    st.write("")
                    st.write("")
                    st.subheader("🔮 Predictive Maintenance & CapEx")
                    st.markdown("Based on home age vs. permit history gaps.")
                    
                    preds = predict_maintenance(year_built, house_permits)
                    
                    if len(preds) == 0:
                        st.info("No deferred maintenance anomalies predicted.")
                    
                    for p in preds:
                        # Color coding based on cost/urgency
                        border_color = "#fca5a5" if p['prob'] == "HIGH" else "#fcd34d"
                        bg_color = "#fef2f2" if p['prob'] == "HIGH" else "#fffbeb"
                        
                        st.markdown(f"""
                        <div style="background-color: {bg_color}; padding: 15px; border-radius: 8px; margin-bottom: 12px; border-left: 5px solid {border_color}; border: 1px solid #e5e7eb;">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <h4 style="margin:0; color:#1f2937;">{p['item']}</h4>
                                <span style="background-color:#fff; padding:2px 8px; border-radius:12px; font-size:0.8em; border:1px solid #ddd;">Est. Cost: <strong>{p['cost']}</strong></span>
                            </div>
                            <div style="margin-top:5px; font-size:0.9em; color:#4b5563;">
                                <strong>Timeline:</strong> {p['time']}<br>
                                <em>{p['reason']}</em>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
            else:
                st.info("ℹ️ Enter a RentCast API Key in the sidebar to unlock Predictive Maintenance & Age Analysis.")

            with st.expander("View Raw Permit Data"):
                st.dataframe(house_permits)

        else:
            st.warning(f"We found permits on '{clean_name}', but none matched #{clean_num}.")
            st.info("Try checking the address number again.")
