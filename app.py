import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
from backtest_engine import run_backtest_from_files, run_wfv_from_files

st.set_page_config(page_title="QuantForge – Backtest Engine", layout="wide")
st.title("🚀 QuantForge – Backtest Engine")
st.markdown("Upload your CSV data, define parameters, and get AI‑powered analysis.")

# --------------------------------------------------------------
# Sidebar – common parameters
# --------------------------------------------------------------
st.sidebar.header("Common Parameters")
risk_cents = st.sidebar.number_input("Risk per Trade (cents)", min_value=1, value=70)
withdrawal_pct_first = st.sidebar.slider("Withdrawal % – First Year", 0, 100, 70)
withdrawal_pct_rest = st.sidebar.slider("Withdrawal % – Rest", 0, 100, 100)

st.sidebar.markdown("---")

# --------------------------------------------------------------
# File Upload
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

# --------------------------------------------------------------
# EA Export
# --------------------------------------------------------------
st.sidebar.subheader("EA Export")
ea_magic = st.sidebar.number_input("Magic Number", value=123457, step=1)
if st.sidebar.button("Download EA (MQL4)"):
    # (EA code – same as before, truncated for brevity)
    ea_code = f"""//+------------------------------------------------------------------+
//|                                   Proposal3_1_ZoneLimit_Overlap  |
//|  Faithful replica of the Python "PROPOSAL 3.1" file:             |
//|  - Tolerance retest (0.5 pip)                                    |
//|  - 3-bar exit confirmation                                       |
//|  - LIMIT order placed AT THE ZONE BOUNDARY (not at exit-bar close)|
//|  - 1-bar expiry if unfilled                                      |
//|  - FIXED flat risk per trade (NOT % of balance - matches the     |
//|    Python file's RISK_CENTS constant exactly, no compounding)    |
//|  - Static/bugged pip value formula (matches Python's leverage    |
//|    model exactly)                                                |
//|  - Breakeven (1.5R) + trailing stop (activate 3.0R, trail 1.0R)  |
//|  - 50-bar forced timeout close                                   |
//|  - Overlap allowed (multiple simultaneous patterns/trades)       |
//|  - 5‑pip SL filter REMOVED (now matches the original backtest)   |
//+------------------------------------------------------------------+
#property copyright "Your Name"
#property link      ""
#property version   "3.11"
#property strict

//+------------------------------------------------------------------+
//| Input parameters                                                 |
//+------------------------------------------------------------------+
extern double RiskMoney        = {risk_cents}.0;
extern int    Slippage         = 3;
extern int    MagicNumber      = {ea_magic};
extern int    MaxBarsOpen      = 50;
extern int    LimitExpiryBars  = 1;
extern int    Debug            = 1;

extern double BE_Multiplier    = 1.5;
extern double Trail_Activate   = 3.0;
extern double Trail_Dist       = 1.0;

// ... (rest of EA code – use the full version from earlier messages)
"""
    st.download_button(
        label="Download EA (MQL4)",
        data=ea_code,
        file_name=f"EA_Risk{risk_cents}_Magic{ea_magic}.mq4",
        mime="text/plain",
    )

st.sidebar.markdown("---")

