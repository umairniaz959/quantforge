import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
from backtest_engine import run_backtest_from_files, run_wfv_from_files

st.set_page_config(page_title="QuantForge – Backtest Engine", layout="wide")
st.title("🚀 QuantForge – Backtest Engine")
st.markdown("Upload your CSV data, define parameters, and get AI‑powered analysis.")

# ... (sidebar code same as before) ...

if st.sidebar.button("Run Single Backtest"):
    if len(st.session_state.uploaded_data) == 0:
        st.error("Please upload CSV files first.")
    else:
        with st.spinner("Running backtest..."):
            try:
                results, trades_df, monthly_df = run_backtest_from_files(
                    st.session_state.uploaded_data,
                    risk_cents=risk_cents,
                    withdrawal_pct_first=withdrawal_pct_first,
                    withdrawal_pct_rest=withdrawal_pct_rest,
                    start_date=start_date.strftime("%Y-%m-%d") if start_date else None,
                    end_date=end_date.strftime("%Y-%m-%d") if end_date else None,
                )
                # ... (rest of success handling) ...
            except Exception as e:
                st.error(f"Error: {e}")
                st.stop()
