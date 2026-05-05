# backtest.py - Module for running the backtest simulation

import pandas as pd
from config import START_DATE, END_DATE, REBALANCE_FREQ, REGIME_ASSET, REGIME_PERIOD, MOCK_COINS, TOP_N
from data_loader import load_ohlcv_data
from universe import get_universe
from indicators import sma
from strategy import rank_coins

def run_backtest():
    """
    Run the backtest and return results.

    Returns:
        dict: Results including equity curve, trades, holdings, diagnostics
    """
    # Load data
    coins = MOCK_COINS  # For mock
    data = load_ohlcv_data(coins)

    # Get universe
    universe = get_universe(data)

    # Dates
    dates = pd.date_range(START_DATE, END_DATE, freq='D')

    # Regime filter: BTC above 200-day MA
    btc_close = data[REGIME_ASSET]['close']
    btc_sma = sma(btc_close, REGIME_PERIOD)

    # Initialize
    holdings = {}  # {coin: {'shares': float, 'entry_price': float}}
    cash = 1.0  # Initial capital
    equity_curve = []
    all_trades = []
    holdings_history = []
    diagnostics = []

    # Rebalance dates: weekly, say every 7 days
    rebalance_dates = pd.date_range(START_DATE, END_DATE, freq='7D')

    for date in dates:
        if date not in data[REGIME_ASSET].index:
            continue

        # Check regime
        regime_active = btc_close.loc[date] > btc_sma.loc[date] if not pd.isna(btc_sma.loc[date]) else False

        # Rebalance if weekly and regime active
        if date in rebalance_dates and regime_active:
            # Get current prices
            current_prices = {coin: data[coin]['close'].loc[date] for coin in universe if coin in data}

            # Calculate total portfolio value
            portfolio_value = cash + sum(holdings[coin]['shares'] * current_prices.get(coin, holdings[coin]['entry_price']) for coin in holdings)

            # Rank universe
            ranked = rank_coins(universe, data, date)

            # Get target positions: top N
            top_coins = ranked[:TOP_N]

            # Sell all current holdings
            for coin in list(holdings.keys()):
                shares = holdings[coin]['shares']
                price = current_prices.get(coin, holdings[coin]['entry_price'])
                cash += shares * price
                all_trades.append({
                    'date': date,
                    'coin': coin,
                    'action': 'exit',
                    'price': price,
                    'shares': shares
                })
                del holdings[coin]

            # Buy top N
            if top_coins:
                weight = 1.0 / len(top_coins)
                for coin in top_coins:
                    if coin in current_prices:
                        price = current_prices[coin]
                        shares = (weight * cash) / price
                        holdings[coin] = {'shares': shares, 'entry_price': price}
                        all_trades.append({
                            'date': date,
                            'coin': coin,
                            'action': 'entry',
                            'price': price,
                            'shares': shares
                        })
                cash = 0  # Fully invested

        # Calculate daily portfolio value
        current_prices = {coin: data[coin]['close'].loc[date] for coin in holdings if coin in data}
        portfolio_value = cash + sum(holdings[coin]['shares'] * current_prices.get(coin, holdings[coin]['entry_price']) for coin in holdings)

        equity_curve.append({'date': date, 'value': portfolio_value})

        holdings_snapshot = {coin: holdings[coin]['shares'] * current_prices.get(coin, holdings[coin]['entry_price']) for coin in holdings}
        holdings_history.append({'date': date, 'holdings': holdings_snapshot, 'value': portfolio_value})

        diagnostics.append({'date': date, 'regime_active': regime_active, 'n_positions': len(holdings), 'cash': cash})

    # Convert to DataFrames
    equity_df = pd.DataFrame(equity_curve).set_index('date')
    trades_df = pd.DataFrame(all_trades)
    holdings_df = pd.DataFrame(holdings_history).set_index('date')
    diagnostics_df = pd.DataFrame(diagnostics).set_index('date')

    return {
        'equity_curve': equity_df,
        'trades': trades_df,
        'holdings': holdings_df,
        'diagnostics': diagnostics_df
    }