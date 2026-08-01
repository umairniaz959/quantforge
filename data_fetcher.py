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
    "4h": "1h",   # Yahoo doesn't have 4h; we'll resample
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

    yf_interval = INTERVAL_MAP.get(interval, "1h")
    resample_4h = (interval == "4h")
    if resample_4h:
        yf_interval = "1h"

    # For intraday intervals, Yahoo has a 730-day limit.
    # If the range exceeds 730 days and interval is intraday, warn and use daily.
    intraday_intervals = ["1m", "5m", "15m", "30m", "1h"]
    if interval in intraday_intervals and days > 730:
        raise ValueError(
            f"Yahoo Finance only allows up to 730 days of intraday data. "
            f"Your range is {days} days. Please shorten the date range or use daily/weekly data."
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

    # If df is empty or not a DataFrame, handle
    if df is None or df.empty:
        raise ValueError(f"No data returned for {symbol} from {start_date} to {end_date} with interval {interval}. "
                         f"Try a different interval or date range.")
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"Unexpected data format from Yahoo Finance: {type(df)}. "
                        f"Try a different interval or date range.")

    # Ensure columns exist
    if 'Open' not in df.columns:
        raise ValueError(f"Data does not contain expected OHLC columns. Found: {df.columns.tolist()}")

    df.columns = [c.lower() for c in df.columns]
    df = df[['open', 'high', 'low', 'close']]

    if resample_4h:
        df = df.resample('4H').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last'
        }).dropna()

    df = df.dropna()
    return df

def get_available_pairs():
    return list(PAIR_MAP.keys())
