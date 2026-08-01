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
# Helper functions
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
    n = len(master_index)
    pip_sizes = {p: get_pip_size(get_pair_currencies(p)[1]) for p in pair_names}
    point_sizes = {p: pip_sizes[p] / 10.0 for p in pair_names}

    patterns = {p: [] for p in pair_names}
    open_trades = {p: [] for p in pair_names}
    pending_orders = {p: [] for p in pair_names}
    balance_cents = float(STARTING_BALANCE_CENTS)
    trades_log = []
    total_withdrawn_cents = 0
    monthly_details = []

    current_month = None
    month_start_balance = balance_cents
    month_peak = balance_cents
    month_max_dd_cents = 0
    monthly_pnl_list = []
    monthly_max_dd_list = []
    first_12_months_end = master_index[0] + timedelta(days=365)

    for i in range(2, n):
        ts = master_index[i]
        month_key = ts.strftime('%Y-%m')
        if current_month is None:
            current_month = month_key
            month_start_balance = balance_cents
            month_peak = balance_cents
            month_max_dd_cents = 0

        for pair_name in pair_names:
            arr_b = bid_arrays[pair_name]
            arr_a = ask_arrays[pair_name]
            row_b = arr_b[i]
            if np.any(np.isnan(row_b)) or np.any(np.isnan(arr_b[i-2:i+1])) or np.any(np.isnan(arr_a[i])):
                continue
            ob, hb, lb, cb = arr_b[i]
            oa, ha, la, ca = arr_a[i]
            quote = get_pair_currencies(pair_name)[1]
            pip_size = pip_sizes[pair_name]
            point_size = point_sizes[pair_name]
            tol = TOUCH_TOLERANCE_PIPS * pip_size

            # Manage OPEN TRADES
            still_open = []
            for tr in open_trades[pair_name]:
                closed = False
                if tr['type'] == 'BUY':
                    if lb <= tr['sl']:
                        exit_price = tr['sl']; closed = True; reason = 'SL'
                    elif hb >= tr['tp']:
                        exit_price = tr['tp']; closed = True; reason = 'TP'
                else:
                    if ha >= tr['sl']:
                        exit_price = tr['sl']; closed = True; reason = 'SL'
                    elif la <= tr['tp']:
                        exit_price = tr['tp']; closed = True; reason = 'TP'

                if not closed and (i - tr['entry_bar']) >= MAX_BARS_OPEN:
                    exit_price = cb if tr['type'] == 'BUY' else ca
                    closed = True; reason = 'TIMEOUT'

                if closed:
                    pip_pnl = (exit_price - tr['entry']) / pip_size if tr['type'] == 'BUY' \
                        else (tr['entry'] - exit_price) / pip_size
                    close_ref_price = cb if tr['type'] == 'BUY' else ca
                    pip_val = get_pip_value(pair_name, quote, close_ref_price, ts, ref_prices, 'triangulated')
                    if pip_val is None:
                        pip_val = tr['pip_val_entry']
                    pnl_cents = pip_pnl * pip_val * 100 * tr['lot']
                    balance_cents += pnl_cents
                    trades_log.append({
                        'pair': pair_name, 'type': tr['type'], 'entry_bar': tr['entry_bar'],
                        'exit_bar': i, 'entry': tr['entry'], 'exit': exit_price, 'reason': reason,
                        'pnl_cents': pnl_cents, 'lot': tr['lot'], 'risk_pips': tr['risk_pips'],
                        'be_set': tr['be_set'], 'balance_after': balance_cents, 'year': ts.year,
                    })
                    if balance_cents > month_peak:
                        month_peak = balance_cents
                    dd = month_peak - balance_cents
                    if dd > month_max_dd_cents:
                        month_max_dd_cents = dd
                    continue

                # Update peak/valley, BE, trail
                if tr['type'] == 'BUY':
                    tr['peak'] = max(tr['peak'], hb)
                    if not tr['be_set'] and tr['peak'] >= tr['entry'] + tr['risk'] * BE_MULTIPLIER:
                        tr['sl'] = tr['entry']; tr['be_set'] = True; tr['last_trail'] = tr['entry']
                    elif tr['peak'] >= tr['entry'] + tr['risk'] * TRAIL_ACTIVATE:
                        new_sl = tr['peak'] - tr['risk'] * TRAIL_DIST
                        if new_sl > tr['sl']:
                            tr['sl'] = new_sl; tr['last_trail'] = new_sl
                else:
                    tr['valley'] = min(tr['valley'], la)
                    if not tr['be_set'] and tr['valley'] <= tr['entry'] - tr['risk'] * BE_MULTIPLIER:
                        tr['sl'] = tr['entry']; tr['be_set'] = True; tr['last_trail'] = tr['entry']
                    elif tr['valley'] <= tr['entry'] - tr['risk'] * TRAIL_ACTIVATE:
                        new_sl = tr['valley'] + tr['risk'] * TRAIL_DIST
                        if new_sl < tr['sl']:
                            tr['sl'] = new_sl; tr['last_trail'] = new_sl

                still_open.append(tr)
            open_trades[pair_name] = still_open

            # Fill PENDING ORDERS
            still_pending = []
            for po in pending_orders[pair_name]:
                if i - po['place_bar'] > LIMIT_EXPIRY_BARS:
                    continue
                filled = False
                if po['cmd'] == 'BUY':
                    if la <= po['entry']:
                        filled = True
                        fill_price = po['entry']
                else:
                    if hb >= po['entry']:
                        filled = True
                        fill_price = po['entry']

                if filled:
                    risk = po['risk']
                    open_trades[pair_name].append({
                        'type': 'BUY' if po['cmd'] == 'BUY' else 'SELL',
                        'entry': fill_price,
                        'sl': po['sl'],
                        'tp': po['tp'],
                        'lot': po['lot'],
                        'entry_bar': i,
                        'risk': risk,
                        'risk_pips': risk / pip_size,
                        'peak': fill_price,
                        'valley': fill_price,
                        'be_set': False,
                        'last_trail': po['sl'],
                        'pip_val_entry': po['pip_val'],
                    })
                else:
                    still_pending.append(po)
            pending_orders[pair_name] = still_pending

            # Process patterns (same as before)
            for pat in patterns[pair_name]:
                if pat['state'] == 0:
                    if cb < pat['zone_low'] or cb > pat['zone_high']:
                        pat['state'] = 1
                elif pat['state'] == 1:
                    touched = (abs(hb - pat['zone_low']) < tol or abs(lb - pat['zone_high']) < tol or
                               abs(hb - pat['zone_high']) < tol or abs(lb - pat['zone_low']) < tol)
                    if touched:
                        pat['state'] = 2
                        pat['retest_bar'] = i
                        pat['bars_since_retest'] = 0
                elif pat['state'] == 2:
                    pat['bars_since_retest'] += 1
                    if pat['bars_since_retest'] > 3:
                        pat['state'] = 6
                        continue
                    exit_down = cb < pat['zone_low']
                    exit_up = cb > pat['zone_high']
                    if exit_down or exit_up:
                        is_break = (pat['type'] == 1 and exit_down) or (pat['type'] == 2 and exit_up)
                        if is_break:
                            spread_pips, limit_pips = get_spread_pips(pair_name, cb, ca)
                            if spread_pips > limit_pips:
                                pat['state'] = 5
                                continue

                            if pat['type'] == 1:
                                cmd = 'SELL'
                                entry_price = pat['zone_low']
                                sl_price = pat['zone_high']
                            else:
                                cmd = 'BUY'
                                entry_price = pat['zone_high']
                                sl_price = pat['zone_low']

                            risk_price = abs(entry_price - sl_price)
                            risk_pips = risk_price / pip_size
                            if risk_pips == 0:
                                pat['state'] = 5
                                continue

                            pip_val = get_pip_value(pair_name, quote, entry_price, ts, ref_prices, 'triangulated')
                            if pip_val is None:
                                pat['state'] = 5
                                continue
                            risk_cents_per_lot = risk_pips * pip_val * 100
                            if risk_cents_per_lot == 0:
                                pat['state'] = 5
                                continue

                            lot = risk_cents / risk_cents_per_lot
                            if SIMULATE_LOT_ROUNDING:
                                lot_step = LOT_STEP
                                lot = np.floor(lot / lot_step) * lot_step
                                lot = max(MIN_LOT, min(MAX_LOT, lot))

                            tp_price = entry_price + 1000 * point_size if cmd == 'BUY' else entry_price - 1000 * point_size

                            pending_orders[pair_name].append({
                                'cmd': cmd,
                                'entry': entry_price,
                                'sl': sl_price,
                                'tp': tp_price,
                                'lot': lot,
                                'risk': risk_price,
                                'pip_val': pip_val,
                                'place_bar': i,
                            })
                            pat['state'] = 3
                        else:
                            pat['state'] = 5

            # Detect new patterns
            o2, h2, l2, c2 = arr_b[i - 2]
            o1, h1, l1, c1 = arr_b[i - 1]
            if hb < l2:
                new_pat = {'state': 0, 'type': 1, 'zone_low': hb, 'zone_high': l2}
            elif lb > h2:
                new_pat = {'state': 0, 'type': 2, 'zone_low': h2, 'zone_high': lb}
            else:
                new_pat = None
            if new_pat is not None:
                if cb < new_pat['zone_low'] or cb > new_pat['zone_high']:
                    new_pat['state'] = 1
                patterns[pair_name].append(new_pat)

            patterns[pair_name] = [p for p in patterns[pair_name] if p['state'] not in (3, 4, 5)]

        # End of month
        if current_month != month_key:
            month_pnl = balance_cents - month_start_balance
            monthly_pnl_list.append(month_pnl)
            monthly_max_dd_list.append(month_max_dd_cents)

            if ts <= first_12_months_end:
                wd_pct = withdrawal_pct_first
            else:
                wd_pct = withdrawal_pct_rest

            if reset_balance_monthly:
                if month_pnl > 0:
                    withdraw_amount = int(month_pnl * wd_pct / 100)
                    total_withdrawn_cents += withdraw_amount
                    remaining_profit = month_pnl - withdraw_amount
                    balance_cents = STARTING_BALANCE_CENTS + remaining_profit
                else:
                    withdraw_amount = 0
                    remaining_profit = month_pnl
                    balance_cents = STARTING_BALANCE_CENTS + remaining_profit
            else:
                if month_pnl > 0:
                    withdraw_amount = int(month_pnl * wd_pct / 100)
                    total_withdrawn_cents += withdraw_amount
                    balance_cents -= withdraw_amount
                else:
                    withdraw_amount = 0

            monthly_details.append({
                'Month': month_key,
                'Starting Balance (cents)': month_start_balance,
                'Monthly P&L (cents)': month_pnl,
                'Withdrawal %': wd_pct,
                'Withdrawn (cents)': withdraw_amount,
                'Remaining P&L (cents)': month_pnl - withdraw_amount,
                'Balance After (cents)': balance_cents,
            })

            current_month = month_key
            month_start_balance = balance_cents
            month_peak = balance_cents
            month_max_dd_cents = 0

    if current_month is not None:
        month_pnl = balance_cents - month_start_balance
        monthly_pnl_list.append(month_pnl)
        monthly_max_dd_list.append(month_max_dd_cents)

    max_dd_cents = max(monthly_max_dd_list) if monthly_max_dd_list else 0
    max_dd_pct = (max_dd_cents / STARTING_BALANCE_CENTS) * 100

    df_trades = pd.DataFrame(trades_log)
    if len(df_trades) == 0:
        return None, None, None

    wins = df_trades[df_trades['pnl_cents'] > 0]['pnl_cents']
    losses = df_trades[df_trades['pnl_cents'] < 0]['pnl_cents']
    pf = abs(wins.sum() / losses.sum()) if losses.sum() != 0 else float('inf')
    win_rate = (df_trades['pnl_cents'] > 0).mean() * 100
    total_withdrawn_usd = total_withdrawn_cents / 100.0
    avg_monthly_usd = total_withdrawn_usd / len(monthly_pnl_list) if monthly_pnl_list else 0

    results = {
        'total_trades': len(df_trades),
        'win_rate': win_rate,
        'profit_factor': pf,
        'total_withdrawn_usd': total_withdrawn_usd,
        'avg_monthly_usd': avg_monthly_usd,
        'max_dd_cents': max_dd_cents,
        'max_dd_percent': max_dd_pct,
    }
    return results, df_trades, monthly_details

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
    try:
        pair_names, master_index, _, _, _ = load_uploaded_data(uploaded_files, start_date=None, end_date=None)
    except Exception as e:
        raise RuntimeError(f"Failed to load data for WFV: {e}")
    if len(master_index) == 0:
        return [], {'Overall Trades': 0, 'Total Withdrawn (USD)': 0, 'Average Monthly (USD)': 0}

    start_year = master_index[0].year
    end_year = master_index[-1].year
    blocks = []
    current_start = start_year
    while current_start <= end_year:
        block_end = min(current_start + block_years - 1, end_year)
        blocks.append((f"{current_start}-{block_end}", current_start, block_end))
        current_start = block_end + 1

    block_results = []
    combined_trades = 0
    combined_withdrawn_usd = 0
    combined_months = 0

    for label, start_year, end_year in blocks:
        start_date = f"{start_year}-01-01"
        end_date = f"{end_year}-12-31"
        results, _, _ = run_backtest_from_files(
            uploaded_files,
            risk_cents=risk_cents,
            withdrawal_pct_first=withdrawal_pct_first,
            withdrawal_pct_rest=withdrawal_pct_rest,
            start_date=start_date,
            end_date=end_date,
            reset_balance_monthly=reset_balance_monthly
        )
        if results is not None:
            block_results.append({
                'Block': label,
                'Trades': results['total_trades'],
                'Win Rate (%)': results['win_rate'],
                'Profit Factor': results['profit_factor'],
                'Total Withdrawn (USD)': results['total_withdrawn_usd'],
                'Avg Monthly (USD)': results['avg_monthly_usd'],
                'Max DD (cents)': results['max_dd_cents'],
                'Max DD (%)': results['max_dd_percent'],
            })
            combined_trades += results['total_trades']
            combined_withdrawn_usd += results['total_withdrawn_usd']
            combined_months += 60
        else:
            block_results.append({
                'Block': label,
                'Trades': 0,
                'Win Rate (%)': 0,
                'Profit Factor': 0,
                'Total Withdrawn (USD)': 0,
                'Avg Monthly (USD)': 0,
                'Max DD (cents)': 0,
                'Max DD (%)': 0,
            })

    summary = {
        'Overall Trades': combined_trades,
        'Total Withdrawn (USD)': combined_withdrawn_usd,
        'Average Monthly (USD)': combined_withdrawn_usd / combined_months if combined_months > 0 else 0,
    }
    return block_results, summary

