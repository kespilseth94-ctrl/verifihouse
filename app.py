import streamlit as st
import requests
import datetime
import io
import zipfile
import csv

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

# --- MET COUNCIL RESIDENTIAL PERMIT DATA ---
# Source: Metropolitan Council 7-county Twin Cities area, 2009–2024
# Public CSV via MN Geospatial Commons (no token required from Streamlit servers)
# Fields confirmed from metadata: CTU_NAME, YEAR, TOTALUNIT, SFUNIT, MFUNIT,
#   CO_CODE, CTU_CODE (county/city FIPS codes)

@st.cache_data(ttl=86400)  # Cache 24 hours — annual dataset, no need to refetch
def get_metc_permit_data():
    """
    Downloads and parses the Met Council residential permits CSV.
    Returns a dict keyed by (CTU_NAME, YEAR) -> {totalunit, sfunit, mfunit}
    and a sorted list of all city names for the dropdown.
    Falls back to None if the download fails.
    """
    ZIP_URL = (
        "https://resources.gisdata.mn.gov/pub/gdrs/data/pub/us_mn_state_metc/"
        "econ_residential_building_permts/"
        "csv_us_mn_state_metc_econ_residential_building_permts.zip"
    )
    try:
        r = requests.get(ZIP_URL, timeout=20)
        r.raise_for_status()
        z = zipfile.ZipFile(io.BytesIO(r.content))
        # Find the CSV inside the zip
        csv_name = next((n for n in z.namelist() if n.endswith('.csv')), None)
        if not csv_name:
            return None, []
        raw = z.read(csv_name).decode('utf-8', errors='replace')
        reader = csv.DictReader(io.StringIO(raw))
        data = {}
        cities = set()
        for row in reader:
            city = (row.get('CTU_NAME') or '').strip()
            year_raw = (row.get('YEAR') or '').strip()
            if not city or not year_raw:
                continue
            try:
                year = int(float(year_raw))
                total = int(float(row.get('TOTALUNIT') or row.get('TOTAL_UNITS') or 0))
                sf    = int(float(row.get('SFUNIT')    or row.get('SF_UNITS')    or 0))
                mf    = int(float(row.get('MFUNIT')    or row.get('MF_UNITS')    or 0))
            except (ValueError, TypeError):
                continue
            data[(city, year)] = {'total': total, 'sf': sf, 'mf': mf}
            cities.add(city)
        return data, sorted(cities)
    except Exception as e:
        return None, []


def get_metc_city_series(data, city_name):
    """
    Returns sorted list of (year, total, sf, mf) for a given CTU_NAME.
    Tries exact match first, then case-insensitive.
    """
    if not data:
        return []
    # Exact match
    rows = [(y, v['total'], v['sf'], v['mf'])
            for (c, y), v in data.items() if c == city_name]
    if not rows:
        # Case-insensitive
        city_lower = city_name.lower()
        rows = [(y, v['total'], v['sf'], v['mf'])
                for (c, y), v in data.items() if c.lower() == city_lower]
    return sorted(rows, key=lambda x: x[0])


