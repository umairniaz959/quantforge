import pandas as pd
import numpy as np
from datetime import timedelta
from strategy_base import Strategy

# --------------------------------------------------------------
# Global settings (unchanged)
# --------------------------------------------------------------
RISK_CENTS = 70
STARTING_BALANCE_CENTS = 10000
TOUCH_TOLERANCE_PIPS = 0.5
LIMIT_EXPIRY_BARS = 1
BE_MULTIPLIER = 1.5
TRAIL_ACTIVATE = 3.0
TRAIL_DIST = 1.0
MAX_BARS_OPEN = 50

MAJOR_PAIRS = {'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD'}
SPREAD_LIMIT_MAJOR_PIPS = 2.0
SPREAD_LIMIT_CROSS_PIPS = 3.0

WITHDRAWAL_PCT_FIRST_YEAR = 70
WITHDRAWAL_PCT_REST = 100

SIMULATE_LOT_ROUNDING = True
LOT_STEP = 0.01
MIN_LOT = 0.01
MAX_LOT = 100.0

# --------------------------------------------------------------
# Helper functions (unchanged) – omitted for brevity
# (keep your existing pair_files, clean_columns, get_pair_currencies, etc.)
# --------------------------------------------------------------
# ...

# --------------------------------------------------------------
# Data loading (unchanged)
# --------------------------------------------------------------
# ...

# --------------------------------------------------------------
# Core simulation (unchanged)
# --------------------------------------------------------------
# ...

# --------------------------------------------------------------
# Public functions (unchanged)
# --------------------------------------------------------------
# ...

# ==============================================================
# DYNAMIC STRATEGY EXECUTION (UPDATED with debug and fixes)
# ==============================================================
def run_generated_strategy(uploaded_files, user_code, params,
                           start_date=None, end_date=None, initial_balance=10000):
    """
    Runs a generated strategy with debug logging and column fixes.
    Returns (results, trades_df, debug_info) – debug_info is a dict.
    """
    # ---- Clean user code: replace uppercase column names ----
    user_code_fixed = user_code
    for col in ['Close', 'High', 'Low', 'Open']:
        user_code_fixed = user_code_fixed.replace(f"['{col}']", f"['{col.lower()}']")
        user_code_fixed = user_code_fixed.replace(f'["{col}"]', f'["{col.lower()}"]')
    if user_code_fixed != user_code:
        print("Fixed uppercase column references in strategy code.")

    # ---- Load data ----
    pair_names, master_index, bid_arrays, ask_arrays, ref_prices = load_uploaded_data(
        uploaded_files, start_date, end_date
    )
    if not pair_names:
        return None, None, {"error": "No pairs found"}

    pair_name = pair_names[0]
    bid_array = bid_arrays[pair_name]
    ask_array = ask_arrays[pair_name]

    data = pd.DataFrame({
        'open': bid_array[:, 0],
        'high': bid_array[:, 1],
        'low': bid_array[:, 2],
        'close': bid_array[:, 3],
    }, index=master_index)
    data.columns = [col.lower() for col in data.columns]
    data = data.ffill().bfill()

    print(f"Data shape: {data.shape}, columns: {data.columns.tolist()}")
    print(f"First few rows:\n{data.head(3)}")

    # ---- Execute user code ----
    local_scope = {'Strategy': Strategy, 'pd': pd, 'np': np}
    try:
        exec(user_code_fixed, local_scope)
        UserStrategy = local_scope['UserStrategy']
        print("UserStrategy class loaded successfully.")
    except Exception as e:
        raise RuntimeError(f"Error in user code: {e}")

    # ---- Instantiate and run ----
    strategy = UserStrategy(data)
    strategy.stop_loss_pips = params.get('stop_loss_pips', 20)
    strategy.take_profit_pips = params.get('take_profit_pips', 40)
    strategy.risk_per_trade = params.get('risk_per_trade', 2.0)
    strategy.init()
    print(f"Strategy initialized. stop_loss_pips={strategy.stop_loss_pips}, take_profit_pips={strategy.take_profit_pips}")

    balance = initial_balance
    trades_log = []
    in_position = False
    entry_price = 0.0
    entry_type = None
    entry_bar = 0
    sl_price = 0.0
    tp_price = 0.0

    for i in range(len(data)):
        try:
            strategy.next(i)
        except Exception as e:
            print(f"Error in strategy.next() at bar {i}: {e}")
            continue

        current_pos = strategy.position
        if current_pos != 0 and not in_position:
            entry_price = data['close'].iloc[i]
            entry_type = 'BUY' if current_pos == 1 else 'SELL'
            sl_price = strategy.sl_price if strategy.sl_price is not None else 0.0
            tp_price = strategy.tp_price if strategy.tp_price is not None else 0.0
            in_position = True
            entry_bar = i
            print(f"OPEN {entry_type} at bar {i}, price {entry_price:.5f}, SL {sl_price:.5f}, TP {tp_price:.5f}")
        elif current_pos == 0 and in_position:
            exit_price = data['close'].iloc[i]
            if entry_type == 'BUY':
                pnl = (exit_price - entry_price) * 100000
            else:
                pnl = (entry_price - exit_price) * 100000
            trades_log.append({
                'entry_bar': entry_bar,
                'exit_bar': i,
                'entry': entry_price,
                'exit': exit_price,
                'type': entry_type,
                'pnl': pnl,
                'sl': sl_price,
                'tp': tp_price
            })
            print(f"CLOSE {entry_type} at bar {i}, exit {exit_price:.5f}, PnL {pnl:.2f}")
            in_position = False
            sl_price = 0.0
            tp_price = 0.0

    df_trades = pd.DataFrame(trades_log)
    if df_trades.empty:
        print("No trades were generated.")
        # Build debug info
        debug_info = {
            "strategy_code": user_code_fixed,
            "data_head": data.head(10).to_dict(),
            "data_shape": data.shape,
            "columns": data.columns.tolist(),
            "message": "No trades generated. Check conditions and data range."
        }
        return None, None, debug_info

    wins = df_trades[df_trades['pnl'] > 0]['pnl']
    losses = df_trades[df_trades['pnl'] < 0]['pnl']
    pf = abs(wins.sum() / losses.sum()) if losses.sum() != 0 else float('inf')
    win_rate = (df_trades['pnl'] > 0).mean() * 100

    results = {
        'total_trades': len(df_trades),
        'win_rate': win_rate,
        'profit_factor': pf,
        'total_withdrawn_usd': 0,
        'avg_monthly_usd': 0,
        'max_dd_cents': 0,
        'max_dd_percent': 0,
    }
    return results, df_trades, {}
