import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="VeriHouse Live Feed", page_icon="📡", layout="wide")
st.title("📡 VeriHouse: City Pulse")
st.markdown("Diagnosing the connection by fetching the **last 10 permits** from the entire city.")

if st.button("🔴 Get Live City Data", type="primary"):
    
    # 1. Use the Active Database
    url = "https://data.sfgov.org/resource/i98e-djp9.json"
    
    # 2. NO SEARCH FILTER. Just "Give me the newest data."
    params = {
        '$limit': 10,
        '$order': 'permit_creation_date DESC'
    }
    
    try:
        with st.spinner("Ping SF Gov Server..."):
            r = requests.get(url, params=params)
            data = r.json()
            
        if isinstance(data, list) and len(data) > 0:
            st.success(f"✅ SUCCESS! Downloaded {len(data)} recent permits.")
            st.info("The app works. Here is exactly how the City formats their addresses:")
            
            # 3. SHOW THE "SECRET" FORMAT
            # We display a clean table of just the address parts
            df = pd.DataFrame(data)
            
            # Check which columns exist to avoid errors
            cols_to_show = ['street_number', 'street_name', 'street_suffix', 'permit_creation_date', 'description']
            # Only pick columns that actually exist in the data
            actual_cols = [c for c in cols_to_show if c in df.columns]
            
            st.table(df[actual_cols].head(10))
            
            st.write("---")
            st.write("👇 **Look at the 'street_name' and 'street_suffix' columns above.**")
            st.caption("Do they use 'MISSION' and 'ST'? Or 'MISSION' and 'STREET'? Use that exact spelling in your next search.")
            
        else:
            st.error("⚠️ Connection successful, but the list was empty.")
            st.json(data)

    except Exception as e:
        st.error(f"Connection Error: {e}")
