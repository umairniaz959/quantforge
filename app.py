import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
from backtest_engine import run_backtest_from_files, run_wfv_from_files

st.set_page_config(page_title="QuantForge – Backtest Engine", layout="wide")

# ============================================================
# SESSION STATE INITIALIZATION (for presets)
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
if st.sidebar.button("🎯 Load Demo Preset (QuantForge Validated)"):
    st.session_state.risk_cents = 70
    st.session_state.withdrawal_pct_first = 70
    st.session_state.withdrawal_pct_rest = 100
    st.session_state.start_date = pd.to_datetime("2023-01-01")
    st.session_state.end_date = pd.to_datetime("2025-01-01")
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
# SIDEBAR – SINGLE BACKTEST
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

                    # ---- EQUITY CURVE & DRAWDOWN ----
                    if trades_df is not None and not trades_df.empty:
                        df_trades = trades_df.sort_values('exit_bar')
                        df_trades['Cumulative P&L (USD)'] = (df_trades['pnl_cents'].cumsum() / 100.0)
                        df_trades['Drawdown (USD)'] = df_trades['Cumulative P&L (USD)'].cummax() - df_trades['Cumulative P&L (USD)']
                        max_dd_from_curve = df_trades['Drawdown (USD)'].max()
                        st.caption(f"Max Drawdown from trade curve: **${max_dd_from_curve:.2f}**")

                        if 'exit_date' in df_trades.columns:
                            x_vals = pd.to_datetime(df_trades['exit_date'])
                            x_title = "Date"
                        else:
                            x_vals = df_trades['exit_bar']
                            x_title = "Trade Sequence"

                        fig = make_subplots(
                            rows=2, cols=1,
                            shared_xaxes=True,
                            vertical_spacing=0.1,
                            subplot_titles=("Equity Curve (USD)", "Drawdown (USD)")
                        )
                        fig.add_trace(
                            go.Scatter(
                                x=x_vals,
                                y=df_trades['Cumulative P&L (USD)'],
                                mode='lines',
                                name='Equity Curve',
                                line=dict(color='green', width=2),
                            ),
                            row=1, col=1
                        )
                        fig.add_trace(
                            go.Bar(
                                x=x_vals,
                                y=df_trades['Drawdown (USD)'],
                                name='Drawdown',
                                marker_color='red',
                            ),
                            row=2, col=1
                        )
                        if max_dd_from_curve > 0:
                            fig.update_yaxes(row=2, col=1, range=[0, max_dd_from_curve * 1.1], title_text="Drawdown (USD)", tickformat="$.2f")
                        else:
                            fig.update_yaxes(row=2, col=1, range=[0, 1], title_text="Drawdown (USD)", tickformat="$.2f")
                        if max_dd_from_curve > 0:
                            fig.add_hline(y=max_dd_from_curve, line_dash="dash", line_color="orange", row=2, col=1,
                                          annotation_text=f"Max DD: ${max_dd_from_curve:.2f}")
                        fig.update_layout(height=700, showlegend=False, xaxis_title=x_title)
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No trade log available.")

                    # ---- METRICS ----
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

                    # ---- REPORT ----
                    st.sidebar.subheader("Report Export")
                    if st.sidebar.button("Generate Report (HTML)"):
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
                st.stop()

st.sidebar.markdown("---")

# --------------------------------------------------------------
# SIDEBAR – WFV
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
