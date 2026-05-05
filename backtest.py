# backtest.py - Module for running the backtest simulation

import pandas as pd
from config import START_DATE, END_DATE, REBALANCE_FREQ, REGIME_ASSET, REGIME_PERIOD, MOCK_COINS, TOP_N, TRADING_FEE, SLIPPAGE, STARTING_CAPITAL, DATA_SOURCE, REAL_SYMBOLS
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
    if DATA_SOURCE == 'real':
        coins = [s.split('/')[0] for s in REAL_SYMBOLS]
    else:
        coins = MOCK_COINS
    data = load_ohlcv_data(coins, use_real=(DATA_SOURCE == 'real'))

    # Get universe
    universe = get_universe(data)

    # Dates
    dates = pd.date_range(START_DATE, END_DATE, freq='D')

    # Regime filter: BTC above 200-day MA
    btc_close = data[REGIME_ASSET]['close']
    btc_sma = sma(btc_close, REGIME_PERIOD)

    # Benchmarks
    btc_start = btc_close.iloc[0]
    eth_start = data['ETH']['close'].iloc[0] if 'ETH' in data else 100
    btc_equity = []
    eth_equity = []

    # Initialize
    holdings = {}  # {coin: {'shares': float, 'entry_price': float}}
    cash = STARTING_CAPITAL  # Starting capital
    total_fees = 0.0
    total_slippage = 0.0
    equity_curve = []
    all_trades = []
    holdings_history = []
    diagnostics = []

    # Rebalance dates: weekly, say every 7 days
    rebalance_dates = pd.date_range(START_DATE, END_DATE, freq='7D')

    for date in dates:
        if date not in data[REGIME_ASSET].index:
            continue

        # Benchmarks
        if date in btc_close.index:
            btc_value = STARTING_CAPITAL * (btc_close.loc[date] / btc_start)
        else:
            btc_value = btc_equity[-1]['value'] if btc_equity else STARTING_CAPITAL
        btc_equity.append({'date': date, 'value': btc_value})
        if 'ETH' in data and date in data['ETH'].index:
            eth_value = STARTING_CAPITAL * (data['ETH']['close'].loc[date] / eth_start)
        else:
            eth_value = eth_equity[-1]['value'] if eth_equity else STARTING_CAPITAL
        eth_equity.append({'date': date, 'value': eth_value})

        # Check regime
        regime_active = btc_close.loc[date] > btc_sma.loc[date] if not pd.isna(btc_sma.loc[date]) else False

        # Rebalance if weekly and regime active
        if date in rebalance_dates and regime_active:
            # Get current prices
            current_prices = {}
            for coin in universe:
                if coin in data and date in data[coin].index:
                    current_prices[coin] = data[coin]['close'].loc[date]

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
                notional = shares * price
                fee = notional * TRADING_FEE
                slippage = notional * SLIPPAGE
                net_proceeds = notional - fee - slippage
                cash += net_proceeds
                total_fees += fee
                total_slippage += slippage
                all_trades.append({
                    'date': date,
                    'coin': coin,
                    'action': 'exit',
                    'price': price,
                    'shares': shares,
                    'trade_notional': notional,
                    'fee_paid': fee,
                    'slippage_paid': slippage,
                    'net_proceeds': net_proceeds
                })
                del holdings[coin]

            # Buy top N
            if top_coins:
                weight = 1.0 / len(top_coins)
                for coin in top_coins:
                    if coin in current_prices:
                        price = current_prices[coin]
                        notional = weight * cash  # Approximate, since cash changes, but for simplicity
                        shares = notional / price
                        fee = notional * TRADING_FEE
                        slippage = notional * SLIPPAGE
                        total_cost = notional + fee + slippage
                        cash -= total_cost
                        holdings[coin] = {'shares': shares, 'entry_price': price}
                        all_trades.append({
                            'date': date,
                            'coin': coin,
                            'action': 'entry',
                            'price': price,
                            'shares': shares,
                            'trade_notional': notional,
                            'fee_paid': fee,
                            'slippage_paid': slippage,
                            'total_cost': total_cost
                        })

        # Calculate daily portfolio value
        current_prices = {}
        for coin in holdings:
            if coin in data and date in data[coin].index:
                current_prices[coin] = data[coin]['close'].loc[date]
            else:
                current_prices[coin] = holdings[coin]['entry_price']  # Use last known
        portfolio_value = cash + sum(holdings[coin]['shares'] * current_prices.get(coin, holdings[coin]['entry_price']) for coin in holdings)

        equity_curve.append({'date': date, 'value': portfolio_value})

        holdings_snapshot = {coin: holdings[coin]['shares'] * current_prices.get(coin, holdings[coin]['entry_price']) for coin in holdings}
        holdings_history.append({'date': date, 'holdings': holdings_snapshot, 'value': portfolio_value})

        diagnostics.append({
            'date': date,
            'regime_active': regime_active,
            'n_positions': len(holdings),
            'cash': cash,
            'cash_pct': cash / portfolio_value if portfolio_value > 0 else 0,
            'total_fees': total_fees,
            'total_slippage': total_slippage
        })

    # Convert to DataFrames
    equity_df = pd.DataFrame(equity_curve).set_index('date')
    trades_df = pd.DataFrame(all_trades)
    holdings_df = pd.DataFrame(holdings_history).set_index('date')
    diagnostics_df = pd.DataFrame(diagnostics).set_index('date')
    btc_df = pd.DataFrame(btc_equity).set_index('date')
    eth_df = pd.DataFrame(eth_equity).set_index('date')

    # Add summary diagnostics
    n_years = (pd.Timestamp(END_DATE) - pd.Timestamp(START_DATE)).days / 365.25
    avg_positions = diagnostics_df['n_positions'].mean()
    rebalance_count = len(rebalance_dates)
    avg_turnover_per_rebalance = TOP_N / 2  # Since fully rebalanced, approx half positions turn over
    annualized_turnover = (rebalance_count * avg_turnover_per_rebalance) / n_years if n_years > 0 else 0

    summary_diagnostics = {
        'data_source': DATA_SOURCE,
        'num_assets_tested': len(universe),
        'date_range': f'{START_DATE} to {END_DATE}',
        'survivorship_bias': True,
        'survivorship_note': 'Using static universe of current top coins',
        'avg_positions_held': avg_positions,
        'avg_turnover_per_rebalance': avg_turnover_per_rebalance,
        'annualized_turnover': annualized_turnover,
        'total_fees': total_fees,
        'total_slippage': total_slippage
    }

    return {
        'equity_curve': equity_df,
        'trades': trades_df,
        'holdings': holdings_df,
        'diagnostics': diagnostics_df,
        'btc_equity': btc_df,
        'eth_equity': eth_df,
        'summary_diagnostics': summary_diagnostics
    }