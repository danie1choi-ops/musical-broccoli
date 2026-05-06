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
    Calculate relative momentum: how coin performs relative to BTC.
    
    This measures the change in the coin/BTC ratio over the period.
    A positive value means the coin is outperforming BTC.
    
    Formula:
    relative_return = (coin_price_today / BTC_price_today) / (coin_price_period_ago / BTC_price_period_ago) - 1
    
    Args:
        coin_prices (pd.Series): Coin price series
        btc_prices (pd.Series): BTC price series
        period (int): Lookback period

    Returns:
        pd.Series: Relative momentum values
    """
    # Calculate the coin/BTC ratio at each point
    coin_btc_ratio = coin_prices / btc_prices
    
    # Calculate momentum of the ratio (not momentum of difference)
    return coin_btc_ratio / coin_btc_ratio.shift(period) - 1