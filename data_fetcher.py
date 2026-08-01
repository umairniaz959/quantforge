import pandas as pd
import requests
import io
import zipfile
from datetime import datetime, timedelta

# Mapping from our interval strings to Dukascopy period codes
PERIOD_MAP = {
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

# Dukascopy instrument codes
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
    Fetch OHLC data directly from Dukascopy's public feed.
    Returns a DataFrame with columns: open, high, low, close.
    """
    instrument = INSTRUMENT_MAP.get(symbol.upper())
    if not instrument:
        raise ValueError(f"Symbol {symbol} not supported. Available: {list(INSTRUMENT_MAP.keys())}")

    period = PERIOD_MAP.get(interval)
    if not period:
        raise ValueError(f"Interval {interval} not supported. Use: {list(PERIOD_MAP.keys())}")

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    # Dukascopy data URL format
    # https://www.dukascopy.com/datafeed/{instrument}/{year}/{month}/{day}/{hour}h_ticks.bi5
    # We'll fetch daily files and combine them

    all_data = []
    
    # Iterate through each day in the range
    current_date = start_dt
    while current_date <= end_dt:
        year = current_date.year
        month = str(current_date.month).zfill(2)
        day = str(current_date.day).zfill(2)
        
        # Format instrument for URL (EURUSD -> EURUSD)
        instrument_code = instrument.replace("/", "")
        
        # Dukascopy stores data in .bi5 files (compressed)
        # We'll use the tick data and resample to our desired timeframe
        base_url = f"https://data.dukascopy.com/datafeed/{instrument_code}/{year}/{month}/{day}/"
        
        # Try to get data for this day
        try:
            response = requests.get(base_url + "00h_ticks.bi5", timeout=10)
            if response.status_code == 200:
                # Process the .bi5 file (it's a binary format)
                # We'll use the bi5 library or parse manually
                # For simplicity, we'll use a fallback: download from alternative source
                # Let's use the CSV endpoint instead
                csv_url = f"https://data.dukascopy.com/datafeed/{instrument_code}/{year}/{month}/{day}/00h_tick.csv"
                csv_response = requests.get(csv_url, timeout=10)
                if csv_response.status_code == 200:
                    df_day = pd.read_csv(io.StringIO(csv_response.text), 
                                        names=['timestamp', 'bid', 'ask', 'volume'])
                    df_day['timestamp'] = pd.to_datetime(df_day['timestamp'], unit='ms')
                    # Convert to OHLC
                    if not df_day.empty:
                        # Resample to the desired interval
                        df_day.set_index('timestamp', inplace=True)
                        ohlc = df_day['bid'].resample(interval).ohlc()
                        ohlc.columns = ['open', 'high', 'low', 'close']
                        all_data.append(ohlc)
        except Exception as e:
            # Skip days with no data (weekends, holidays)
            pass
        
        current_date += timedelta(days=1)

    if not all_data:
        raise ValueError(f"No data found for {symbol} from {start_date} to {end_date}")

    # Combine all days
    df = pd.concat(all_data)
    df = df[~df.index.duplicated(keep='first')]
    df = df.sort_index()
    
    # Remove NaN values
    df = df.dropna()
    
    if df.empty:
        raise ValueError(f"All rows dropped. Try a different date range.")

    return df

def get_available_pairs():
    return list(INSTRUMENT_MAP.keys())
