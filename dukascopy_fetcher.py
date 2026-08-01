import pandas as pd
from datetime import datetime
from dukascopy import Dukascopy

# Mapping of currency pairs to Dukascopy instrument codes
# (The library uses the same format: EUR/USD, GBP/USD, etc.)
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

# Timeframe mapping – same as before
INTERVAL_MAP = {
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

def fetch_forex_data(symbol, start_date, end_date, interval="1h"):
    """
    Fetch OHLC data from Dukascopy for a given currency pair.

    Args:
        symbol (str): e.g., "EURUSD"
        start_date (str): "YYYY-MM-DD"
        end_date (str): "YYYY-MM-DD"
        interval (str): timeframe, e.g., "1h", "1d"

    Returns:
        pd.DataFrame with columns: open, high, low, close
    """
    instrument = INSTRUMENT_MAP.get(symbol.upper())
    if not instrument:
        raise ValueError(f"Symbol {symbol} not supported. Available: {list(INSTRUMENT_MAP.keys())}")

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    interval_d = INTERVAL_MAP.get(interval)
    if not interval_d:
        raise ValueError(f"Interval {interval} not supported. Use one of: {list(INTERVAL_MAP.keys())}")

    client = Dukascopy()

    try:
        # The dukascopy library returns a list of tuples: (timestamp, open, high, low, close, volume)
        data = client.get_instrument_data(
            instrument=instrument,
            start=start,
            end=end,
            period=interval_d
        )
    except Exception as e:
        raise RuntimeError(f"Failed to fetch data from Dukascopy: {e}")

    if not data:
        raise ValueError(f"No data returned for {symbol} from {start_date} to {end_date}")

    # Convert to DataFrame
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')  # Dukascopy returns timestamps in ms
    df.set_index('timestamp', inplace=True)

    # Keep only OHLC
    df = df[['open', 'high', 'low', 'close']]

    # Drop any NaN
    df = df.dropna()

    return df

def get_available_pairs():
    """Return list of supported currency pairs."""
    return list(INSTRUMENT_MAP.keys())
