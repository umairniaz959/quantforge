import pandas as pd
import numpy as np
import requests
import io
import pickle
import time
from datetime import datetime, timedelta
from pathlib import Path
import yfinance as yf  # fallback

# ---------- Configuration ----------
CACHE_DIR = Path("data_cache")
CACHE_DIR.mkdir(exist_ok=True)

# Supported pairs
PAIR_MAP = {
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY",
    "AUDUSD": "AUD/USD",
    "USDCAD": "USD/CAD",
    "USDCHF": "USD/CHF",
    "NZDUSD": "NZD/USD",
    "EURGBP": "EUR/GBP",
    "EURJPY": "EUR/JPY",
    "GBPJPY": "GBP/JPY",
}

# Map our interval strings to pandas resample frequency
# Valid pandas offset strings: https://pandas.pydata.org/docs/user_guide/timeseries.html#offset-aliases
RESAMPLE_MAP = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1D",
    "1w": "1W",
    "1mn": "1MS",
}

# For Yahoo fallback
YAHOO_MAP = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "USDCAD=X",
    "USDCHF": "USDCHF=X",
    "NZDUSD": "NZDUSD=X",
    "EURGBP": "EURGBP=X",
    "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X",
}

# ---------- Cache helpers ----------
def get_cache_key(symbol, start, end, interval):
    return f"{symbol}_{start}_{end}_{interval}.pkl"

def load_from_cache(key):
    path = CACHE_DIR / key
    if path.exists():
        with open(path, 'rb') as f:
            return pickle.load(f)
    return None

def save_to_cache(key, df):
    path = CACHE_DIR / key
    with open(path, 'wb') as f:
        pickle.dump(df, f)

# ---------- Dukascopy Direct HTTP (primary) ----------
def fetch_dukascopy_direct(symbol, start_date, end_date, interval, retries=3):
    """
    Fetch OHLC data directly from Dukascopy's public tick CSV endpoint.
    Downloads tick data for each day and resamples to the requested interval.
    Returns DataFrame or None on failure.
    """
    instrument = PAIR_MAP.get(symbol.upper())
    if not instrument:
        return None
    
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    instrument_code = instrument.replace("/", "")  # "EUR/USD" → "EURUSD"
    
    # We'll collect daily DataFrames and then concatenate
    all_dfs = []
    current = start_dt
    total_days = (end_dt - start_dt).days + 1
    
    # Show progress (we can log to console)
    print(f"Fetching {symbol} from Dukascopy: {total_days} days...")
    
    while current <= end_dt:
        year = current.year
        month = str(current.month).zfill(2)
        day = str(current.day).zfill(2)
        
        # Dukascopy tick CSV URL (for the whole day)
        url = f"https://data.dukascopy.com/datafeed/{instrument_code}/{year}/{month}/{day}/00h_tick.csv"
        
        df_day = None
        for attempt in range(retries):
            try:
                resp = requests.get(url, timeout=15)
                if resp.status_code == 200:
                    # Parse CSV: columns are timestamp, bid, ask, volume (all in ms)
                    df_day = pd.read_csv(io.StringIO(resp.text), 
                                        names=['timestamp', 'bid', 'ask', 'volume'])
                    df_day['timestamp'] = pd.to_datetime(df_day['timestamp'], unit='ms')
                    df_day.set_index('timestamp', inplace=True)
                    # Resample to the target interval
                    # Use the 'bid' price as representative; you could also use (bid+ask)/2
                    ohlc = df_day['bid'].resample(RESAMPLE_MAP[interval]).ohlc()
                    ohlc.columns = ['open', 'high', 'low', 'close']
                    # Drop rows with NaN (bars with no data)
                    ohlc = ohlc.dropna()
                    if not ohlc.empty:
                        all_dfs.append(ohlc)
                    break  # success, exit retry loop
                else:
                    # 404 often means no data for that day (weekend/holiday) – skip silently
                    break
            except Exception as e:
                print(f"  Attempt {attempt+1} failed for {year}-{month}-{day}: {e}")
                time.sleep(1)  # wait before retry
        # Move to next day
        current += timedelta(days=1)
    
    if not all_dfs:
        return None
    
    # Concatenate all days
    df = pd.concat(all_dfs)
    # Remove duplicate indices (in case of overlapping)
    df = df[~df.index.duplicated(keep='first')]
    df = df.sort_index()
    # Drop any remaining NaN
    df = df.dropna()
    
    # If interval is 4h, we already resampled to 4h directly from ticks,
    # but the tick data is resampled to 4h correctly.
    # However, if you prefer to resample from 1h, that's also possible.
    # Here we resample directly from ticks to the target, which is fine.
    
    return df

