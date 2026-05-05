# data_loader.py - Module for loading OHLCV data from Binance or mock data

import pandas as pd
import numpy as np
from config import START_DATE, END_DATE, MOCK_COINS

# data_loader.py - Module for loading OHLCV data from Binance or mock data

import pandas as pd
import numpy as np
import os
from config import START_DATE, END_DATE, MOCK_COINS

def load_ohlcv_data(coins, start_date=START_DATE, end_date=END_DATE, use_real=False):
    """
    Load OHLCV data for the given coins.

    Args:
        coins (list): List of coin symbols (e.g., ['BTC', 'ETH'])
        start_date (str): Start date in 'YYYY-MM-DD' format
        end_date (str): End date in 'YYYY-MM-DD' format
        use_real (bool): If True, load from real data; else, use mock

    Returns:
        dict: Dictionary with coin symbols as keys and DataFrames as values
    """
    if use_real:
        return _load_real_data(coins)
    else:
        return _load_mock_data(coins, start_date, end_date)

def download_binance_data(symbols, start_date, end_date):
    """
    Download OHLCV data from Binance and save to CSV.
    """
    import ccxt
    exchange = ccxt.binance()
    os.makedirs('data/ohlcv', exist_ok=True)

    for symbol in symbols:
        print(f"Downloading {symbol}...")
        since = int(pd.Timestamp(start_date).timestamp() * 1000)
        end_ts = int(pd.Timestamp(end_date).timestamp() * 1000)
        ohlcv = []

        while since < end_ts:
            try:
                candles = exchange.fetch_ohlcv(symbol, '1d', since, 1000)
                if not candles:
                    break
                ohlcv.extend(candles)
                since = candles[-1][0] + 86400000  # Next day in ms
            except Exception as e:
                print(f"Error downloading {symbol}: {e}")
                break

        if ohlcv:
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df = df.loc[start_date:end_date]  # Filter to date range
            path = f'data/ohlcv/{symbol.replace("/", "_")}.csv'
            df.to_csv(path)
            print(f"Saved {symbol} to {path}")
        else:
            print(f"No data for {symbol}")

def _load_real_data(coins):
    """
    Load real OHLCV data from saved CSV files.
    """
    data = {}
    for coin in coins:
        symbol = f'{coin}/USDT'
        path = f'data/ohlcv/{symbol.replace("/", "_")}.csv'
        if os.path.exists(path):
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            data[coin] = df
        else:
            print(f"Warning: Data for {coin} not found at {path}")
    return data