import streamlit as st
import requests

# --- INITIALIZATION ---
# Paste your RentCast API key between the quotes below
api_key = "PASTE_YOUR_RENTCAST_KEY_HERE"

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
    if api_key == "PASTE_YOUR_RENTCAST_KEY_HERE":
        st.error("Please update line 6 with your actual RentCast API key.")
    elif not street_number or not street_name:
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
                    
                    # This shows the actual house data (Year Built, Square Feet, etc.)
                    if data:
                        property_info = data[0] # RentCast returns a list
                        st.json(property_info)
                        
                        # Update your dashboard metrics with real data
                        m1, m2, m3 = st.columns(3)
                        m1.metric("Year Built", property_info.get("yearBuilt", "N/A"))
                        m2.metric("Sq Ft", property_info.get("squareFootage", "N/A"))
                        m3.metric("Property Type", property_info.get("propertyType", "N/A"))
                    else:
                        st.warning("No data found for this specific address.")
                
                elif response.status_code == 401:
                    st.error("RentCast Error: Invalid API Key. Please check your key on line 6.")
                else:
                    st.error(f"RentCast Error: {response.status_code} - {response.text}")

            except Exception as e:
                st.error(f"Connection Error: {e}")
