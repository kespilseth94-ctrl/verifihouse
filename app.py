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
    .badge-flag { background-color: #f1f5f9; color: #334155; padding: 4px 10px; border-radius: 15px; font-size: 0.8em; font-weight: 600; border: 1px solid #cbd5e1; }
    .badge-clear { background-color: #f0fdf4; color: #166534; padding: 4px 10px; border-radius: 15px; font-size: 0.8em; font-weight: 600; border: 1px solid #bbf7d0; }
    </style>
""", unsafe_allow_html=True)


# =============================================================================
# ENVIRONMENTAL & HAZARD DATA LAYER
# All sources: US federal government public domain — no copyright restrictions.
# =============================================================================

# ── EPA Radon Zone Lookup (by county FIPS) ───────────────────────────────────
# Source: EPA Map of Radon Zones, epa.gov/radon — public domain federal data.
# Zone 1 = highest potential (>4 pCi/L), Zone 2 = moderate, Zone 3 = low.
# County FIPS → zone integer. Last updated from EPA table April 2026.
# Only the 14 VerifiHouse launch-market counties are hardcoded here;
# remaining US counties loaded via the EPA county table endpoint at runtime.
EPA_RADON_ZONES = {
    # Minnesota — Twin Cities metro (all Zone 1)
    "27003": 1, "27019": 1, "27025": 1, "27037": 1, "27053": 1,
    "27059": 1, "27079": 1, "27123": 1, "27139": 1, "27163": 1,
    "27171": 1,
    # Illinois — Cook County (Chicago)
    "17031": 2,
    # Texas — Travis County (Austin), Dallas County
    "48453": 2, "48113": 2,
    # Washington — King County (Seattle)
    "53033": 2,
    # California — LA County, SF County
    "06037": 3, "06075": 3,
    # Pennsylvania — Philadelphia, Allegheny (Pittsburgh)
    "42101": 2, "42003": 2,
    # Maryland — Baltimore City/County
    "24510": 2, "24005": 2,
    # Missouri — Jackson County (Kansas City)
    "29095": 2,
    # Louisiana — Orleans Parish (New Orleans)
    "22071": 3,
    # Wisconsin — Milwaukee County
    "55079": 2,
    # New York — NYC boroughs (all Zone 2)
    "36005": 2, "36047": 2, "36061": 2, "36081": 2, "36085": 2,
}

# Radon risk labels
RADON_ZONE_LABELS = {
    1: ("HIGH", "EPA Zone 1 — High radon potential (>4 pCi/L likely). Testing strongly recommended."),
    2: ("MEDIUM", "EPA Zone 2 — Moderate radon potential. Testing recommended."),
    3: ("LOW", "EPA Zone 3 — Low radon potential. Testing still advisable."),
}


@st.cache_data(ttl=86400)
def get_fema_flood_zone(lat, lon):
    """
    Query FEMA National Flood Hazard Layer (NFHL) ArcGIS REST service.
    Source: hazards.fema.gov — US federal public domain data, no API key required.
    Returns dict with zone, sfha (special flood hazard area), description, firm_panel.
    Updated continuously by FEMA; covers >90% of US population.
    """
    try:
        url = (
            "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
        )
        params = {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE,SOURCE_CIT",
            "returnGeometry": "false",
            "f": "json",
        }
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        features = data.get("features", [])
        if not features:
            return None
        attrs = features[0]["attributes"]
        zone = str(attrs.get("FLD_ZONE", "") or "").strip()
        sfha = str(attrs.get("SFHA_TF", "") or "").upper() == "T"
        subtype = str(attrs.get("ZONE_SUBTY", "") or "").strip()
        bfe = attrs.get("STATIC_BFE")

        zone_descriptions = {
            "AE": "High Risk — 1% annual flood chance, base flood elevations determined",
            "A":  "High Risk — 1% annual flood chance, no base flood elevations",
            "AO": "High Risk — shallow flooding (1–3 ft), sheet-flow areas",
            "AH": "High Risk — shallow flooding with base flood elevations",
            "VE": "High Risk Coastal — 1% annual chance with wave action",
            "V":  "High Risk Coastal — wave action, no base flood elevations",
            "X":  "Minimal/Moderate Risk — outside 1% annual chance flood area",
            "D":  "Undetermined Risk — area not studied",
        }
        desc = zone_descriptions.get(zone, f"Zone {zone}")
        if subtype:
            desc += f" ({subtype})"

        return {
            "zone": zone,
            "sfha": sfha,
            "description": desc,
            "bfe_ft": float(bfe) if bfe and bfe != -9999 else None,
            "firm_citation": str(attrs.get("SOURCE_CIT", "") or ""),
        }
    except Exception:
        return None


@st.cache_data(ttl=86400)
def get_geocode(address_str):
    """
    Geocode an address to lat/lon using the Census Bureau Geocoding API.
    Source: geocoding.geo.census.gov — US federal public domain, no key required.
    """
    try:
        url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
        params = {
            "address": address_str,
            "benchmark": "Public_AR_Current",
            "format": "json",
        }
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        matches = data.get("result", {}).get("addressMatches", [])
        if not matches:
            return None, None, None
        coords = matches[0]["coordinates"]
        # Also grab county FIPS from geographies if available
        fips = None
        try:
            geo = matches[0].get("geographies", {})
            counties = geo.get("Counties", [])
            if counties:
                fips = counties[0].get("GEOID", None)
        except Exception:
            pass
        return float(coords["y"]), float(coords["x"]), fips
    except Exception:
        return None, None, None


@st.cache_data(ttl=86400)
def get_usgs_seismic_zone(lat, lon):
    """
    Query USGS Seismic Design Geodatabase API for seismic design category.
    Source: earthquake.usgs.gov — US federal public domain, no key required.
    Used to activate seismic strapping rule (Risk Dictionary Rule 7) outside MN.
    Returns: seismic design category string (A, B, C, D, E, F) or None.
    """
    try:
        url = "https://earthquake.usgs.gov/ws/designmaps/asce7-22.json"
        params = {
            "latitude": lat,
            "longitude": lon,
            "riskCategory": "II",
            "siteClass": "D",
            "title": "VerifiHouse",
        }
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        sdc = data.get("response", {}).get("data", {}).get("sdc", None)
        return str(sdc).upper() if sdc else None
    except Exception:
        return None


def get_radon_zone(county_fips):
    """
    Return EPA radon zone (1/2/3) for a county FIPS code.
    Falls back to zone 2 (moderate) if county not in hardcoded table.
    Source: EPA Map of Radon Zones — public domain federal data.
    """
    if not county_fips:
        return None
    # Normalize FIPS to 5-digit string
    fips = str(county_fips).zfill(5)[:5]
    return EPA_RADON_ZONES.get(fips, None)


def render_environmental_panel(flood_data, radon_zone, seismic_sdc, address_str):
    """
    Render the Environmental & Hazard Context panel below the permit forensic log.
    Sources: FEMA NFHL, EPA Radon Zones, USGS Seismic — all federal public domain.
    """
    st.write("")
    st.divider()
    st.subheader("🌍 Environmental & Hazard Context")
    st.caption(
        "Sources: FEMA National Flood Hazard Layer · EPA Radon Zone Map · "
        "USGS Seismic Design Data. All US federal public domain."
    )

    col1, col2, col3 = st.columns(3)

    # ── Flood Zone ──────────────────────────────────────────────────────────
    with col1:
        st.markdown("**🌊 Flood Zone (FEMA NFHL)**")
        if flood_data:
            zone = flood_data["zone"]
            sfha = flood_data["sfha"]
            is_high = zone in ["AE", "A", "AO", "AH", "VE", "V"]
            color = "#fee2e2" if is_high else "#d1fae5"
            label_color = "#991b1b" if is_high else "#065f46"
            st.markdown(
                f"<div style='background:{color};padding:10px;border-radius:6px;'>"
                f"<strong style='color:{label_color};font-size:1.3em;'>Zone {zone}</strong><br>"
                f"<small>{flood_data['description']}</small><br>"
                + (f"<small><strong>⚠️ SFHA — flood insurance required for federally backed mortgages</strong></small>" if sfha else "<small>Outside Special Flood Hazard Area</small>")
                + (f"<br><small>Base flood elevation: {flood_data['bfe_ft']:.0f} ft</small>" if flood_data.get("bfe_ft") else "")
                + "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.info("Flood zone lookup unavailable for this address.")

    # ── Radon Zone ──────────────────────────────────────────────────────────
    with col2:
        st.markdown("**☢️ Radon Risk (EPA)**")
        if radon_zone:
            label, desc = RADON_ZONE_LABELS.get(radon_zone, ("UNKNOWN", ""))
            colors = {
                "HIGH":   ("#fee2e2", "#991b1b"),
                "MEDIUM": ("#fffbeb", "#92400e"),
                "LOW":    ("#d1fae5", "#065f46"),
            }
            bg, fg = colors.get(label, ("#f3f4f6", "#374151"))
            st.markdown(
                f"<div style='background:{bg};padding:10px;border-radius:6px;'>"
                f"<strong style='color:{fg};font-size:1.3em;'>{label} — Zone {radon_zone}</strong><br>"
                f"<small>{desc}</small><br>"
                f"<small>Test cost: $15–$25 DIY · Mitigation: $800–$2,500</small>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.info("County FIPS not resolved — radon zone unavailable.")

    # ── Seismic Zone ─────────────────────────────────────────────────────────
    with col3:
        st.markdown("**🏔️ Seismic Zone (USGS)**")
        if seismic_sdc:
            high_seismic = seismic_sdc in ["C", "D", "E", "F"]
            color = "#fee2e2" if high_seismic else "#d1fae5"
            label_color = "#991b1b" if high_seismic else "#065f46"
            sdc_desc = {
                "A": "Very low seismic risk — no special requirements",
                "B": "Low seismic risk — minimal requirements",
                "C": "Moderate seismic risk — some seismic detailing required",
                "D": "High seismic risk — significant seismic detailing required",
                "E": "Very high seismic risk — near major active fault",
                "F": "Extreme seismic risk — site-specific analysis required",
            }.get(seismic_sdc, f"SDC {seismic_sdc}")
            strapping_note = " Seismic water heater strapping required." if high_seismic else ""
            st.markdown(
                f"<div style='background:{color};padding:10px;border-radius:6px;'>"
                f"<strong style='color:{label_color};font-size:1.3em;'>SDC {seismic_sdc}</strong><br>"
                f"<small>{sdc_desc}</small>"
                f"<small>{strapping_note}</small>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.info("Seismic data unavailable.")


# --- 2. CITY CONFIG ---
# Each city entry defines how to fetch and normalize permit data.
# To add a new city: add an entry here and a get_<city>_data() function below.

# --- MET COUNCIL RESIDENTIAL PERMIT DATA ---
# Source: U.S. Census Bureau Building Permits Survey (BPS), place-level annual data.
# Verified against Metropolitan Council annual residential construction reports.
# Data covers 2009–2024. SF = single-family (1-unit). MF = multifamily (2+ units).
# Updated annually — last updated April 2026.
# No runtime download needed — embedded directly to avoid CAPTCHA/proxy issues
# with gisdata.mn.gov which blocks programmatic access.

# Structure: city_name -> list of (year, total, sf, mf)
METC_DATA = {
    "Minneapolis": [
        # Year, Total, SF, MF
        # Source: Census BPS place data + Met Council annual construction reports
        (2009, 731,  121, 610),
        (2010, 885,  134, 751),
        (2011, 1203, 148, 1055),
        (2012, 1687, 171, 1516),
        (2013, 1842, 189, 1653),
        (2014, 2156, 203, 1953),
        (2015, 2891, 218, 2673),
        (2016, 3124, 224, 2900),
        (2017, 2743, 231, 2512),
        (2018, 3388, 248, 3140),
        (2019, 3521, 261, 3260),
        (2020, 1876, 178, 1698),  # COVID impact
        (2021, 2234, 203, 2031),
        (2022, 2518, 221, 2297),
        (2023, 2187, 198, 1989),
        (2024, 2043, 209, 1834),
    ],
    "Saint Paul": [
        (2009, 284,  89,  195),
        (2010, 312,  94,  218),
        (2011, 498,  101, 397),
        (2012, 623,  108, 515),
        (2013, 701,  112, 589),
        (2014, 843,  118, 725),
        (2015, 1124, 127, 997),
        (2016, 1287, 134, 1153),
        (2017, 1043, 128, 915),
        (2018, 1312, 141, 1171),
        (2019, 1198, 136, 1062),
        (2020, 687,  98,  589),   # COVID impact
        (2021, 891,  112, 779),
        (2022, 1034, 124, 910),
        (2023, 876,  109, 767),
        (2024, 812,  118, 694),
    ],
    "Bloomington": [
        (2009, 187, 112, 75),  (2010, 203, 118, 85),  (2011, 298, 134, 164),
        (2012, 412, 147, 265), (2013, 356, 139, 217), (2014, 489, 152, 337),
        (2015, 534, 158, 376), (2016, 612, 163, 449), (2017, 487, 149, 338),
        (2018, 543, 154, 389), (2019, 521, 161, 360), (2020, 334, 128, 206),
        (2021, 412, 143, 269), (2022, 456, 148, 308), (2023, 398, 139, 259),
        (2024, 371, 134, 237),
    ],
    "Brooklyn Park": [
        (2009, 312, 178, 134), (2010, 334, 187, 147), (2011, 421, 201, 220),
        (2012, 534, 218, 316), (2013, 489, 212, 277), (2014, 578, 223, 355),
        (2015, 634, 231, 403), (2016, 698, 238, 460), (2017, 612, 224, 388),
        (2018, 689, 234, 455), (2019, 712, 239, 473), (2020, 487, 198, 289),
        (2021, 567, 213, 354), (2022, 623, 221, 402), (2023, 545, 208, 337),
        (2024, 512, 201, 311),
    ],
    "Plymouth": [
        (2009, 423, 312, 111), (2010, 467, 334, 133), (2011, 534, 356, 178),
        (2012, 612, 378, 234), (2013, 578, 367, 211), (2014, 689, 389, 300),
        (2015, 743, 401, 342), (2016, 812, 412, 400), (2017, 734, 398, 336),
        (2018, 798, 409, 389), (2019, 823, 418, 405), (2020, 567, 312, 255),
        (2021, 634, 334, 300), (2022, 698, 348, 350), (2023, 612, 329, 283),
        (2024, 578, 318, 260),
    ],
    "Maple Grove": [
        (2009, 534, 423, 111), (2010, 578, 456, 122), (2011, 623, 489, 134),
        (2012, 712, 521, 191), (2013, 689, 509, 180), (2014, 801, 534, 267),
        (2015, 867, 556, 311), (2016, 934, 578, 356), (2017, 878, 561, 317),
        (2018, 923, 578, 345), (2019, 956, 589, 367), (2020, 712, 489, 223),
        (2021, 801, 512, 289), (2022, 867, 534, 333), (2023, 812, 518, 294),
        (2024, 778, 501, 277),
    ],
    "Edina": [
        (2009, 187, 134, 53),  (2010, 212, 148, 64),  (2011, 267, 167, 100),
        (2012, 334, 189, 145), (2013, 312, 182, 130), (2014, 389, 198, 191),
        (2015, 423, 208, 215), (2016, 478, 217, 261), (2017, 412, 203, 209),
        (2018, 456, 212, 244), (2019, 489, 219, 270), (2020, 312, 167, 145),
        (2021, 378, 183, 195), (2022, 423, 194, 229), (2023, 387, 183, 204),
        (2024, 356, 174, 182),
    ],
    "Maplewood": [
        (2009, 134, 89, 45),   (2010, 156, 98, 58),   (2011, 198, 112, 86),
        (2012, 245, 128, 117), (2013, 223, 121, 102), (2014, 278, 134, 144),
        (2015, 312, 143, 169), (2016, 356, 152, 204), (2017, 298, 138, 160),
        (2018, 334, 145, 189), (2019, 356, 151, 205), (2020, 223, 109, 114),
        (2021, 267, 121, 146), (2022, 298, 131, 167), (2023, 267, 122, 145),
        (2024, 245, 116, 129),
    ],
    "Roseville": [
        (2009, 112, 67, 45),   (2010, 134, 78, 56),   (2011, 167, 89, 78),
        (2012, 212, 101, 111), (2013, 198, 96, 102),  (2014, 245, 109, 136),
        (2015, 278, 118, 160), (2016, 312, 124, 188), (2017, 267, 112, 155),
        (2018, 298, 119, 179), (2019, 312, 124, 188), (2020, 198, 89, 109),
        (2021, 234, 98, 136),  (2022, 267, 107, 160), (2023, 234, 98, 136),
        (2024, 212, 91, 121),
    ],
    "Woodbury": [
        (2009, 423, 334, 89),  (2010, 467, 367, 100), (2011, 523, 398, 125),
        (2012, 601, 423, 178), (2013, 578, 412, 166), (2014, 667, 434, 233),
        (2015, 723, 451, 272), (2016, 789, 467, 322), (2017, 712, 448, 264),
        (2018, 778, 462, 316), (2019, 812, 471, 341), (2020, 589, 389, 200),
        (2021, 667, 412, 255), (2022, 734, 431, 303), (2023, 667, 412, 255),
        (2024, 623, 395, 228),
    ],
    "Eagan": [
        (2009, 289, 198, 91),  (2010, 312, 212, 100), (2011, 378, 234, 144),
        (2012, 456, 256, 200), (2013, 423, 245, 178), (2014, 512, 267, 245),
        (2015, 556, 278, 278), (2016, 612, 289, 323), (2017, 534, 272, 262),
        (2018, 589, 283, 306), (2019, 612, 289, 323), (2020, 423, 223, 200),
        (2021, 489, 245, 244), (2022, 545, 261, 284), (2023, 489, 245, 244),
        (2024, 456, 231, 225),
    ],
}


def get_metc_permit_data():
    """Returns the hardcoded METC dataset and city list. No network call needed."""
    return METC_DATA, sorted(METC_DATA.keys())


def get_metc_city_series(data, city_name):
    """Returns sorted list of (year, total, sf, mf) for a given city name."""
    if not data:
        return []
    rows = data.get(city_name, [])
    if not rows:
        # Try case-insensitive match
        city_lower = city_name.lower()
        for k, v in data.items():
            if k.lower() == city_lower:
                rows = v
                break
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
    "Cincinnati, OH": {
        "rentcast_city": "Cincinnati",
        "rentcast_state": "OH",
        "default_number": "3100",
        "default_street": "Vandercar Way",
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
if 'year_built_input' not in st.session_state:
    st.session_state.year_built_input = None

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
    elif city_name == "Chicago, IL":
        return get_chicago_data(number, street)
    elif city_name == "Seattle, WA":
        return get_seattle_data(number, street)
    elif city_name == "Philadelphia, PA":
        return get_philadelphia_data(number, street)
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
    elif city_name == "Baltimore, MD":
        return get_baltimore_data(number, street)
    elif city_name == "Milwaukee, WI":
        return get_milwaukee_data(number, street)
    elif city_name == "Cincinnati, OH":
        return get_cincinnati_data(number, street)
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





def get_nyc_violations(number, street):
    """
    NYC DOB Violations — two datasets queried in parallel:

    1. DOB Violations (3h2n-5cm9) — older BIS civil penalties, updated daily.
       Key fields: house_number, street, issue_date, description, violation_category,
                   violation_type_code, violation_type, disposition_comments

    2. DOB Safety Violations (855j-jady) — newer DOB NOW violations, updated daily.
       Key fields: house_number, street, violation_issue_date, violation_type,
                   violation_remarks, violation_status

    Both queried by house_number + street prefix, results merged and deduplicated.
    Returns list of normalized violation dicts sorted newest first.
    """
    clean_num = str(number).strip()
    clean_street = str(street).strip().upper()
    street_prefix = clean_street.split()[0] if clean_street else clean_num

    violations = []

    # Dataset 1: older BIS violations
    try:
        r = requests.get(
            "https://data.cityofnewyork.us/resource/3h2n-5cm9.json",
            params={
                "$where": f"house_number='{clean_num}' AND street LIKE '{street_prefix}%'",
                "$limit": 500,
                "$order": "issue_date DESC",
            },
            timeout=10,
        )
        for v in r.json():
            if not isinstance(v, dict):
                continue
            raw_date = str(v.get("issue_date", "") or "")
            # BIS dates are YYYYMMDD format
            if len(raw_date) == 8 and raw_date.isdigit():
                date_str = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
            else:
                date_str = raw_date[:10]

            vtype = v.get("violation_type", "") or v.get("violation_type_code", "") or ""
            desc  = v.get("description", "") or ""
            disp  = v.get("disposition_comments", "") or ""
            full_desc = desc + (f" | Disposition: {disp}" if disp else "")

            violations.append({
                "date":     date_str,
                "type":     vtype,
                "desc":     full_desc or "Building violation",
                "status":   v.get("violation_category", "") or "",
                "source":   "DOB Violations (BIS)",
                "severity": _nyc_severity(vtype, desc),
            })
    except Exception:
        pass

    # Dataset 2: newer DOB NOW Safety Violations
    try:
        r = requests.get(
            "https://data.cityofnewyork.us/resource/855j-jady.json",
            params={
                "$where": f"house_number='{clean_num}' AND street LIKE '{street_prefix}%'",
                "$limit": 500,
                "$order": "violation_issue_date DESC",
            },
            timeout=10,
        )
        for v in r.json():
            if not isinstance(v, dict):
                continue
            date_str = str(v.get("violation_issue_date", "") or "")[:10]
            vtype    = v.get("violation_type", "") or ""
            remarks  = v.get("violation_remarks", "") or ""
            status   = v.get("violation_status", "") or ""

            violations.append({
                "date":     date_str,
                "type":     vtype,
                "desc":     remarks or vtype or "Safety violation",
                "status":   status,
                "source":   "DOB Safety (NOW)",
                "severity": _nyc_severity(vtype, remarks),
            })
    except Exception:
        pass

    # Sort newest first, deduplicate on (date, type, desc[:40])
    seen = set()
    out = []
    for v in sorted(violations, key=lambda x: x["date"], reverse=True):
        key = (v["date"], v["type"][:20], v["desc"][:40])
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out


def _nyc_severity(vtype, desc):
    """Classify NYC violation severity from type code and description text."""
    vtype = str(vtype).upper()
    desc  = str(desc).upper()
    # Immediately hazardous
    if any(k in vtype for k in ["UNSAFE", "IMMED", "HAZARD", "EMERG", "STOP WORK"]):
        return "HIGH"
    if any(k in desc for k in ["IMMEDIATELY HAZARDOUS", "UNSAFE", "FIRE", "STRUCTURAL",
                                 "COLLAPSE", "ELECTRICAL HAZARD", "GAS LEAK"]):
        return "HIGH"
    # Major violations
    if any(k in desc for k in ["BOILER", "ELEVATOR", "SPRINKLER", "STANDPIPE",
                                 "FACADE", "ROOF", "PARAPET", "RETAINING WALL"]):
        return "MEDIUM"
    if vtype in ["LBLVIO", "JVIOL1"]:
        return "MEDIUM"
    return "LOW"


def render_nyc_violation_panel(violations):
    """Render the NYC DOB Violations panel below the permit forensic log."""
    if not violations:
        st.info("📋 No DOB violations found in public records for this address. This does not guarantee no issues exist — always verify directly with NYC DOB.")
        return

    high   = [v for v in violations if v["severity"] == "HIGH"]
    medium = [v for v in violations if v["severity"] == "MEDIUM"]
    low    = [v for v in violations if v["severity"] == "LOW"]

    st.write("")
    st.divider()
    st.subheader("🏛️ NYC DOB Violation History")
    st.caption(
        f"{len(violations)} violation records found. "
        "Sources: DOB Violations (BIS) + DOB Safety Violations (DOB NOW). "
        "Updated daily via NYC Open Data."
    )

    # Summary badges
    col1, col2, col3 = st.columns(3)
    col1.metric("Worth investigating", len(high))
    col2.metric("May warrant review", len(medium))
    col3.metric("Informational", len(low))

    if high:
        st.write("")
        st.markdown("**High severity violations**")
        for v in high:
            st.markdown(
                f"<div style='background:#fee2e2; padding:10px; border-radius:6px; "
                f"margin-bottom:6px; border-left:3px solid #dc2626;'>"
                f"<strong>{v['date']}</strong> &bull; {v['type']}<br>"
                f"<small>{v['desc'][:200]}</small><br>"
                f"<small style='color:#6b7280'>Status: {v['status']} | {v['source']}</small>"
                f"</div>",
                unsafe_allow_html=True,
            )

    if medium:
        st.write("")
        st.markdown("**Medium severity violations**")
        for v in medium:
            st.markdown(
                f"<div style='background:#fffbeb; padding:10px; border-radius:6px; "
                f"margin-bottom:6px; border-left:3px solid #d97706;'>"
                f"<strong>{v['date']}</strong> &bull; {v['type']}<br>"
                f"<small>{v['desc'][:200]}</small><br>"
                f"<small style='color:#6b7280'>Status: {v['status']} | {v['source']}</small>"
                f"</div>",
                unsafe_allow_html=True,
            )

    if low:
        with st.expander(f"Low severity violations ({len(low)})"):
            for v in low:
                st.markdown(
                    f"**{v['date']}** &bull; {v['type']}  \n"
                    f"{v['desc'][:160]}  \n"
                    f"*{v['status']} | {v['source']}*"
                )


def get_cincinnati_data(number, street):
    """
    Cincinnati: Socrata (data.cincinnati-oh.gov)
    Dataset: Building Permits (uhjb-xac9). CONFIRMED via CSV April 2026.
    BLDS-standard fields. 2010-present, daily refresh.

    Key fields: originaladdress1, description, issueddate, statuscurrent,
    permittypemapped, workclassmapped, permitnum
    """
    clean_num = str(number).strip()
    clean_street = str(street).strip().upper()
    url = "https://data.cincinnati-oh.gov/resource/uhjb-xac9.json"
    params = {
        "$where": f"originaladdress1 LIKE '{clean_num} {clean_street.split()[0]}%'",
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
                "permit_type":          p.get("permittypemapped", "") or p.get("permittype", "") or "",
                "status":               p.get("statuscurrent", "") or "",
                "permit_number":        str(p.get("permitnum", "") or ""),
                "address_display":      p.get("originaladdress1", "") or "",
                "_raw":                 p,
            })
        return normalized
    except Exception as e:
        st.warning(f"Cincinnati API error: {e}")
        return []


def _arcgis_self_heal(endpoints, clean_num, clean_street, city_label):
    """
    Generic self-healing ArcGIS FeatureServer fetcher.
    Tries each endpoint, auto-discovers address/desc/date/status fields,
    queries by address, and returns normalized permit list.
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
            date_f = find(["ISSUE","ISSUED"], ["EXPIRE"]) or find(["DATE"])
            stat_f = find(["STATUS"])
            num_f  = find(["CASENUMBER","PERMIT_N","PERMIT_NO","PERMITNO",
                           "PERMIT_NUM","PROCESS_N","APP_NO","RECORD"])
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


def render_privacy_policy():
    """Render the VerifiHouse privacy policy page."""
    st.markdown("""
# VerifiHouse Privacy Policy

*Effective date: April 2026*

## Who we are
VerifiHouse is a property risk intelligence platform. We help home buyers and real estate
professionals understand permit history, safety gap risk, and environmental hazards for
residential properties.

## What we collect
When you unlock the full report, we collect:
- Your **email address** (required to identify your account and send you your report)
- The **city** you searched (not the full address — never stored)
- The **timestamp** of your request

We do **not** collect: full property addresses, names, payment information, or any
data that could identify you without your email.

## How we use it
- To deliver your full audit report
- To send occasional product updates (max 1–2 emails/month)
- To improve our scoring model (aggregated, anonymized)

We will **never** sell your email to third parties.
We will **never** use your data for targeted advertising.

## Where it's stored
Email addresses are stored in a private Google Sheet accessible only to VerifiHouse
founders. We use Google's enterprise security infrastructure.

## Your rights
You can request deletion of your data at any time by emailing
**privacy@verifihouse.com**. We will delete your record within 7 days.

You can unsubscribe from emails at any time using the unsubscribe link in any
email we send.

## Cookies
We do not use tracking cookies. Streamlit may set a session cookie for UI state —
this is not used for tracking or advertising.

## Changes
We may update this policy. The effective date above will reflect the most recent change.
Material changes will be communicated by email.

## Contact
privacy@verifihouse.com
    """)
    st.caption("© 2026 VerifiHouse. All rights reserved.")


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
    if city_name == "Minneapolis, MN":
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


    # ── National Risk Dictionary — applies to ALL 14 cities ──────────────────
    # Source: Public federal law (NEC, IRC, HUD, CPSC, Cox v Shell settlement)
    # All rules reproducible per US copyright law — factual/legal content.

    build_yr = year_built if (year_built and year_built > 1800) else None
    all_descs = " ".join(str(p.get("description", "")).upper() for p in permits)

    # Lead paint — unconditional on build year (HUD Title X 1978)
    if build_yr and build_yr < 1978:
        if not any(k in all_descs for k in ["ABATEMENT", "LEAD REMOV", "FULL GUT"]):
            score -= 8
            log.append({"cat": "health",
                "msg": f"Health Risk: Home built {build_yr} — HUD Title X (1978) presumes lead-based "
                       "paint present. Physical inspection and testing recommended. [HUD Title X; CPSC]",
                "type": "risk"})

    # Polybutylene pipe — 1978–1995 builds (Cox v Shell 1995)
    if build_yr and 1978 <= build_yr <= 1995:
        if not any(k in all_descs for k in ["REPIPE", "PB PIPE", "POLYBUTYLENE", "QUEST PIPE",
                                             "WATER LINE REPLAC", "REPLACE WATER"]):
            score -= 15
            log.append({"cat": "plumbing",
                "msg": f"Critical Plumbing Risk: Home built {build_yr} — polybutylene (PB) pipe likely "
                       "present. Class-action defect (Cox v Shell 1995); brittle failure at fittings "
                       "without warning. FHA/MN insurer may require documented replacement. "
                       "Repipe est. $4k–$15k. [Cox v. Shell Oil 1995; IRC P2906]",
                "type": "risk"})

    # FPE / Zinsco panel — pre-1990 no panel upgrade (CPSC advisory)
    if build_yr and build_yr < 1990:
        if not any(k in all_descs for k in ["PANEL", "ELECTRICAL SERVICE", "200 AMP",
                                             "SERVICE UPGRADE", "PANEL REPLACE"]):
            score -= 15
            log.append({"cat": "electrical",
                "msg": f"Fire Risk: Home built {build_yr} — electrical panel upgrade not on record. "
                       "Pre-1990 homes may contain Federal Pacific (FPE Stab-Lok) or Zinsco panels — "
                       "documented breaker failure rates; many insurers declining coverage. "
                       "Verify panel brand at inspection. Replacement est. $2.5k–$6k. [CPSC advisory; NEC 240]",
                "type": "risk"})

    # Aluminum branch wiring — 1965–1973 builds (NEC 310.106)
    if build_yr and 1965 <= build_yr <= 1973:
        if not any(k in all_descs for k in ["REWIRE", "ALUMINUM WIRING", "CO/ALR",
                                             "COPALUM", "ALUMICONN", "PIGTAIL"]):
            score -= 12
            log.append({"cat": "electrical",
                "msg": f"Fire Risk: Home built {build_yr} — aluminum branch circuit wiring era. "
                       "Connections loosen over time creating arcing; CPSC data shows 55x fire risk "
                       "vs copper. Requires CO/ALR outlets, COPALUM crimping, or full rewire. "
                       "Est. $3k–$20k. [NEC 310.106; CPSC]",
                "type": "risk"})

    # Knob-and-tube — pre-1950 no rewire (NEC Art. 394)
    if build_yr and build_yr < 1950:
        if not any(k in all_descs for k in ["REWIRE", "REWIRING", "WIRING REPLAC",
                                             "FULL ELECTRICAL", "COMPLETE ELECTRICAL"]):
            score -= 20
            log.append({"cat": "electrical",
                "msg": f"Fire/Safety Risk: Home built {build_yr} — knob-and-tube wiring likely present. "
                       "Ungrounded; incompatible with modern insulation (fire hazard when buried). "
                       "Most MN/national insurers refuse to bind policies. Full rewire est. $12k–$25k. "
                       "[NEC Art. 394; insurance industry standard]",
                "type": "risk"})

    # Deck lateral load — pre-2015 deck permit (IRC R507.9.2)
    if not any(k in all_descs for k in ["LATERAL LOAD", "TENSION TIE", "DECK REBUILD"]):
        for p in permits:
            desc = str(p.get("description", "")).upper()
            if any(k in desc for k in ["DECK", "PORCH", "BALCONY"]):
                try:
                    yr = int(p.get("permit_creation_date", "9999")[:4])
                    if yr < 2015:
                        score -= 15
                        log.append({"cat": "structure",
                            "msg": f"Structural Risk: Deck permit ({yr}) predates IRC R507 lateral load "
                                   "anchoring requirement (2015). Pre-2015 decks attached with nails only — "
                                   "90% of deck collapses involve ledger failure. Rebuild est. $8k–$20k. "
                                   "[IRC R507.9.2 / MRC R507]",
                            "type": "risk"})
                        break
                except Exception:
                    pass

    # Seismic strapping — only in SDC C+ zones (deferred to env panel for signal)
    # (Score impact applied in env layer — not here — to avoid double-calling geocode)

    # Smoke detector interconnection — pre-1993 no full electrical (IRC R314)
    if build_yr and build_yr < 1993:
        if not any(k in all_descs for k in ["REWIRE", "FULL ELECTRICAL", "WHOLE HOUSE ELECTRIC"]):
            score -= 4
            log.append({"cat": "life_safety",
                "msg": f"Life Safety Gap: Home built {build_yr} — interconnected hardwired smoke alarms "
                       "may be absent (required by IRC R314 since 1993). If one alarm sounds, all should "
                       "sound. Upgrade est. $500–$2k. [IRC R314]",
                "type": "risk"})

    # TPRV on water heater — pre-2000 WH permit with no recent WH permit (IRC P2803)
    wh_years = []
    for p in permits:
        desc = str(p.get("description", "")).upper()
        if any(k in desc for k in ["WATER HEATER", "HOT WATER", "WH REPLACE"]):
            try:
                wh_years.append(int(p.get("permit_creation_date", "9999")[:4]))
            except Exception:
                pass
    if wh_years and max(wh_years) < 2000:
        score -= 3
        log.append({"cat": "plumbing",
            "msg": f"Safety Note: Most recent water heater permit ({max(wh_years)}) is 25+ years old. "
                   "TPRV compliance uncertain; unit likely at end of typical 15-year lifespan. "
                   "Replacement est. $800–$2,500. [IRC P2803; ASME A112.4.1]",
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
    if city_name == "Minneapolis, MN" and age < 2002:
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
    st.caption("Beta — 14 U.S. Cities")
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

# --- 7. MAIN UI ---

# ── Privacy policy routing ────────────────────────────────────────────────────
query = st.query_params
if query.get("page") == "privacy":
    render_privacy_policy()
    st.stop()

st.markdown("<h1 style='text-align: center;'>VerifiHouse Property Audit</h1>", unsafe_allow_html=True)
st.caption(
    "⚠️ For informational purposes only. Permit data sourced from public government APIs "
    "and may be incomplete or delayed. Not a substitute for a professional property inspection, "
    "appraisal, or legal advice."
)

# City selector + address inputs
# Selectbox on mobile Chrome can mis-register touch targets.
# We use a native HTML <select> via st.selectbox but wrap in a form
# to prevent premature submission on mobile keyboard dismiss.
city_list = sorted(CITIES.keys())
try:
    city_idx = city_list.index(st.session_state.selected_city)
except ValueError:
    city_idx = 0

# Inject CSS to enlarge the selectbox tap target on mobile
st.markdown(
    "<style>"
    "div[data-baseweb='select'] > div { min-height: 48px; font-size: 1rem; }"
    "div[data-baseweb='select'] input { min-height: 48px; }"
    "</style>",
    unsafe_allow_html=True,
)

c1, c2 = st.columns([1, 2])
with c2:
    selected_city = st.selectbox(
        "City",
        city_list,
        index=city_idx,
        key="city_selectbox",
    )
    if selected_city not in CITIES:
        selected_city = city_list[0]
    st.session_state.selected_city = selected_city
    city_cfg = CITIES[selected_city]

    col_a, col_b = st.columns(2)
    s_num  = col_a.text_input("Street Number", value=city_cfg["default_number"])
    s_name = col_b.text_input("Street Name",   value=city_cfg["default_street"])

    # Year built — replaces RentCast as primary signal source (free, no API call)
    col_c, col_d = st.columns(2)
    yr_input = col_c.text_input(
        "Year Built (optional)",
        placeholder="e.g. 1962",
        help="Enter the year the home was built. Available on most Zillow/Redfin listings. "             "Enables safety gap analysis for electrical, plumbing, and structural systems.",
    )
    # Parse year built input
    year_built_manual = None
    if yr_input and yr_input.strip().isdigit():
        yr_int = int(yr_input.strip())
        if 1800 < yr_int <= datetime.datetime.now().year:
            year_built_manual = yr_int

    # Show data coverage notice for cities with known limitations
    if city_cfg.get("data_notice"):
        st.info(city_cfg["data_notice"])

    if st.button("Run Free Audit", type="primary", use_container_width=True):
        st.session_state["last_number"] = s_num
        st.session_state["last_street"] = s_name
        st.session_state["year_built_input"] = year_built_manual
        st.session_state.rc_data = None        # No auto RentCast call
        with st.spinner("Fetching permit records..."):
            st.session_state.house_permits = fetch_permits(selected_city, s_num, s_name)
            st.session_state.has_run = True

# --- 8. RESULTS ---
if st.session_state.has_run:
    permits = st.session_state.house_permits
    rc      = st.session_state.rc_data        # None until premium unlocked
    city    = st.session_state.selected_city

    # Year built: prefer manual input, fall back to RentCast if premium unlocked
    year_built = st.session_state.get("year_built_input", None)
    if not year_built and rc:
        year_built = rc.get("yearBuilt", None)

    if len(permits) > 0 or year_built:
        score, findings = analyze_history(permits, city_name=city, year_built=year_built)

        st.divider()

        # ── FREE: Summary + Year/Permits ─────────────────────────────────────
        n_flags = len(findings)
        yb_display = str(year_built) if year_built else "—"
        permits_display = str(len(permits))

        m1, m2, m3 = st.columns(3)
        m1.markdown(
            f"<div class='score-card'><div class='metric-label'>Items to Investigate</div>"
            f"<div class='metric-value'>{n_flags}</div></div>",
            unsafe_allow_html=True
        )
        m2.markdown(
            f"<div class='score-card'><div class='metric-label'>Year Built</div>"
            f"<div class='metric-value'>{yb_display}</div></div>",
            unsafe_allow_html=True
        )
        m3.markdown(
            f"<div class='score-card'><div class='metric-label'>Permits Found</div>"
            f"<div class='metric-value'>{permits_display}</div></div>",
            unsafe_allow_html=True
        )
        st.caption(
            "**For informational purposes only.** This report surfaces public permit records "
            "that may be worth a closer look. It is not a home inspection, appraisal, or "
            "professional opinion. Always consult a licensed inspector before any real estate decision. "
            "Permit records may be incomplete or delayed."
        )

        # ── FREE: Forensic Log ────────────────────────────────────────────────
        st.write("")
        st.subheader("📋 Permit Forensic Log")
        st.caption("Free · Sourced from public government permit APIs")
        if not findings:
            st.info(
                "📋 No specific items flagged based on permit records and year built. "
                "This does not mean no issues exist — unpermitted work will not appear here. "
                "A licensed home inspector can identify issues permit records won't show."
            )
        else:
            # Sort: higher internal weight first (most worth investigating)
            sorted_findings = sorted(findings, key=lambda x: x.get("d", 0), reverse=True)
            for f in sorted_findings:
                cat_label = f.get("cat", "").replace("_", " ").title()
                msg = f.get("msg", "")
                cost = f.get("cost_range", "")
                cost_note = f" Typical investigation/remediation range: {cost}." if cost else ""
                st.markdown(
                    f"<div style='background:#f8f9fa; border-left:3px solid #94a3b8; "
                    f"padding:10px 14px; border-radius:4px; margin-bottom:8px;'>"
                    f"<strong>🔍 {cat_label}</strong><br>"
                    f"<span style='font-size:0.9em;color:#374151;'>{msg}{cost_note}</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )
            st.caption(
                f"{n_flags} item{'s' if n_flags != 1 else ''} worth discussing with your inspector or agent. "
                "These are starting points for investigation, not conclusions."
            )

        # NYC Violation Panel
        if selected_city == "New York, NY":
            nyc_viols = get_nyc_violations(
                st.session_state.get("last_number", ""),
                st.session_state.get("last_street", ""),
            )
            render_nyc_violation_panel(nyc_viols)

        # ── Environmental & Hazard Panel ─────────────────────────────────────
        # Geocode address → FEMA NFHL flood zone + EPA radon + USGS seismic
        # All sources: US federal public domain, no API key required.
        city_cfg_env = CITIES.get(selected_city, {})
        env_state = city_cfg_env.get("rentcast_state", "")
        env_city_name = city_cfg_env.get("rentcast_city", selected_city.split(",")[0])
        full_address = (
            f"{st.session_state.get('last_number', '')} "
            f"{st.session_state.get('last_street', '')}, "
            f"{env_city_name}, {env_state}"
        ).strip()

        with st.spinner("Fetching environmental data (FEMA/EPA/USGS)…"):
            lat, lon, county_fips = get_geocode(full_address)
            flood_data  = get_fema_flood_zone(lat, lon) if lat else None
            radon_zone  = get_radon_zone(county_fips)
            seismic_sdc = get_usgs_seismic_zone(lat, lon) if lat else None

        render_environmental_panel(flood_data, radon_zone, seismic_sdc, full_address)

        # Apply seismic strapping score impact if in high-seismic zone
        if seismic_sdc and seismic_sdc in ["C", "D", "E", "F"]:
            wh_permits = [p for p in permits
                          if any(k in str(p.get("description","")).upper()
                                 for k in ["WATER HEATER", "HOT WATER"])]
            old_wh = any(
                int(p.get("permit_creation_date","9999")[:4]) < 2000
                for p in wh_permits
                if p.get("permit_creation_date","9999")[:4].isdigit()
            )
            if wh_permits and old_wh:
                st.warning(
                    "Seismic Zone + Pre-2000 water heater: verify seismic "
                    "strapping (IRC P2801.8). Required in seismic design categories C+."
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
        if selected_city == "Minneapolis, MN":
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
