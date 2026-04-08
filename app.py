import streamlit as st
import requests
import datetime

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="VerifiHouse", page_icon="🛡️", layout="wide")

st.markdown("""
    <style>
    .score-card { padding: 20px; border-radius: 10px; background-color: #f8f9fa; border: 1px solid #e9ecef; text-align: center; }
    .metric-value { font-size: 2.2em; font-weight: 800; color: #2C3E50; }
    .metric-label { font-size: 0.85em; color: #6c757d; text-transform: uppercase; letter-spacing: 1px; }
    .badge-risk { background-color: #fee2e2; color: #991b1b; padding: 4px 10px; border-radius: 15px; font-size: 0.8em; font-weight: bold; }
    .badge-safe { background-color: #d1fae5; color: #065f46; padding: 4px 10px; border-radius: 15px; font-size: 0.8em; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- 2. CITY CONFIG ---
# Each city entry defines how to fetch and normalize permit data.
# To add a new city: add an entry here and a get_<city>_data() function below.
CITIES = {
    "San Francisco, CA": {
        "rentcast_city": "San Francisco",
        "rentcast_state": "CA",
        "default_number": "301",
        "default_street": "Mission",
    },
    "Minneapolis, MN": {
        "rentcast_city": "Minneapolis",
        "rentcast_state": "MN",
        "default_number": "4149",
        "default_street": "Aldrich Ave S",
    },
}

# --- 3. INITIALIZE STATE ---
if 'house_permits' not in st.session_state:
    st.session_state.house_permits = []
if 'rc_data' not in st.session_state:
    st.session_state.rc_data = None
if 'has_run' not in st.session_state:
    st.session_state.has_run = False
if 'selected_city' not in st.session_state:
    st.session_state.selected_city = "San Francisco, CA"

# --- 4. DATA FETCH FUNCTIONS ---

def get_sf_data(number, street):
    """
    San Francisco: Socrata API (data.sfgov.org)
    Dataset: Building Permits (i98e-djp9)
    """
    clean_num = str(number).strip()
    clean_street = str(street).strip().title()

    url = "https://data.sfgov.org/resource/i98e-djp9.json"
    params = {
        'street_name': clean_street,
        '$limit': 2000,
        '$order': 'permit_creation_date DESC'
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        raw = [p for p in data if clean_num in str(p.get('street_number', ''))]

        # Normalize to common schema
        normalized = []
        for p in raw:
            normalized.append({
                'description':          p.get('description', ''),
                'permit_creation_date': p.get('permit_creation_date', '')[:10],
                'permit_type':          p.get('permit_type', ''),
                'status':               p.get('status', ''),
                'permit_number':        p.get('permit_number', ''),
                '_raw':                 p,
            })
        return normalized
    except Exception as e:
        st.warning(f"SF API error: {e}")
        return []


def get_minneapolis_data(number, street):
    """
    Minneapolis: ArcGIS REST API (City of Minneapolis CCS Permits)
    Endpoint: services.arcgis.com/.../CCS_Permits/FeatureServer/0/query
    Field mapping confirmed via live API test April 2026.

    Key fields:
      Display      -> full address string (used for matching)
      comments     -> work description (maps to 'description')
      issueDate    -> Unix ms timestamp
      permitType   -> "Plumbing", "Mechanical", "Residential", etc.
      workType     -> sub-category
      status       -> "Issued", "Closed", "Expired"
      permitNumber -> unique permit ID
      APN          -> parcel number
    """
    clean_num = str(number).strip()
    clean_street = str(street).strip().upper()
    address_prefix = f"{clean_num} {clean_street}"

    url = (
        "https://services.arcgis.com/afSMGVsC7QlRK1kZ/arcgis/rest/services/"
        "CCS_Permits/FeatureServer/0/query"
    )
    params = {
        'where':         f"Display LIKE '{address_prefix}%'",
        'outFields':     'Display,comments,issueDate,permitType,workType,status,permitNumber,APN',
        'orderByFields': 'issueDate DESC',
        'resultRecordCount': 2000,
        'f':             'json',
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        features = data.get('features', [])

        normalized = []
        for feat in features:
            attrs = feat.get('attributes', {})

            # Convert Unix ms timestamp to YYYY-MM-DD string
            issue_ms = attrs.get('issueDate')
            if issue_ms:
                try:
                    date_str = datetime.datetime.utcfromtimestamp(
                        issue_ms / 1000
                    ).strftime('%Y-%m-%d')
                except Exception:
                    date_str = ''
            else:
                date_str = ''

            normalized.append({
                'description':          attrs.get('comments', '') or '',
                'permit_creation_date': date_str,
                'permit_type':          attrs.get('permitType', '') or '',
                'status':               attrs.get('status', '') or '',
                'permit_number':        str(attrs.get('permitNumber', '') or ''),
                'work_type':            attrs.get('workType', '') or '',
                'apn':                  attrs.get('APN', '') or '',
                'address_display':      attrs.get('Display', '') or '',
                '_raw':                 attrs,
            })
        return normalized

    except Exception as e:
        st.warning(f"Minneapolis API error: {e}")
        return []


def fetch_permits(city_name, number, street):
    """Router: calls the right city fetch function."""
    if city_name == "San Francisco, CA":
        return get_sf_data(number, street)
    elif city_name == "Minneapolis, MN":
        return get_minneapolis_data(number, street)
    else:
        return []


def get_rentcast_data(number, street, city, state):
    try:
        key = st.secrets["rentcast_key"]
    except Exception:
        return None

    url = "https://api.rentcast.io/v1/properties"
    params = {'address': f"{number} {street}, {city}, {state}"}
    headers = {'X-Api-Key': key}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        data = r.json()
        if isinstance(data, list) and len(data) > 0:
            return data[0]
    except Exception:
        return None
    return None


# --- 5. ANALYSIS FUNCTIONS ---

def analyze_history(permits, city_name=""):
    score = 100
    log = []

    # Universal risk keywords
    risks = [
        {"k": ["KNOB", "TUBE"],              "d": 25, "c": "fire",      "m": "Major Electrical Risk: Knob & Tube Wiring."},
        {"k": ["ALUMINUM WIRING"],           "d": 15, "c": "fire",      "m": "Fire Risk: Aluminum branch wiring."},
        {"k": ["UNPERMITTED", "ILLEGAL WIRING"], "d": 20, "c": "legal", "m": "Compliance Risk: Unpermitted work."},
        {"k": ["UNDERPIN", "SHORING", "FOUNDATION"], "d": 30, "c": "structure", "m": "Structural Risk: Foundation movement."},
        {"k": ["SISTERING", "JOIST", "TERMITE"], "d": 15, "c": "structure", "m": "Structural Decay: Frame damage/rot."},
        {"k": ["FIRE DAMAGE", "CHARRED", "BURNING"], "d": 30, "c": "fire",   "m": "Structural Risk: Past fire evidence."},
        {"k": ["WATER DAMAGE", "MOLD", "FUNGAL"],    "d": 20, "c": "water",  "m": "Health Risk: Water intrusion/mold."},
        {"k": ["REMEDIATION", "ASBESTOS", "LEAD"],   "d": 10, "c": "health", "m": "Toxic Material: Hazmat remediation."},
        {"k": ["NOV ", "NOTICE OF VIOLATION"],       "d": 25, "c": "legal",  "m": "Legal Risk: City Violations found."},
        {"k": ["SOLAR", "LEASE", "PPA"],             "d": 15, "c": "finance","m": "Financial Encumbrance: Solar Lease."},
    ]

    for p in permits:
        desc = str(p.get('description', '')).upper()
        date = p.get('permit_creation_date', 'N/A')[:4]

        for r in risks:
            if any(k in desc for k in r['k']):
                if "BURNING" in desc and "STOVE" in desc:
                    continue
                score -= r['d']
                log.append({"cat": r['c'], "msg": f"{r['m']} ({date})", "type": "risk"})

    # --- Minneapolis-specific Safety Gap checks ---
    if city_name == "Minneapolis, MN":

        # Pre-2015 deck check: any deck permit before 2015 = lateral load gap
        # MRC Section R507 (2015) mandated lateral load anchoring.
        deck_permits = [
            p for p in permits
            if any(kw in str(p.get('description', '')).upper()
                   for kw in ["DECK", "PORCH", "BALCONY"])
        ]
        if deck_permits:
            for dp in deck_permits:
                try:
                    yr = int(dp.get('permit_creation_date', '9999')[:4])
                    if yr < 2015:
                        score -= 15
                        log.append({
                            "cat": "structure",
                            "msg": (
                                f"Safety Gap: Deck permitted {yr}, predates MRC R507 (2015) "
                                "lateral load requirements. Collapse risk — inspect ledger connection. "
                                "Rebuild est. $8k–$20k."
                            ),
                            "type": "risk",
                        })
                        break
                except Exception:
                    pass
        else:
            # No deck permit at all — flag for older homes
            has_old_permits = any(
                int(p.get('permit_creation_date', '9999')[:4]) < 2000
                for p in permits
                if p.get('permit_creation_date', '')
            )
            if has_old_permits or len(permits) == 0:
                log.append({
                    "cat": "structure",
                    "msg": (
                        "No deck permit found. If a deck exists and was built before 2015, "
                        "it likely lacks required lateral load anchoring (MRC R507). Verify on inspection."
                    ),
                    "type": "risk",
                })

        # Expired permit flag (Minneapolis often shows expired = uninspected work)
        expired = [
            p for p in permits
            if str(p.get('status', '')).upper() == 'EXPIRED'
        ]
        if expired:
            score -= 10
            for ep in expired:
                desc_short = str(ep.get('description', 'Unknown work'))[:60]
                log.append({
                    "cat": "legal",
                    "msg": (
                        f"Expired Permit: '{desc_short}' — work done but final inspection "
                        "never completed. Verify with city."
                    ),
                    "type": "risk",
                })

    return max(score, 0), log


def predict_future(age, permits, city_name=""):
    preds = []
    text = " ".join([str(p.get('description', '')).upper() for p in permits])

    if age < 1960 and "REWIRE" not in text and "PANEL" not in text:
        preds.append({
            "item": "Full Rewire",
            "cost": "$15k–$30k",
            "prob": "HIGH",
            "why": f"Built {age}, no rewiring found in permit history."
        })

    if age < 1975 and "COPPER" not in text and "REPIPE" not in text:
        preds.append({
            "item": "Galvanized Pipe Swap",
            "cost": "$8k–$15k",
            "prob": "MEDIUM",
            "why": f"Built {age}, original pipes likely still in place."
        })

    # Roof check
    recent_roof = False
    current_year = datetime.datetime.now().year
    for p in permits:
        if "ROOF" in str(p.get('description', '')).upper():
            try:
                if int(p.get('permit_creation_date', '1900')[:4]) > (current_year - 20):
                    recent_roof = True
            except Exception:
                pass

    if not recent_roof:
        preds.append({
            "item": "Roof Replacement",
            "cost": "$12k–$25k",
            "prob": "HIGH",
            "why": "No roof permits found in last 20 years."
        })

    # Minneapolis-specific: EIFS/stucco exterior insurance cliff
    if city_name == "Minneapolis, MN":
        if "STUCCO" in text or "EIFS" in text:
            stucco_repaired = any(
                kw in text for kw in ["RESIDE", "MOISTURE BARRIER", "WATER MANAGEMENT"]
            )
            if not stucco_repaired:
                preds.append({
                    "item": "EIFS Stucco Water Management",
                    "cost": "$15k–$40k",
                    "prob": "HIGH",
                    "why": (
                        "Stucco/EIFS found with no re-siding or moisture barrier permit. "
                        "MN insurers increasingly declining EIFS coverage — renewal risk within 1–3 years."
                    )
                })

    return preds


def check_truth(claims, permits):
    claims = claims.upper()
    issues = []
    cy = datetime.datetime.now().year

    # Kitchen
    if any(x in claims for x in ["NEW KITCHEN", "REMODELED KITCHEN", "CHEF"]):
        found = any(
            "KITCHEN" in str(p.get('description', '')).upper()
            and int(p.get('permit_creation_date', '1900')[:4]) > (cy - 10)
            for p in permits
        )
        if not found:
            issues.append("Claim: 'Remodeled Kitchen' — No recent kitchen permits found.")

    # Bath
    if any(x in claims for x in ["NEW BATH", "UPDATED BATH", "SPA-LIKE"]):
        found = any(
            ("BATH" in str(p.get('description', '')).upper()
             or "SHOWER" in str(p.get('description', '')).upper())
            and int(p.get('permit_creation_date', '1900')[:4]) > (cy - 10)
            for p in permits
        )
        if not found:
            issues.append("Claim: 'Updated Bathroom' — No recent bath permits found.")

    return issues


# --- 6. SIDEBAR ---
with st.sidebar:
    st.title("🛡️ VerifiHouse")
    st.info("System Online 🟢")
    st.caption("Beta — Minneapolis & San Francisco")

# --- 7. MAIN UI ---
st.markdown("<h1 style='text-align: center;'>VerifiHouse Property Audit</h1>", unsafe_allow_html=True)

# City selector + address inputs
c1, c2 = st.columns([1, 2])
with c2:
    selected_city = st.selectbox(
        "City",
        list(CITIES.keys()),
        index=list(CITIES.keys()).index(st.session_state.selected_city),
    )
    st.session_state.selected_city = selected_city
    city_cfg = CITIES[selected_city]

    col_a, col_b = st.columns(2)
    s_num  = col_a.text_input("Street Number", value=city_cfg["default_number"])
    s_name = col_b.text_input("Street Name",   value=city_cfg["default_street"])

    if st.button("Generate Full Audit", type="primary", use_container_width=True):
        with st.spinner("Analyzing..."):
            st.session_state.house_permits = fetch_permits(selected_city, s_num, s_name)
            st.session_state.rc_data = get_rentcast_data(
                s_num, s_name,
                city_cfg["rentcast_city"],
                city_cfg["rentcast_state"],
            )
            st.session_state.has_run = True

# --- 8. RESULTS ---
if st.session_state.has_run:
    permits = st.session_state.house_permits
    rc      = st.session_state.rc_data
    city    = st.session_state.selected_city

    if len(permits) > 0 or rc:
        score, findings = analyze_history(permits, city_name=city)

        # Tier logic
        if   score >= 90: tier = "PLATINUM"
        elif score >= 80: tier = "GOLD"
        elif score >= 70: tier = "SILVER"
        else:             tier = "STANDARD"

        st.divider()

        # Metrics row
        m1, m2, m3 = st.columns(3)
        m1.markdown(
            f"<div class='score-card'><div class='metric-label'>Score</div>"
            f"<div class='metric-value'>{score}</div></div>",
            unsafe_allow_html=True
        )
        m2.markdown(
            f"<div class='score-card'><div class='metric-label'>Tier</div>"
            f"<div class='metric-value'>{tier}</div></div>",
            unsafe_allow_html=True
        )

        val = rc['yearBuilt'] if (rc and 'yearBuilt' in rc) else len(permits)
        lbl = "Year Built"   if (rc and 'yearBuilt' in rc) else "Permits Found"
        m3.markdown(
            f"<div class='score-card'><div class='metric-label'>{lbl}</div>"
            f"<div class='metric-value'>{val}</div></div>",
            unsafe_allow_html=True
        )

        # Forensic log
        st.write("")
        st.subheader("📋 Forensic Log")
        if not findings:
            st.success("No major risks found in permit history.")
        else:
            for f in findings:
                st.markdown(
                    f"<div style='margin-bottom:5px'>"
                    f"<span class='badge-risk'>⚠ {f['cat'].upper()}</span> {f['msg']}"
                    f"</div>",
                    unsafe_allow_html=True
                )

        # Predictive maintenance (requires RentCast year built)
        if rc:
            st.write("")
            st.subheader("🔮 Predictive Maintenance")
            preds = predict_future(rc.get('yearBuilt', 0), permits, city_name=city)
            if not preds:
                st.info("No anomalies predicted.")
            else:
                for p in preds:
                    bg = "#fef2f2" if p['prob'] == "HIGH" else "#fffbeb"
                    st.markdown(
                        f"<div style='background-color:{bg}; padding:10px; border-radius:5px; margin-bottom:5px;'>"
                        f"<strong>{p['item']}</strong> ({p['cost']})<br>"
                        f"<small>{p['why']}</small></div>",
                        unsafe_allow_html=True
                    )
        else:
            # No RentCast data — note for Minneapolis (RentCast suburb coverage varies)
            if city == "Minneapolis, MN":
                st.caption(
                    "ℹ️ Predictive Maintenance requires property age data. "
                    "RentCast coverage may be limited for this address — "
                    "add year built manually to enable predictions."
                )

        # Listing Truth Check
        st.write("")
        st.divider()
        st.subheader("🕵️ Listing Truth Check")
        with st.form("truth_checker"):
            txt = st.text_area("Paste Listing Description:")
            if st.form_submit_button("Analyze"):
                issues = check_truth(txt, permits)
                if issues:
                    st.error(f"Found {len(issues)} Discrepancies:")
                    for i in issues:
                        st.write(f"- {i}")
                else:
                    st.success("Claims verified.")

        # Raw data expander
        with st.expander("Raw Permit Data"):
            display_cols = ['permit_creation_date', 'permit_type', 'description', 'status', 'permit_number']
            # Only show columns that exist in the data
            available_cols = [c for c in display_cols if any(c in p for p in permits)]
            if available_cols:
                import pandas as pd
                df = pd.DataFrame([{c: p.get(c, '') for c in display_cols} for p in permits])
                st.dataframe(df, use_container_width=True)
            else:
                st.json(permits)

    else:
        st.warning(
            "No permit data found for this address. "
            "Verify the street number and name, then try again. "
            "For Minneapolis, use all-caps street names (e.g. 'ALDRICH AVE S')."
        )
