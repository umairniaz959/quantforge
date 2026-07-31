import streamlit as st
import pandas as pd
import os
from backtest_engine import run_backtest, run_wfv

st.set_page_config(page_title="QuantForge – Backtest Engine", layout="wide")
st.title("🚀 QuantForge – Backtest Engine")
st.markdown("Upload your data, define parameters, and get AI‑powered analysis.")

# --------------------------------------------------------------
# Sidebar – common parameters
# --------------------------------------------------------------
st.sidebar.header("Common Parameters")
data_folder = st.sidebar.text_input("Data Folder Path", value=r"C:\BRE\data")
risk_cents = st.sidebar.number_input("Risk per Trade (cents)", min_value=1, value=70)
withdrawal_pct_first = st.sidebar.slider("Withdrawal % – First Year", 0, 100, 70)
withdrawal_pct_rest = st.sidebar.slider("Withdrawal % – Rest", 0, 100, 100)

st.sidebar.markdown("---")

# --------------------------------------------------------------
# SINGLE BACKTEST (custom date range)
# --------------------------------------------------------------
st.sidebar.subheader("Single Backtest")
start_date = st.sidebar.date_input("Start Date", value=pd.to_datetime("2023-01-01"))
end_date = st.sidebar.date_input("End Date", value=pd.to_datetime("2025-01-01"))

if st.sidebar.button("Run Single Backtest"):
    if not os.path.exists(data_folder):
        st.error("Data folder not found.")
    else:
        with st.spinner("Running backtest..."):
            try:
                results, trades_df, monthly_df = run_backtest(
                    data_folder,
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
            except Exception as e:
                st.error(f"Error: {e}")

st.sidebar.markdown("---")

# --------------------------------------------------------------
# WALK-FORWARD VALIDATION (fixed 5‑year blocks)
# --------------------------------------------------------------
st.sidebar.subheader("Walk-Forward Validation (WFV)")
st.sidebar.caption("Runs on the standard 4 blocks: 2005-2009, 2010-2014, 2015-2019, 2020-2024")

if st.sidebar.button("Run WFV"):
    if not os.path.exists(data_folder):
        st.error("Data folder not found.")
    else:
        with st.spinner("Running WFV across 4 blocks..."):
            try:
                block_results, summary = run_wfv(
                    data_folder,
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