# --------------------------------------------------------------
# SINGLE BACKTEST
# --------------------------------------------------------------
st.sidebar.subheader("Single Backtest")
start_date = st.sidebar.date_input("Start Date", value=pd.to_datetime("2023-01-01"))
end_date = st.sidebar.date_input("End Date", value=pd.to_datetime("2025-01-01"))

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
                if results is None:
                    st.warning("No trades in the selected period.")
                else:
                    st.success("Backtest complete!")
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Total Trades", results['total_trades'])
                    col2.metric("Win Rate", f"{results['win_rate']:.1f}%")
                    col3.metric("Profit Factor", f"{results['profit_factor']:.2f}")
                    col4.metric("Avg Monthly P&L (USD)", f"${results['avg_monthly_usd']:.2f}")

                    # --------------------------------------------------
                    # EQUITY CURVE AND DRAWDOWN (with debugging)
                    # --------------------------------------------------
                    if monthly_df:
                        df_month = pd.DataFrame(monthly_df)
                        # Convert to USD (if not already)
                        df_month['Cumulative P&L (USD)'] = (df_month['Monthly P&L (cents)'] / 100.0).cumsum()
                        df_month['Drawdown (USD)'] = df_month['Cumulative P&L (USD)'].cummax() - df_month['Cumulative P&L (USD)']

                        # Display the actual drawdown values for debugging
                        with st.expander("Debug: Monthly Drawdown Values (USD)"):
                            st.dataframe(df_month[['Month', 'Drawdown (USD)']])

                        max_dd = df_month['Drawdown (USD)'].max()
                        st.caption(f"Max Drawdown from chart data: **${max_dd:.2f}**")

                        fig = make_subplots(
                            rows=2, cols=1,
                            shared_xaxes=True,
                            vertical_spacing=0.1,
                            subplot_titles=("Equity Curve (USD)", "Drawdown (USD)")
                        )

                        # Equity curve
                        fig.add_trace(
                            go.Scatter(
                                x=df_month['Month'],
                                y=df_month['Cumulative P&L (USD)'],
                                mode='lines+markers',
                                name='Equity Curve',
                                line=dict(color='green', width=2),
                            ),
                            row=1, col=1
                        )

                        # Drawdown bars
                        fig.add_trace(
                            go.Bar(
                                x=df_month['Month'],
                                y=df_month['Drawdown (USD)'],
                                name='Drawdown',
                                marker_color='red',
                            ),
                            row=2, col=1
                        )

                        # Fix y‑axis: start at 0, go slightly above max
                        if max_dd > 0:
                            fig.update_yaxes(
                                row=2, col=1,
                                range=[0, max_dd * 1.1],
                                title_text="Drawdown (USD)",
                                tickprefix="$",
                                tickformat=".2f"
                            )
                        else:
                            fig.update_yaxes(row=2, col=1, range=[0, 1], title_text="Drawdown (USD)", tickprefix="$", tickformat=".2f")

                        # Horizontal line at max drawdown
                        if max_dd > 0:
                            fig.add_hline(y=max_dd, line_dash="dash", line_color="orange", row=2, col=1,
                                          annotation_text=f"Max DD: ${max_dd:.2f}")

                        fig.update_layout(height=700, showlegend=False)
                        st.plotly_chart(fig, use_container_width=True)

                    # --------------------------------------------------
                    # METRICS AND TABLES
                    # --------------------------------------------------
                    st.subheader("Detailed Metrics")
                    st.dataframe(pd.DataFrame([results]).T.rename(columns={0: "Value"}))

                    if monthly_df:
                        st.subheader("Monthly Breakdown")
                        df_month = pd.DataFrame(monthly_df)
                        df_month['Starting Balance (USD)'] = df_month['Starting Balance (cents)'] / 100.0
                        df_month['Monthly P&L (USD)'] = df_month['Monthly P&L (cents)'] / 100.0
                        df_month['Withdrawn (USD)'] = df_month['Withdrawn (cents)'] / 100.0
                        df_month['Balance After (USD)'] = df_month['Balance After (cents)'] / 100.0
                        st.dataframe(df_month[['Month', 'Starting Balance (USD)', 'Monthly P&L (USD)',
                                               'Withdrawal %', 'Withdrawn (USD)', 'Balance After (USD)']])

                    if trades_df is not None and not trades_df.empty:
                        csv = trades_df.to_csv(index=False).encode('utf-8')
                        st.download_button("Download Trade Log (CSV)", csv, "trade_log.csv", "text/csv")

                    # --------------------------------------------------
                    # GENERATE REPORT (HTML)
                    # --------------------------------------------------
                    st.sidebar.subheader("Report Export")
                    if st.sidebar.button("Generate Report (HTML)"):
                        # Build HTML report (same as before)
                        # I'll include a simple version here
                        html_content = f"""
                        <!DOCTYPE html>
                        <html>
                        <head><meta charset="UTF-8"><title>QuantForge Report</title>
                        <style>body {{ font-family: Arial; margin: 40px; }}</style>
                        </head>
                        <body>
                        <h1>QuantForge Backtest Report</h1>
                        <p><strong>Risk:</strong> {risk_cents} cents</p>
                        <p><strong>Period:</strong> {start_date} to {end_date}</p>
                        <h2>Summary</h2>
                        <p>Total Trades: {results['total_trades']}</p>
                        <p>Win Rate: {results['win_rate']:.1f}%</p>
                        <p>Profit Factor: {results['profit_factor']:.2f}</p>
                        <p>Total Withdrawn: ${results['total_withdrawn_usd']:.2f}</p>
                        <p>Avg Monthly: ${results['avg_monthly_usd']:.2f}</p>
                        <p>Max DD: ${results['max_dd_cents']/100:.2f}</p>
                        </body>
                        </html>
                        """
                        st.download_button("Download Report (HTML)", data=html_content,
                                           file_name="quantforge_report.html", mime="text/html")
            except Exception as e:
                st.error(f"Error: {e}")

st.sidebar.markdown("---")

# --------------------------------------------------------------
# WFV
# --------------------------------------------------------------
st.sidebar.subheader("Walk-Forward Validation (WFV)")
st.sidebar.caption("Runs on the standard 4 blocks: 2005-2009, 2010-2014, 2015-2019, 2020-2024")

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
