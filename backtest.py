# backtest.py - Module for running the backtest simulation

import os
import pandas as pd
from config import START_DATE, END_DATE, REBALANCE_FREQ, REGIME_ASSET, REGIME_PERIOD, MOCK_COINS, TOP_N, TRADING_FEE, SLIPPAGE, STARTING_CAPITAL, DATA_SOURCE, REAL_SYMBOLS, MOMENTUM_MODE, REGIME_FILTER_MODE
from data_loader import load_ohlcv_data
from universe import get_universe
from indicators import sma, momentum
from strategy import rank_coins

def _build_rebalance_dates(start_date, end_date, frequency):
    if frequency == 'weekly':
        return pd.date_range(start_date, end_date, freq='7D')
    if frequency == 'monthly':
        return pd.date_range(start_date, end_date, freq='30D')
    return pd.date_range(start_date, end_date, freq=frequency)


def _check_regime(date, regime_mode, btc_close, btc_sma, btc_momentum_50_200):
    """
    Check if regime is active based on selected filter mode.
    
    Args:
        date: Current date
        regime_mode: 'btc_200dma', 'dual_trend', or 'btc_90d_positive'
        btc_close: BTC close prices Series
        btc_sma: BTC 200-day SMA Series
        btc_momentum_50_200: DataFrame with 50DMA and 200DMA
    
    Returns:
        bool: True if regime is active
    """
    if regime_mode == 'btc_200dma':
        # BTC > 200DMA
        return btc_close.loc[date] > btc_sma.loc[date] if not pd.isna(btc_sma.loc[date]) else False
    
    elif regime_mode == 'dual_trend':
        # BTC > 200DMA AND 50DMA > 200DMA
        if pd.isna(btc_sma.loc[date]):
            return False
        price_above = btc_close.loc[date] > btc_sma.loc[date]
        sma_50 = btc_momentum_50_200.loc[date, 'sma_50'] if date in btc_momentum_50_200.index else None
        sma_200 = btc_sma.loc[date]
        trend_up = sma_50 > sma_200 if (not pd.isna(sma_50) and not pd.isna(sma_200)) else False
        return price_above and trend_up
    
    elif regime_mode == 'btc_90d_positive':
        # BTC 90-day return > 0
        if len(btc_close.loc[:date]) < 90:
            return False
        ret_90d = (btc_close.loc[date] / btc_close.loc[:date].iloc[-91]) - 1 if len(btc_close.loc[:date]) > 90 else 0
        return ret_90d > 0
    
    return False



