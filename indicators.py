# indicators.py - Module for calculating technical indicators

import pandas as pd

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