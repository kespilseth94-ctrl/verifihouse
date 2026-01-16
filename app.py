import streamlit as st
import requests
import datetime

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="VeriHouse | Certified Home History", page_icon="🛡️", layout="wide")

# --- BRANDING CSS ---
st.markdown("""
    <style>
    /* VeriHouse Brand Colors: Navy Blue & Success Green */
    .main-header { font-family: 'Helvetica Neue', sans-serif; color: #2C3E50; }
    
    .score-card { 
        padding: 25px; 
        border-radius: 12px; 
        background-color: #ffffff; 
        border: 1px solid #e1e4e8;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        text-align: center;
    }
    .metric-value { font-size: 2.5em; font-weight: 800; color: #2C3E50; }
    .metric-label { font-size: 0.9em; color: #586069; text-transform: uppercase; letter-spacing: 1.5px; }
    
    /* Custom Badge Styles */
    .badge-verified {
        background-color: #d1fae5; color: #065f46; 
        padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 0.9em;
    }
    .badge-warning {
        background-color: #fee2e2; color: #991b1b; 
        padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 0.9em;
    }
    </style>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
with st.sidebar:
    st.title("🛡️ VeriHouse")
    st.markdown("**The Standard for Home Verification.**")
    st.write("We analyze municipal data to certify the safety and quality of residential assets.")
    st.divider()
    st.caption("Coverage: San Francisco, CA")
    st.caption("v1.2 Beta")
    
    # --- DISCLAIMER SECTION ---
    st.divider()
    st.warning("""
    **Disclaimer:**
    This tool is for informational purposes only and does not constitute a professional home inspection or legal advice. 
    VerifiHouse is not affiliated with the City of San Francisco. 
    Always verify public records with an official city clerk.
    """)

# --- MAIN HERO SECTION ---
st.markdown("<h1 style='text-align: center; color: #2C3E50;'>VeriHouse Property Audit</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #666;'>Enter an address to generate a certified permit history report.</p>", unsafe_allow_html=True)
st.write("") # Spacer

# --- INPUT SECTION (Centered) ---
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    with st.container():
        c1, c2 = st.columns(2)
        street_num = c1.text_input("Street Number", value="3300")
        street_name = c2.text_input("Street Name", value="20TH")
        run_btn = st.button("Verify Property", type="primary", use_container_width=True)

# --- LOGIC ENGINE ---
def calculate_verihouse_score(permits):
    score = 100
    findings = []
    
    # DEDUCTIONS (Risks)
    deductions = {
        "SOLAR LEASE": -15,
        "KNOB & TUBE": -25,
        "UNPERMITTED ROOF": -10
    }
    
    # RISK KEYWORDS
    solar_lease_terms = ["SUNRUN", "SOLARCITY", "TESLA", "LEASE", "PPA"]
    elec_risk = ["KNOB", "TUBE", "UNGROUNDED"]
    
    # QUALITY KEYWORDS
    quality_terms = ["COPPER", "ROMEX", "SPRINKLER", "SEISMIC", "RETROFIT", "FOUNDATION REPLACEMENT"]

    for p in permits:
        desc = str(p.get('description', '')).upper()
        date = p.get('permit_creation_date', 'N/A')[:4]
        
        # 1. Solar Checks
        if "SOLAR" in desc:
            is_lease = any(term in desc for term in solar_lease_terms)
            if is_lease:
                score += deductions["SOLAR LEASE"]
                findings.append({"type": "warning", "msg": f"Encumbered Asset: Solar Lease detected ({date})"})
            else:
                findings.append({"type": "verified", "msg": f"Clean Asset: Owned Solar System detected ({date})"})
        
        # 2. Electrical Checks
        if any(k in desc for k in elec_risk):
            score += deductions["KNOB & TUBE"]
            findings.append({"type": "warning", "msg": f"Safety Risk: Evidence of Knob & Tube wiring ({date})"})
            
        # 3. Quality Checks
        if any(k in desc for k in quality_terms):
            findings.append({"type": "verified", "msg": f"Modern System: {desc[:40]}... ({date})"})

    # Latent Risk Penalty (No data = Bad data)
    if len(permits) == 0:
        score = 60
        findings.append({"type": "warning", "msg": "High Latent Risk: No digital permit records found."})

    return max(score, 0), findings

# --- REPORT DISPLAY ---
if run_btn:
    with st.spinner(f"Verifying records for {street_num} {street_name}..."):
        url = "https://data.sfgov.org/resource/i98e-djp9.json"
        params = {"street_number": street_num, "street_name": street_name.upper(), "$limit": 50, "$order": "permit_creation_date DESC"}
        
        try:
            r = requests.get(url, params=params)
            data = r.json()
            
            # Run Logic
            final_score, notes = calculate_verihouse_score(data)
            
            # Determine Tier
            if final_score >= 90: tier = "Platinum"
            elif final_score >= 80: tier = "Gold"
            elif final_score >= 70: tier = "Silver"
            else: tier = "Standard"
            
            st.divider()
            
            # --- DASHBOARD ---
            m1, m2, m3 = st.columns(3)
            
            with m1:
                st.markdown(f"""
                <div class="score-card">
                    <div class="metric-label">VeriHouse Score</div>
                    <div class="metric-value">{final_score}</div>
                </div>
                """, unsafe_allow_html=True)
                
            with m2:
                st.markdown(f"""
                <div class="score-card">
                    <div class="metric-label">Asset Tier</div>
                    <div class="metric-value">{tier}</div>
                </div>
                """, unsafe_allow_html=True)
                
            with m3:
                st.markdown(f"""
                <div class="score-card">
                    <div class="metric-label">Records Analyzed</div>
                    <div class="metric-value">{len(data)}</div>
                </div>
                """, unsafe_allow_html=True)

            st.write("")
            st.write("")

            # --- DETAILED FINDINGS ---
            st.subheader("📋 Verification Log")
            
            if len(notes) == 0:
                st.info("No specific positive or negative flags found. Property appears standard.")
            
            for note in notes:
                if note["type"] == "verified":
                    st.markdown(f'<span class="badge-verified">✓ VERIFIED</span> {note["msg"]}', unsafe_allow_html=True)
                else:
                    st.markdown(f'<span class="badge-warning">⚠ ALERT</span> {note["msg"]}', unsafe_allow_html=True)
                st.write("") # small gap

        except Exception as e:

            st.error(f"Connection Error: {e}")
