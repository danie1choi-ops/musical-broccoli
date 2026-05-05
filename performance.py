# performance.py - Module for calculating performance metrics

import pandas as pd
import numpy as np
from config import START_DATE, END_DATE

def calculate_performance(equity_curve, trades):
    """
    Calculate key performance metrics.

    Args:
        equity_curve (pd.DataFrame): Equity curve with 'value' column
        trades (pd.DataFrame): Trades DataFrame

    Returns:
        dict: Performance metrics
    """
    if equity_curve.empty:
        return {}

    # CAGR
    start_value = equity_curve['value'].iloc[0]
    end_value = equity_curve['value'].iloc[-1]
    n_years = (pd.Timestamp(END_DATE) - pd.Timestamp(START_DATE)).days / 365.25
    cagr = (end_value / start_value) ** (1 / n_years) - 1 if n_years > 0 else 0

    # Drawdown
    peak = equity_curve['value'].expanding().max()
    drawdown = (equity_curve['value'] - peak) / peak
    max_drawdown = drawdown.min()

    # Sharpe Ratio (assuming risk-free rate 0)
    daily_returns = equity_curve['value'].pct_change().dropna()
    if len(daily_returns) > 0:
        sharpe = daily_returns.mean() / daily_returns.std() * np.sqrt(252)  # Annualized
    else:
        sharpe = 0

    # Turnover
    if not trades.empty:
        # Turnover as sum of |weight changes| / 2 per period
        # Simplified: number of trades
        turnover = len(trades) / n_years
    else:
        turnover = 0

    # Trades
    n_trades = len(trades) if not trades.empty else 0

    return {
        'CAGR': cagr,
        'Max Drawdown': max_drawdown,
        'Sharpe Ratio': sharpe,
        'Turnover': turnover,
        'Number of Trades': n_trades
    }