def run_variant_backtest(entry_top=10, exit_top=20, trailing_stop=True, rebalance_freq='weekly', momentum_mode='absolute', regime_filter_mode='btc_200dma', save_diagnostics=False):
    """
    Run a parameterized variant backtest.
    
    Args:
        save_diagnostics (bool): If True, save momentum scores and rankings to CSV
    """
    # Load data
    coins = [s.split('/')[0] for s in REAL_SYMBOLS] if DATA_SOURCE == 'real' else MOCK_COINS
    data = load_ohlcv_data(coins, use_real=(DATA_SOURCE == 'real'))

    # Get universe
    universe = get_universe(data)

    # Dates
    dates = pd.date_range(START_DATE, END_DATE, freq='D')

    # Regime filter: BTC data
    btc_close = data[REGIME_ASSET]['close']
    btc_sma_200 = sma(btc_close, REGIME_PERIOD)
    btc_sma_50 = sma(btc_close, 50)
    btc_momentum_50_200 = pd.DataFrame({
        'sma_50': btc_sma_50,
        'sma_200': btc_sma_200
    })

    # Benchmarks
    btc_start = btc_close.iloc[0]
    eth_start = data['ETH']['close'].iloc[0] if 'ETH' in data else 100
    btc_equity = []
    eth_equity = []

    # Initialize
    holdings = {}
    cash = STARTING_CAPITAL
    total_fees = 0.0
    total_slippage = 0.0
    equity_curve = []
    all_trades = []
    holdings_history = []
    diagnostics = []
    avg_holding_periods = []
    momentum_diagnostics = []  # Track momentum scores and rankings

    rebalance_dates = _build_rebalance_dates(START_DATE, END_DATE, rebalance_freq)

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
        regime_active = _check_regime(date, regime_filter_mode, btc_close, btc_sma_200, btc_momentum_50_200)

        # Rebalance if periodic and regime active
        if date in rebalance_dates and regime_active:
            current_prices = {}
            for coin in universe:
                if coin in data and date in data[coin].index:
                    current_prices[coin] = data[coin]['close'].loc[date]

            portfolio_value = cash + sum(
                holdings[coin]['shares'] * current_prices.get(coin, holdings[coin]['entry_price'])
                for coin in holdings
            )

            ranked = rank_coins(universe, data, date, momentum_mode=momentum_mode)
            target_coins = ranked[:entry_top]

            # Identify exits - check both ranking and trailing stop
            exit_coins = []
            for coin, position in holdings.items():
                # Exit rule 1: falls outside exit_top by ranking
                if coin not in ranked[:exit_top]:
                    exit_coins.append(coin)
                    continue
                
                # Exit rule 2: trailing stop hit
                if trailing_stop and coin in data and date in data[coin].index:
                    entry_date = position['entry_date']
                    highest = data[coin]['close'].loc[entry_date:date].max()
                    current_price = data[coin]['close'].loc[date]
                    if current_price < highest * 0.75:
                        exit_coins.append(coin)

            # Execute exits
            for coin in exit_coins:
                shares = holdings[coin]['shares']
                entry_date = holdings[coin]['entry_date']
                price = current_prices.get(coin, holdings[coin]['entry_price'])
                notional = shares * price
                fee = notional * TRADING_FEE
                slippage = notional * SLIPPAGE
                net_proceeds = notional - fee - slippage
                cash += net_proceeds
                total_fees += fee
                total_slippage += slippage
                holding_days = (date - entry_date).days
                avg_holding_periods.append(holding_days)
                all_trades.append({
                    'date': date,
                    'coin': coin,
                    'action': 'exit',
                    'price': price,
                    'shares': shares,
                    'trade_notional': notional,
                    'fee_paid': fee,
                    'slippage_paid': slippage,
                    'total_cost': fee + slippage,
                    'net_proceeds': net_proceeds,
                    'holding_days': holding_days
                })
                del holdings[coin]

            # Enter new positions
            open_coins = [coin for coin in target_coins if coin not in holdings]
            if open_coins:
                weight = min(1.0 / len(target_coins), 0.1) if target_coins else 0
                desired_notional = weight * portfolio_value
                total_required = desired_notional * len(open_coins)
                scale = min(1.0, cash / total_required) if total_required > 0 else 0
                for coin in open_coins:
                    if coin in current_prices and cash > 0:
                        price = current_prices[coin]
                        notional = desired_notional * scale
                        shares = notional / price
                        fee = notional * TRADING_FEE
                        slippage = notional * SLIPPAGE
                        total_cost = fee + slippage
                        cash -= (notional + total_cost)
                        if cash < 0:
                            break
                        holdings[coin] = {
                            'shares': shares,
                            'entry_price': price,
                            'entry_date': date
                        }
                        total_fees += fee
                        total_slippage += slippage
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

        current_prices = {}
        for coin in holdings:
            if coin in data and date in data[coin].index:
                current_prices[coin] = data[coin]['close'].loc[date]
            else:
                current_prices[coin] = holdings[coin]['entry_price']
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

    equity_df = pd.DataFrame(equity_curve).set_index('date')
    trades_df = pd.DataFrame(all_trades)
    holdings_df = pd.DataFrame(holdings_history).set_index('date')
    diagnostics_df = pd.DataFrame(diagnostics).set_index('date')
    btc_df = pd.DataFrame(btc_equity).set_index('date')
    eth_df = pd.DataFrame(eth_equity).set_index('date')

    n_years = (pd.Timestamp(END_DATE) - pd.Timestamp(START_DATE)).days / 365.25
    avg_positions = diagnostics_df['n_positions'].mean()
    rebalance_count = len(rebalance_dates)
    avg_turnover_per_rebalance = entry_top / 2
    annualized_turnover = (rebalance_count * avg_turnover_per_rebalance) / n_years if n_years > 0 else 0
    avg_holding_period = sum(avg_holding_periods) / len(avg_holding_periods) if avg_holding_periods else 0

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
        'total_slippage': total_slippage,
        'avg_holding_period': avg_holding_period
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


