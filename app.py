import streamlit as st
import requests

# --- INITIALIZATION ---
# This line grabs the key securely from your .streamlit/secrets.toml file
# You do NOT need to paste the key here anymore.
try:
    api_key = st.secrets["rentcast_key"]
except FileNotFoundError:
    st.error("Secrets file not found. Please create .streamlit/secrets.toml")
    st.stop()
except KeyError:
    st.error("Key 'rentcast_key' not found in secrets.toml")
    st.stop()

# --- PAGE SETUP ---
st.set_page_config(page_title="VerifiHouse", layout="wide")

# --- SIDEBAR ---
with st.sidebar:
    st.title("🛡️ VeriHouse")
    st.markdown("**The Standard for Home Verification.**")
    st.divider()
    st.success("System Online 🟢")
    
    st.divider()
    st.caption("Coverage: San Francisco, CA")
    st.caption("v1.2 Beta")

# --- MAIN HERO SECTION ---
st.markdown("<h1 style='text-align: center;'>VerifiHouse Property Audit</h1>", unsafe_allow_html=True)

# --- INPUT SECTION ---
col1, col2 = st.columns(2)
with col1:
    street_number = st.text_input("Street Number", placeholder="301")
with col2:
    street_name = st.text_input("Street Name", placeholder="Mission")

# --- THE BUTTON LOGIC ---
if st.button("Generate Full Audit", type="primary"):
    if not street_number or not street_name:
        st.warning("Please enter both a street number and name.")
    else:
        with st.spinner("Fetching data from RentCast..."):
            # RentCast needs the address formatted correctly
            full_address = f"{street_number} {street_name}, San Francisco, CA"
            
            # RentCast API Setup
            url = "https://api.rentcast.io/v1/properties"
            params = {"address": full_address}
            headers = {
                "accept": "application/json",
                "X-Api-Key": api_key
            }

            try:
                # This is the actual call to RentCast
                response = requests.get(url, headers=headers, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    st.success(f"Audit Complete for {full_address}!")
                    
                    # This shows the actual house data (Year Built, Square Feet, etc
