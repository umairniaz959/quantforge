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
    ea_code = f'''//+------------------------------------------------------------------+
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
extern double RiskMoney        = {risk_cents}.0;   // FIXED flat risk per trade
extern int    Slippage         = 3;
extern int    MagicNumber      = {ea_magic};
extern int    MaxBarsOpen      = 50;
extern int    LimitExpiryBars  = 1;
extern int    Debug            = 1;

extern double BE_Multiplier    = 1.5;
extern double Trail_Activate   = 3.0;
extern double Trail_Dist       = 1.0;

//+------------------------------------------------------------------+
//| Pattern structure                                                 |
//+------------------------------------------------------------------+
struct Pattern {{
   int    state;
   int    type;
   double zoneLow;
   double zoneHigh;
   int    barsSinceRetest;
   int    pendingTicket;
   datetime placedBarTime;
   double requestedEntry;
}};

Pattern patterns[];
int      patternCount = 0;
int      maxPatterns = 100;

//+------------------------------------------------------------------+
//| Trade tracker                                                     |
//+------------------------------------------------------------------+
struct TradeTracker {{
   int ticket;
   double entry;
   double risk;
   double peak;
   double valley;
   bool   beSet;
   double lastTrail;
}};

TradeTracker trackers[];
int      trackerCount = 0;

//+------------------------------------------------------------------+
//| Helper functions                                                 |
//+------------------------------------------------------------------+
string GetQuoteCurrency()
{{
   string symbol = Symbol();
   if(StringLen(symbol) >= 6) return StringSubstr(symbol, 3, 3);
   return "USD";
}}

double GetPipSize()
{{
   string quote = GetQuoteCurrency();
   return (quote == "JPY") ? 0.01 : 0.0001;
}}

double GetPipValueUSD_1Lot(double price)
{{
   string quote = GetQuoteCurrency();
   if(quote == "JPY") {{
      if(price == 0) return 0;
      return (0.01 / price) * 100000.0;
   }}
   return 10.0;
}}

void LogSlippage(string context, int ticket, double requested, double actual, bool isBuySide)
{{
   double slippagePoints = isBuySide ? (actual - requested) / Point : (requested - actual) / Point;
   double slippagePips = slippagePoints * Point / GetPipSize();
   string verdict = (slippagePoints > 0) ? "WORSE than requested" :
                     (slippagePoints < 0) ? "BETTER than requested" : "EXACT, no slippage";
   Print("[SLIPPAGE] ", context, " #", ticket, " on ", Symbol(),
         " | requested=", DoubleToStr(requested, Digits),
         " actual=", DoubleToStr(actual, Digits),
         " | ", DoubleToStr(slippagePoints, 1), " points (", DoubleToStr(slippagePips, 2), " pips) - ", verdict);
}}

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
{{
   ArrayResize(patterns, maxPatterns);
   ArrayResize(trackers, 100);
   patternCount = 0;
   trackerCount = 0;
   if(Debug) Print("Proposal 3.1 EA initialized on ", Symbol(),
                    " (fixed risk=", RiskMoney, ", zone-boundary limit entry, 1-bar expiry, overlap allowed)");
   return(INIT_SUCCEEDED);
}}

void OnDeinit(const int reason) {{}}

void CheckAndCloseTimeoutTrades()
{{
   int total = OrdersTotal();
   for(int i = total - 1; i >= 0; i--) {{
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;
      int cmd = OrderType();
      if(cmd > OP_SELL) continue;
      datetime openTime = OrderOpenTime();
      int barsOpen = iBarShift(Symbol(), PERIOD_H1, openTime, false);
      if(barsOpen >= MaxBarsOpen) {{
         int ticket = OrderTicket();
         double requestedClose = (cmd == OP_BUY) ? Bid : Ask;
         if(OrderClose(ticket, OrderLots(), requestedClose, Slippage, clrRed)) {{
            if(Debug) Print("Force-closed timeout trade #", ticket, " after ", barsOpen, " bars.");
            if(OrderSelect(ticket, SELECT_BY_TICKET)) {{
               double actualClose = OrderClosePrice();
               bool isBuySide = (cmd == OP_SELL);
               LogSlippage("TIMEOUT CLOSE", ticket, requestedClose, actualClose, isBuySide);
            }}
         }} else {{
            Print("Failed to force-close timeout trade #", ticket, " error: ", GetLastError());
         }}
      }}
   }}
}}

void ManageOpenTrades()
{{
   static datetime lastBarTime = 0;
   datetime currentBarTime = Time[0];
   bool newBar = (currentBarTime != lastBarTime);
   if(newBar) lastBarTime = currentBarTime;

   for(int i = trackerCount - 1; i >= 0; i--) {{
      bool gone = !OrderSelect(trackers[i].ticket, SELECT_BY_TICKET);
      bool closedNow = (!gone && OrderCloseTime() > 0);
      if(gone || closedNow) {{
         if(closedNow) {{
            double closePrice = OrderClosePrice();
            double sl = OrderStopLoss();
            double tp = OrderTakeProfit();
            double reference = (MathAbs(closePrice - tp) < MathAbs(closePrice - sl)) ? tp : sl;
            bool isBuySide = (OrderType() == OP_SELL);
            LogSlippage("SL/TP STOP-OUT", trackers[i].ticket, reference, closePrice, isBuySide);
         }}
         for(int j = i; j < trackerCount - 1; j++) trackers[j] = trackers[j+1];
         trackerCount--;
      }}
   }}

   int total = OrdersTotal();
   for(int i = total - 1; i >= 0; i--) {{
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderSymbol() != Symbol() || OrderMagicNumber() != MagicNumber) continue;
      int cmd = OrderType();
      if(cmd > OP_SELL) continue;

      int ticket = OrderTicket();
      double entry = OrderOpenPrice();
      double currentSL = OrderStopLoss();
      double risk = MathAbs(entry - currentSL);
      if(risk == 0) continue;

      int trIdx = -1;
      for(int j = 0; j < trackerCount; j++) {{
         if(trackers[j].ticket == ticket) {{ trIdx = j; break; }}
      }}
      if(trIdx == -1) {{
         if(trackerCount >= ArraySize(trackers)) ArrayResize(trackers, trackerCount + 10);
         trackers[trackerCount].ticket = ticket;
         trackers[trackerCount].entry = entry;
         trackers[trackerCount].risk = risk;
         trackers[trackerCount].peak = entry;
         trackers[trackerCount].valley = entry;
         trackers[trackerCount].beSet = false;
         trackers[trackerCount].lastTrail = currentSL;
         trIdx = trackerCount;
         trackerCount++;
         if(Debug) Print("New position picked up by manager: #", ticket, " (filled limit order)");
      }}

      if(newBar) {{
         if(cmd == OP_BUY) {{ if(High[1] > trackers[trIdx].peak) trackers[trIdx].peak = High[1]; }}
         else               {{ if(Low[1]  < trackers[trIdx].valley) trackers[trIdx].valley = Low[1]; }}
      }}

      if(!trackers[trIdx].beSet) {{
         bool beTriggered = false;
         if(cmd == OP_BUY) {{ if(High[1] >= entry + risk * BE_Multiplier) beTriggered = true; }}
         else               {{ if(Low[1]  <= entry - risk * BE_Multiplier) beTriggered = true; }}
         if(beTriggered) {{
            if(OrderModify(ticket, entry, entry, OrderTakeProfit(), 0, clrNONE)) {{
               trackers[trIdx].beSet = true;
               trackers[trIdx].lastTrail = entry;
               if(Debug) Print("Moved SL to breakeven on #", ticket);
            }}
            continue;
         }}
      }}

      bool trailActivated = false;
      if(cmd == OP_BUY) {{ if(trackers[trIdx].peak   >= entry + risk * Trail_Activate) trailActivated = true; }}
      else               {{ if(trackers[trIdx].valley <= entry - risk * Trail_Activate) trailActivated = true; }}

      if(newBar && trailActivated) {{
         double trailSL;
         if(cmd == OP_BUY) trailSL = trackers[trIdx].peak - risk * Trail_Dist;
         else               trailSL = trackers[trIdx].valley + risk * Trail_Dist;

         if((cmd == OP_BUY && trailSL > currentSL) || (cmd == OP_SELL && trailSL < currentSL)) {{
            if(MathAbs(trailSL - trackers[trIdx].lastTrail) > Point/2) {{
               if(OrderModify(ticket, entry, trailSL, OrderTakeProfit(), 0, clrNONE)) {{
                  trackers[trIdx].lastTrail = trailSL;
                  if(Debug) Print("Trail updated SL to ", trailSL, " on #", ticket);
               }}
            }}
         }}
      }}
   }}
}}

void CheckPendingFills()
{{
   for(int i = 0; i < patternCount; i++) {{
      if(patterns[i].state != 3) continue;

      if(!OrderSelect(patterns[i].pendingTicket, SELECT_BY_TICKET)) {{
         patterns[i].state = 6;
         if(Debug) Print("Pending limit order #", patterns[i].pendingTicket, " no longer exists (expired).");
         continue;
      }}

      int t = OrderType();
      if(t == OP_BUY || t == OP_SELL) {{
         double actualFillPrice = OrderOpenPrice();
         LogSlippage("ENTRY FILL", patterns[i].pendingTicket, patterns[i].requestedEntry,
                     actualFillPrice, (t == OP_BUY));
         patterns[i].state = 4;
         if(Debug) Print("Pending order #", patterns[i].pendingTicket, " filled.");
         continue;
      }}

      int barsElapsed = iBarShift(Symbol(), PERIOD_H1, patterns[i].placedBarTime, false);
      if(barsElapsed >= LimitExpiryBars) {{
         if(OrderDelete(patterns[i].pendingTicket)) {{
            if(Debug) Print("Manually deleted expired pending order #", patterns[i].pendingTicket);
         }} else {{
            Print("Failed to delete expired pending order #", patterns[i].pendingTicket,
                  " error: ", GetLastError());
         }}
         patterns[i].state = 6;
      }}
   }}
}}

void OnTick()
{{
   static datetime lastBarTime = 0;
   datetime currentTime = Time[0];

   ManageOpenTrades();
   CheckPendingFills();

   if(lastBarTime == currentTime) return;
   lastBarTime = currentTime;

   CheckAndCloseTimeoutTrades();

   if(Bars >= 4) {{
      if(High[1] < Low[3]) AddPattern(1, Low[3], High[1]);
      else if(Low[1] > High[3]) AddPattern(2, High[3], Low[1]);
   }}

   for(int i = patternCount - 1; i >= 0; i--) {{
      ProcessPattern(i);
   }}

   CleanPatterns();
}}

void AddPattern(int type, double low, double high)
{{
   if(patternCount >= maxPatterns) {{
      if(Debug) Print("Pattern queue full, skipping new pattern");
      return;
   }}
   patterns[patternCount].state = 0;
   patterns[patternCount].type = type;
   patterns[patternCount].zoneLow = low;
   patterns[patternCount].zoneHigh = high;
   patterns[patternCount].barsSinceRetest = -1;
   patterns[patternCount].pendingTicket = -1;
   patterns[patternCount].placedBarTime = 0;
   patterns[patternCount].requestedEntry = 0;
   patternCount++;
   if(Debug) Print("New pattern added. Type: ", type, " Zone: ", low, "-", high, " Total: ", patternCount);
}}

void ProcessPattern(int idx)
{{
   if(patterns[idx].state >= 3) return;

   double close = Close[1];
   double high = High[1];
   double low  = Low[1];

   switch(patterns[idx].state) {{
      case 0:
         if(close < patterns[idx].zoneLow || close > patterns[idx].zoneHigh) {{
            patterns[idx].state = 1;
            if(Debug) Print("Departure detected for pattern ", idx);
         }}
         break;

      case 1:
      {{
         double pipSize = GetPipSize();
         double tolerance = 0.5 * pipSize;
         bool touched = (MathAbs(high - patterns[idx].zoneLow)  < tolerance ||
                         MathAbs(low  - patterns[idx].zoneHigh) < tolerance ||
                         MathAbs(high - patterns[idx].zoneHigh) < tolerance ||
                         MathAbs(low  - patterns[idx].zoneLow)  < tolerance);
         if(touched) {{
            patterns[idx].state = 2;
            patterns[idx].barsSinceRetest = 0;
            if(Debug) Print("Retest detected (tolerance) for pattern ", idx);
         }}
         break;
      }}

      case 2:
      {{
         patterns[idx].barsSinceRetest++;
         if(patterns[idx].barsSinceRetest > 3) {{
            patterns[idx].state = 6;
            if(Debug) Print("Pattern expired - no exit confirmation within 3 bars");
            break;
         }}
         bool exitDown = (close < patterns[idx].zoneLow);
         bool exitUp   = (close > patterns[idx].zoneHigh);
         if(!exitDown && !exitUp) break;

         bool isImmediateBreak = false;
         if(patterns[idx].type == 1 && exitDown) isImmediateBreak = true;
         else if(patterns[idx].type == 2 && exitUp) isImmediateBreak = true;

         if(isImmediateBreak) {{
            PlaceZoneLimitOrder(idx);
         }} else {{
            patterns[idx].state = 5;
            if(Debug) Print("Exit is rejection (wrong direction), pattern ", idx, " dropped");
         }}
         break;
      }}
   }}
}}

void PlaceZoneLimitOrder(int idx)
{{
   int cmd;
   double entryPrice, stopLoss, takeProfit;

   if(patterns[idx].type == 1) {{
      cmd = OP_SELLLIMIT;
      entryPrice = patterns[idx].zoneLow;
      stopLoss   = patterns[idx].zoneHigh;
   }} else {{
      cmd = OP_BUYLIMIT;
      entryPrice = patterns[idx].zoneHigh;
      stopLoss   = patterns[idx].zoneLow;
   }}

   double riskPrice = MathAbs(entryPrice - stopLoss);
   if(riskPrice == 0) {{ patterns[idx].state = 5; return; }}

   takeProfit = (cmd == OP_SELLLIMIT) ? entryPrice - 1000 * Point : entryPrice + 1000 * Point;

   double currentPrice = (cmd == OP_SELLLIMIT) ? Bid : Ask;
   int minStop = (int)MarketInfo(Symbol(), MODE_STOPLEVEL);
   int freezeLevel = (int)MarketInfo(Symbol(), MODE_FREEZELEVEL);
   int minDistPoints = MathMax(minStop, freezeLevel);
   double distPoints = MathAbs(entryPrice - currentPrice) / Point;
   if(minDistPoints > 0 && distPoints < minDistPoints) {{
      Print("Zone-limit entry too close to market (", distPoints, " < ", minDistPoints,
            ") - broker would reject. Pattern ", idx, " dropped.");
      patterns[idx].state = 5;
      return;
   }}

   double riskPips = riskPrice / GetPipSize();

   double pipValueUSD_1Lot = GetPipValueUSD_1Lot(entryPrice);
   if(pipValueUSD_1Lot <= 0) {{ patterns[idx].state = 5; return; }}

   double pipValueCents_1Lot = pipValueUSD_1Lot * 100.0;
   double riskCentsPerLot = riskPips * pipValueCents_1Lot;
   if(riskCentsPerLot <= 0) {{ patterns[idx].state = 5; return; }}

   double lotSize = RiskMoney / riskCentsPerLot;

   double minLot = MarketInfo(Symbol(), MODE_MINLOT);
   double maxLot = MarketInfo(Symbol(), MODE_MAXLOT);
   double lotStep = MarketInfo(Symbol(), MODE_LOTSTEP);
   if(lotStep > 0) lotSize = MathFloor(lotSize / lotStep) * lotStep;
   lotSize = MathMax(minLot, MathMin(maxLot, lotSize));

   datetime expirationTime = Time[0] + LimitExpiryBars * Period() * 60;

   if(Debug) {{
      Print("Placing zone-limit: cmd=", cmd, " entry=", entryPrice, " SL=", stopLoss, " TP=", takeProfit,
            " lot=", lotSize, " riskMoney=", RiskMoney, " riskPips=", riskPips, " expires=", TimeToStr(expirationTime));
   }}

   int ticket = OrderSend(Symbol(), cmd, lotSize, entryPrice, Slippage, stopLoss, takeProfit,
                           "Zone31", MagicNumber, expirationTime, clrNONE);
   if(ticket < 0) {{
      Print("OrderSend (zone limit) failed: ", GetLastError(), " on ", Symbol());
      patterns[idx].state = 5;
   }} else {{
      patterns[idx].pendingTicket = ticket;
      patterns[idx].placedBarTime = Time[0];
      patterns[idx].requestedEntry = entryPrice;
      patterns[idx].state = 3;
      if(Debug) Print("Zone-limit order placed: Ticket ", ticket);
   }}
}}

void CleanPatterns()
{{
   int j = 0;
   for(int i = 0; i < patternCount; i++) {{
      if(patterns[i].state != 4 && patterns[i].state != 5 && patterns[i].state != 6) {{
         if(j != i) patterns[j] = patterns[i];
         j++;
      }}
   }}
   patternCount = j;
}}
//+------------------------------------------------------------------+
'''
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
                    # EQUITY CURVE AND DRAWDOWN
                    # --------------------------------------------------
                    if monthly_df:
                        df_month = pd.DataFrame(monthly_df)
                        df_month['Cumulative P&L (USD)'] = (df_month['Monthly P&L (cents)'] / 100.0).cumsum()
                        df_month['Drawdown (USD)'] = df_month['Cumulative P&L (USD)'].cummax() - df_month['Cumulative P&L (USD)']

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

                        fig.add_trace(
                            go.Bar(
                                x=df_month['Month'],
                                y=df_month['Drawdown (USD)'],
                                name='Drawdown',
                                marker_color='red',
                            ),
                            row=2, col=1
                        )

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