def run_backtest():
    return run_variant_backtest(entry_top=TOP_N, exit_top=20, trailing_stop=True, rebalance_freq='weekly', momentum_mode=MOMENTUM_MODE, regime_filter_mode=REGIME_FILTER_MODE)


def compare_variants():
    variants = [
        {
            'name': 'baseline',
            'entry_top': 10,
            'exit_top': 20,
            'trailing_stop': True,
            'rebalance_freq': 'weekly'
        },
        {
            'name': 'wider_hold_buffer',
            'entry_top': 10,
            'exit_top': 30,
            'trailing_stop': True,
            'rebalance_freq': 'weekly'
        },
        {
            'name': 'monthly_rebalance',
            'entry_top': 10,
            'exit_top': 20,
            'trailing_stop': True,
            'rebalance_freq': 'monthly'
        },
        {
            'name': 'stricter_entry',
            'entry_top': 5,
            'exit_top': 15,
            'trailing_stop': True,
            'rebalance_freq': 'weekly'
        },
        {
            'name': 'no_trailing_stop',
            'entry_top': 10,
            'exit_top': 20,
            'trailing_stop': False,
            'rebalance_freq': 'weekly'
        }
    ]

    rows = []
    from performance import calculate_performance

    for variant in variants:
        results = run_variant_backtest(
            entry_top=variant['entry_top'],
            exit_top=variant['exit_top'],
            trailing_stop=variant['trailing_stop'],
            rebalance_freq=variant['rebalance_freq']
        )
        metrics = calculate_performance(
            results['equity_curve'],
            results['trades'],
            results['btc_equity'],
            results['eth_equity'],
            results['summary_diagnostics']
        )
        rows.append({
            'variant': variant['name'],
            'strategy_cagr': metrics['Strategy CAGR'],
            'strategy_max_drawdown': metrics['Strategy Max Drawdown'],
            'strategy_sharpe': metrics['Strategy Sharpe'],
            'total_trades': metrics['Total Trades'],
            'annualized_turnover': metrics['Annualized Turnover'],
            'total_fees': metrics['Total Fees'],
            'total_slippage': metrics['Total Slippage'],
            'final_equity': results['equity_curve']['value'].iloc[-1] if not results['equity_curve'].empty else 0,
            'btc_cagr': metrics['BTC CAGR'],
            'btc_max_drawdown': metrics['BTC Max Drawdown'],
            'eth_cagr': metrics['ETH CAGR'],
            'eth_max_drawdown': metrics['ETH Max Drawdown']
        })

    return pd.DataFrame(rows)