# --------------------------------------------------------------
# DEMO STRATEGY
# --------------------------------------------------------------
def run_demo_backtest(uploaded_files, risk_cents=RISK_CENTS,
                      start_date=None, end_date=None,
                      demo_sl=20, demo_tp=40,
                      reset_balance_monthly=True):
    pair_names, master_index, bid_arrays, ask_arrays, ref_prices = load_uploaded_data(
        uploaded_files, start_date, end_date
    )
    n = len(master_index)
    if not pair_names:
        return None, None, None
    pair_name = pair_names[0]
    bid_array = bid_arrays[pair_name]
    ask_array = ask_arrays[pair_name]
    close = bid_array[:, 3]

    ma_fast = pd.Series(close).rolling(5).mean().values
    ma_slow = pd.Series(close).rolling(20).mean().values

    balance_cents = float(STARTING_BALANCE_CENTS)
    trades_log = []
    monthly_details = []

    current_month = None
    month_start_balance = balance_cents
    month_peak = balance_cents
    month_max_dd_cents = 0
    monthly_pnl_list = []
    monthly_max_dd_list = []

    pip_size = get_pip_size(get_pair_currencies(pair_name)[1])
    point_size = pip_size / 10.0

    for i in range(20, n - 1):
        ts = master_index[i]
        month_key = ts.strftime('%Y-%m')
        if current_month is None:
            current_month = month_key
            month_start_balance = balance_cents
            month_peak = balance_cents
            month_max_dd_cents = 0

        buy_signal = ma_fast[i] > ma_slow[i] and ma_fast[i-1] <= ma_slow[i-1]
        sell_signal = ma_fast[i] < ma_slow[i] and ma_fast[i-1] >= ma_slow[i-1]

        if buy_signal:
            entry_price = ask_array[i][3]
            sl_price = entry_price - demo_sl * pip_size
            tp_price = entry_price + demo_tp * pip_size
            cmd = 'BUY'
            risk_pips = demo_sl
            pip_val = get_pip_value(pair_name, get_pair_currencies(pair_name)[1], entry_price, ts, ref_prices, 'triangulated')
            if pip_val is None:
                continue
            risk_cents_per_lot = risk_pips * pip_val * 100
            lot = risk_cents / risk_cents_per_lot

            exit_price = close[i+1]
            pnl_cents = ((exit_price - entry_price) / pip_size) * pip_val * 100 * lot
            balance_cents += pnl_cents
            trades_log.append({
                'pair': pair_name, 'type': cmd, 'entry_bar': i, 'exit_bar': i+1,
                'entry': entry_price, 'exit': exit_price, 'reason': 'TP/SL',
                'pnl_cents': pnl_cents, 'lot': lot, 'risk_pips': risk_pips,
                'be_set': False, 'balance_after': balance_cents, 'year': ts.year,
            })
            if balance_cents > month_peak:
                month_peak = balance_cents
            dd = month_peak - balance_cents
            if dd > month_max_dd_cents:
                month_max_dd_cents = dd

        elif sell_signal:
            entry_price = bid_array[i][3]
            sl_price = entry_price + demo_sl * pip_size
            tp_price = entry_price - demo_tp * pip_size
            cmd = 'SELL'
            risk_pips = demo_sl
            pip_val = get_pip_value(pair_name, get_pair_currencies(pair_name)[1], entry_price, ts, ref_prices, 'triangulated')
            if pip_val is None:
                continue
            risk_cents_per_lot = risk_pips * pip_val * 100
            lot = risk_cents / risk_cents_per_lot

            exit_price = close[i+1]
            pnl_cents = ((entry_price - exit_price) / pip_size) * pip_val * 100 * lot
            balance_cents += pnl_cents
            trades_log.append({
                'pair': pair_name, 'type': cmd, 'entry_bar': i, 'exit_bar': i+1,
                'entry': entry_price, 'exit': exit_price, 'reason': 'TP/SL',
                'pnl_cents': pnl_cents, 'lot': lot, 'risk_pips': risk_pips,
                'be_set': False, 'balance_after': balance_cents, 'year': ts.year,
            })
            if balance_cents > month_peak:
                month_peak = balance_cents
            dd = month_peak - balance_cents
            if dd > month_max_dd_cents:
                month_max_dd_cents = dd

        if current_month != month_key:
            month_pnl = balance_cents - month_start_balance
            monthly_pnl_list.append(month_pnl)
            monthly_max_dd_list.append(month_max_dd_cents)
            monthly_details.append({
                'Month': month_key,
                'Starting Balance (cents)': month_start_balance,
                'Monthly P&L (cents)': month_pnl,
                'Withdrawal %': 0,
                'Withdrawn (cents)': 0,
                'Remaining P&L (cents)': month_pnl,
                'Balance After (cents)': balance_cents,
            })
            current_month = month_key
            month_start_balance = balance_cents
            month_peak = balance_cents
            month_max_dd_cents = 0

    if current_month is not None:
        month_pnl = balance_cents - month_start_balance
        monthly_pnl_list.append(month_pnl)
        monthly_max_dd_list.append(month_max_dd_cents)

    max_dd_cents = max(monthly_max_dd_list) if monthly_max_dd_list else 0
    max_dd_pct = (max_dd_cents / STARTING_BALANCE_CENTS) * 100

    df_trades = pd.DataFrame(trades_log)
    if len(df_trades) == 0:
        return None, None, None

    wins = df_trades[df_trades['pnl_cents'] > 0]['pnl_cents']
    losses = df_trades[df_trades['pnl_cents'] < 0]['pnl_cents']
    pf = abs(wins.sum() / losses.sum()) if losses.sum() != 0 else float('inf')
    win_rate = (df_trades['pnl_cents'] > 0).mean() * 100
    total_withdrawn_usd = 0

    results = {
        'total_trades': len(df_trades),
        'win_rate': win_rate,
        'profit_factor': pf,
        'total_withdrawn_usd': total_withdrawn_usd,
        'avg_monthly_usd': total_withdrawn_usd / len(monthly_pnl_list) if monthly_pnl_list else 0,
        'max_dd_cents': max_dd_cents,
        'max_dd_percent': max_dd_pct,
    }
    return results, df_trades, monthly_details

