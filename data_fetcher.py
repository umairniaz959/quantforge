import pandas as pd
import numpy as np
import requests
import io
import pickle
import time
from datetime import datetime, timedelta
from pathlib import Path
import yfinance as yf

# ---------- Configuration ----------
CACHE_DIR = Path("data_cache")
CACHE_DIR.mkdir(exist_ok=True)

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

# ---------- Cache ----------
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

# ---------- Dukascopy Direct ----------
def fetch_dukascopy_direct(symbol, start_date, end_date, interval, retries=3):
    instrument = PAIR_MAP.get(symbol.upper())
    if not instrument:
        return None

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    instrument_code = instrument.replace("/", "")

    all_dfs = []
    current = start_dt
    total_days = (end_dt - start_dt).days + 1
    print(f"Fetching {symbol} from Dukascopy: {total_days} days...")

    while current <= end_dt:
        year = current.year
        month = str(current.month).zfill(2)
        day = str(current.day).zfill(2)
        url = f"https://data.dukascopy.com/datafeed/{instrument_code}/{year}/{month}/{day}/00h_tick.csv"

        for attempt in range(retries):
            try:
                resp = requests.get(url, timeout=15)
                if resp.status_code == 200:
                    df_day = pd.read_csv(io.StringIO(resp.text),
                                         names=['timestamp', 'bid', 'ask', 'volume'])
                    df_day['timestamp'] = pd.to_datetime(df_day['timestamp'], unit='ms')
                    df_day.set_index('timestamp', inplace=True)
                    ohlc = df_day['bid'].resample(RESAMPLE_MAP[interval]).ohlc()
                    ohlc.columns = ['open', 'high', 'low', 'close']
                    ohlc = ohlc.dropna()
                    if not ohlc.empty:
                        all_dfs.append(ohlc)
                    break
                else:
                    break
            except Exception:
                time.sleep(1)
        current += timedelta(days=1)

    if not all_dfs:
        return None

    df = pd.concat(all_dfs)
    df = df[~df.index.duplicated(keep='first')]
    df = df.sort_index()
    df = df.dropna()
    return df

# ---------- Yahoo fallback with tuple check ----------
def fetch_yahoo(symbol, start_date, end_date, interval):
    ticker = YAHOO_MAP.get(symbol.upper())
    if not ticker:
        return None

    yf_interval_map = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "4h": "1h",
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

    # ---- FIX: Check for tuple ----
    if df is None:
        return None
    if isinstance(df, tuple):
        # If it's a tuple, it's likely an error tuple (None, error)
        return None

    if df.empty:
        return None

    # Ensure columns exist
    if not all(c in df.columns for c in ['Open', 'High', 'Low', 'Close']):
        return None

    df.columns = [c.lower() for c in df.columns]
    df = df[['open', 'high', 'low', 'close']]

    if resample_4h:
        if len(df) < 4:
            return None
        df = df.resample('4h').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last'
        }).dropna()

    return df.dropna()

# ---------- Synthetic ----------
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
    key = get_cache_key(symbol, start_date, end_date, interval)
    cached = load_from_cache(key)
    if cached is not None:
        return cached, 'cache', False

    # 1. Dukascopy
    df = fetch_dukascopy_direct(symbol, start_date, end_date, interval)
    if df is not None and not df.empty:
        save_to_cache(key, df)
        return df, 'dukascopy', False

    # 2. Yahoo
    df = fetch_yahoo(symbol, start_date, end_date, interval)
    if df is not None and not df.empty:
        save_to_cache(key, df)
        return df, 'yahoo', False

    # 3. Synthetic
    df = generate_synthetic_data(symbol, start_date, end_date, interval)
    save_to_cache(key, df)
    return df, 'synthetic', True

def get_available_pairs():
    return list(PAIR_MAP.keys())
