import pandas as pd
import numpy as np
from datetime import timedelta
from strategy_base import Strategy

# --------------------------------------------------------------
# Global settings
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
# Helper functions (unchanged)
# --------------------------------------------------------------
def pair_files(all_files):
    bid_files = [f for f in all_files if '_ask' not in f.lower()]
    ask_files = [f for f in all_files if '_ask' in f.lower()]
    pairs = []
    for b in bid_files:
        base = b.replace('_H1.csv', '')
        a = base + '_H1_ASK.csv'
        if a in ask_files:
            pairs.append((b, a, base))
    return pairs

def clean_columns(df):
    df.columns = [c.lower() for c in df.columns]
    rename_map = {}
    for col in df.columns:
        if col in ['open', 'o']: rename_map[col] = 'open'
        if col in ['high', 'h']: rename_map[col] = 'high'
        if col in ['low', 'l']: rename_map[col] = 'low'
        if col in ['close', 'c']: rename_map[col] = 'close'
    df.rename(columns=rename_map, inplace=True)
    return df

def get_pair_currencies(pair_name):
    return pair_name[:3], pair_name[3:]

def get_pip_size(quote_currency):
    return 0.01 if quote_currency == 'JPY' else 0.0001

def get_pip_value_usd_static(quote, price):
    if quote == 'JPY':
        if price == 0:
            return None
        return (0.01 / price) * 100000.0
    return 10.0

def get_pip_value_usd_triangulated(pair_name, price, timestamp, ref_prices, lot_units=100000):
    base, quote = get_pair_currencies(pair_name)
    pip_size = get_pip_size(quote)
    if quote == 'USD':
        return pip_size * lot_units
    if base == 'USD':
        if price == 0 or np.isnan(price):
            return None
        return (pip_size * lot_units) / price
    pip_value_quote = pip_size * lot_units
    quote_usd_pair = quote + 'USD'
    usd_quote_pair = 'USD' + quote
    if quote_usd_pair in ref_prices:
        conv_rate = ref_prices[quote_usd_pair].get(timestamp)
        if conv_rate is None or np.isnan(conv_rate):
            return None
        return pip_value_quote * conv_rate
    if usd_quote_pair in ref_prices:
        conv_rate = ref_prices[usd_quote_pair].get(timestamp)
        if conv_rate is None or np.isnan(conv_rate) or conv_rate == 0:
            return None
        return pip_value_quote / conv_rate
    return None

def get_pip_value(pair_name, quote, price, timestamp, ref_prices, mode='triangulated'):
    if mode == 'static':
        return get_pip_value_usd_static(quote, price)
    return get_pip_value_usd_triangulated(pair_name, price, timestamp, ref_prices)

# --------------------------------------------------------------
# Data loading
# --------------------------------------------------------------
def load_uploaded_data(uploaded_files, start_date=None, end_date=None):
    all_files = list(uploaded_files.keys())
    pairs = pair_files(all_files)
    if not pairs:
        raise RuntimeError("No paired BID/ASK files found. Make sure you upload both BID and ASK files for each pair.")

    bid_dfs, ask_dfs = {}, {}
    for bid_file, ask_file, pair_name in pairs:
        try:
            df_bid = pd.read_csv(uploaded_files[bid_file])
            df_ask = pd.read_csv(uploaded_files[ask_file])
        except Exception as e:
            raise RuntimeError(f"Failed to read file {bid_file} or {ask_file}: {e}")

        if df_bid.empty or df_ask.empty:
            raise RuntimeError(f"File {bid_file} or {ask_file} is empty.")

        for df in (df_bid, df_ask):
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
            else:
                date_col = next((c for c in df.columns if 'date' in c.lower() or 'time' in c.lower()), None)
                if date_col:
                    df[date_col] = pd.to_datetime(df[date_col])
                    df.set_index(date_col, inplace=True)
                else:
                    try:
                        df.index = pd.to_datetime(df.iloc[:, 0])
                        df = df.iloc[:, 1:]
                    except:
                        raise RuntimeError(f"File {bid_file} has no timestamp column and cannot parse first column as datetime.")
        df_bid = clean_columns(df_bid).sort_index()
        df_ask = clean_columns(df_ask).sort_index()
        bid_dfs[pair_name] = df_bid[['open', 'high', 'low', 'close']]
        ask_dfs[pair_name] = df_ask[['open', 'high', 'low', 'close']]

    master_index = None
    for df in bid_dfs.values():
        master_index = df.index if master_index is None else master_index.union(df.index)
    master_index = master_index.sort_values()

    if master_index.tz is None:
        master_index = master_index.tz_localize('UTC')
    else:
        master_index = master_index.tz_convert('UTC')

    if start_date is not None:
        start_dt = pd.to_datetime(start_date).tz_localize('UTC')
        master_index = master_index[master_index >= start_dt]
    if end_date is not None:
        end_dt = pd.to_datetime(end_date).tz_localize('UTC')
        master_index = master_index[master_index <= end_dt]

    if len(master_index) == 0:
        raise RuntimeError("No data in the selected date range.")

    bid_arrays, ask_arrays = {}, {}
    for pair_name in bid_dfs:
        bid_arrays[pair_name] = bid_dfs[pair_name].reindex(master_index).to_numpy(dtype=np.float64)
        ask_arrays[pair_name] = ask_dfs[pair_name].reindex(master_index).to_numpy(dtype=np.float64)

    ref_prices = {}
    for pair_name in bid_dfs:
        base, quote = get_pair_currencies(pair_name)
        if base == 'USD' or quote == 'USD':
            s = bid_dfs[pair_name]['close'].reindex(master_index)
            ref_prices[pair_name] = {ts: v for ts, v in zip(master_index, s.values) if not np.isnan(v)}

    return list(bid_arrays.keys()), master_index, bid_arrays, ask_arrays, ref_prices

