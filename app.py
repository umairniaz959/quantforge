import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import datetime
import os
from dotenv import load_dotenv
from backtest_engine import (
    run_backtest_from_files,
    run_wfv_from_files,
    run_demo_backtest,
    run_generated_strategy
)
from ai_parser import parse_strategy_full
from db import init_db, register_user, login_user, save_backtest_result, get_user_results

# Load .env file (for local development)
load_dotenv()

# If running on Streamlit Cloud, override with secrets
if hasattr(st, 'secrets') and "GEMINI_API_KEY" in st.secrets:
    os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]

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
if "uploaded_data" not in st.session_state:
    st.session_state.uploaded_data = {}
if "demo_mode" not in st.session_state:
    st.session_state.demo_mode = False
if "uploaded_data_custom" not in st.session_state:
    st.session_state.uploaded_data_custom = {}

# Studio session state
if "studio_step" not in st.session_state:
    st.session_state.studio_step = "describe"
if "studio_description" not in st.session_state:
    st.session_state.studio_description = ""
if "studio_data" not in st.session_state:
    st.session_state.studio_data = None
if "studio_confirmed" not in st.session_state:
    st.session_state.studio_confirmed = False
if "studio_params" not in st.session_state:
    st.session_state.studio_params = {}

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

    page = st.sidebar.radio("Go to", ["Backtest", "My History", "Strategy Studio"])

    if page == "Backtest":
        show_backtest()
    elif page == "My History":
        show_history()
    else:
        show_strategy_studio()

# ============================================================
# BACKTEST PAGE (existing – unchanged)
# ============================================================
def show_backtest():
    # (keep your existing implementation – not shown here for brevity)
    st.write("Backtest page (unchanged)")

# ============================================================
# HISTORY PAGE (existing – unchanged)
# ============================================================
def show_history():
    # (keep your existing implementation – not shown here for brevity)
    st.write("History page (unchanged)")

