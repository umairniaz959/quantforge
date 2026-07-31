import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import streamlit_authenticator as stauth
from backtest_engine import run_backtest_from_files, run_wfv_from_files, run_demo_backtest
from db import init_db, register_user, login_user, save_backtest_result, get_user_results, get_session

# --- Initialize database ---
init_db()

st.set_page_config(page_title="QuantForge – Backtest Engine", layout="wide")

# ============================================================
# SESSION STATE INITIALIZATION
# ============================================================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "username" not in st.session_state:
    st.session_state.username = None
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "page" not in st.session_state:
    st.session_state.page = "main"

# ============================================================
# LOGIN / SIGNUP PAGE
# ============================================================
def login_signup_page():
    st.title("🔐 QuantForge – Login / Signup")
    tab1, tab2 = st.tabs(["Login", "Signup"])

    with tab1:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
            if submitted:
                if not username or not password:
                    st.error("Please fill in all fields.")
                else:
                    success, user_id = login_user(username, password)
                    if success:
                        st.session_state.authenticated = True
                        st.session_state.username = username
                        st.session_state.user_id = user_id
                        st.rerun()
                    else:
                        st.error("Invalid username or password.")

    with tab2:
        with st.form("signup_form"):
            new_username = st.text_input("Choose a username")
            new_email = st.text_input("Email")
            new_password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign Up")
            if submitted:
                if not new_username or not new_email or not new_password:
                    st.error("Please fill in all fields.")
                else:
                    success, msg = register_user(new_username, new_email, new_password)
                    if success:
                        st.success("Account created! Please login.")
                    else:
                        st.error(msg)

# ============================================================
# MAIN APP (requires authentication)
# ============================================================
def main_app():
    st.sidebar.header(f"Welcome, {st.session_state.username}!")
    if st.sidebar.button("Logout"):
        st.session_state.authenticated = False
        st.session_state.username = None
        st.session_state.user_id = None
        st.rerun()

    # Navigation
    page = st.sidebar.radio("Go to", ["Backtest", "My History"])

    if page == "Backtest":
        show_backtest()
    else:
        show_history()