def get_spread_pips(pair_name, bid_price, ask_price):
    if pair_name in MAJOR_PAIRS:
        limit_pips = SPREAD_LIMIT_MAJOR_PIPS
    else:
        limit_pips = SPREAD_LIMIT_CROSS_PIPS
    pip_size = get_pip_size(get_pair_currencies(pair_name)[1])
    spread_pips = (ask_price - bid_price) / pip_size
    return spread_pips, limit_pips

# --------------------------------------------------------------
# Core simulation (validated strategy) – unchanged
# --------------------------------------------------------------
def run_simulation_on_arrays(pair_names, master_index, bid_arrays, ask_arrays, ref_prices,
                             risk_cents=RISK_CENTS,
                             withdrawal_pct_first=WITHDRAWAL_PCT_FIRST_YEAR,
                             withdrawal_pct_rest=WITHDRAWAL_PCT_REST,
                             reset_balance_monthly=True):
    # This function is unchanged – I've omitted it for brevity.
    # Keep your existing implementation here.
    # (If you need the full function, it's the same as before.)
    pass

# --------------------------------------------------------------
# Public functions for the web app
# --------------------------------------------------------------
def run_backtest_from_files(uploaded_files, risk_cents=RISK_CENTS,
                            withdrawal_pct_first=WITHDRAWAL_PCT_FIRST_YEAR,
                            withdrawal_pct_rest=WITHDRAWAL_PCT_REST,
                            start_date=None, end_date=None,
                            reset_balance_monthly=True):
    try:
        pair_names, master_index, bid_arrays, ask_arrays, ref_prices = load_uploaded_data(
            uploaded_files, start_date, end_date
        )
    except Exception as e:
        raise RuntimeError(f"Failed to load data: {e}")
    return run_simulation_on_arrays(
        pair_names, master_index, bid_arrays, ask_arrays, ref_prices,
        risk_cents, withdrawal_pct_first, withdrawal_pct_rest,
        reset_balance_monthly=reset_balance_monthly
    )

def run_wfv_from_files(uploaded_files, risk_cents=RISK_CENTS,
                       withdrawal_pct_first=WITHDRAWAL_PCT_FIRST_YEAR,
                       withdrawal_pct_rest=WITHDRAWAL_PCT_REST,
                       block_years=5,
                       reset_balance_monthly=True):
    # Keep your existing implementation – omitted for brevity.
    pass

def run_demo_backtest(uploaded_files, risk_cents=RISK_CENTS,
                      start_date=None, end_date=None,
                      demo_sl=20, demo_tp=40,
                      reset_balance_monthly=True):
    # Keep your existing implementation – omitted for brevity.
    pass

# ==============================================================
# DYNAMIC STRATEGY EXECUTION (from generated code)
# ==============================================================
def run_generated_strategy(uploaded_files, user_code, params,
                           start_date=None, end_date=None, initial_balance=10000):
    """
    Runs a generated strategy with the given parameters dict.
    params must contain: stop_loss_pips, take_profit_pips, risk_per_trade.
    """
    # Load data
    pair_names, master_index, bid_arrays, ask_arrays, ref_prices = load_uploaded_data(
        uploaded_files, start_date, end_date
    )
    if not pair_names:
        return None, None, None

    # Use first pair
    pair_name = pair_names[0]
    bid_array = bid_arrays[pair_name]
    ask_array = ask_arrays[pair_name]

    data = pd.DataFrame({
        'open': bid_array[:, 0],
        'high': bid_array[:, 1],
        'low': bid_array[:, 2],
        'close': bid_array[:, 3],
    }, index=master_index)

    # Execute user code
    local_scope = {'Strategy': Strategy, 'pd': pd, 'np': np}
    try:
        exec(user_code, local_scope)
        UserStrategy = local_scope['UserStrategy']
    except Exception as e:
        raise RuntimeError(f"Error in user code: {e}")

    # Instantiate and set params
    strategy = UserStrategy(data)
    strategy.stop_loss_pips = params.get('stop_loss_pips', 20)
    strategy.take_profit_pips = params.get('take_profit_pips', 40)
    strategy.risk_per_trade = params.get('risk_per_trade', 2.0)
    strategy.init()

    balance = initial_balance
    trades_log = []
    in_position = False
    entry_price = 0.0
    entry_type = None
    entry_bar = 0
    sl_price = 0.0
    tp_price = 0.0

    for i in range(len(data)):
        strategy.next(i)
        current_pos = strategy.position
        if current_pos != 0 and not in_position:
            entry_price = data['close'].iloc[i]
            entry_type = 'BUY' if current_pos == 1 else 'SELL'
            sl_price = strategy.sl_price if strategy.sl_price else 0.0
            tp_price = strategy.tp_price if strategy.tp_price else 0.0
            in_position = True
            entry_bar = i
        elif current_pos == 0 and in_position:
            exit_price = data['close'].iloc[i]
            if entry_type == 'BUY':
                pnl = (exit_price - entry_price) * 100000   # simplistic lot size
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
            in_position = False
            sl_price = 0.0
            tp_price = 0.0

    df_trades = pd.DataFrame(trades_log)
    if df_trades.empty:
        return None, None, None

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
    return results, df_trades, []
