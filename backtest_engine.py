import pandas as pd
import numpy as np
from datetime import timedelta

# (All global settings remain the same as before)

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

def get_pip_value(pair_name, quote, price, timestamp, ref_prices, mode='static'):
    if mode == 'static':
        return get_pip_value_usd_static(quote, price)
    return get_pip_value_usd_triangulated(pair_name, price, timestamp, ref_prices)

# --------------------------------------------------------------
# Data loading from uploaded files (fixed)
# --------------------------------------------------------------
def load_uploaded_data(uploaded_files, start_date=None, end_date=None):
    """
    uploaded_files: dict {filename: UploadedFile object} from Streamlit
    Returns: pair_names, master_index, bid_arrays, ask_arrays, ref_prices
    """
    all_files = list(uploaded_files.keys())
    pairs = pair_files(all_files)
    if not pairs:
        raise RuntimeError("No paired BID/ASK files found. Make sure you upload both BID and ASK files for each pair.")

    bid_dfs, ask_dfs = {}, {}
    for bid_file, ask_file, pair_name in pairs:
        try:
            # Use the file object directly
            df_bid = pd.read_csv(uploaded_files[bid_file])
            df_ask = pd.read_csv(uploaded_files[ask_file])
        except Exception as e:
            raise RuntimeError(f"Failed to read file {bid_file} or {ask_file}: {e}")

        # Check if dataframes are empty
        if df_bid.empty or df_ask.empty:
            raise RuntimeError(f"File {bid_file} or {ask_file} is empty.")

        # Convert timestamp column to datetime and set as index
        for df in (df_bid, df_ask):
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
            else:
                # Look for a date-like column
                date_col = next((c for c in df.columns if 'date' in c.lower() or 'time' in c.lower()), None)
                if date_col:
                    df[date_col] = pd.to_datetime(df[date_col])
                    df.set_index(date_col, inplace=True)
                else:
                    # If no timestamp, assume first column is datetime
                    df.index = pd.to_datetime(df.iloc[:, 0])
                    df = df.iloc[:, 1:]
        df_bid = clean_columns(df_bid).sort_index()
        df_ask = clean_columns(df_ask).sort_index()
        bid_dfs[pair_name] = df_bid[['open', 'high', 'low', 'close']]
        ask_dfs[pair_name] = df_ask[['open', 'high', 'low', 'close']]

    # Create master index
    master_index = None
    for df in bid_dfs.values():
        master_index = df.index if master_index is None else master_index.union(df.index)
    master_index = master_index.sort_values()

    # Handle timezone
    if master_index.tz is None:
        master_index = master_index.tz_localize('UTC')
    else:
        master_index = master_index.tz_convert('UTC')

    # Apply date filter
    if start_date is not None:
        start_dt = pd.to_datetime(start_date).tz_localize('UTC')
        master_index = master_index[master_index >= start_dt]
    if end_date is not None:
        end_dt = pd.to_datetime(end_date).tz_localize('UTC')
        master_index = master_index[master_index <= end_dt]

    if len(master_index) == 0:
        raise RuntimeError("No data in the selected date range.")

    # Reindex arrays
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

# (rest of the file remains unchanged: get_spread_pips, run_simulation_on_arrays, run_backtest_from_files, run_wfv_from_files)