# ---------- Yahoo fallback (for daily and above) ----------
def fetch_yahoo(symbol, start_date, end_date, interval):
    ticker = YAHOO_MAP.get(symbol.upper())
    if not ticker:
        return None
    
    # Yahoo intervals: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
    yf_interval_map = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "4h": "1h",      # Yahoo doesn't have 4h; will resample later
        "1d": "1d",
        "1w": "1wk",
        "1mn": "1mo",
    }
    yf_interval = yf_interval_map.get(interval, "1d")
    resample_4h = (interval == "4h")
    
    try:
        df = yf.download(
            tickers=ticker,
            start=start_date,
            end=end_date,
            interval=yf_interval,
            progress=False,
            auto_adjust=False
        )
    except Exception:
        return None
    
    if df is None or df.empty:
        return None
    
    df.columns = [c.lower() for c in df.columns]
    required = ['open', 'high', 'low', 'close']
    if not all(c in df.columns for c in required):
        return None
    df = df[required]
    
    if resample_4h:
        df = df.resample('4h').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last'
        }).dropna()
    
    return df.dropna()

# ---------- Synthetic fallback ----------
def generate_synthetic_data(symbol, start_date, end_date, interval, seed=42):
    np.random.seed(seed)
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    
    freq_map = {
        "1m": "min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "h",
        "4h": "4h",
        "1d": "D",
        "1w": "W",
        "1mn": "MS",
    }
    freq = freq_map.get(interval, "h")
    idx = pd.date_range(start=start, end=end, freq=freq)
    if len(idx) == 0:
        idx = pd.date_range(start=start, periods=100, freq=freq)
    
    n = len(idx)
    returns = np.random.normal(0, 0.01, n)
    price = 1.0 + np.cumsum(returns)
    price = np.maximum(price, 0.5)
    
    df = pd.DataFrame({
        'open': price * (1 + np.random.normal(0, 0.001, n)),
        'high': price * (1 + np.abs(np.random.normal(0, 0.002, n))),
        'low': price * (1 - np.abs(np.random.normal(0, 0.002, n))),
        'close': price * (1 + np.random.normal(0, 0.001, n)),
    }, index=idx)
    df['high'] = df[['open', 'high', 'close']].max(axis=1)
    df['low'] = df[['open', 'low', 'close']].min(axis=1)
    return df[['open', 'high', 'low', 'close']]

# ---------- Main hybrid function ----------
def fetch_forex_data(symbol, start_date, end_date, interval="1h"):
    """
    Hybrid data fetcher:
    1. Try Dukascopy direct HTTP (primary)
    2. If fails, try Yahoo Finance (fallback)
    3. If still fails, generate synthetic data (ultimate fallback)
    Returns: (DataFrame, provider_name, was_fallback)
    """
    # Check cache
    key = get_cache_key(symbol, start_date, end_date, interval)
    cached = load_from_cache(key)
    if cached is not None:
        return cached, 'cache', False
    
    # 1. Dukascopy Direct HTTP
    df = fetch_dukascopy_direct(symbol, start_date, end_date, interval)
    if df is not None and not df.empty:
        save_to_cache(key, df)
        return df, 'dukascopy', False
    
    # 2. Yahoo Finance (fallback)
    df = fetch_yahoo(symbol, start_date, end_date, interval)
    if df is not None and not df.empty:
        save_to_cache(key, df)
        return df, 'yahoo', False
    
    # 3. Synthetic (ultimate fallback)
    df = generate_synthetic_data(symbol, start_date, end_date, interval)
    save_to_cache(key, df)
    return df, 'synthetic', True

def get_available_pairs():
    return list(PAIR_MAP.keys())
