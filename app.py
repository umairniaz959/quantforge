import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
from backtest_engine import run_backtest_from_files, run_wfv_from_files, run_demo_backtest

st.set_page_config(page_title="QuantForge – Backtest Engine", layout="wide")

# ============================================================
# SESSION STATE INITIALIZATION
# ============================================================
if "risk_cents" not in st.session_state:
    st.session_state.risk_cents = 70
if "withdrawal_pct_first" not in st.session_state:
    st.session_state.withdrawal_pct_first = 70
if "withdrawal_pct_rest" not in st.session_state:
    st.session_state.withdrawal_pct_rest = 100
if "start_date" not in st.session_state:
    st.session_state.start_date = pd.to_datetime("2023-01-01")
if "end_date" not in st.session_state:
    st.session_state.end_date = pd.to_datetime("2025-01-01")

# ============================================================
# HEADER
# ============================================================
st.title("🚀 QuantForge – Backtest Engine")
st.markdown("Upload your CSV data, define parameters, and get AI‑powered analysis.")

# --------------------------------------------------------------
# SIDEBAR – PRESETS
# --------------------------------------------------------------
st.sidebar.header("⚡ Presets")
if st.sidebar.button("🎯 Load Demo Preset (MA Crossover)"):
    st.session_state.risk_cents = 70
    st.session_state.withdrawal_pct_first = 70
    st.session_state.withdrawal_pct_rest = 100
    st.session_state.start_date = pd.to_datetime("2023-01-01")
    st.session_state.end_date = pd.to_datetime("2025-01-01")
    st.session_state.demo_mode = True
    st.rerun()

st.sidebar.markdown("---")

# --------------------------------------------------------------
# SIDEBAR – COMMON PARAMETERS
# --------------------------------------------------------------
st.sidebar.header("Common Parameters")
risk_cents = st.sidebar.number_input(
    "Risk per Trade (cents)",
    min_value=1,
    value=st.session_state.risk_cents,
    key="risk_cents"
)
withdrawal_pct_first = st.sidebar.slider(
    "Withdrawal % – First Year",
    0, 100,
    st.session_state.withdrawal_pct_first,
    key="withdrawal_pct_first"
)
withdrawal_pct_rest = st.sidebar.slider(
    "Withdrawal % – Rest",
    0, 100,
    st.session_state.withdrawal_pct_rest,
    key="withdrawal_pct_rest"
)

st.sidebar.markdown("---")

# --------------------------------------------------------------
# SIDEBAR – FILE UPLOAD
# --------------------------------------------------------------
st.sidebar.subheader("Upload Data")
uploaded_files = st.sidebar.file_uploader(
    "Upload your CSV files (BID and ASK)",
    type=["csv"],
    accept_multiple_files=True,
)

if not uploaded_files:
    st.info("👈 Please upload your CSV files (BID and ASK) in the sidebar to get started.")
    st.stop()

if "uploaded_data" not in st.session_state:
    st.session_state.uploaded_data = {}

for file in uploaded_files:
    if file.name not in st.session_state.uploaded_data:
        st.session_state.uploaded_data[file.name] = file

st.sidebar.success(f"{len(st.session_state.uploaded_data)} files uploaded.")

st.sidebar.markdown("---")

# --------------------------------------------------------------
# SIDEBAR – EA EXPORT
# --------------------------------------------------------------
st.sidebar.subheader("EA Export")
ea_magic = st.sidebar.number_input("Magic Number", value=123457, step=1)
if st.sidebar.button("Download EA (MQL4)"):
    ea_code = "// Your full EA code here (truncated for brevity)"
    st.download_button(
        label="Download EA (MQL4)",
        data=ea_code,
        file_name=f"EA_Risk{risk_cents}_Magic{ea_magic}.mq4",
        mime="text/plain",
    )

st.sidebar.markdown("---")

# --------------------------------------------------------------
# SIDEBAR – SINGLE BACKTEST (with demo mode toggle)
# --------------------------------------------------------------
st.sidebar.subheader("Single Backtest")
start_date = st.sidebar.date_input(
    "Start Date",
    value=st.session_state.start_date,
    key="start_date"
)
end_date = st.sidebar.date_input(
    "End Date",
    value=st.session_state.end_date,
    key="end_date"
)

if st.sidebar.button("Run Single Backtest"):
    if len(st.session_state.uploaded_data) == 0:
        st.error("Please upload CSV files first.")
    else:
        with st.spinner("Running backtest..."):
            try:
                # Check if we are in demo mode
                if st.session_state.get("demo_mode", False):
                    results, trades_df, monthly_df = run_demo_backtest(
                        st.session_state.uploaded_data,
                        risk_cents=risk_cents,
                        start_date=start_date.strftime("%Y-%m-%d") if start_date else None,
                        end_date=end_date.strftime("%Y-%m-%d") if end_date else None,
                    )
                    st.info("ℹ️ This is a DEMO strategy (Moving Average Crossover) – not the validated edge.")
                else:
                    results, trades_df, monthly_df = run_backtest_from_files(
                        st.session_state.uploaded_data,
                        risk_cents=risk_cents,
                        withdrawal_pct_first=withdrawal_pct_first,
                        withdrawal_pct_rest=withdrawal_pct_rest,
                        start_date=start_date.strftime("%Y-%m-%d") if start_date else None,
                        end_date=end_date.strftime("%Y-%m-%d") if end_date else None,
                    )

                if results is None:
                    st.warning("No trades in the selected period.")
                else:
                    st.success("Backtest complete!")
                    # Display results (same as before)

            except Exception as e:
                st.error(f"Error: {e}")
                st.stop()

st.sidebar.markdown("---")

# --------------------------------------------------------------
# SIDEBAR – WFV (only runs the real strategy, not demo)
# --------------------------------------------------------------
st.sidebar.subheader("Walk-Forward Validation (WFV)")
st.sidebar.caption("Runs the validated strategy on 4 blocks.")

if st.sidebar.button("Run WFV"):
    if len(st.session_state.uploaded_data) == 0:
        st.error("Please upload CSV files first.")
    else:
        with st.spinner("Running WFV across 4 blocks..."):
            try:
                block_results, summary = run_wfv_from_files(
                    st.session_state.uploaded_data,
                    risk_cents=risk_cents,
                    withdrawal_pct_first=withdrawal_pct_first,
                    withdrawal_pct_rest=withdrawal_pct_rest,
                )
                if not block_results or all(b['Trades'] == 0 for b in block_results):
                    st.warning("No trades in any block.")
                else:
                    st.success("WFV complete!")
                    st.subheader("Block Performance")
                    df_blocks = pd.DataFrame(block_results)
                    st.dataframe(df_blocks)

                    st.subheader("WFV Summary")
                    st.dataframe(pd.DataFrame([summary]).T.rename(columns={0: "Value"}))

                    csv_blocks = df_blocks.to_csv(index=False).encode('utf-8')
                    st.download_button("Download WFV Results (CSV)", csv_blocks, "wfv_results.csv", "text/csv")
            except Exception as e:
                st.error(f"Error running WFV: {e}")

st.sidebar.markdown("---")
st.sidebar.caption("Powered by your validated backtest engine.")
