# data_loader.py - Module for loading OHLCV data from Binance or mock data

import pandas as pd
import numpy as np
from config import START_DATE, END_DATE, MOCK_COINS

def load_ohlcv_data(coins, start_date=START_DATE, end_date=END_DATE, use_mock=True):
    """
    Load OHLCV data for the given coins.

    Args:
        coins (list): List of coin symbols (e.g., ['BTC', 'ETH'])
        start_date (str): Start date in 'YYYY-MM-DD' format
        end_date (str): End date in 'YYYY-MM-DD' format
        use_mock (bool): If True, use mock data; else, load from Binance API

    Returns:
        dict: Dictionary with coin symbols as keys and DataFrames as values
    """
    if use_mock:
        return _load_mock_data(coins, start_date, end_date)
    else:
        return _load_binance_data(coins, start_date, end_date)

def _load_mock_data(coins, start_date, end_date):
    """
    Generate mock OHLCV data for testing.
    """
    dates = pd.date_range(start_date, end_date, freq='D')
    data = {}

    for coin in coins:
        # Seed for reproducibility
        np.random.seed(hash(coin) % 2**32)

        # Generate random walk prices
        n_days = len(dates)
        returns = np.random.normal(0.001, 0.03, n_days)  # mean return 0.1%, vol 3%
        prices = 100 * np.exp(np.cumsum(returns))

        # Generate OHLC
        opens = prices * np.random.uniform(0.98, 1.02, n_days)
        highs = prices * np.random.uniform(1.00, 1.05, n_days)
        lows = prices * np.random.uniform(0.95, 1.00, n_days)
        closes = prices
        volumes = np.random.uniform(1e6, 1e8, n_days)  # Volume in base currency, but we'll treat as USD for simplicity

        df = pd.DataFrame({
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes
        }, index=dates)

        data[coin] = df

    return data

def _load_binance_data(coins, start_date, end_date):
    """
    Load real OHLCV data from Binance API.
    Note: Requires ccxt library and API keys.
    """
    # Placeholder for real data loading
    # import ccxt
    # exchange = ccxt.binance()
    # data = {}
    # for coin in coins:
    #     symbol = f'{coin}/USDT'
    #     ohlcv = exchange.fetch_ohlcv(symbol, '1d', since=pd.Timestamp(start_date).timestamp()*1000)
    #     df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    #     df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    #     df.set_index('timestamp', inplace=True)
    #     data[coin] = df
    # return data
    raise NotImplementedError("Real Binance data loading not implemented yet. Use use_mock=True.")