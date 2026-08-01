import pandas as pd
from datetime import datetime, timedelta
from dukascopy_tick import Dukascopy

# Mapping of currency pairs to Dukascopy instrument codes
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

# Map timeframe strings to Dukascopy's period constants
# Dukascopy uses: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 1mn
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
    # Get instrument name
    instrument = INSTRUMENT_MAP.get(symbol.upper())
    if not instrument:
        raise ValueError(f"Symbol {symbol} not supported. Available: {list(INSTRUMENT_MAP.keys())}")

    # Convert dates to datetime
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    # Map interval
    interval_d = INTERVAL_MAP.get(interval)
    if not interval_d:
        raise ValueError(f"Interval {interval} not supported. Use one of: {list(INTERVAL_MAP.keys())}")

    # Initialize Dukascopy client
    client = Dukascopy()

    try:
        # Fetch data
        df = client.get_instrument_history(
            instrument=instrument,
            start=start,
            end=end,
            period=interval_d
        )
    except Exception as e:
        raise RuntimeError(f"Failed to fetch data from Dukascopy: {e}")

    if df.empty:
        raise ValueError(f"No data returned for {symbol} from {start_date} to {end_date}")

    # Ensure we have the right columns
    # Dukascopy returns columns: timestamp, open, high, low, close, volume
    # We only need OHLC
    df = df.rename(columns={
        'timestamp': 'datetime',
        'open': 'open',
        'high': 'high',
        'low': 'low',
        'close': 'close'
    })

    # Set index to datetime
    df['datetime'] = pd.to_datetime(df['datetime'])
    df.set_index('datetime', inplace=True)

    # Keep only OHLC
    df = df[['open', 'high', 'low', 'close']]

    # Drop any rows with NaN
    df = df.dropna()

    return df

def get_available_pairs():
    """Return list of supported currency pairs."""
    return list(INSTRUMENT_MAP.keys())