def compare_regimes():
    """
    Compare strategy performance across momentum modes, regime filters, rebalance frequencies, and entry tops.
    """
    regime_configs = [
        {
            'name': 'abs_btc200_weekly_top10',
            'momentum_mode': 'absolute',
            'regime_filter_mode': 'btc_200dma',
            'rebalance_freq': 'weekly',
            'entry_top': 10
        },
        {
            'name': 'abs_btc200_weekly_top5',
            'momentum_mode': 'absolute',
            'regime_filter_mode': 'btc_200dma',
            'rebalance_freq': 'weekly',
            'entry_top': 5
        },
        {
            'name': 'abs_btc200_monthly_top10',
            'momentum_mode': 'absolute',
            'regime_filter_mode': 'btc_200dma',
            'rebalance_freq': 'monthly',
            'entry_top': 10
        },
        {
            'name': 'abs_dual_trend_weekly_top10',
            'momentum_mode': 'absolute',
            'regime_filter_mode': 'dual_trend',
            'rebalance_freq': 'weekly',
            'entry_top': 10
        },
        {
            'name': 'abs_btc90d_weekly_top10',
            'momentum_mode': 'absolute',
            'regime_filter_mode': 'btc_90d_positive',
            'rebalance_freq': 'weekly',
            'entry_top': 10
        },
        {
            'name': 'rel_btc200_weekly_top10',
            'momentum_mode': 'relative',
            'regime_filter_mode': 'btc_200dma',
            'rebalance_freq': 'weekly',
            'entry_top': 10
        },
        {
            'name': 'rel_btc200_weekly_top5',
            'momentum_mode': 'relative',
            'regime_filter_mode': 'btc_200dma',
            'rebalance_freq': 'weekly',
            'entry_top': 5
        },
        {
            'name': 'rel_btc200_monthly_top10',
            'momentum_mode': 'relative',
            'regime_filter_mode': 'btc_200dma',
            'rebalance_freq': 'monthly',
            'entry_top': 10
        },
        {
            'name': 'rel_dual_trend_weekly_top10',
            'momentum_mode': 'relative',
            'regime_filter_mode': 'dual_trend',
            'rebalance_freq': 'weekly',
            'entry_top': 10
        },
        {
            'name': 'rel_btc90d_weekly_top10',
            'momentum_mode': 'relative',
            'regime_filter_mode': 'btc_90d_positive',
            'rebalance_freq': 'weekly',
            'entry_top': 10
        }
    ]

    rows = []
    from performance import calculate_performance

    for config in regime_configs:
        print(f"Running {config['name']}...")
        results = run_variant_backtest(
            entry_top=config['entry_top'],
            exit_top=max(config['entry_top'] * 2, 20),  # Exit at 2x entry_top
            trailing_stop=True,
            rebalance_freq=config['rebalance_freq'],
            momentum_mode=config['momentum_mode'],
            regime_filter_mode=config['regime_filter_mode']
        )
        metrics = calculate_performance(
            results['equity_curve'],
            results['trades'],
            results['btc_equity'],
            results['eth_equity'],
            results['summary_diagnostics']
        )
        rows.append({
            'variant': config['name'],
            'momentum_mode': config['momentum_mode'],
            'regime_filter': config['regime_filter_mode'],
            'rebalance_freq': config['rebalance_freq'],
            'entry_top': config['entry_top'],
            'strategy_cagr': metrics['Strategy CAGR'],
            'strategy_max_drawdown': metrics['Strategy Max Drawdown'],
            'strategy_sharpe': metrics['Strategy Sharpe'],
            'total_trades': metrics['Total Trades'],
            'annualized_turnover': metrics['Annualized Turnover'],
            'total_fees': metrics['Total Fees'],
            'total_slippage': metrics['Total Slippage'],
            'final_equity': results['equity_curve']['value'].iloc[-1] if not results['equity_curve'].empty else 0,
            'avg_holding_period': results['summary_diagnostics'].get('avg_holding_period', 0),
            'avg_positions_held': results['summary_diagnostics'].get('avg_positions_held', 0),
            'btc_cagr': metrics['BTC CAGR'],
            'btc_max_drawdown': metrics['BTC Max Drawdown'],
            'eth_cagr': metrics['ETH CAGR'],
            'eth_max_drawdown': metrics['ETH Max Drawdown']
        })

    return pd.DataFrame(rows)