def show_backtest():
    # --- Your existing backtest interface (with demo mode, parameters, etc.) ---
    # I'll include a condensed version; you can copy your full backtest code here.
    st.title("🚀 QuantForge – Backtest Engine")
    st.markdown("Upload your CSV data, define parameters, and get AI‑powered analysis.")

    # --- Demo mode banner (same as before) ---
    if st.session_state.get("demo_mode", False):
        st.info("📂 **Demo Mode Active** – please upload your CSV files and set your parameters.")

    # --- Sidebar parameters (same as before) ---
    with st.sidebar:
        st.header("⚡ Presets")
        if st.button("🎯 Load Demo Preset (MA Crossover)"):
            st.session_state.risk_cents = 70
            st.session_state.withdrawal_pct_first = 70
            st.session_state.withdrawal_pct_rest = 100
            st.session_state.start_date = pd.to_datetime("2023-01-01")
            st.session_state.end_date = pd.to_datetime("2025-01-01")
            st.session_state.demo_mode = True
            st.rerun()

        st.markdown("---")

        if st.session_state.get("demo_mode", False):
            st.warning("🧪 Demo Mode: MA Crossover")
        else:
            st.success("🔒 Validated Strategy")

        st.markdown("---")

        st.header("Common Parameters")
        risk_cents = st.number_input("Risk per Trade (cents)", min_value=1, value=70, key="risk_cents")
        withdrawal_pct_first = st.slider("Withdrawal % – First Year", 0, 100, 70, key="withdrawal_pct_first")
        withdrawal_pct_rest = st.slider("Withdrawal % – Rest", 0, 100, 100, key="withdrawal_pct_rest")

        st.markdown("---")

        if st.session_state.get("demo_mode", False):
            st.subheader("Demo Strategy Parameters")
            demo_sl = st.number_input("Stop Loss (pips)", min_value=1, value=20, step=1, key="demo_sl")
            demo_tp = st.number_input("Take Profit (pips)", min_value=1, value=40, step=1, key="demo_tp")

        st.markdown("---")

        st.subheader("Upload Data")
        uploaded_files = st.file_uploader("Upload your CSV files (BID and ASK)", type=["csv"], accept_multiple_files=True)
        if not uploaded_files:
            st.info("👈 Please upload your CSV files.")
            st.stop()

        # Store uploaded files in session state
        if "uploaded_data" not in st.session_state:
            st.session_state.uploaded_data = {}
        for file in uploaded_files:
            if file.name not in st.session_state.uploaded_data:
                st.session_state.uploaded_data[file.name] = file
        st.success(f"{len(st.session_state.uploaded_data)} files uploaded.")

        st.markdown("---")

        st.subheader("EA Export")
        ea_magic = st.number_input("Magic Number", value=123457, step=1)
        if st.button("Download EA (MQL4)"):
            ea_code = "// Your EA code here (use the full code from your validated EA)"
            st.download_button("Download EA (MQL4)", data=ea_code, file_name=f"EA_Risk{risk_cents}_Magic{ea_magic}.mq4", mime="text/plain")

        st.markdown("---")

        st.subheader("Single Backtest")
        start_date = st.date_input("Start Date", value=pd.to_datetime("2023-01-01"), key="start_date")
        end_date = st.date_input("End Date", value=pd.to_datetime("2025-01-01"), key="end_date")

        if st.button("Run Single Backtest"):
            if len(st.session_state.uploaded_data) == 0:
                st.error("Please upload CSV files first.")
            else:
                with st.spinner("Running backtest..."):
                    try:
                        # Determine which strategy to run
                        if st.session_state.get("demo_mode", False):
                            results, trades_df, monthly_df = run_demo_backtest(
                                st.session_state.uploaded_data,
                                risk_cents=risk_cents,
                                start_date=start_date.strftime("%Y-%m-%d") if start_date else None,
                                end_date=end_date.strftime("%Y-%m-%d") if end_date else None,
                                demo_sl=demo_sl,
                                demo_tp=demo_tp
                            )
                            st.info("ℹ️ Demo backtest complete.")
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
                            # Display results (metrics, equity curve, etc.)
                            # (I'll include the display code from your previous version)
                            col1, col2, col3, col4 = st.columns(4)
                            col1.metric("Total Trades", results['total_trades'])
                            col2.metric("Win Rate", f"{results['win_rate']:.1f}%")
                            col3.metric("Profit Factor", f"{results['profit_factor']:.2f}")
                            col4.metric("Avg Monthly P&L (USD)", f"${results['avg_monthly_usd']:.2f}")

                            # ... (equity curve, tables, download buttons)
                            # (You can copy the display code from your previous app.py)

                            # Save result to database
                            save_success = save_backtest_result(
                                st.session_state.user_id,
                                {
                                    'risk_cents': risk_cents,
                                    'total_trades': results['total_trades'],
                                    'win_rate': results['win_rate'],
                                    'profit_factor': results['profit_factor'],
                                    'total_withdrawn_usd': results['total_withdrawn_usd'],
                                    'avg_monthly_usd': results['avg_monthly_usd'],
                                    'max_dd_cents': results['max_dd_cents'],
                                    'max_dd_percent': results['max_dd_percent']
                                },
                                trades_df,
                                monthly_df,
                                start_date.strftime("%Y-%m-%d"),
                                end_date.strftime("%Y-%m-%d")
                            )
                            if save_success:
                                st.success("Result saved to your history.")
                            else:
                                st.warning("Could not save result.")
                    except Exception as e:
                        st.error(f"Error: {e}")

        st.markdown("---")

        st.subheader("Walk-Forward Validation (WFV)")
        if st.button("Run WFV"):
            if len(st.session_state.uploaded_data) == 0:
                st.error("Please upload CSV files first.")
            else:
                with st.spinner("Running WFV..."):
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
                            st.dataframe(pd.DataFrame(block_results))
                            st.subheader("WFV Summary")
                            st.dataframe(pd.DataFrame([summary]).T.rename(columns={0: "Value"}))
                            csv_blocks = pd.DataFrame(block_results).to_csv(index=False).encode('utf-8')
                            st.download_button("Download WFV Results (CSV)", csv_blocks, "wfv_results.csv", "text/csv")
                    except Exception as e:
                        st.error(f"Error: {e}")

def show_history():
    st.title("📜 My Backtest History")
    results = get_user_results(st.session_state.user_id)
    if not results:
        st.info("No backtest results saved yet. Run a backtest to save it.")
    else:
        for r in results:
            with st.expander(f"{r.start_date} to {r.end_date} (Risk: {r.risk_cents}c) – Trades: {r.total_trades}"):
                st.write(f"**Win Rate:** {r.win_rate:.1f}%")
                st.write(f"**Profit Factor:** {r.profit_factor:.2f}")
                st.write(f"**Total Withdrawn:** ${r.total_withdrawn_usd:.2f}")
                st.write(f"**Avg Monthly:** ${r.avg_monthly_usd:.2f}")
                st.write(f"**Max DD:** ${r.max_dd_cents/100:.2f} ({r.max_dd_percent:.2f}%)")
                st.caption(f"Saved on: {r.created_at.strftime('%Y-%m-%d %H:%M')}")

# ============================================================
# ENTRY POINT
# ============================================================
if not st.session_state.authenticated:
    login_signup_page()
else:
    main_app()
