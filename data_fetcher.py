import pandas as pd
from datetime import datetime
from dukascopy import Dukascopy

# Mapping from our interval strings to Dukascopy periods
PERIOD_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
    "1w": "1w",
    "1mn": "1mn",
}

# Dukascopy instrument names (they use "EUR/USD" format)
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

def fetch_forex_data(symbol, start_date, end_date, interval="1h"):
    """
    Fetch OHLC data from Dukascopy for any timeframe.
    Returns a DataFrame with columns: open, high, low, close.
    """
    # Validate symbol
    instrument = INSTRUMENT_MAP.get(symbol.upper())
    if not instrument:
        raise ValueError(f"Symbol {symbol} not supported. Available: {list(INSTRUMENT_MAP.keys())}")

    # Validate interval
    period = PERIOD_MAP.get(interval)
    if not period:
        raise ValueError(f"Interval {interval} not supported. Use: {list(PERIOD_MAP.keys())}")

    # Convert dates
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    # Dukascopy client
    client = Dukascopy()

    try:
        # Fetch data – returns list of (timestamp, open, high, low, close, volume)
        data = client.get_instrument_data(
            instrument=instrument,
            start=start_dt,
            end=end_dt,
            period=period
        )
    except Exception as e:
        raise RuntimeError(f"Failed to fetch data from Dukascopy: {e}")

    if not data:
        raise ValueError(
            f"No data returned for {symbol} from {start_date} to {end_date} with interval {interval}.\n"
            f"The date range may be outside the available history or the pair may not have data."
        )

    # Convert to DataFrame
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)

    # Keep only OHLC
    df = df[['open', 'high', 'low', 'close']]

    # Drop any NaN rows
    df = df.dropna()

    if df.empty:
        raise ValueError(f"All rows dropped after cleaning. Try a different date range.")

    return df

def get_available_pairs():
    return list(INSTRUMENT_MAP.keys())
