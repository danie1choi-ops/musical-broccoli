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
    Calculate relative momentum: how the coin performs relative to BTC.
    
    This measures the ratio of coin returns to BTC returns.
    A value > 1 means the coin outperformed BTC.
    A value < 1 means the coin underperformed BTC.
    
    Formula:
    coin_return = (coin_price_today / coin_price_period_ago) - 1
    btc_return = (btc_price_today / btc_price_period_ago) - 1
    relative_strength = coin_return / btc_return (or coin_return - btc_return if btc_return ~= 0)
    
    Args:
        coin_prices (pd.Series): Coin price series
        btc_prices (pd.Series): BTC price series
        period (int): Lookback period

    Returns:
        pd.Series: Relative strength values (coin_return / btc_return)
    """
    # Calculate absolute returns
    coin_return = momentum(coin_prices, period)
    btc_return = momentum(btc_prices, period)
    
    # To avoid division by zero, use the difference when BTC return is near zero
    # Otherwise use the ratio for true relative strength
    relative_strength = coin_return.copy()
    
    # Where BTC return is not near zero, use ratio
    nonzero_btc = btc_return.abs() > 0.001
    relative_strength[nonzero_btc] = coin_return[nonzero_btc] / btc_return[nonzero_btc]
    
    # Where BTC return is near zero, use difference
    zero_btc = ~nonzero_btc
    relative_strength[zero_btc] = coin_return[zero_btc] - btc_return[zero_btc]
    
    return relative_strength