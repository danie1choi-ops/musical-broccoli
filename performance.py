# performance.py - Module for calculating performance metrics

import pandas as pd
import numpy as np
from config import START_DATE, END_DATE

def calculate_performance(equity_curve, trades, btc_equity, eth_equity, summary_diagnostics):
    """
    Calculate key performance metrics.

    Args:
        equity_curve (pd.DataFrame): Equity curve with 'value' column
        trades (pd.DataFrame): Trades DataFrame
        btc_equity (pd.DataFrame): BTC equity curve
        eth_equity (pd.DataFrame): ETH equity curve
        summary_diagnostics (dict): Summary diagnostics

    Returns:
        dict: Performance metrics
    """
    if equity_curve.empty:
        return {}

    # Strategy metrics
    start_value = equity_curve['value'].iloc[0]
    end_value = equity_curve['value'].iloc[-1]
    n_years = (pd.Timestamp(END_DATE) - pd.Timestamp(START_DATE)).days / 365.25
    strategy_cagr = (end_value / start_value) ** (1 / n_years) - 1 if n_years > 0 else 0

    peak = equity_curve['value'].expanding().max()
    drawdown = (equity_curve['value'] - peak) / peak
    strategy_max_dd = drawdown.min()

    daily_returns = equity_curve['value'].pct_change().dropna()
    if len(daily_returns) > 0:
        strategy_sharpe = daily_returns.mean() / daily_returns.std() * np.sqrt(252)
    else:
        strategy_sharpe = 0

    # BTC metrics
    btc_start = btc_equity['value'].iloc[0]
    btc_end = btc_equity['value'].iloc[-1]
    btc_cagr = (btc_end / btc_start) ** (1 / n_years) - 1 if n_years > 0 else 0
    btc_peak = btc_equity['value'].expanding().max()
    btc_drawdown = (btc_equity['value'] - btc_peak) / btc_peak
    btc_max_dd = btc_drawdown.min()

    # ETH metrics
    eth_start = eth_equity['value'].iloc[0]
    eth_end = eth_equity['value'].iloc[-1]
    eth_cagr = (eth_end / eth_start) ** (1 / n_years) - 1 if n_years > 0 else 0
    eth_peak = eth_equity['value'].expanding().max()
    eth_drawdown = (eth_equity['value'] - eth_peak) / eth_peak
    eth_max_dd = eth_drawdown.min()

    # Other metrics
    total_trades = len(trades) if not trades.empty else 0
    total_fees = summary_diagnostics.get('total_fees', 0)
    total_slippage = summary_diagnostics.get('total_slippage', 0)
    annualized_turnover = summary_diagnostics.get('annualized_turnover', 0)

    return {
        'Strategy CAGR': strategy_cagr,
        'Strategy Max Drawdown': strategy_max_dd,
        'Strategy Sharpe': strategy_sharpe,
        'BTC CAGR': btc_cagr,
        'BTC Max Drawdown': btc_max_dd,
        'ETH CAGR': eth_cagr,
        'ETH Max Drawdown': eth_max_dd,
        'Total Trades': total_trades,
        'Total Fees': total_fees,
        'Total Slippage': total_slippage,
        'Annualized Turnover': annualized_turnover
    }