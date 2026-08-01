import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

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

INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "1h",   # Yahoo doesn't have 4h; we fetch 1h and resample
    "1d": "1d",
    "1w": "1wk",
    "1mn": "1mo",
}

def fetch_forex_data(symbol, start_date, end_date, interval="1h"):
    """
    Fetch OHLC data from Yahoo Finance with robust error handling.
    """
    ticker = PAIR_MAP.get(symbol.upper())
    if not ticker:
        raise ValueError(f"Symbol {symbol} not supported. Available: {list(PAIR_MAP.keys())}")

    # Convert dates to datetime
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    days = (end_dt - start_dt).days

    # Map interval
    yf_interval = INTERVAL_MAP.get(interval, "1h")
    resample_4h = (interval == "4h")
    if resample_4h:
        yf_interval = "1h"

    # Check if the date range is too far back for intraday data
    # Yahoo only allows intraday data within the last 730 days from today
    if yf_interval in ["1m", "5m", "15m", "30m", "1h"]:
        today = datetime.now()
        oldest_allowed = today - timedelta(days=730)
        if end_dt < oldest_allowed:
            raise ValueError(
                f"Yahoo Finance only provides intraday data for the last 730 days. "
                f"Your range ends on {end_date}, which is before {oldest_allowed.strftime('%Y-%m-%d')}. "
                f"Please use daily or weekly data for older ranges."
            )

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

    # ---- Handle different return types ----
    if df is None:
        raise ValueError(f"No data returned for {symbol} from {start_date} to {end_date} with interval {interval}. "
                         f"The ticker may not be available or the date range is invalid.")

    if not isinstance(df, pd.DataFrame):
        # If it's a tuple, it might be an error from yfinance
        if isinstance(df, tuple):
            raise TypeError(f"Yahoo Finance returned an error tuple: {df}. "
                            f"The ticker '{ticker}' may be delisted or invalid. "
                            f"Try a different currency pair.")
        else:
            raise TypeError(f"Unexpected data type from Yahoo Finance: {type(df)}. "
                            f"Try a different interval or date range.")

    if df.empty:
        # For 4h, we used 1h, which might be too short for the range; fallback suggestion.
        if interval == "4h":
            raise ValueError(f"No 1-hour data found for {symbol} from {start_date} to {end_date} to create 4-hour bars. "
                             f"Try using '1d' (daily) or a different date range.")
        else:
            raise ValueError(f"Empty DataFrame for {symbol} from {start_date} to {end_date} with interval {interval}. "
                             f"Try a different interval or date range.")

    # Ensure required columns exist
    required_cols = ['Open', 'High', 'Low', 'Close']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Data missing required columns: {missing}. Found columns: {df.columns.tolist()}")

    # Clean and select
    df.columns = [c.lower() for c in df.columns]
    df = df[['open', 'high', 'low', 'close']]

    if resample_4h:
        df = df.resample('4H').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last'
        }).dropna()
        if df.empty:
            raise ValueError(f"No 4-hour bars could be created from 1-hour data. "
                             f"Try a different date range or use daily data.")

    df = df.dropna()
    if df.empty:
        raise ValueError(f"All rows were dropped after cleaning. Try a different date range or interval.")

    return df

def get_available_pairs():
    return list(PAIR_MAP.keys())
