import pandas as pd
import yfinance as yf
import requests
from datetime import datetime, timedelta
import io

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

# Yahoo Finance tickers
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

def fetch_dukascopy_intraday(symbol, start_date, end_date, interval):
    """Fetch intraday data from Dukascopy public feed."""
    instrument = INSTRUMENT_MAP.get(symbol.upper())
    if not instrument:
        return None
    
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    instrument_code = instrument.replace("/", "")
    
    all_data = []
    current_date = start_dt
    
    while current_date <= end_dt:
        year = current_date.year
        month = str(current_date.month).zfill(2)
        day = str(current_date.day).zfill(2)
        
        csv_url = f"https://data.dukascopy.com/datafeed/{instrument_code}/{year}/{month}/{day}/00h_tick.csv"
        try:
            response = requests.get(csv_url, timeout=10)
            if response.status_code == 200:
                df_day = pd.read_csv(io.StringIO(response.text), 
                                    names=['timestamp', 'bid', 'ask', 'volume'])
                df_day['timestamp'] = pd.to_datetime(df_day['timestamp'], unit='ms')
                if not df_day.empty:
                    df_day.set_index('timestamp', inplace=True)
                    ohlc = df_day['bid'].resample(interval).ohlc()
                    ohlc.columns = ['open', 'high', 'low', 'close']
                    all_data.append(ohlc)
        except:
            pass
        current_date += timedelta(days=1)
    
    if not all_data:
        return None
    
    df = pd.concat(all_data)
    df = df[~df.index.duplicated(keep='first')]
    df = df.sort_index().dropna()
    return df

def fetch_yahoo_data(symbol, start_date, end_date, interval):
    """Fetch data from Yahoo Finance (good for daily and above)."""
    ticker = YAHOO_MAP.get(symbol.upper())
    if not ticker:
        return None
    
    yf_interval = "1d" if interval == "1d" else "1wk" if interval == "1w" else "1mo"
    
    try:
        df = yf.download(
            tickers=ticker,
            start=start_date,
            end=end_date,
            interval=yf_interval,
            progress=False,
            auto_adjust=False
        )
        if df is None or df.empty:
            return None
        df.columns = [c.lower() for c in df.columns]
        df = df[['open', 'high', 'low', 'close']]
        return df.dropna()
    except:
        return None

def fetch_forex_data(symbol, start_date, end_date, interval="1h"):
    """
    Fetch OHLC data – uses Dukascopy for intraday, Yahoo for daily+.
    """
    intraday_intervals = ["1m", "5m", "15m", "30m", "1h", "4h"]
    
    if interval in intraday_intervals:
        df = fetch_dukascopy_intraday(symbol, start_date, end_date, interval)
        if df is not None and not df.empty:
            return df
        # Fallback to Yahoo daily if Dukascopy fails
        print(f"Dukascopy failed, falling back to Yahoo daily for {symbol}")
        df = fetch_yahoo_data(symbol, start_date, end_date, "1d")
        if df is not None and not df.empty:
            return df
    else:
        df = fetch_yahoo_data(symbol, start_date, end_date, interval)
        if df is not None and not df.empty:
            return df
    
    raise ValueError(f"No data found for {symbol} from {start_date} to {end_date} with interval {interval}")

def get_available_pairs():
    return list(INSTRUMENT_MAP.keys())