# ============================================================
# STRATEGY STUDIO PAGE (new workflow)
# ============================================================
def show_strategy_studio():
    st.title("🧪 Strategy Studio – Build Your Own Strategy")
    st.markdown("Describe your strategy in plain English, and we'll code it for you.")

    # ---- STEP 1: Describe ----
    if st.session_state.studio_step == "describe":
        with st.form("describe_form"):
            description = st.text_area("Describe your strategy", height=150,
                                       placeholder="Example: Buy when 14-period RSI crosses above 30, sell when RSI crosses below 70. Stop loss 50 pips, take profit 100 pips. Risk 2% per trade.")
            submitted = st.form_submit_button("🚀 Code the Strategy")
        if submitted:
            if not description.strip():
                st.warning("Please enter a description.")
            else:
                with st.spinner("Gemini is coding your strategy..."):
                    try:
                        data = parse_strategy_full(description)
                        st.session_state.studio_description = description
                        st.session_state.studio_data = data
                        st.session_state.studio_params = data["params"].copy()
                        st.session_state.studio_step = "confirm"
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

    # ---- STEP 2: Confirm ----
    elif st.session_state.studio_step == "confirm":
        data = st.session_state.studio_data
        st.subheader("📋 Strategy Summary")
        st.write(data["summary"])
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Yes, that's correct"):
                st.session_state.studio_confirmed = True
                st.session_state.studio_step = "tune"
                st.rerun()
        with col2:
            if st.button("❌ No, refine it"):
                st.session_state.studio_step = "refine"
                st.rerun()

    # ---- STEP 3: Refine ----
    elif st.session_state.studio_step == "refine":
        st.subheader("✏️ Refine Your Strategy")
        st.write("The strategy summary above didn't match what you wanted. Please describe the changes:")
        with st.form("refine_form"):
            additional = st.text_area("What needs to be changed or added?", height=100)
            submitted = st.form_submit_button("Regenerate")
        if submitted:
            if not additional.strip():
                st.warning("Please describe the changes.")
            else:
                with st.spinner("Regenerating with your feedback..."):
                    full_desc = st.session_state.studio_description + " " + additional
                    try:
                        data = parse_strategy_full(full_desc)
                        st.session_state.studio_description = full_desc
                        st.session_state.studio_data = data
                        st.session_state.studio_params = data["params"].copy()
                        st.session_state.studio_step = "confirm"
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

    # ---- STEP 4: Tune & Backtest ----
    elif st.session_state.studio_step == "tune":
        st.success("✅ Strategy confirmed! Now you can adjust parameters and backtest.")

        params = st.session_state.studio_params

        # Build dynamic summary
        ind_list = [f"{i.get('name')} ({i.get('period')})" for i in params.get("indicators", [])]
        ind_str = ", ".join(ind_list) if ind_list else "price"
        summary = f"This strategy uses {ind_str}. " \
                  f"Stop loss: {params.get('stop_loss_pips', 20)} pips, " \
                  f"Take profit: {params.get('take_profit_pips', 40)} pips, " \
                  f"Risk: {params.get('risk_per_trade', 2.0)}% per trade."

        st.subheader("📊 Current Strategy (plain English)")
        st.write(summary)

        st.subheader("⚙️ Parameters (editable)")
        col1, col2 = st.columns(2)
        with col1:
            new_sl = st.number_input("Stop Loss (pips)", value=params.get("stop_loss_pips", 20), step=1)
            new_tp = st.number_input("Take Profit (pips)", value=params.get("take_profit_pips", 40), step=1)
        with col2:
            new_risk = st.number_input("Risk per Trade (%)", value=params.get("risk_per_trade", 2.0), step=0.1)
            # Show indicators (read-only for now)
            if params.get("indicators"):
                st.write("Indicators used:")
                for ind in params["indicators"]:
                    st.text(f"{ind.get('name')} (period {ind.get('period')})")

        # Update params in session state
        params["stop_loss_pips"] = new_sl
        params["take_profit_pips"] = new_tp
        params["risk_per_trade"] = new_risk
        st.session_state.studio_params = params

        # Upload data
        st.subheader("📂 Upload Data for Backtest")
        uploaded_files = st.file_uploader("Upload CSV files (BID and ASK)", type=["csv"], accept_multiple_files=True, key="studio_upload")
        if uploaded_files:
            st.session_state.uploaded_data_custom = {f.name: f for f in uploaded_files}
            st.success(f"{len(uploaded_files)} files uploaded.")

        if st.button("▶️ Run Backtest"):
            if "uploaded_data_custom" not in st.session_state or not st.session_state.uploaded_data_custom:
                st.error("Please upload data files.")
            else:
                with st.spinner("Running backtest..."):
                    try:
                        results, trades_df, monthly_df = run_generated_strategy(
                            st.session_state.uploaded_data_custom,
                            st.session_state.studio_data["code"],
                            params=params,
                            start_date=None,
                            end_date=None
                        )
                        if results is None:
                            st.warning("No trades generated. Try adjusting parameters.")
                        else:
                            st.success("Backtest complete!")
                            col1, col2, col3, col4 = st.columns(4)
                            col1.metric("Total Trades", results['total_trades'])
                            col2.metric("Win Rate", f"{results['win_rate']:.1f}%")
                            col3.metric("Profit Factor", f"{results['profit_factor']:.2f}")
                            col4.metric("Avg Monthly P&L (USD)", f"${results['avg_monthly_usd']:.2f}")

                            if trades_df is not None and not trades_df.empty:
                                trades_df['cumulative'] = trades_df['pnl'].cumsum()
                                fig_equity = go.Figure()
                                fig_equity.add_trace(go.Scatter(x=trades_df['exit_bar'], y=trades_df['cumulative'],
                                                                 mode='lines', name='Equity'))
                                st.plotly_chart(fig_equity, use_container_width=True)
                                st.subheader("Trade Log")
                                st.dataframe(trades_df[['entry', 'exit', 'type', 'pnl']])
                                csv_trades = trades_df.to_csv(index=False).encode('utf-8')
                                st.download_button("Download Trades (CSV)", data=csv_trades, file_name="studio_trades.csv", mime="text/csv")
                    except Exception as e:
                        st.error(f"Error: {e}")

# ============================================================
# ENTRY POINT
# ============================================================
if not st.session_state.authenticated:
    login_signup_page()
else:
    main_app()
