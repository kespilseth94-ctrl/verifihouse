import streamlit as st
import requests
import datetime

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(
    page_title="VeriHouse | Certified Asset History", 
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
    </style>
""", unsafe_allow_html=True)

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🛡️ VeriHouse")
    st.markdown("**Residential Risk Intelligence**")
    st.divider()
    st.info("System Status: Online 🟢")
    st.caption("Database: SF Active Permits (i98e)")
    st.divider()
    st.warning("Disclaimer: Not a substitute for professional inspection.")

# --- 4. MAIN INTERFACE ---
st.markdown("<h1 style='text-align: center;'>VeriHouse Property Audit</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #666;'>AI-Powered Permit Analysis & Risk Scoring</p>", unsafe_allow_html=True)
st.write("")

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    with st.container():
        c1, c2 = st.columns(2)
        st_num = c1.text_input("Street Number", value="301")
        st_name = c2.text_input("Street Name", value="Mission") 
        run_btn = st.button("Generate Risk Report", type="primary", use_container_width=True)

# --- 5. THE FORENSIC ENGINE ---
def analyze_risks(permits):
    score = 100
    findings = []
    
    # --- DEEP SEARCH DICTIONARY ---
    risk_map = [
        # 1. ELECTRICAL HAZARDS
        {"keywords": ["KNOB", "TUBE"], "deduction": 25, "msg": "Major Electrical Risk: Knob & Tube Wiring detected.", "cat": "fire"},
        {"keywords": ["ALUMINUM WIRING"], "deduction": 15, "msg": "Fire Risk: Aluminum branch wiring detected.", "cat": "fire"},
        {"keywords": ["UNPERMITTED", "ILLEGAL WIRING", "WORK WITHOUT PERMIT"], "deduction": 20, "msg": "Compliance Risk: History of unpermitted electrical work.", "cat": "legal"},

        # 2. STRUCTURAL FAILURE
        {"keywords": ["UNDERPIN", "SHORING", "FOUNDATION REPAIR", "SETTLEMENT"], "deduction": 30, "msg": "Major Structural Risk: Foundation movement/repair detected.", "cat": "structure"},
        {"keywords": ["SISTERING", "JOIST REPAIR", "DRY ROT", "TERMITE"], "deduction": 15, "msg": "Structural Decay: Frame damage (rot/termites) noted.", "cat": "structure"},
        {"keywords": ["SHEAR WALL", "SOFT STORY"], "deduction": 5, "msg": "Seismic Note: Soft-story retrofit (Safety upgrade, but indicates older structure).", "cat": "structure"},

        # 3. FIRE & BURNING
        {"keywords": ["FIRE DAMAGE", "FIRE REPAIR", "CHARRED", "SCORCH", "BURNING", "SMOKE DAMAGE"], "deduction": 30, "msg": "Structural Risk: Evidence of past fire/burning.", "cat": "fire"},

        # 4. WATER & TOXICITY
        {"keywords": ["WATER DAMAGE", "LEAK", "MOLD", "FUNGAL", "MICROBIAL"], "deduction": 20, "msg": "Health Risk: History of water intrusion or mold.", "cat": "water"},
        {"keywords": ["REMEDIATION", "ABATEMENT", "ASBESTOS", "LEAD PAINT"], "deduction": 10, "msg": "Toxic Material: History of hazmat remediation.", "cat": "health"},

        # 5. LEGAL & ZONING
        {"keywords": ["NOV ", "NOTICE OF VIOLATION", "ORDER OF ABATEMENT", "STOP WORK"], "deduction": 25, "msg": "Legal Risk: Property has received City Violations/Stop Work Orders.", "cat": "legal"},
        {"keywords": ["ILLEGAL UNIT", "UNAUTHORIZED DWELLING", "LEGALIZATION"], "deduction": 15, "msg": "Zoning Risk: History of illegal/unauthorized units.", "cat": "legal"},
        
        # 6. SOLAR
        {"keywords": ["SOLAR", "LEASE", "PPA", "SUNRUN", "TESLA"], "match_all": True, "deduction": 15, "msg": "Financial Encumbrance: Solar Lease detected.", "cat": "finance"},
    ]
    
    # ASSET DICTIONARY
    assets = [
        {"keywords": ["REROOF", "RE-ROOF", "NEW ROOF"], "msg": "Capital Improvement: Roof replaced recently."},
        {"keywords": ["SEISMIC", "RETROFIT", "BOLT"], "msg": "Safety Asset: Seismic retrofitting completed."},
        {"keywords": ["COPPER", "REPIPE"], "msg": "Plumbing Asset: Copper repiping detected."},
        {"keywords": ["100 AMP", "200 AMP", "PANEL UPGRADE"], "msg": "Electrical Asset: Main service panel upgraded."},
    ]

    for p in permits:
        desc = str(p.get('description', '')).upper()
        date = p.get('permit_creation_date', 'N/A')[:4]
        
        # Check Risks
        for risk in risk_map:
            # A. Complex logic: Solar Lease
            if risk.get("match_all"):
                if "SOLAR" in desc and any(term in desc for term in ["LEASE", "PPA", "POWER PURCHASE"]):
                    score -= risk["deduction"]
                    findings.append({"type": "risk", "msg": f"{risk['msg']} ({date})", "cat": risk['cat']})
            
            # B. Standard Logic
            elif any(k in desc for k in risk["keywords"]):
                # SAFEGUARD: Ignore "Burning" if it talks about a stove/fireplace/log
                if "BURNING" in desc and any(safe in desc for safe in ["STOVE", "INSERT", "LOG", "WOOD"]):
                    pass # Skip this risk, it's safe
                else:
                    score -= risk["deduction"]
                    findings.append({"type": "risk", "msg": f"{risk['msg']} ({date})", "cat": risk['cat']})
                    
        # Check Assets
        for asset in assets:
             if any(k in desc for k in asset["keywords"]):
                 findings.append({"type": "safe", "msg": f"{asset['msg']} ({date})"})

    return max(score, 0), findings

# --- 6. EXECUTION LOGIC ---
if run_btn:
    with st.spinner(f"Analyzing municipal records for {st_num} {st_name}..."):
        url = "https://data.sfgov.org/resource/i98e-djp9.json"
        
        # FORMAT INPUTS
        clean_name = st_name.strip().title()
        clean_num = st_num.strip()
        
        # FETCH
        params = {'street_name': clean_name, '$limit': 2000, '$order': 'permit_creation_date DESC'}
        
        try:
            r = requests.get(url, params=params)
            data = r.json()
            
            # FILTER
            house_permits = []
            if isinstance(data, list):
                for p in data:
                    if clean_num in str(p.get('street_number', '')):
                        house_permits.append(p)
            
            # REPORT
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
                with m3: st.markdown(f"<div class='score-card'><div class='metric-label'>Records Analyzed</div><div class='metric-value'>{len(house_permits)}</div></div>", unsafe_allow_html=True)
                
                st.write("")
                st.subheader("📋 Verification Log")
                
                if len(notes) == 0:
                    st.success("No significant risk keywords found in recent history.")
                
                notes.sort(key=lambda x: x['type']) 
                
                for note in notes:
                    if note['type'] == 'risk':
                        st.markdown(f"<div style='margin-bottom:10px;'><span class='badge-risk'>⚠ {note['cat'].upper()} RISK</span> &nbsp; {note['msg']}</div>", unsafe_allow_html=True)
                    elif note['type'] == 'safe':
                        st.markdown(f"<div style='margin-bottom:10px;'><span class='badge-safe'>✓ VERIFIED</span> &nbsp; {note['msg']}</div>", unsafe_allow_html=True)
                
                with st.expander("View Raw Permit Data"):
                    st.dataframe(house_permits)

            else:
                st.warning(f"We found permits on '{clean_name}', but none matched #{clean_num}.")
                st.info("Try checking the address number again.")

        except Exception as e:
            st.error(f"Connection Error: {e}")