# ==============================================================
# DYNAMIC STRATEGY EXECUTION (from generated code, with DataFrame)
# ==============================================================
def run_generated_strategy_from_df(data, user_code, params, initial_balance=10000):
    """
    Runs a generated strategy directly on a DataFrame (no file uploads).
    data must have columns: open, high, low, close.
    """
    # Ensure column names are lowercase
    data.columns = [col.lower() for col in data.columns]

    # Forward fill any NaN
    data = data.ffill().bfill()

    # Add prev_day_close using resample (assumes datetime index)
    if isinstance(data.index, pd.DatetimeIndex):
        daily_close = data['close'].resample('D').last()
        prev_day_close = daily_close.shift(1).reindex(data.index, method='ffill')
        data['prev_day_close'] = prev_day_close
    else:
        # Fallback: shift by 24 bars (assuming hourly)
        data['prev_day_close'] = data['close'].shift(24)

    # Clean user code: replace uppercase column names
    user_code_fixed = user_code
    for col in ['Close', 'High', 'Low', 'Open']:
        user_code_fixed = user_code_fixed.replace(f"['{col}']", f"['{col.lower()}']")
        user_code_fixed = user_code_fixed.replace(f'["{col}"]', f'["{col.lower()}"]')

    # Execute user code
    local_scope = {'Strategy': Strategy, 'pd': pd, 'np': np}
    try:
        exec(user_code_fixed, local_scope)
        UserStrategy = local_scope['UserStrategy']
    except Exception as e:
        raise RuntimeError(f"Error in user code: {e}")

    # Instantiate and set params
    strategy = UserStrategy(data)
    strategy.stop_loss_pips = params.get('stop_loss_pips', 20)
    strategy.take_profit_pips = params.get('take_profit_pips', 40)
    strategy.risk_per_trade = params.get('risk_per_trade', 2.0)
    strategy.init()

    # Simulation loop
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
        elif current_pos == 0 and in_position:
            exit_price = data['close'].iloc[i]
            if entry_type == 'BUY':
                pnl = (exit_price - entry_price) * 100000  # simplistic lot size
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
        debug_info = {
            "strategy_code": user_code_fixed,
            "data_head": data.head(10).to_dict(),
            "data_shape": data.shape,
            "columns": data.columns.tolist(),
            "message": "No trades generated. Check conditions."
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
