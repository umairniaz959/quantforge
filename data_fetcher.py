import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import requests
import io
import zipfile
import os
import pickle
from pathlib import Path

# ---------- Configuration ----------
CACHE_DIR = Path("data_cache")
CACHE_DIR.mkdir(exist_ok=True)

# Supported pairs
PAIR_MAP = {
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

INSTRUMENT_MAP = {
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

INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "1h",   # Yahoo doesn't have 4h; we'll resample
    "1d": "1d",
    "1w": "1wk",
    "1mn": "1mo",
}

# Dukascopy period codes (in minutes)
DUKAS_PERIOD = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
    "1w": 10080,
    "1mn": 43200,
}

# ---------- Helper: generate synthetic data ----------
def generate_synthetic_data(symbol, start_date, end_date, interval, seed=42):
    """Generate a random walk price series as ultimate fallback."""
    np.random.seed(seed)
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    
    # Map interval to frequency for date range
    freq_map = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1H",
        "4h": "4H",
        "1d": "1D",
        "1w": "1W",
        "1mn": "1MS",
    }
    freq = freq_map.get(interval, "1H")
    idx = pd.date_range(start=start, end=end, freq=freq)
    if len(idx) == 0:
        idx = pd.date_range(start=start, periods=100, freq=freq)
    
    # Random walk
    n = len(idx)
    returns = np.random.normal(0, 0.01, n)
    price = 1.0 + np.cumsum(returns)
    price = np.maximum(price, 0.5)  # floor
    
    df = pd.DataFrame({
        'open': price * (1 + np.random.normal(0, 0.001, n)),
        'high': price * (1 + np.abs(np.random.normal(0, 0.002, n))),
        'low': price * (1 - np.abs(np.random.normal(0, 0.002, n))),
        'close': price * (1 + np.random.normal(0, 0.001, n)),
    }, index=idx)
    
    # Ensure high is max, low is min
    df['high'] = df[['open', 'high', 'close']].max(axis=1)
    df['low'] = df[['open', 'low', 'close']].min(axis=1)
    df = df[['open', 'high', 'low', 'close']]
    return df

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

# ---------- Dukascopy fetcher ----------
def fetch_dukascopy(symbol, start_date, end_date, interval):
    """Attempt to fetch from Dukascopy's public data feed."""
    instrument = INSTRUMENT_MAP.get(symbol.upper())
    if not instrument:
        return None
    
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    # For 4h, we need 1h data, so we adjust
    if interval == "4h":
        interval = "1h"
    
    period = DUKAS_PERIOD.get(interval)
    if period is None:
        return None
    
    instrument_code = instrument.replace("/", "")
    
    all_data = []
    current_date = start_dt
    while current_date <= end_dt:
        year = current_date.year
        month = str(current_date.month).zfill(2)
        day = str(current_date.day).zfill(2)
        
        # Try to get tick data (CSV)
        csv_url = f"https://data.dukascopy.com/datafeed/{instrument_code}/{year}/{month}/{day}/00h_tick.csv"
        try:
            response = requests.get(csv_url, timeout=10)
            if response.status_code == 200:
                df_day = pd.read_csv(io.StringIO(response.text), 
                                    names=['timestamp', 'bid', 'ask', 'volume'])
                df_day['timestamp'] = pd.to_datetime(df_day['timestamp'], unit='ms')
                if not df_day.empty:
                    df_day.set_index('timestamp', inplace=True)
                    # Resample to requested interval
                    ohlc = df_day['bid'].resample(interval).ohlc()
                    ohlc.columns = ['open', 'high', 'low', 'close']
                    all_data.append(ohlc)
        except Exception:
            pass
        current_date += timedelta(days=1)
    
    if not all_data:
        return None
    
    df = pd.concat(all_data)
    df = df[~df.index.duplicated(keep='first')]
    df = df.sort_index()
    df = df.dropna()
    return df

# ---------- Yahoo fetcher ----------
def fetch_yahoo(symbol, start_date, end_date, interval):
    ticker = PAIR_MAP.get(symbol.upper())
    if not ticker:
        return None
    
    yf_interval = INTERVAL_MAP.get(interval, "1d")
    resample_4h = (interval == "4h")
    if resample_4h:
        yf_interval = "1h"
    
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
    
    required_cols = ['Open', 'High', 'Low', 'Close']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        return None
    
    df.columns = [c.lower() for c in df.columns]
    df = df[['open', 'high', 'low', 'close']]
    
    if resample_4h:
        if len(df) < 4:
            return None
        df = df.resample('4H').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last'
        }).dropna()
    
    df = df.dropna()
    return df if not df.empty else None

# ---------- Main hybrid function ----------
def fetch_forex_data(symbol, start_date, end_date, interval="1h"):
    """
    Hybrid data fetcher – tries multiple sources, guarantees data.
    Returns (DataFrame, provider_name, was_fallback).
    provider_name can be: 'dukascopy', 'yahoo', 'synthetic'
    """
    # Check cache first
    key = get_cache_key(symbol, start_date, end_date, interval)
    cached = load_from_cache(key)
    if cached is not None:
        return cached, 'cache', False
    
    # Try Dukascopy (best for intraday)
    df = fetch_dukascopy(symbol, start_date, end_date, interval)
    if df is not None and not df.empty:
        save_to_cache(key, df)
        return df, 'dukascopy', False
    
    # Try Yahoo Finance
    df = fetch_yahoo(symbol, start_date, end_date, interval)
    if df is not None and not df.empty:
        save_to_cache(key, df)
        return df, 'yahoo', False
    
    # Ultimate fallback: synthetic data
    df = generate_synthetic_data(symbol, start_date, end_date, interval)
    save_to_cache(key, df)
    return df, 'synthetic', True

def get_available_pairs():
    return list(PAIR_MAP.keys())
