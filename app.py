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
    st.title("🚀 QuantForge – Backtest Engine")
    st.markdown("Upload your CSV data, define parameters, and get AI‑powered analysis.")

    if st.session_state.get("demo_mode", False):
        st.info("📂 **Demo Mode Active** – this uses a simple MA crossover strategy for illustration only.")

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
        reset_balance_monthly = st.checkbox("Reset balance to starting capital each month", value=True, key="reset_balance")

        st.markdown("---")

        if st.session_state.get("demo_mode", False):
            st.subheader("Demo Strategy Parameters")
            demo_sl = st.number_input("Stop Loss (pips)", min_value=1, value=20, step=1, key="demo_sl")
            demo_tp = st.number_input("Take Profit (pips)", min_value=1, value=40, step=1, key="demo_tp")

        st.markdown("---")

        st.subheader("Upload Data")
        uploaded_files = st.file_uploader("Upload your CSV files (BID and ASK)", type=["csv"], accept_multiple_files=True)
        if uploaded_files:
            st.session_state.uploaded_data = {file.name: file for file in uploaded_files}
            st.success(f"{len(uploaded_files)} files uploaded.")

        if st.button("Clear Files"):
            st.session_state.uploaded_data = {}
            st.rerun()

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
                        if st.session_state.get("demo_mode", False):
                            results, trades_df, monthly_df = run_demo_backtest(
                                st.session_state.uploaded_data,
                                risk_cents=risk_cents,
                                start_date=start_date.strftime("%Y-%m-%d") if start_date else None,
                                end_date=end_date.strftime("%Y-%m-%d") if end_date else None,
                                demo_sl=demo_sl,
                                demo_tp=demo_tp,
                                reset_balance_monthly=reset_balance_monthly
                            )
                            st.info("ℹ️ Demo backtest complete (simple MA crossover).")
                        else:
                            results, trades_df, monthly_df = run_backtest_from_files(
                                st.session_state.uploaded_data,
                                risk_cents=risk_cents,
                                withdrawal_pct_first=withdrawal_pct_first,
                                withdrawal_pct_rest=withdrawal_pct_rest,
                                start_date=start_date.strftime("%Y-%m-%d") if start_date else None,
                                end_date=end_date.strftime("%Y-%m-%d") if end_date else None,
                                reset_balance_monthly=reset_balance_monthly
                            )

                        if results is None:
                            st.warning("No trades in the selected period.")
                        else:
                            st.success("Backtest complete!")
                            results['risk_cents'] = risk_cents

                            col1, col2, col3, col4 = st.columns(4)
                            col1.metric("Total Trades", results['total_trades'])
                            col2.metric("Win Rate", f"{results['win_rate']:.1f}%")
                            col3.metric("Profit Factor", f"{results['profit_factor']:.2f}")
                            col4.metric("Avg Monthly P&L (USD)", f"${results['avg_monthly_usd']:.2f}")

                            if trades_df is not None and not trades_df.empty:
                                trades_df['cumulative'] = trades_df['pnl_cents'].cumsum()
                                fig_equity = go.Figure()
                                fig_equity.add_trace(go.Scatter(x=trades_df['exit_bar'], y=trades_df['cumulative'],
                                                                 mode='lines', name='Equity (cents)'))
                                fig_equity.update_layout(title='Equity Curve', xaxis_title='Bar Index', yaxis_title='Cumulative P&L (cents)')
                                st.plotly_chart(fig_equity, use_container_width=True)

                            st.subheader("Trade Log")
                            st.dataframe(trades_df[['pair', 'type', 'entry', 'exit', 'pnl_cents', 'lot', 'reason']])

                            if monthly_df:
                                st.subheader("Monthly Performance")
                                monthly_df_display = pd.DataFrame(monthly_df)
                                st.dataframe(monthly_df_display)
                                fig_monthly = go.Figure()
                                fig_monthly.add_trace(go.Bar(x=monthly_df_display['Month'], y=monthly_df_display['Monthly P&L (cents)'],
                                                             name='Monthly P&L'))
                                fig_monthly.update_layout(title='Monthly P&L', xaxis_title='Month', yaxis_title='P&L (cents)')
                                st.plotly_chart(fig_monthly, use_container_width=True)

                            csv_trades = trades_df.to_csv(index=False).encode('utf-8')
                            st.download_button("Download Trades (CSV)", data=csv_trades, file_name="trades.csv", mime="text/csv")
                            if monthly_df:
                                csv_monthly = pd.DataFrame(monthly_df).to_csv(index=False).encode('utf-8')
                                st.download_button("Download Monthly (CSV)", data=csv_monthly, file_name="monthly.csv", mime="text/csv")

                            save_success = save_backtest_result(
                                st.session_state.user_id,
                                results,
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
        block_years = st.number_input("Block size (years)", min_value=1, value=5, step=1, key="block_years")
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
                            block_years=block_years,
                            reset_balance_monthly=reset_balance_monthly
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

# ============================================================
# HISTORY PAGE
# ============================================================
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
# STRATEGY STUDIO PAGE
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

        # --- Back button to go to confirmation without changes ---
        if st.button("← Back to summary"):
            st.session_state.studio_step = "confirm"
            st.rerun()

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
