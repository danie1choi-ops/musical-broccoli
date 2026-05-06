# indicators.py - Module for calculating technical indicators

import pandas as pd
import numpy as np

def momentum(prices, period=30):
    """
    Calculate momentum as the percentage return over the period.

    Args:
        prices (pd.Series): Price series
        period (int): Lookback period

    Returns:
        pd.Series: Momentum values
    """
    return prices / prices.shift(period) - 1

def sma(prices, period=200):
    """
    Calculate Simple Moving Average.

    Args:
        prices (pd.Series): Price series
        period (int): MA period

    Returns:
        pd.Series: SMA values
    """
    return prices.rolling(window=period).mean()

def relative_momentum(coin_prices, btc_prices, period=30):
    """
    Calculate relative momentum: coin return - BTC return.

    Args:
        coin_prices (pd.Series): Coin price series
        btc_prices (pd.Series): BTC price series
        period (int): Lookback period

    Returns:
        pd.Series: Relative momentum values
    """
    coin_mom = momentum(coin_prices, period)
    btc_mom = momentum(btc_prices, period)
    return coin_mom - btc_mom