def render_metc_panel(selected_city, data):
    """
    Renders the Twin Cities Market Context panel for MN cities.
    Shows: permit volume trend chart, SF vs MF breakdown, and peer comparison.
    """
    if not data:
        st.info(
            "📊 Met Council market data unavailable — "
            "could not reach gisdata.mn.gov. Try again later."
        )
        return

    # Map Streamlit city name -> CTU_NAME in Met Council data
    CITY_MAP = {
        "Minneapolis, MN": "Minneapolis",
        "Saint Paul, MN":  "Saint Paul",
    }
    ctu = CITY_MAP.get(selected_city, selected_city.replace(", MN", ""))

    series = get_metc_city_series(data, ctu)
    if not series:
        st.info(f"📊 No Met Council permit data found for {ctu}.")
        return

    years  = [r[0] for r in series]
    totals = [r[1] for r in series]
    sfs    = [r[2] for r in series]
    mfs    = [r[3] for r in series]

    # Key stats
    latest_year = years[-1]
    latest_total = totals[-1]
    peak_year  = years[totals.index(max(totals))]
    peak_total = max(totals)
    avg_5yr    = int(sum(totals[-5:]) / min(5, len(totals))) if totals else 0
    latest_sf  = sfs[-1]
    latest_mf  = mfs[-1]

    st.write("")
    st.divider()
    st.subheader("📊 Twin Cities Market Context")
    st.caption(
        f"Met Council residential permit data, 7-county metro area, 2009–{latest_year}. "
        "Source: Metropolitan Council via MN Geospatial Commons."
    )

    # --- Top metrics row ---
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"{latest_year} Permits", f"{latest_total:,}", help="Total residential units permitted")
    m2.metric("5-Year Avg", f"{avg_5yr:,}", help="Average annual units permitted, last 5 years")
    m3.metric("Peak Year", f"{peak_year} ({peak_total:,})", help="Highest single-year permit volume")
    sf_pct = int(100 * latest_sf / latest_total) if latest_total else 0
    m4.metric(f"{latest_year} Single-Family", f"{sf_pct}%", help="Share of permits that are single-family")

    # --- Trend chart using st.bar_chart ---
    st.write("")
    st.markdown(f"**Annual Residential Permit Volume — {ctu}**")

    import pandas as pd
    df_trend = pd.DataFrame({
        "Year": years,
        "Single-Family": sfs,
        "Multifamily": mfs,
    }).set_index("Year")
    st.bar_chart(df_trend, height=220, use_container_width=True)

    # --- Peer comparison: show the city vs 5 neighbors for latest year ---
    PEERS = {
        "Minneapolis": ["Minneapolis", "Saint Paul", "Bloomington", "Brooklyn Park",
                        "Plymouth", "Maple Grove", "Edina"],
        "Saint Paul":  ["Saint Paul", "Minneapolis", "Bloomington", "Maplewood",
                        "Roseville", "Woodbury", "Eagan"],
    }
    peer_list = PEERS.get(ctu, [ctu])
    peer_rows = []
    for peer in peer_list:
        peer_series = get_metc_city_series(data, peer)
        if peer_series:
            last = peer_series[-1]
            peer_rows.append({"City": peer, "Year": last[0],
                               "Total Units": last[1], "SF": last[2], "MF": last[3]})

    if peer_rows:
        st.write("")
        st.markdown(f"**Peer Comparison — {latest_year} Permit Volume**")
        df_peers = pd.DataFrame(peer_rows).sort_values("Total Units", ascending=False)
        df_peers["SF %"] = df_peers.apply(
            lambda r: f"{int(100*r['SF']/r['Total Units'])}%" if r['Total Units'] > 0 else "—", axis=1
        )
        # Highlight selected city
        def highlight_city(row):
            if row["City"] == ctu:
                return ["background-color: #dbeafe"] * len(row)
            return [""] * len(row)
        st.dataframe(
            df_peers[["City", "Total Units", "SF", "MF", "SF %"]].style.apply(highlight_city, axis=1),
            use_container_width=True,
            hide_index=True,
        )

    # 10-year trajectory note
    if len(totals) >= 10:
        delta_10yr = totals[-1] - totals[-10]
        direction  = "▲ up" if delta_10yr > 0 else "▼ down"
        st.caption(
            f"{ctu} residential permitting is {direction} {abs(delta_10yr):,} units "
            f"vs. 10 years ago ({years[-10]}: {totals[-10]:,} → {latest_year}: {latest_total:,})."
        )



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
    "Saint Paul, MN": {
        "rentcast_city": "Saint Paul",
        "rentcast_state": "MN",
        "default_number": "1080",
        "default_street": "Montreal Ave",
        # Note: Saint Paul migrated to PAULIE system (Sept 2025).
        # The Socrata dataset covers permits from 2013 through mid-2025.
        # Very recent permits (post-July 2025) may not yet appear here.
        "data_notice": (
            "⚠️ Saint Paul's open data API is offline (post-July 2025 security incident). "
            "PAULIE (new system) completed its data migration April 2026 but has no public API yet. "
            "RentCast property data and predictive analysis still work. Permit history requires manual lookup."
        ),
    },
    "Chicago, IL": {
        "rentcast_city": "Chicago",
        "rentcast_state": "IL",
        "default_number": "3200",
        "default_street": "N Clark St",
    },
    "Seattle, WA": {
        "rentcast_city": "Seattle",
        "rentcast_state": "WA",
        "default_number": "1314",
        "default_street": "E Marion St",
    },
    "Philadelphia, PA": {
        "rentcast_city": "Philadelphia",
        "rentcast_state": "PA",
        "default_number": "1234",
        "default_street": "Market St",
    },
    "Denver, CO": {
        "rentcast_city": "Denver",
        "rentcast_state": "CO",
        "default_number": "1600",
        "default_street": "Glenarm Pl",
        "data_notice": (
            "ℹ️ Denver migrated its permit portal. "
            "If no permits appear, visit opendata-geospatialdenver.hub.arcgis.com"
        ),
    },
    "Dallas, TX": {
        "rentcast_city": "Dallas",
        "rentcast_state": "TX",
        "default_number": "2911",
        "default_street": "Clydedale Dr",
    },
    "Austin, TX": {
        "rentcast_city": "Austin",
        "rentcast_state": "TX",
        "default_number": "6409",
        "default_street": "Bradsher Dr",
    },
    "New York, NY": {
        "rentcast_city": "New York",
        "rentcast_state": "NY",
        "default_number": "350",
        "default_street": "Fifth Ave",
        "data_notice": (
            "ℹ️ NYC data covers DOB job filings. Work type fields "
            "(electrical, plumbing, structural) are scanned for risk keywords."
        ),
    },
    "Kansas City, MO": {
        "rentcast_city": "Kansas City",
        "rentcast_state": "MO",
        "default_number": "2440",
        "default_street": "Pershing Rd",
        # Confirmed Socrata ntw8-aacc. Note: data paused Mar 2024 for server
        # updates per kcmo.gov — older records still queryable.
        "data_notice": (
            "ℹ️ Kansas City permit data paused in March 2024 for server updates. "
            "Historic records (2010–2024) are still queryable."
        ),
    },
    "Los Angeles, CA": {
        "rentcast_city": "Los Angeles",
        "rentcast_state": "CA",
        "default_number": "13692",
        "default_street": "Erwin St",
    },
    "New Orleans, LA": {
        "rentcast_city": "New Orleans",
        "rentcast_state": "LA",
        "default_number": "2338",
        "default_street": "Constance St",
        # Confirmed Socrata rcm3-fn58. 2012-present, updated nightly.
    },
    "Pittsburgh, PA": {
        "rentcast_city": "Pittsburgh",
        "rentcast_state": "PA",
        "default_number": "125",
        "default_street": "North Highland Ave",
        # WPRDC CKAN API. Resource: f4d1177a. CONFIRMED LIVE April 2026.
        # Note: Building permits now called "Building & Development Application"
        # since June 2024 BDA system launch. Plumbing NOT included (Allegheny
        # County Health Dept handles separately).
    },
    "Miami, FL": {
        "rentcast_city": "Miami",
        "rentcast_state": "FL",
        "default_number": "1 NW",
        "default_street": "1st St",
        # Miami-Dade County ArcGIS open data — last 3 years of permits.
        # Uses self-healing field discovery on the FeatureServer endpoint.
        "data_notice": (
            "ℹ️ Miami-Dade permit data covers unincorporated county. "
            "City of Miami permits may require separate lookup at miamidade.gov/permits"
        ),
    },
    "Cleveland, OH": {
        "rentcast_city": "Cleveland",
        "rentcast_state": "OH",
        "default_number": "2079",
        "default_street": "E 9th St",
    },
    "Detroit, MI": {
        "rentcast_city": "Detroit",
        "rentcast_state": "MI",
        "default_number": "2900",
        "default_street": "E Grand Blvd",
    },
    "Nashville, TN": {
        "rentcast_city": "Nashville",
        "rentcast_state": "TN",
        "default_number": "500",
        "default_street": "Deaderick St",
    },
    "Baltimore, MD": {
        "rentcast_city": "Baltimore",
        "rentcast_state": "MD",
        "default_number": "100",
        "default_street": "N Holliday St",
    },
    "Milwaukee, WI": {
        "rentcast_city": "Milwaukee",
        "rentcast_state": "WI",
        "default_number": "401",
        "default_street": "E Kilbourn Ave",
        # CKAN portal (data.milwaukee.gov). Monthly updates.
        # CSV fields confirmed: Address, Record ID, Permit Type,
        # Status, Date Issued, Date Opened, Construction Total Cost.
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


def get_saint_paul_data(number, street):
    """
    Saint Paul permit data is currently in transition.

    Timeline:
    - July 2025: City suffered a digital security incident; old systems (ECLIPS/AMANDA)
      taken offline. The old Socrata open data portal (j8ip-eytd) went dead.
    - Sept 17, 2025: PAULIE launched as MVP — new permits only, no historical data yet.
    - April 1–6, 2026: PAULIE taken offline for legacy data migration (20+ years of records).
    - April 6, 2026: PAULIE came back online WITH historical data, but as a web portal
      only — no public API or open data export exists yet.

    Until Saint Paul publishes a new open data API, permit data must be looked up manually
    at: https://online.stpaul.gov/stpaulportal (PAULIE public portal)
    """
    clean_num = str(number).strip()
    clean_street = str(street).strip().upper()

    st.info(
        f"**Saint Paul permit data is transitioning to a new system (PAULIE).**\n\n"
        f"Saint Paul's old open data API was taken offline after a July 2025 security "
        f"incident. The new PAULIE system just completed a full data migration (April 2026) "
        f"and now holds 20+ years of permit records — but a public API has not yet been "
        f"published.\n\n"
        f"**To look up permits for {clean_num} {clean_street} manually:**\n"
        f"Visit [Saint Paul PAULIE Portal](https://online.stpaul.gov/stpaulportal) "
        f"and search by address. The RentCast property data and predictive analysis below "
        f"are still active based on year built."
    )
    return []
    """
    Saint Paul: Socrata API (information.stpaul.gov)
    Dataset: Approved Building Permits (j8ip-eytd), covering 2013 to mid-2025.

    Strategy:
      1. Fetch one sample record to auto-discover actual field names
      2. Try multiple address query formats until we get results
      3. Normalize whatever fields exist into the common schema
    """
    clean_num = str(number).strip()
    clean_street = str(street).strip().upper()
    url = "https://information.stpaul.gov/resource/j8ip-eytd.json"

    try:
        # --- Step 1: Discover field names from a sample record ---
        sample_r = requests.get(url, params={'$limit': 1}, timeout=10)
        sample = sample_r.json()
        if not isinstance(sample, list) or len(sample) == 0:
            st.warning("Saint Paul API returned no sample data.")
            return []

        sample_record = sample[0]
        available_fields = list(sample_record.keys())

        # --- Step 2: Find the address field ---
        # Common names Saint Paul / Socrata datasets use
        addr_candidates = [
            'address', 'site_address', 'property_address',
            'permit_address', 'full_address', 'location_address',
        ]
        addr_field = next((f for f in addr_candidates if f in available_fields), None)

        # --- Step 3: Find description / work description field ---
        desc_candidates = [
            'work_description', 'description', 'job_description',
            'permit_description', 'scope_of_work', 'work_type',
            'comments', 'notes',
        ]
        desc_field = next((f for f in desc_candidates if f in available_fields), None)

        # --- Step 4: Find date field ---
        date_candidates = [
            'issue_date', 'issued_date', 'permit_date',
            'permit_creation_date', 'application_date', 'date_issued',
        ]
        date_field = next((f for f in date_candidates if f in available_fields), None)

        # --- Step 5: Find status / permit type / permit number fields ---
        status_field  = next((f for f in ['status', 'permit_status', 'current_status'] if f in available_fields), None)
        type_field    = next((f for f in ['permit_type', 'type', 'permit_type_description', 'work_class'] if f in available_fields), None)
        number_field  = next((f for f in ['permit_number', 'permit_no', 'permit_num', 'permit_id', 'id'] if f in available_fields), None)

        # --- Step 6: Try multiple address query formats ---
        # Saint Paul may store as "591 FAIRVIEW AVE S" or "591 S FAIRVIEW AVE" etc.
        queries_to_try = []
        if addr_field:
            queries_to_try = [
                {f'$where': f"{addr_field} LIKE '{clean_num} {clean_street}%'"},
                {f'$where': f"upper({addr_field}) LIKE '{clean_num} {clean_street}%'"},
                {addr_field: f"{clean_num} {clean_street}"},
                {f'$where': f"{addr_field} LIKE '{clean_num}%'"},
            ]
        else:
            # No address field found — try generic full-text search
            queries_to_try = [{'$q': f"{clean_num} {clean_street}"}]

        data = []
        used_query = None
        for q in queries_to_try:
            q['$limit'] = 2000
            if date_field:
                q['$order'] = f'{date_field} DESC'
            try:
                r = requests.get(url, params=q, timeout=10)
                result = r.json()
                if isinstance(result, list) and len(result) > 0:
                    data = result
                    used_query = q
                    break
            except Exception:
                continue

        # --- Debug info shown in expander so it doesn't clutter the UI ---
        with st.expander("🔧 Saint Paul API Debug", expanded=(len(data) == 0)):
            st.caption(f"Available fields: `{', '.join(available_fields)}`")
            st.caption(f"Mapped → address:`{addr_field}` desc:`{desc_field}` date:`{date_field}` status:`{status_field}`")
            st.caption(f"Records found: {len(data)} | Query used: `{used_query}`")

        if not data:
            return []

        # --- Step 7: Normalize to common schema ---
        normalized = []
        for p in data:
            desc = (p.get(desc_field, '') if desc_field else '') or ''
            date = (p.get(date_field, '') if date_field else '') or ''
            normalized.append({
                'description':          desc,
                'permit_creation_date': str(date)[:10],
                'permit_type':          (p.get(type_field, '') if type_field else '') or '',
                'status':               (p.get(status_field, '') if status_field else '') or '',
                'permit_number':        str((p.get(number_field, '') if number_field else '') or ''),
                'address_display':      (p.get(addr_field, '') if addr_field else '') or '',
                '_raw':                 p,
            })
        return normalized

    except Exception as e:
        st.warning(f"Saint Paul API error: {e}")
        return []


def get_chicago_data(number, street):
    """
    Chicago: Socrata API (data.cityofchicago.org)
    Dataset: Building Permits (ydr8-5enu), 2006-present, ~1M+ records.
    CONFIRMED LIVE April 2026.

    Address is SPLIT into three fields:
      street_number    -> house number
      street_direction -> N/S/E/W (may be empty for some addresses)
      street_name      -> street name e.g. "CLARK ST"

    Key fields:
      permit_          -> permit number (note the trailing underscore)
      permit_type      -> e.g. "PERMIT - RENOVATION/ALTERATION"
      work_description -> description of work
      issue_date       -> ISO date string
      street_number + street_direction + street_name -> combined address
      statuscurrent    -> permit status (note: no underscore before current)
    """
    clean_num = str(number).strip()
    # Chicago stores street name as uppercase e.g. "CLARK ST", "KEDZIE AVE"
    clean_street = str(street).strip().upper()
    # Parse direction prefix if present (N, S, E, W)
    direction = ""
    parts = clean_street.split()
    if parts and parts[0] in ("N", "S", "E", "W"):
        direction = parts[0]
        clean_street_name = " ".join(parts[1:])
    else:
        clean_street_name = clean_street

    url = "https://data.cityofchicago.org/resource/ydr8-5enu.json"

    # Try with direction first, then without
    queries = [
        {"street_number": clean_num, "street_direction": direction,
         "street_name": clean_street_name, "$limit": 2000, "$order": "issue_date DESC"},
        {"street_number": clean_num, "street_name": clean_street_name,
         "$limit": 2000, "$order": "issue_date DESC"},
        {"$where": f"street_number=\'{clean_num}\' AND street_name LIKE \'{clean_street_name}%\'",
         "$limit": 2000, "$order": "issue_date DESC"},
    ]

    for params in queries:
        try:
            r = requests.get(url, params=params, timeout=10)
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                normalized = []
                for p in data:
                    normalized.append({
                        "description":          p.get("work_description", "") or "",
                        "permit_creation_date": (p.get("issue_date", "") or "")[:10],
                        "permit_type":          p.get("permit_type", "") or "",
                        "status":               p.get("permit_status", "") or p.get("statuscurrent", "") or "",
                        "permit_number":        str(p.get("permit_", "") or ""),
                        "address_display":      f"{p.get('street_number','')} {p.get('street_direction','')} {p.get('street_name','')}".strip(),
                        "_raw":                 p,
                    })
                return normalized
        except Exception:
            continue
    return []


def get_seattle_data(number, street):
    """
    Seattle: Socrata API (data.seattle.gov)
    Dataset: Building Permits (76t5-zqzr), 20+ years.
    CONFIRMED LIVE April 2026.

    Key fields:
      permitnum        -> permit number
      permittypemapped -> permit category e.g. "Building", "Electrical"
      description      -> work description
      issueddate       -> ISO date string
      originaladdress1 -> full address e.g. "1314 E MARION ST"
      statuscurrent    -> permit status
      permitclassmapped -> "Residential" / "Commercial"
    """
    clean_num = str(number).strip()
    clean_street = str(street).strip().upper()
    address_prefix = f"{clean_num} {clean_street}"

    url = "https://data.seattle.gov/resource/76t5-zqzr.json"
    params = {
        "$where": f"originaladdress1 LIKE '{address_prefix}%'",
        "$limit": 2000,
        "$order": "issueddate DESC",
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if not isinstance(data, list):
            return []

        normalized = []
        for p in data:
            normalized.append({
                "description":          p.get("description", "") or "",
                "permit_creation_date": (p.get("issueddate", "") or "")[:10],
                "permit_type":          p.get("permittypemapped", "") or "",
                "status":               p.get("statuscurrent", "") or "",
                "permit_number":        str(p.get("permitnum", "") or ""),
                "permit_class":         p.get("permitclassmapped", "") or "",
                "address_display":      p.get("originaladdress1", "") or "",
                "_raw":                 p,
            })
        return normalized
    except Exception as e:
        st.warning(f"Seattle API error: {e}")
        return []


def get_philadelphia_data(number, street):
    """
    Philadelphia: Carto SQL API (phl.carto.com) — NOT Socrata.
    Table: permits (managed by City of Philadelphia L&I dept)
    CONFIRMED LIVE April 2026.

    Key fields:
      permitnumber         -> permit number
      permittype           -> permit category
      approvedscopeofwork  -> description of approved work (richest description field)
      permitissuedate      -> ISO date string
      status               -> permit status
      address              -> full address string e.g. "1234 MARKET ST"
      typeofwork           -> type of work
    """
    clean_num = str(number).strip()
    clean_street = str(street).strip().upper()
    address_like = f"{clean_num} {clean_street}%"

    url = "https://phl.carto.com/api/v2/sql"
    # Carto uses SQL — address field contains full address string
    query = (
        f"SELECT permitnumber, permittype, approvedscopeofwork, "
        f"permitissuedate, status, address, typeofwork, commercialorresidential "
        f"FROM permits "
        f"WHERE address LIKE '{address_like}' "
        f"ORDER BY permitissuedate DESC "
        f"LIMIT 200"
    )
    params = {"q": query, "format": "json"}

    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        rows = data.get("rows", [])

        normalized = []
        for p in rows:
            # approvedscopeofwork is the richest description field
            desc = p.get("approvedscopeofwork") or p.get("typeofwork") or ""
            normalized.append({
                "description":          desc,
                "permit_creation_date": (p.get("permitissuedate", "") or "")[:10],
                "permit_type":          p.get("permittype", "") or "",
                "status":               p.get("status", "") or "",
                "permit_number":        str(p.get("permitnumber", "") or ""),
                "address_display":      p.get("address", "") or "",
                "_raw":                 p,
            })
        return normalized
    except Exception as e:
        st.warning(f"Philadelphia API error: {e}")
        return []


def get_denver_data(number, street):
    """
    Denver: migrated from Socrata to ArcGIS Hub.
    Old endpoint (rffu-79qm) redirects — new endpoint TBD.
    Uses self-healing field discovery. Will show a data notice if the
    endpoint cannot be found.

    To update: find the current FeatureServer URL at
    opendata-geospatialdenver.hub.arcgis.com and update DENVER_ENDPOINT below.
    """
    # Known candidate ArcGIS endpoints for Denver building permits
    # Update this when confirmed:
    DENVER_ENDPOINTS = [
        "https://services1.arcgis.com/zdB7qR0BtYrg0Xpl/arcgis/rest/services/ODC_PERMIT_P_BC_public/FeatureServer/0/query",
        "https://services.arcgis.com/zdB7qR0BtYrg0Xpl/arcgis/rest/services/Building_Permits/FeatureServer/0/query",
    ]

    clean_num = str(number).strip()
    clean_street = str(street).strip().upper()

    for endpoint in DENVER_ENDPOINTS:
        try:
            # Try a sample fetch to test if endpoint is alive
            test = requests.get(endpoint, params={
                "where": "1=1", "outFields": "*",
                "resultRecordCount": 1, "f": "json"
            }, timeout=8)
            sample = test.json()

            if "features" not in sample or sample.get("error"):
                continue

            # Discover field names from sample
            attrs = sample["features"][0]["attributes"] if sample["features"] else {}
            fields = list(attrs.keys())

            # Map fields
            addr_field = next((f for f in fields if "address" in f.lower() or "addr" in f.lower()), None)
            desc_field = next((f for f in fields if "desc" in f.lower() or "work" in f.lower() or "scope" in f.lower()), None)
            date_field = next((f for f in fields if "issued" in f.lower() or "issue" in f.lower() or "date" in f.lower()), None)
            num_field  = next((f for f in fields if "permit" in f.lower() and ("num" in f.lower() or "no" in f.lower() or "id" in f.lower())), None)
            stat_field = next((f for f in fields if "status" in f.lower()), None)
            type_field = next((f for f in fields if "type" in f.lower() and "permit" in f.lower()), None)

            if not addr_field:
                continue

            # Query for the address
            r2 = requests.get(endpoint, params={
                "where": f"{addr_field} LIKE '{clean_num} {clean_street}%'",
                "outFields": "*",
                "resultRecordCount": 2000,
                "orderByFields": f"{date_field} DESC" if date_field else "",
                "f": "json"
            }, timeout=10)
            result = r2.json()
            features = result.get("features", [])

            normalized = []
            for feat in features:
                a = feat.get("attributes", {})
                date_val = a.get(date_field, "") if date_field else ""
                # Convert Unix ms if needed
                if isinstance(date_val, (int, float)) and date_val > 1e10:
                    try:
                        date_val = datetime.datetime.utcfromtimestamp(
                            date_val / 1000).strftime("%Y-%m-%d")
                    except Exception:
                        date_val = ""
                normalized.append({
                    "description":          str(a.get(desc_field, "") or "") if desc_field else "",
                    "permit_creation_date": str(date_val)[:10],
                    "permit_type":          str(a.get(type_field, "") or "") if type_field else "",
                    "status":               str(a.get(stat_field, "") or "") if stat_field else "",
                    "permit_number":        str(a.get(num_field, "") or "") if num_field else "",
                    "address_display":      str(a.get(addr_field, "") or "") if addr_field else "",
                    "_raw":                 a,
                })
            return normalized

        except Exception:
            continue

    # All endpoints failed — show helpful message
    st.info(
        "Denver permit data endpoint could not be reached. "
        "Denver migrated from Socrata to ArcGIS Hub. "
        "Visit [Denver Open Data](https://opendata-geospatialdenver.hub.arcgis.com) "
        "to find the current building permits dataset. "
        "RentCast property data and predictive analysis below are still active."
    )
    return []


def get_dallas_data(number, street):
    """
    Dallas: Socrata API (dallasopendata.com)
    Dataset: Building Permits (e7gq-4sah). CONFIRMED LIVE April 2026.

    Key fields (confirmed):
      street_address  -> full address string e.g. "2911 CLYDEDALE DR"
      work_description -> description of work
      issued_date     -> date string e.g. "12/31/19" (MM/DD/YY format)
      permit_type     -> permit category
      permit_number   -> unique permit ID
      land_use        -> residential / commercial / etc.
      value           -> declared job value
    """
    clean_num = str(number).strip()
    clean_street = str(street).strip().upper()
    address_prefix = f"{clean_num} {clean_street}"

    url = "https://www.dallasopendata.com/resource/e7gq-4sah.json"
    params = {
        "$where": f"street_address LIKE '{address_prefix}%'",
        "$limit": 2000,
        "$order": "issued_date DESC",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if not isinstance(data, list):
            return []
        normalized = []
        for p in data:
            # Dallas issued_date is "MM/DD/YY" — convert to YYYY-MM-DD
            raw_date = p.get("issued_date", "") or ""
            try:
                if raw_date and len(raw_date) == 8 and "/" in raw_date:
                    parts = raw_date.split("/")
                    yr = int(parts[2])
                    yr = 2000 + yr if yr < 100 else yr
                    date_str = f"{yr}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
                else:
                    date_str = raw_date[:10]
            except Exception:
                date_str = raw_date[:10]
            normalized.append({
                "description":          p.get("work_description", "") or "",
                "permit_creation_date": date_str,
                "permit_type":          p.get("permit_type", "") or "",
                "status":               p.get("status_current", "") or "",
                "permit_number":        str(p.get("permit_number", "") or ""),
                "address_display":      p.get("street_address", "") or "",
                "_raw":                 p,
            })
        return normalized
    except Exception as e:
        st.warning(f"Dallas API error: {e}")
        return []


def get_austin_data(number, street):
    """
    Austin: Socrata API (data.austintexas.gov)
    Dataset: Building Permits (3syk-w9eu). CONFIRMED LIVE April 2026.

    Key fields (confirmed):
      original_address1 -> full address e.g. "6409 BRADSHER DR BLDG 3"
      description       -> work description
      issue_date        -> ISO datetime e.g. "2026-03-25T00:00:00.000"
      permit_type       -> category code e.g. "PP" (Plumbing Permit)
      permit_type_desc  -> full description e.g. "Plumbing Permit"
      status_current    -> permit status
      permit_number     -> unique permit ID
      work_class        -> type of work e.g. "Irrigation", "Addition"
    """
    clean_num = str(number).strip()
    clean_street = str(street).strip().upper()
    address_prefix = f"{clean_num} {clean_street}"

    url = "https://data.austintexas.gov/resource/3syk-w9eu.json"
    params = {
        "$where": f"original_address1 LIKE '{address_prefix}%'",
        "$limit": 2000,
        "$order": "issue_date DESC",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if not isinstance(data, list):
            return []
        normalized = []
        for p in data:
            # Full description = type desc + work class + description
            desc_parts = [
                p.get("permit_type_desc", "") or "",
                p.get("work_class", "") or "",
                p.get("description", "") or "",
            ]
            desc = " — ".join(d for d in desc_parts if d)
            normalized.append({
                "description":          desc,
                "permit_creation_date": (p.get("issue_date", "") or "")[:10],
                "permit_type":          p.get("permit_type_desc", "") or p.get("permit_type", "") or "",
                "status":               p.get("status_current", "") or "",
                "permit_number":        str(p.get("permit_number", "") or ""),
                "address_display":      p.get("original_address1", "") or "",
                "_raw":                 p,
            })
        return normalized
    except Exception as e:
        st.warning(f"Austin API error: {e}")
        return []


def get_nyc_data(number, street):
    """
    New York City: Socrata API (data.cityofnewyork.us)
    Dataset: DOB Job Application Filings (w9ak-ipjd). CONFIRMED LIVE April 2026.

    NYC DOB data is structured differently — work types are separate boolean/text
    fields rather than a single description field. Address is split:
      house_no    -> street number e.g. "350"
      street_name -> street name e.g. "FIFTH AVE"

    Key date/status fields:
      filing_date     -> when filed (ISO)
      approved_date   -> when approved
      filing_status   -> e.g. "APPROVED", "FILED", "PERMIT ISSUED"
      job_type        -> "A1" (Alt 1 — major), "A2" (Alt 2 — minor), "NB" (new bldg)

    Work type fields (combined into description):
      general_construction_work_type_
      plumbing_work_type
      mechanical_systems_work_type_
      structural_work_type_
      boiler_equipment_work_type_
      earth_work_work_type_
      foundation_work_type_
    """
    clean_num = str(number).strip()
    clean_street = str(street).strip().upper()

    url = "https://data.cityofnewyork.us/resource/w9ak-ipjd.json"
    params = {
        "house_no": clean_num,
        "$where": f"street_name LIKE '{clean_street}%'",
        "$limit": 2000,
        "$order": "filing_date DESC",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if not isinstance(data, list):
            return []

        work_type_fields = [
            "general_construction_work_type_",
            "plumbing_work_type",
            "mechanical_systems_work_type_",
            "structural_work_type_",
            "boiler_equipment_work_type_",
            "earth_work_work_type_",
            "foundation_work_type_",
            "sprinkler_work_type",
        ]

        normalized = []
        for p in data:
            # Combine all non-empty work type fields into one description
            work_parts = [
                str(p.get(f, "") or "").strip()
                for f in work_type_fields
                if p.get(f, "")
            ]
            job_type = p.get("job_type", "") or ""
            job_map = {"A1": "Major Alteration", "A2": "Minor Alteration",
                       "NB": "New Building", "DM": "Demolition", "SG": "Sign"}
            job_desc = job_map.get(job_type, job_type)
            desc_parts = [job_desc] + work_parts
            desc = " | ".join(d for d in desc_parts if d)

            normalized.append({
                "description":          desc,
                "permit_creation_date": (p.get("filing_date", "") or "")[:10],
                "permit_type":          job_desc,
                "status":               p.get("filing_status", "") or "",
                "permit_number":        str(p.get("job_filing_number", "") or ""),
                "address_display":      f"{p.get('house_no','')} {p.get('street_name','')} {p.get('borough','')}".strip(),
                "_raw":                 p,
            })
        return normalized
    except Exception as e:
        st.warning(f"NYC API error: {e}")
        return []


def fetch_permits(city_name, number, street):
    """Router: calls the right city fetch function."""
    if city_name == "San Francisco, CA":
        return get_sf_data(number, street)
    elif city_name == "Minneapolis, MN":
        return get_minneapolis_data(number, street)
    elif city_name == "Saint Paul, MN":
        return get_saint_paul_data(number, street)
    elif city_name == "Chicago, IL":
        return get_chicago_data(number, street)
    elif city_name == "Seattle, WA":
        return get_seattle_data(number, street)
    elif city_name == "Philadelphia, PA":
        return get_philadelphia_data(number, street)
    elif city_name == "Denver, CO":
        return get_denver_data(number, street)
    elif city_name == "Dallas, TX":
        return get_dallas_data(number, street)
    elif city_name == "Austin, TX":
        return get_austin_data(number, street)
    elif city_name == "New York, NY":
        return get_nyc_data(number, street)
    elif city_name == "Kansas City, MO":
        return get_kansas_city_data(number, street)
    elif city_name == "Los Angeles, CA":
        return get_los_angeles_data(number, street)
    elif city_name == "New Orleans, LA":
        return get_new_orleans_data(number, street)
    elif city_name == "Pittsburgh, PA":
        return get_pittsburgh_data(number, street)
    elif city_name == "Miami, FL":
        return get_miami_data(number, street)
    elif city_name == "Cleveland, OH":
        return get_cleveland_data(number, street)
    elif city_name == "Detroit, MI":
        return get_detroit_data(number, street)
    elif city_name == "Nashville, TN":
        return get_nashville_data(number, street)
    elif city_name == "Baltimore, MD":
        return get_baltimore_data(number, street)
    elif city_name == "Milwaukee, WI":
        return get_milwaukee_data(number, street)
    else:
        return []


def get_kansas_city_data(number, street):
    """
    Kansas City: Socrata API (data.kcmo.org)
    Dataset: Permits - CPD Dataset (ntw8-aacc). CONFIRMED via CSV April 2026.
    Uses BLDS standard fields — same structure as Seattle/Austin.

    Key fields (confirmed from CSV headers):
      originaladdress1  -> full address e.g. "2440 Pershing Rd"
      description       -> work description (often detailed)
      issueddate        -> ISO datetime
      statuscurrent     -> permit status e.g. "Issued", "Completed"
      permitnum         -> permit number
      permittypedesc    -> full type description
      workclassmapped   -> "New", "Existing", etc.

    Note: Data paused March 2024 for server updates per kcmo.gov.
    Historic records (2010-2024) still fully queryable.
    """
    clean_num = str(number).strip()
    clean_street = str(street).strip().upper()
    address_prefix = f"{clean_num} {clean_street}"

    url = "https://data.kcmo.org/resource/ntw8-aacc.json"
    params = {
        "$where": f"originaladdress1 LIKE '{address_prefix}%'",
        "$limit": 2000,
        "$order": "issueddate DESC",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if not isinstance(data, list):
            return []
        normalized = []
        for p in data:
            desc_parts = [
                p.get("description", "") or "",
                p.get("workclassmapped", "") or "",
            ]
            desc = " — ".join(d for d in desc_parts if d)
            normalized.append({
                "description":          desc,
                "permit_creation_date": (p.get("issueddate", "") or "")[:10],
                "permit_type":          p.get("permittypedesc", "") or p.get("permittype", "") or "",
                "status":               p.get("statuscurrent", "") or "",
                "permit_number":        str(p.get("permitnum", "") or ""),
                "address_display":      p.get("originaladdress1", "") or "",
                "_raw":                 p,
            })
        return normalized
    except Exception as e:
        st.warning(f"Kansas City API error: {e}")
        return []


def get_los_angeles_data(number, street):
    """
    Los Angeles: Socrata API (data.lacity.org)
    Dataset: LADBS Permits (9k3p-zrda). CONFIRMED via CSV April 2026.

    Key fields (confirmed from CSV headers):
      PRIMARY_ADDRESS -> full address e.g. "13692 W ERWIN ST"
      WORK_DESC       -> work description
      ISSUE_DATE      -> date string e.g. "10/30/2024"
      STATUS_DESC     -> permit status e.g. "Permit Finaled", "Issued"
      PERMIT_NBR      -> permit number
      PERMIT_TYPE     -> category e.g. "Electrical", "Building"
      PERMIT_SUB_TYPE -> subcategory e.g. "1 or 2 Family Dwelling"

    Note: LA address format includes direction prefix e.g. "13692 W ERWIN ST".
    Search by number + street name without direction for broadest match.
    """
    clean_num = str(number).strip()
    clean_street = str(street).strip().upper()

    url = "https://data.lacity.org/resource/9k3p-zrda.json"

    # Try with full prefix first, then just number
    for where_clause in [
        f"primary_address LIKE '{clean_num}%{clean_street}%'",
        f"primary_address LIKE '{clean_num} %{clean_street.split()[0] if clean_street else ''}%'",
    ]:
        try:
            params = {
                "$where": where_clause,
                "$limit": 2000,
                "$order": "issue_date DESC",
            }
            r = requests.get(url, params=params, timeout=10)
            data = r.json()
            if not isinstance(data, list) or not data:
                continue

            normalized = []
            for p in data:
                # ISSUE_DATE comes as "MM/DD/YYYY" — normalize to YYYY-MM-DD
                # LA API returns lowercase field names
                raw_date = p.get("issue_date", "") or p.get("submitted_date", "") or ""
                date_str = str(raw_date)[:10] if raw_date else ""

                permit_type = p.get("permit_type", "") or ""
                sub_type = p.get("permit_sub_type", "") or ""
                type_str = f"{permit_type} — {sub_type}" if sub_type else permit_type

                normalized.append({
                    "description":          p.get("work_desc", "") or "",
                    "permit_creation_date": date_str,
                    "permit_type":          type_str,
                    "status":               p.get("status_desc", "") or "",
                    "permit_number":        str(p.get("permit_nbr", "") or ""),
                    "address_display":      p.get("primary_address", "") or "",
                    "_raw":                 p,
                })
            return normalized
        except Exception:
            continue

    return []


def get_new_orleans_data(number, street):
    """
    New Orleans: Socrata API (data.nola.gov)
    Dataset: Permits (rcm3-fn58). CONFIRMED via CSV April 2026. 2012-present, nightly updates.

    Key fields (confirmed from CSV):
      Address       -> full address e.g. "2338 Constance St"
      Description   -> work description (often detailed)
      Type          -> permit type e.g. "Renovation (Non-Structural)", "Plumbing Permit"
      IssueDate     -> datetime string e.g. "04/03/2025 10:20:12 AM"
      CurrentStatus -> e.g. "Permit Issued", "Certificate of Completion"
      NumString     -> permit number e.g. "24-24294-POOL"
      FilingDate    -> when filed
      LandUse       -> "Single Family", "Two-Family", "Business Use", etc.
    """
    clean_num = str(number).strip()
    clean_street = str(street).strip().upper()
    address_prefix = f"{clean_num} {clean_street}"

    url = "https://data.nola.gov/resource/rcm3-fn58.json"
    params = {
        "$where": f"Address LIKE '{address_prefix}%'",
        "$limit": 2000,
        "$order": "IssueDate DESC",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if not isinstance(data, list):
            return []
        normalized = []
        for p in data:
            raw_date = p.get("IssueDate", "") or p.get("issuedate", "") or ""
            # Format: "04/03/2025 10:20:12 AM" -> "2025-04-03"
            try:
                if raw_date and "/" in raw_date:
                    date_str = raw_date.split(" ")[0]
                    parts = date_str.split("/")
                    date_str = f"{parts[2]}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
                else:
                    date_str = raw_date[:10]
            except Exception:
                date_str = raw_date[:10]

            desc = p.get("Description", "") or p.get("description", "") or ""
            land_use = p.get("LandUse", "") or p.get("landuse", "") or ""
            if land_use:
                desc = f"{desc} [{land_use}]".strip(" []")

            normalized.append({
                "description":          desc,
                "permit_creation_date": date_str,
                "permit_type":          p.get("Type", "") or p.get("type", "") or "",
                "status":               p.get("CurrentStatus", "") or p.get("currentstatus", "") or "",
                "permit_number":        str(p.get("NumString", "") or p.get("numstring", "") or ""),
                "address_display":      p.get("Address", "") or p.get("address", "") or "",
                "_raw":                 p,
            })
        return normalized
    except Exception as e:
        st.warning(f"New Orleans API error: {e}")
        return []


def get_pittsburgh_data(number, street):
    """
    Pittsburgh: WPRDC CKAN API (data.wprdc.org)
    Dataset: PLI Permits. CONFIRMED LIVE April 2026 with 2026 data.
    Resource ID: f4d1177a-f597-4c32-8cbf-7885f56253f6

    Key fields (confirmed from live test):
      address          -> full address e.g. "125 N HIGHLAND AVE, Pittsburgh, PA 15206-"
      work_description -> description of work
      work_type        -> type of work
      permit_type      -> e.g. "BUILDING", "Building & Development Application"
      issue_date       -> ISO date string e.g. "2026-03-31"
      status           -> permit status
      permit_id        -> unique permit ID
      neighborhood     -> Pittsburgh neighborhood

    Note: Since June 2024, building permits are "Building & Development Application".
    Plumbing NOT included (Allegheny County Health Dept handles separately).
    """
    clean_num = str(number).strip()
    clean_street = str(street).strip().upper()
    search_term = f"{clean_num} {clean_street.split()[0]}" if clean_street else clean_num

    RESOURCE_ID = "f4d1177a-f597-4c32-8cbf-7885f56253f6"
    CKAN_BASE = "https://data.wprdc.org/api/3/action/datastore_search"

    try:
        r = requests.get(CKAN_BASE, params={
            "resource_id": RESOURCE_ID,
            "q": search_term,
            "limit": 500,
        }, timeout=10)
        data = r.json()
        if not data.get("success") or not data.get("result", {}).get("records"):
            return []

        records = data["result"]["records"]
        # Filter to confirmed address prefix match
        records = [rec for rec in records
                   if str(rec.get("address", "")).upper().startswith(clean_num + " ")]

        normalized = []
        for p in records:
            desc = p.get("work_description", "") or p.get("work_type", "") or ""
            normalized.append({
                "description":          desc,
                "permit_creation_date": str(p.get("issue_date", "") or "")[:10],
                "permit_type":          p.get("permit_type", "") or "",
                "status":               p.get("status", "") or "",
                "permit_number":        str(p.get("permit_id", "") or ""),
                "address_display":      p.get("address", "") or "",
                "_raw":                 p,
            })
        return normalized

    except Exception as e:
        st.warning(f"Pittsburgh API error: {e}")
        return []


def get_miami_data(number, street):
    """
    Miami-Dade: ArcGIS Open Data (gis-mdc.opendata.arcgis.com)
    Building permits for last 3 years, county-wide.
    Uses self-healing field discovery — ArcGIS FeatureServer query.

    Known fields from metadata:
      ADDRESS or SITE_ADDR -> property address
      JOB_DESC or DESCRIPTION -> work description
      ISSUE_DATE or DATE_ISSUED -> issue date (Unix ms or string)
      STATUS or PERMIT_STATUS -> current status
      PROCESS_NUM or PERMIT_NUM -> permit number
      PERMIT_TYPE -> category

    Note: Covers unincorporated Miami-Dade. City of Miami permits
    may be in a separate dataset.
    """
    clean_num = str(number).strip()
    clean_street = str(street).strip().upper()

    # Known candidate ArcGIS endpoints for Miami-Dade building permits
    endpoints = [
        "https://services1.arcgis.com/CvuPhqcTQpZPT9qY/arcgis/rest/services/Building_Permit/FeatureServer/0/query",
        "https://gis.miamidade.gov/arcgis/rest/services/Building/BuildingPermits/FeatureServer/0/query",
        "https://services1.arcgis.com/CvuPhqcTQpZPT9qY/arcgis/rest/services/MDC_BuildingPermit/FeatureServer/0/query",
    ]

    for endpoint in endpoints:
        try:
            # Sample fetch to discover fields and verify endpoint
            test = requests.get(endpoint, params={
                "where": "1=1", "outFields": "*",
                "resultRecordCount": 1, "f": "json"
            }, timeout=8)
            sample = test.json()
            if "features" not in sample or sample.get("error"):
                continue

            attrs = sample["features"][0]["attributes"] if sample["features"] else {}
            fields = list(attrs.keys())

            addr_f = next((f for f in fields if any(x in f.upper() for x in ["ADDRESS","ADDR","SITE"])), None)
            desc_f = next((f for f in fields if any(x in f.upper() for x in ["DESC","WORK","SCOPE","JOB"])), None)
            date_f = next((f for f in fields if any(x in f.upper() for x in ["ISSUE","DATE","ISSUED"])), None)
            stat_f = next((f for f in fields if "STATUS" in f.upper()), None)
            num_f  = next((f for f in fields if any(x in f.upper() for x in ["PROCESS","PERMIT_N","PERMIT_NUM","NUMBER"])), None)
            type_f = next((f for f in fields if "TYPE" in f.upper() and "PERMIT" in f.upper()), None)

            if not addr_f:
                continue

            r = requests.get(endpoint, params={
                "where": f"{addr_f} LIKE '{clean_num}%{clean_street.split()[0]}%'",
                "outFields": "*", "resultRecordCount": 2000, "f": "json"
            }, timeout=10)
            result = r.json()
            features = result.get("features", [])

            normalized = []
            for feat in features:
                a = feat.get("attributes", {})
                date_val = a.get(date_f, "") if date_f else ""
                if isinstance(date_val, (int, float)) and date_val > 1e10:
                    try:
                        date_val = datetime.datetime.utcfromtimestamp(date_val / 1000).strftime("%Y-%m-%d")
                    except Exception:
                        date_val = ""
                normalized.append({
                    "description":          str(a.get(desc_f, "") or "") if desc_f else "",
                    "permit_creation_date": str(date_val)[:10],
                    "permit_type":          str(a.get(type_f, "") or "") if type_f else "",
                    "status":               str(a.get(stat_f, "") or "") if stat_f else "",
                    "permit_number":        str(a.get(num_f, "") or "") if num_f else "",
                    "address_display":      str(a.get(addr_f, "") or "") if addr_f else "",
                    "_raw":                 a,
                })
            return normalized

        except Exception:
            continue

    st.info(
        "Miami-Dade permit data endpoint could not be reached. "
        "Search permits at [miamidade.gov/permits](https://www.miamidade.gov/permits/). "
        "RentCast property data and predictive analysis are still active."
    )
    return []


def _arcgis_self_heal(endpoints, clean_num, clean_street, city_label):
    """
    Generic self-healing ArcGIS FeatureServer fetcher.
    Tries each endpoint, auto-discovers address/desc/date/status fields,
    queries by address, and returns normalized permit list.
    Used by Cleveland, Detroit, Nashville, Miami.
    """
    for endpoint in endpoints:
        try:
            test = requests.get(endpoint, params={
                "where": "1=1", "outFields": "*",
                "resultRecordCount": 1, "f": "json"
            }, timeout=8)
            sample = test.json()
            if "features" not in sample or sample.get("error"):
                continue
            attrs = (sample["features"][0].get("attributes", {})
                     if sample["features"] else {})
            if not attrs:
                continue
            fields = list(attrs.keys())

            def find(keywords, exclude=None):
                kws = [k.upper() for k in keywords]
                exc = [e.upper() for e in (exclude or [])]
                return next((f for f in fields
                             if any(k in f.upper() for k in kws)
                             and not any(e in f.upper() for e in exc)), None)

            addr_f = find(["ADDRESS","ADDR","LOCATION","SITE"], ["NUMBER","NUM","URL"])
            desc_f = find(["DESC","WORK","SCOPE","JOB","NOTES"])
            date_f = find(["ISSUE","ISSUED"], ["EXPIRE","EXPIR"]) or find(["DATE"])
            stat_f = find(["STATUS"])
            num_f  = find(["PERMIT_N","PERMIT_NO","PERMITNO","PERMIT_NUM",
                           "PROCESS_N","APP_NO","APPNO","RECORD"])
            type_f = find(["PERMIT_TYPE","PERMITTYPE","TYPE","CATEGORY"],
                          ["SUBTYPE","SUB_TYPE"])

            if not addr_f:
                continue

            where = (f"{addr_f} LIKE '{clean_num} {clean_street.split()[0]}%'"
                     if clean_street else f"{addr_f} LIKE '{clean_num}%'")
            r = requests.get(endpoint, params={
                "where": where, "outFields": "*",
                "resultRecordCount": 2000,
                "orderByFields": f"{date_f} DESC" if date_f else "",
                "f": "json"
            }, timeout=10)
            features = r.json().get("features", [])

            normalized = []
            for feat in features:
                a = feat.get("attributes", {})
                dv = a.get(date_f, "") if date_f else ""
                if isinstance(dv, (int, float)) and dv and dv > 1e10:
                    try:
                        dv = datetime.datetime.utcfromtimestamp(
                            dv / 1000).strftime("%Y-%m-%d")
                    except Exception:
                        dv = ""
                normalized.append({
                    "description":          str(a.get(desc_f) or "") if desc_f else "",
                    "permit_creation_date": str(dv)[:10],
                    "permit_type":          str(a.get(type_f) or "") if type_f else "",
                    "status":               str(a.get(stat_f) or "") if stat_f else "",
                    "permit_number":        str(a.get(num_f) or "") if num_f else "",
                    "address_display":      str(a.get(addr_f) or "") if addr_f else "",
                    "_raw":                 a,
                })
            return normalized
        except Exception:
            continue
    return []


def get_milwaukee_data(number, street):
    """
    Milwaukee: CKAN open data portal (data.milwaukee.gov).
    Resource ID: 828e9630-d7cb-42e4-960e-964eae916397
    Updated monthly. CONFIRMED via CSV download April 2026.

    Key fields (confirmed from CSV):
      Address                -> full address e.g. "401 E KILBOURN AV"
      Record ID              -> permit number e.g. "COM-ALT-16-1169828-H"
      Permit Type            -> e.g. "Commercial Alteration Permit",
                                "Residential New Construction Permit"
      Status                 -> e.g. "Issued"
      Date Issued            -> ISO datetime e.g. "2016-10-19 00:00:00"
      Date Opened            -> when application was opened
      Construction Total Cost -> declared cost

    CKAN datastore_search API — address filter uses plain text search.
    Falls back to full CSV fetch + local filter if datastore API unavailable.
    """
    clean_num = str(number).strip()
    clean_street = str(street).strip().upper()
    address_prefix = f"{clean_num} {clean_street.split()[0]}"

    RESOURCE_ID = "828e9630-d7cb-42e4-960e-964eae916397"
    CKAN_BASE = "https://data.milwaukee.gov/api/3/action/datastore_search"

    # Try CKAN datastore_search with q (full-text search on address)
    try:
        params = {
            "resource_id": RESOURCE_ID,
            "q": address_prefix,
            "limit": 500,
        }
        r = requests.get(CKAN_BASE, params=params, timeout=10)
        data = r.json()

        if data.get("success") and data.get("result", {}).get("records"):
            records = data["result"]["records"]
            # Filter to address matches (CKAN full-text search is broad)
            records = [rec for rec in records
                       if str(rec.get("Address", "")).upper().startswith(
                           f"{clean_num} ")]
            normalized = []
            for p in records:
                raw_date = p.get("Date Issued", "") or p.get("Date Opened", "") or ""
                date_str = str(raw_date)[:10]
                normalized.append({
                    "description":          p.get("Use of Building", "") or "",
                    "permit_creation_date": date_str,
                    "permit_type":          p.get("Permit Type", "") or "",
                    "status":               p.get("Status", "") or "",
                    "permit_number":        str(p.get("Record ID", "") or ""),
                    "address_display":      p.get("Address", "") or "",
                    "_raw":                 p,
                })
            if normalized:
                return normalized

    except Exception:
        pass

    # Fallback: try filters endpoint for exact address match
    try:
        filter_params = {
            "resource_id": RESOURCE_ID,
            "filters": f'{{"Address":"{clean_num} {clean_street}"}}',
            "limit": 500,
        }
        r2 = requests.get(CKAN_BASE, params=filter_params, timeout=10)
        data2 = r2.json()
        if data2.get("success") and data2.get("result", {}).get("records"):
            records2 = data2["result"]["records"]
            normalized2 = []
            for p in records2:
                raw_date = p.get("Date Issued", "") or p.get("Date Opened", "") or ""
                normalized2.append({
                    "description":          p.get("Use of Building", "") or "",
                    "permit_creation_date": str(raw_date)[:10],
                    "permit_type":          p.get("Permit Type", "") or "",
                    "status":               p.get("Status", "") or "",
                    "permit_number":        str(p.get("Record ID", "") or ""),
                    "address_display":      p.get("Address", "") or "",
                    "_raw":                 p,
                })
            return normalized2
    except Exception:
        pass

    st.info(
        "Milwaukee permit data could not be fetched from the CKAN portal. "
        "Search at [data.milwaukee.gov](https://data.milwaukee.gov/dataset/buildingpermits). "
        "RentCast property data and predictions still active."
    )
    return []


def get_baltimore_data(number, street):
    """
    Baltimore: ArcGIS FeatureServer (egisdata.baltimorecity.gov).
    Dataset: Building Permits in DHCD Open Baltimore Datasets (Layer 3).
    Display field: csm_projname. Uses _arcgis_self_heal() for field discovery.

    Known field from ArcGIS metadata: csm_projname (project name/description).
    Other fields discovered at runtime.
    """
    endpoints = [
        "https://egisdata.baltimorecity.gov/egis/rest/services/Housing/DHCD_Open_Baltimore_Datasets/FeatureServer/3/query",
        "https://geodata.baltimorecity.gov/egis/rest/services/Housing/DHCD_Open_Baltimore_Datasets/FeatureServer/3/query",
    ]
    result = _arcgis_self_heal(endpoints, str(number).strip(),
                               str(street).strip().upper(), "Baltimore")
    if not result:
        st.info(
            "Baltimore permit data endpoint could not be reached. "
            "Search at [data.baltimorecity.gov](https://data.baltimorecity.gov). "
            "RentCast property data and predictions still active."
        )
    return result


def get_cleveland_data(number, street):
    """
    Cleveland: ArcGIS Hub (data.clevelandohio.gov). Launched April 2024.
    Dataset: Issued Building Permits — Building and Housing dept.
    Uses _arcgis_self_heal() for field discovery.
    """
    endpoints = [
        "https://services6.arcgis.com/F5y6NqxUFGVMXmAD/arcgis/rest/services/Issued_Building_Permits/FeatureServer/0/query",
        "https://services.arcgis.com/F5y6NqxUFGVMXmAD/arcgis/rest/services/Building_Permits/FeatureServer/0/query",
    ]
    result = _arcgis_self_heal(endpoints, str(number).strip(),
                               str(street).strip().upper(), "Cleveland")
    if not result:
        st.info("Cleveland permit data endpoint not confirmed. "
                "Search at [data.clevelandohio.gov](https://data.clevelandohio.gov). "
                "RentCast data and predictions still active.")
    return result


def get_detroit_data(number, street):
    """
    Detroit: ArcGIS Hub (data.detroitmi.gov).
    Dataset: Building Permits issued by BSEED (Buildings, Safety Engineering
    & Environmental Department).
    Uses _arcgis_self_heal() for field discovery.
    """
    endpoints = [
        "https://services2.arcgis.com/qvkbeam8ghSnvbe5/arcgis/rest/services/Building_Permits/FeatureServer/0/query",
        "https://services6.arcgis.com/PUGEyBT6P6xHBHdV/arcgis/rest/services/Building_Permits/FeatureServer/0/query",
        "https://services.arcgis.com/PUGEyBT6P6xHBHdV/arcgis/rest/services/Building_Permits/FeatureServer/0/query",
    ]
    result = _arcgis_self_heal(endpoints, str(number).strip(),
                               str(street).strip().upper(), "Detroit")
    if not result:
        st.info("Detroit permit data endpoint not confirmed. "
                "Search at [data.detroitmi.gov](https://data.detroitmi.gov). "
                "RentCast data and predictions still active.")
    return result


def get_nashville_data(number, street):
    """
    Nashville: ArcGIS Hub (datanashvillegov-nashville.hub.arcgis.com).
    Migrated from Socrata. Two datasets:
      - Building Permits Issued (3-year rolling)
      - Building Permit Applications
    Uses _arcgis_self_heal() for field discovery.
    """
    endpoints = [
        "https://services2.arcgis.com/HdTo6HJqh92wn4D8/arcgis/rest/services/Building_Permits_Issued/FeatureServer/0/query",
        "https://services2.arcgis.com/HdTo6HJqh92wn4D8/arcgis/rest/services/Building_Permit_Applications/FeatureServer/0/query",
        "https://services1.arcgis.com/HdTo6HJqh92wn4D8/arcgis/rest/services/Building_Permits_Issued/FeatureServer/0/query",
        "https://services1.arcgis.com/HdTo6HJqh92wn4D8/arcgis/rest/services/Building_Permits/FeatureServer/0/query",
    ]
    result = _arcgis_self_heal(endpoints, str(number).strip(),
                               str(street).strip().upper(), "Nashville")
    if not result:
        st.info("Nashville permit data endpoint not confirmed. "
                "Search at [datanashvillegov-nashville.hub.arcgis.com]"
                "(https://datanashvillegov-nashville.hub.arcgis.com). "
                "RentCast data and predictions still active.")
    return result


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

def analyze_history(permits, city_name="", year_built=None):
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


    # --- MN Code Timeline Safety Gap analysis ---
    # Source: public law — MN DLI, revisor.mn.gov (freely reproducible)
    if city_name in ("Minneapolis, MN", "Saint Paul, MN"):
        score, log = _run_mn_code_timeline(permits, score, log, year_built)

        # Expired permit flag (Minneapolis-specific)
        if city_name == "Minneapolis, MN":
            expired = [p for p in permits if str(p.get('status', '')).upper() == 'EXPIRED']
            if expired:
                score -= 10
                for ep in expired:
                    desc_short = str(ep.get('description', 'Unknown work'))[:60]
                    log.append({"cat": "legal",
                        "msg": f"Expired Permit: '{desc_short}' — work done but final inspection never completed.",
                        "type": "risk"})

    return max(score, 0), log


# ── MN Code Timeline ─────────────────────────────────────────────────────────
# All entries sourced from public Minnesota law:
#   MN Rule 1309 (IRC), MN Rule 1315 (NEC), MN Rule 4714 (UPC)
#   revisor.mn.gov | dli.mn.gov | Official Publication of the State of Minnesota

MN_CODE_TIMELINE = [
    # ELECTRICAL
    {"id": "elec_knob_tube", "system": "electrical", "cutoff_year": 1950,
     "risk_level": "HIGH", "cost_range": "$15k–$40k",
     "remediation_kw": ["REWIRE", "KNOB AND TUBE", "K&T", "REPLACE WIRING", "FULL REWIRE", "WIRING REPLACEMENT"],
     "gap_kw": [],
     "code_ref": "NEC Art. 394; MN Rule 1315",
     "msg": "Home built before 1950 — no rewiring permit found. Likely original knob-and-tube wiring. "
            "Incompatible with modern insulation; MN insurers increasingly declining coverage. "
            "Full rewire est. $15k–$40k."},

    {"id": "elec_aluminum", "system": "electrical", "cutoff_year": 1973,
     "risk_level": "HIGH", "cost_range": "$3k–$20k",
     "remediation_kw": ["ALUMINUM WIRING", "AL WIRING", "CO/ALR", "PIGTAIL", "WIRE NUT", "COPPER PIGTAIL"],
     "gap_kw": [],
     "code_ref": "NEC 310.106; MN Rule 1315",
     "msg": "Home built 1965–1973 — aluminum branch wiring era. Fire risk at connections over time. "
            "Requires CO/ALR outlets or full replacement. Est. $3k–$20k.",
     "year_range": (1965, 1973)},

    {"id": "elec_afci_bedrooms", "system": "electrical", "cutoff_year": 2002,
     "risk_level": "MEDIUM", "cost_range": "$800–$3k",
     "remediation_kw": ["AFCI", "ARC FAULT", "ARC-FAULT", "PANEL UPGRADE", "BREAKER REPLACEMENT"],
     "gap_kw": [],
     "code_ref": "NEC 210.12 (1999 ed.); MN effective Jan 1 2002; dli.mn.gov",
     "msg": "Home built before 2002 — bedroom circuits may lack AFCI protection "
            "(required by MN since 2002). AFCI breakers detect arc faults before fires start. "
            "Upgrade est. $800–$3k."},

    {"id": "elec_afci_whole_home", "system": "electrical", "cutoff_year": 2012,
     "risk_level": "MEDIUM", "cost_range": "$2k–$6k",
     "remediation_kw": ["AFCI", "ARC FAULT", "PANEL UPGRADE", "WHOLE HOUSE AFCI"],
     "gap_kw": [],
     "code_ref": "NEC 210.12 (2011 ed.); MN Rule 1315",
     "msg": "Home built before 2012 — AFCI may cover bedrooms only, not all habitable rooms "
            "(required by current MN code). Full AFCI upgrade est. $2k–$6k."},

    {"id": "elec_gfci", "system": "electrical", "cutoff_year": 1975,
     "risk_level": "MEDIUM", "cost_range": "$500–$2.5k",
     "remediation_kw": ["GFCI", "GROUND FAULT", "GFI", "RECEPTACLE REPLACEMENT"],
     "gap_kw": [],
     "code_ref": "NEC 210.8 (multiple eds.); MN Rule 1315",
     "msg": "Home built before 1975 — may lack GFCI protection in bathrooms, kitchen, garage, "
            "and outdoor locations. Required progressively from 1975 (bathrooms) through 1990s. "
            "Upgrade est. $500–$2.5k."},

    {"id": "elec_fed_pacific", "system": "electrical", "cutoff_year": 1990,
     "risk_level": "HIGH", "cost_range": "$2.5k–$6k",
     "remediation_kw": ["FPE", "STAB-LOK", "STAB LOK", "ZINSCO", "PANEL REPLACEMENT", "MAIN PANEL", "SERVICE PANEL"],
     "gap_kw": ["PANEL", "MAIN PANEL", "SERVICE PANEL"],
     "code_ref": "CPSC advisory; MN Rule 1315",
     "msg": "Panel permit found — verify original panel was not FPE Stab-Lok or Zinsco "
            "(common 1950–1990). Documented breaker failure rates; many MN insurers declining coverage. "
            "Replacement est. $2.5k–$6k."},

    # STRUCTURAL
    {"id": "struct_deck_lateral", "system": "structure", "cutoff_year": 2015,
     "risk_level": "HIGH", "cost_range": "$8k–$20k",
     "remediation_kw": ["DECK", "PORCH", "BALCONY", "DECK REPAIR", "DECK REBUILD", "LATERAL LOAD"],
     "gap_kw": ["DECK", "PORCH", "BALCONY"],
     "code_ref": "MRC R507.1, R507.2.3; MN Rule 1309 (2015 IRC); revisor.mn.gov 1309.0507",
     "msg": "Deck permit predates 2015 MN code requiring lateral load anchoring (MRC R507). "
            "Pre-2015 decks attached with nails only — insufficient lateral resistance. "
            "90% of deck collapses involve ledger failure. Rebuild est. $8k–$20k."},

    {"id": "struct_egress", "system": "structure", "cutoff_year": 1990,
     "risk_level": "HIGH", "cost_range": "$3k–$8k",
     "remediation_kw": ["EGRESS", "EGRESS WINDOW", "WINDOW WELL", "EGRESS OPENING"],
     "gap_kw": [],
     "code_ref": "IRC R310; MN Rule 1309",
     "msg": "Home pre-1990 listed with basement bedrooms — no egress window permit found. "
            "Pre-code basement bedrooms may be illegal and uninsurable as sleeping rooms. "
            "Egress window installation est. $3k–$8k per opening."},

    {"id": "struct_stucco_eifs", "system": "structure", "cutoff_year": 2003,
     "risk_level": "HIGH", "cost_range": "$15k–$60k",
     "remediation_kw": ["STUCCO", "EIFS", "RESIDE", "RE-SIDE", "MOISTURE BARRIER", "WATER MANAGEMENT",
                        "DRAINAGE PLANE", "SYNTHETIC STUCCO"],
     "gap_kw": ["STUCCO", "EIFS"],
     "code_ref": "IRC R703; MN Rule 1309; MN moisture barrier amendments (post-Woodbury 2002)",
     "msg": "EIFS/stucco permit found predating 2003 MN moisture barrier requirements. "
            "Post-Woodbury (2002), MN code requires drainage plane — pre-code EIFS traps moisture "
            "causing concealed rot. MN insurers increasingly declining. Est. $15k–$60k."},

    # PLUMBING
    {"id": "plumb_polybutylene", "system": "plumbing", "cutoff_year": 1996,
     "risk_level": "HIGH", "cost_range": "$4k–$15k",
     "remediation_kw": ["POLYBUTYLENE", "PB PIPE", "QUEST PIPE", "REPIPE", "REPLACE WATER LINES"],
     "gap_kw": [],
     "code_ref": "Cox v. Shell Oil 1995 settlement; MN Rule 4714",
     "msg": "Home built 1978–1995 — no repipe permit found. May contain polybutylene (PB) water pipe. "
            "Subject to fitting failure; most MN insurers require documented replacement. "
            "Full repipe est. $4k–$15k.",
     "year_range": (1978, 1995)},

    {"id": "plumb_galvanized", "system": "plumbing", "cutoff_year": 1960,
     "risk_level": "MEDIUM", "cost_range": "$5k–$18k",
     "remediation_kw": ["REPIPE", "COPPER", "PEX", "WATER LINE", "SUPPLY LINE", "REPLACE PIPE"],
     "gap_kw": [],
     "code_ref": "UPC 604.1; MN Rule 4714",
     "msg": "Home built before 1960 — no repipe permit. Likely original galvanized steel supply lines. "
            "Galvanized corrodes internally, reducing flow and eventually failing. "
            "At or past 50–70 year lifespan. Repipe est. $5k–$18k."},

    {"id": "plumb_sewer", "system": "plumbing", "cutoff_year": 1980,
     "risk_level": "HIGH", "cost_range": "$5k–$25k",
     "remediation_kw": ["SEWER LATERAL", "SEWER LINE", "CLAY TILE", "SEWER REPAIR", "LATERAL REPLACEMENT"],
     "gap_kw": [],
     "code_ref": "MN Rule 4714; Twin Cities municipal sewer compliance programs",
     "msg": "Home built before 1980 — likely clay tile or Orangeburg sewer lateral. "
            "Many Twin Cities municipalities require point-of-sale sewer compliance inspection. "
            "Replacement est. $5k–$25k."},

    {"id": "plumb_septic", "system": "plumbing", "cutoff_year": 9999,
     "risk_level": "HIGH", "cost_range": "$3k–$40k",
     "remediation_kw": ["SEPTIC COMPLIANCE", "MOUND SYSTEM REPAIR", "DRAINFIELD REPAIR"],
     "gap_kw": ["SEPTIC", "ISTS", "DRAINFIELD", "MOUND SYSTEM"],
     "code_ref": "MN Rule 7080; MN Statute 115.55 (revisor.mn.gov)",
     "msg": "Property has septic system. MN law (Rule 7080) requires compliance inspection at sale "
            "and pump-out every 3 years. Failed compliance = no mortgage closing. "
            "Replacement est. $3k–$40k depending on system type."},

    # ROOFING
    {"id": "roof_ice_barrier", "system": "roofing", "cutoff_year": 2000,
     "risk_level": "MEDIUM", "cost_range": "$500–$2k added at reroofing",
     "remediation_kw": ["ICE BARRIER", "ICE AND WATER", "ICE SHIELD", "REROOF", "ROOF REPLACEMENT"],
     "gap_kw": ["ROOF", "REROOF", "SHINGLE"],
     "code_ref": "IRC R905.2.7.1; MN Rule 1309; MN climate zone 6",
     "msg": "Roof permit predates 2000 — ice barrier membrane at eaves may be absent. "
            "Required in MN (Climate Zone 6) by IRC R905.2.7. "
            "Prevents water infiltration from ice dams. Added cost at reroofing: $500–$2k."},

    # HVAC
    {"id": "hvac_co_detector", "system": "hvac", "cutoff_year": 2009,
     "risk_level": "LOW", "cost_range": "$100–$500",
     "remediation_kw": ["CO DETECTOR", "CARBON MONOXIDE", "CO ALARM"],
     "gap_kw": [],
     "code_ref": "MN Statute 299F.50; IRC R315",
     "msg": "Home built before 2009 with fuel appliances — verify CO detector installation. "
            "Required by MN Statute 299F.50 since August 2009. "
            "Inexpensive ($30–$100/detector) but required for MN home sale."},
]


def _run_mn_code_timeline(permits, score, log, year_built=None):
    """
    Evaluates every MN Code Timeline entry against the property's permit history.
    Uses three modes:
      1. remediation_found: a relevant permit exists → gap addressed, skip
      2. gap_kw match pre-cutoff: confirmed Safety Gap → flag + deduct
      3. Year-based inference using year_built (from RentCast) as fallback
    Source: public Minnesota law (freely reproducible per US copyright law)
    """
    current_year = datetime.datetime.now().year
    all_desc = " ".join(str(p.get('description', '')).upper() for p in permits)

    permit_years = []
    for p in permits:
        try:
            permit_years.append(int(p.get('permit_creation_date', '9999')[:4]))
        except Exception:
            pass
    earliest_permit_yr = min(permit_years) if permit_years else 9999

    # Use year_built from RentCast if available — more reliable than permit dates
    ref_year = year_built if (year_built and year_built > 1800) else earliest_permit_yr

    for entry in MN_CODE_TIMELINE:
        entry_id    = entry["id"]
        cutoff      = entry["cutoff_year"]
        rem_kw      = entry["remediation_kw"]
        gap_kw      = entry["gap_kw"]
        risk        = entry["risk_level"]
        deduction   = {"HIGH": 20, "MEDIUM": 12, "LOW": 4}.get(risk, 10)
        year_range  = entry.get("year_range")

        # Check if remediation already done
        remediated = any(kw in all_desc for kw in rem_kw)

        # ── Special: time-based (roof, furnace, septic) ──
        if cutoff == 9999:
            if entry_id == "plumb_septic":
                if any(kw in all_desc for kw in gap_kw) and not remediated:
                    score -= deduction
                    log.append({"cat": entry["system"], "msg": entry["msg"],
                                 "type": "risk", "code": entry["code_ref"]})
            continue

        if remediated:
            continue  # Gap addressed, no flag

        # ── Year-range entries (only flag within a build year window) ──
        if year_range:
            lo, hi = year_range
            if not (lo <= ref_year <= hi):
                continue

        # Check for gap-keyword permits predating the cutoff
        gap_confirmed = False
        gap_yr = None
        if gap_kw:
            for p in permits:
                desc = str(p.get('description', '')).upper()
                if any(kw in desc for kw in gap_kw):
                    try:
                        yr = int(p.get('permit_creation_date', '9999')[:4])
                        if yr < cutoff:
                            gap_confirmed = True
                            gap_yr = yr
                            break
                    except Exception:
                        pass

        if gap_confirmed:
            score -= deduction
            log.append({
                "cat": entry["system"],
                "msg": f"Safety Gap ({gap_yr}): {entry['msg']} [{entry['code_ref']}]",
                "type": "risk",
            })
        elif ref_year < cutoff and not gap_kw:
            # Year-based inference — no gap keywords but year clearly predates requirement
            partial = max(deduction // 2, 4)
            if risk == "HIGH":
                score -= partial
                log.append({
                    "cat": entry["system"],
                    "msg": f"Potential Gap: {entry['msg']} [{entry['code_ref']}]",
                    "type": "risk",
                })

    return score, log



def predict_future(age, permits, city_name=""):
    preds = []
    if not age or age == 0:
        return preds
    text = " ".join([str(p.get('description', '')).upper() for p in permits])
    current_year = datetime.datetime.now().year

    # Electrical predictions
    if age < 1950 and not any(kw in text for kw in ["REWIRE", "PANEL", "ELECTRICAL", "WIRING"]):
        preds.append({"item": "Full Rewire (Knob & Tube)", "cost": "$15k–$40k", "prob": "HIGH",
            "why": f"Built {age} — no electrical update permits. Original wiring likely knob-and-tube."})
    elif age < 1973 and not any(kw in text for kw in ["REWIRE", "PANEL", "WIRING"]):
        preds.append({"item": "Electrical Panel / Wiring Update", "cost": "$5k–$20k", "prob": "MEDIUM",
            "why": f"Built {age} — may predate AFCI, GFCI, and modern panel requirements."})

    # Plumbing predictions
    if age < 1960 and not any(kw in text for kw in ["REPIPE", "COPPER", "PEX"]):
        preds.append({"item": "Galvanized Pipe Replacement", "cost": "$5k–$18k", "prob": "HIGH",
            "why": f"Built {age} — galvanized steel pipes likely at or past 50–70 year lifespan."})
    elif 1978 <= age <= 1995 and not any(kw in text for kw in ["REPIPE", "PB", "QUEST", "POLYBUTYLENE"]):
        preds.append({"item": "Polybutylene Pipe Replacement", "cost": "$4k–$15k", "prob": "HIGH",
            "why": f"Built {age} — PB pipe era. Most MN insurers require documented replacement."})

    # Roof prediction
    recent_roof = False
    for p in permits:
        desc = str(p.get('description', '')).upper()
        if any(kw in desc for kw in ["ROOF", "REROOF", "SHINGLE"]):
            try:
                if current_year - int(p.get('permit_creation_date', '1900')[:4]) <= 20:
                    recent_roof = True
            except Exception:
                pass
    if not recent_roof:
        preds.append({"item": "Roof Replacement", "cost": "$10k–$25k", "prob": "HIGH",
            "why": "No roof permit in last 20 years. Standard asphalt shingle lifespan is 20–25 yrs in MN."})

    # MN renovation cascade warning
    if city_name in ("Minneapolis, MN", "Saint Paul, MN") and age < 2002:
        preds.append({"item": "Renovation Permit Cascade Risk", "cost": "$10k–$30k additional",
            "prob": "MEDIUM",
            "why": f"Homes built before 2002 in MN: pulling a permit for a major remodel triggers "
                   "full code compliance for electrical, plumbing, and mechanical — even in unrelated areas. "
                   "Budget 20–40% above quoted scope."})
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
    st.caption("Beta — 20 U.S. Cities")
    st.divider()
    st.markdown("**⚠️ Disclaimer**")
    st.markdown(
        "VerifiHouse is an **informational research tool** only. "
        "Permit data is sourced from public government APIs and may be incomplete, "
        "delayed, or contain errors. This tool does **not** constitute a property "
        "inspection, appraisal, or legal advice. Always consult a licensed "
        "inspector, appraiser, or attorney before making real estate decisions. "
        "VerifiHouse makes no representations about the accuracy or completeness "
        "of the data presented."
    )
    st.divider()
    st.caption("Data sources: City open data portals, RentCast API.")
    st.caption("© 2026 VerifiHouse. All rights reserved.")

# Pre-warm Met Council cache in background (silently — no spinner shown)
# This runs once on cold start so MN city queries are instant thereafter
if "metc_prewarmed" not in st.session_state:
    try:
        get_metc_permit_data()
    except Exception:
        pass
    st.session_state.metc_prewarmed = True

# --- 7. MAIN UI ---

st.markdown("<h1 style='text-align: center;'>VerifiHouse Property Audit</h1>", unsafe_allow_html=True)
st.caption(
    "⚠️ For informational purposes only. Permit data sourced from public government APIs "
    "and may be incomplete or delayed. Not a substitute for a professional property inspection, "
    "appraisal, or legal advice."
)

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

    # Show data coverage notice for cities with known limitations
    if city_cfg.get("data_notice"):
        st.info(city_cfg["data_notice"])

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
        year_built = rc.get("yearBuilt", None) if rc else None
        score, findings = analyze_history(permits, city_name=city, year_built=year_built)

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

        # Disclaimer under score cards
        st.caption(
            "⚠️ **Informational only.** This score is generated from public permit records "
            "and automated analysis. It is not a professional inspection, appraisal, or legal opinion. "
            "Data may be incomplete or delayed. Consult a licensed inspector before making "
            "any real estate decision."
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

        # Met Council market context — MN cities only
        if selected_city in ("Minneapolis, MN", "Saint Paul, MN"):
            metc_data, _ = get_metc_permit_data()
            render_metc_panel(selected_city, metc_data)

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
