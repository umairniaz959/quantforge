# data_fetcher.py

import pandas as pd
import yfinance as yf
from datetime import datetime

# Supported pairs – Yahoo Finance uses "EURUSD=X" format
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

# Yahoo Finance supports these intervals
INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "1h",   # Yahoo doesn't have 4h; we'll fetch 1h and resample later (or just use 1h)
    "1d": "1d",
    "1w": "1wk",
    "1mn": "1mo",
}

def fetch_forex_data(symbol, start_date, end_date, interval="1h"):
    """
    Fetch OHLC data from Yahoo Finance for a currency pair.

    Args:
        symbol (str): e.g., "EURUSD"
        start_date (str): "YYYY-MM-DD"
        end_date (str): "YYYY-MM-DD"
        interval (str): "1m", "5m", "15m", "30m", "1h", "1d", "1w", "1mn"

    Returns:
        pd.DataFrame with columns: open, high, low, close
    """
    ticker = PAIR_MAP.get(symbol.upper())
    if not ticker:
        raise ValueError(f"Symbol {symbol} not supported. Available: {list(PAIR_MAP.keys())}")

    # Map interval – if 4h, we use 1h and then resample later (optional)
    yf_interval = INTERVAL_MAP.get(interval, "1h")
    if interval == "4h":
        # We'll fetch 1h and resample to 4h
        yf_interval = "1h"
        resample_4h = True
    else:
        resample_4h = False

    try:
        df = yf.download(
            tickers=ticker,
            start=start_date,
            end=end_date,
            interval=yf_interval,
            progress=False,
            auto_adjust=False
        )
    except Exception as e:
        raise RuntimeError(f"Failed to fetch data from Yahoo Finance: {e}")

    if df.empty:
        raise ValueError(f"No data returned for {symbol} from {start_date} to {end_date}")

    # Clean columns (lowercase)
    df.columns = [c.lower() for c in df.columns]
    # Keep only OHLC
    df = df[['open', 'high', 'low', 'close']]

    # Resample to 4h if needed
    if resample_4h:
        # Resample using OHLC aggregation
        df = df.resample('4H').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last'
        }).dropna()

    # Drop any NaN rows
    df = df.dropna()

    return df

def get_available_pairs():
    """Return list of supported currency pairs."""
    return list(PAIR_MAP.keys())
