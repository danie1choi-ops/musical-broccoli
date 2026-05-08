# backtest.py - Module for running the backtest simulation

import os
import pandas as pd
from config import START_DATE, END_DATE, REBALANCE_FREQ, REGIME_ASSET, REGIME_PERIOD, MOCK_COINS, TOP_N, TRADING_FEE, SLIPPAGE, STARTING_CAPITAL, DATA_SOURCE, REAL_SYMBOLS, MOMENTUM_MODE, REGIME_FILTER_MODE, POSITION_SIZING_MODE, MAX_POSITION_SIZE, USE_BREADTH_SCALING, EXECUTION_MODE, MIN_SLIPPAGE, MAX_SLIPPAGE, SLIPPAGE_IMPACT_FACTOR, ADV_LOOKBACK_DAYS
from data_loader import load_ohlcv_data
from universe import get_universe
from indicators import sma, momentum
from strategy import rank_coins, get_momentum_scores, calculate_position_weights, calculate_market_breadth, exposure_scale_from_breadth, calculate_alt_participation, target_exposure_for_mode, scale_position_weights

def _build_rebalance_dates(start_date, end_date, frequency):
    if frequency == 'weekly':
        return pd.date_range(start_date, end_date, freq='7D')
    if frequency == 'monthly':
        return pd.date_range(start_date, end_date, freq='30D')
    return pd.date_range(start_date, end_date, freq=frequency)


def _get_data_date_bounds(data):
    """Return first and last available date for each loaded asset."""
    bounds = {}
    for coin, df in data.items():
        if df.empty:
            continue
        index = pd.DatetimeIndex(df.index)
        bounds[coin] = {
            'start_date': index.min(),
            'end_date': index.max(),
            'rows': len(df)
        }
    return bounds


def _latest_available_backtest_date(data, regime_asset=REGIME_ASSET):
    """Use the regime asset's latest date as the latest date the strategy can evaluate."""
    bounds = _get_data_date_bounds(data)
    if regime_asset in bounds:
        return bounds[regime_asset]['end_date']
    if not bounds:
        return pd.Timestamp(END_DATE)
    return max(asset_bounds['end_date'] for asset_bounds in bounds.values())


def _next_available_date(index, date):
    future_dates = pd.DatetimeIndex(index)[pd.DatetimeIndex(index) > pd.Timestamp(date)]
    if len(future_dates) == 0:
        return None
    return future_dates[0]


def _execution_fill_price(data, coin, date, execution_mode=EXECUTION_MODE):
    """Return expected close and simulated execution fill for a coin/date."""
    details = _execution_fill_details(data, coin, date, execution_mode)
    if details is None:
        return None, None
    return details['expected_fill'], details['simulated_fill']


def _execution_fill_details(data, coin, date, execution_mode=EXECUTION_MODE):
    """Return execution fill details with explicit signal/execution timestamps."""
    if coin not in data or date not in data[coin].index:
        return None
    df = data[coin]
    expected_fill = df.loc[date, 'close']
    details = {
        'signal_date': pd.Timestamp(date),
        'execution_date': pd.Timestamp(date),
        'expected_fill': expected_fill,
        'simulated_fill': expected_fill,
        'fill_data_end_date': pd.Timestamp(date),
        'fill_uses_full_next_day_ohlc': False
    }
    if execution_mode == 'same_close':
        return details

    next_date = _next_available_date(df.index, date)
    if next_date is None:
        return details
    assert next_date > pd.Timestamp(date), 'Delayed execution must occur after signal date.'
    details['execution_date'] = pd.Timestamp(next_date)
    details['fill_data_end_date'] = pd.Timestamp(next_date)
    if execution_mode == 'next_open':
        details['simulated_fill'] = df.loc[next_date, 'open']
        return details
    if execution_mode == 'next_day_vwap_approx':
        row = df.loc[next_date]
        details['simulated_fill'] = (row['open'] + row['high'] + row['low'] + row['close']) / 4
        details['fill_uses_full_next_day_ohlc'] = True
        assert details['fill_data_end_date'] == details['execution_date'], 'VWAP approximation may only use execution-date OHLC.'
        return details
    return details


def _average_daily_dollar_volume(data, coin, date, lookback=ADV_LOOKBACK_DAYS):
    """Average daily dollar volume up to the signal date."""
    if coin not in data:
        return 0.0
    df = data[coin].loc[:date].tail(lookback)
    if df.empty:
        return 0.0
    return (df['close'] * df['volume']).mean()


def _liquidity_slippage_pct(notional, average_daily_dollar_volume, min_slippage=MIN_SLIPPAGE, max_slippage=MAX_SLIPPAGE, impact_factor=SLIPPAGE_IMPACT_FACTOR):
    """Scale slippage by ADV participation with configurable caps."""
    if notional <= 0:
        return 0.0
    if average_daily_dollar_volume <= 0:
        return max_slippage
    adv_participation = notional / average_daily_dollar_volume
    return min(max(impact_factor * adv_participation, min_slippage), max_slippage)


def _execution_context(data, universe, date, execution_mode=EXECUTION_MODE):
    """Build close/fill/ADV maps used by the rebalance engine."""
    expected_prices = {}
    execution_prices = {}
    execution_details = {}
    average_daily_dollar_volume = {}
    for coin in universe:
        details = _execution_fill_details(data, coin, date, execution_mode)
        if details is None:
            continue
        assert details['fill_data_end_date'] >= details['signal_date']
        assert details['fill_data_end_date'] <= details['execution_date']
        expected_prices[coin] = details['expected_fill']
        execution_prices[coin] = details['simulated_fill']
        execution_details[coin] = details
        average_daily_dollar_volume[coin] = _average_daily_dollar_volume(data, coin, date)
    return expected_prices, execution_prices, average_daily_dollar_volume, execution_details


def _trade_record(date, coin, action, expected_fill, simulated_fill, shares, fee, slippage, slippage_pct, adv_participation, execution_mode, execution_details=None, extra=None):
    trade_notional = shares * simulated_fill
    execution_details = execution_details or {}
    signal_date = execution_details.get('signal_date', pd.Timestamp(date))
    execution_date = execution_details.get('execution_date', pd.Timestamp(date))
    fill_data_end_date = execution_details.get('fill_data_end_date', execution_date)
    record = {
        'date': date,
        'signal_date': signal_date,
        'execution_date': execution_date,
        'portfolio_update_date': pd.Timestamp(date),
        'fill_data_end_date': fill_data_end_date,
        'coin': coin,
        'action': action,
        'price': simulated_fill,
        'expected_fill': expected_fill,
        'simulated_fill': simulated_fill,
        'fill_uses_full_next_day_ohlc': execution_details.get('fill_uses_full_next_day_ohlc', False),
        'shares': shares,
        'trade_notional': trade_notional,
        'fee_paid': fee,
        'slippage_paid': slippage,
        'slippage_pct': slippage_pct * 100,
        'adv_participation_pct': adv_participation * 100,
        'execution_mode': execution_mode,
        'total_cost': fee + slippage
    }
    if extra:
        record.update(extra)
    return record


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


def _rebalance_portfolio(holdings, target_weights, current_prices, portfolio_value, cash, date, execution_prices=None, average_daily_dollar_volume=None, execution_details=None, execution_mode=EXECUTION_MODE):
    """Rebalance holdings to target weights with fees and slippage."""
    trades = []
    total_fees = 0.0
    total_slippage = 0.0
    execution_prices = execution_prices or current_prices
    average_daily_dollar_volume = average_daily_dollar_volume or {}
    execution_details = execution_details or {}

    # Exit any held coins that are not part of the target allocation
    for coin in list(holdings):
        if coin not in target_weights or coin not in current_prices:
            expected_fill = current_prices.get(coin, holdings[coin]['entry_price'])
            simulated_fill = execution_prices.get(coin, expected_fill)
            shares = holdings[coin]['shares']
            notional = shares * simulated_fill
            fee = notional * TRADING_FEE
            adv = average_daily_dollar_volume.get(coin, 0)
            adv_participation = notional / adv if adv > 0 else 0
            slippage_pct = _liquidity_slippage_pct(notional, adv)
            slippage = notional * slippage_pct
            net_proceeds = notional - fee - slippage
            cash += net_proceeds
            total_fees += fee
            total_slippage += slippage
            trades.append(_trade_record(
                date, coin, 'exit', expected_fill, simulated_fill, shares,
                fee, slippage, slippage_pct, adv_participation, execution_mode,
                execution_details.get(coin),
                {'net_proceeds': net_proceeds}
            ))
            del holdings[coin]

    # Calculate current notional for coins that will remain in the portfolio
    current_values = {}
    for coin in target_weights:
        if coin in holdings and coin in current_prices:
            current_values[coin] = holdings[coin]['shares'] * current_prices[coin]
        else:
            current_values[coin] = 0.0

    buy_orders = {}
    sell_orders = {}
    for coin, target_weight in target_weights.items():
        if coin not in current_prices:
            continue
        target_value = target_weight * portfolio_value
        current_value = current_values.get(coin, 0.0)
        diff = target_value - current_value
        if diff > 0:
            buy_orders[coin] = diff
        elif diff < 0:
            sell_orders[coin] = -diff

    # Execute sells first to free up cash for rebalance purchases
    for coin, notional in sell_orders.items():
        if coin not in holdings or coin not in current_prices:
            continue
        expected_fill = current_prices[coin]
        simulated_fill = execution_prices.get(coin, expected_fill)
        shares = min(notional / expected_fill, holdings[coin]['shares'])
        if shares <= 0:
            continue
        trade_notional = shares * simulated_fill
        fee = trade_notional * TRADING_FEE
        adv = average_daily_dollar_volume.get(coin, 0)
        adv_participation = trade_notional / adv if adv > 0 else 0
        slippage_pct = _liquidity_slippage_pct(trade_notional, adv)
        slippage = trade_notional * slippage_pct
        net_proceeds = trade_notional - fee - slippage
        holdings[coin]['shares'] -= shares
        if holdings[coin]['shares'] <= 1e-12:
            del holdings[coin]
        cash += net_proceeds
        total_fees += fee
        total_slippage += slippage
        trades.append(_trade_record(
            date, coin, 'rebalance_sell', expected_fill, simulated_fill, shares,
            fee, slippage, slippage_pct, adv_participation, execution_mode,
            execution_details.get(coin),
            {'net_proceeds': net_proceeds}
        ))

    # Execute buys with available cash
    total_buy_notional = sum(buy_orders.values())
    if total_buy_notional > 0:
        estimated_cost = total_buy_notional * (1 + TRADING_FEE + SLIPPAGE)
        scale = min(1.0, cash / estimated_cost) if estimated_cost > 0 else 0.0
    else:
        scale = 0.0

    for coin, notional in buy_orders.items():
        if coin not in current_prices:
            continue
        scaled_notional = notional * scale
        if scaled_notional <= 0:
            continue
        expected_fill = current_prices[coin]
        simulated_fill = execution_prices.get(coin, expected_fill)
        shares = scaled_notional / simulated_fill
        trade_notional = shares * simulated_fill
        fee = trade_notional * TRADING_FEE
        adv = average_daily_dollar_volume.get(coin, 0)
        adv_participation = trade_notional / adv if adv > 0 else 0
        slippage_pct = _liquidity_slippage_pct(trade_notional, adv)
        slippage = trade_notional * slippage_pct
        total_cost = fee + slippage
        if trade_notional + total_cost > cash and cash > 0:
            scaled_notional = cash / (1 + TRADING_FEE + slippage_pct)
            shares = scaled_notional / simulated_fill
            trade_notional = shares * simulated_fill
            fee = trade_notional * TRADING_FEE
            adv_participation = trade_notional / adv if adv > 0 else 0
            slippage_pct = _liquidity_slippage_pct(trade_notional, adv)
            slippage = trade_notional * slippage_pct
            total_cost = fee + slippage
        if trade_notional <= 0:
            continue
        cash -= trade_notional + total_cost
        total_fees += fee
        total_slippage += slippage
        if coin in holdings:
            holdings[coin]['shares'] += shares
        else:
            holdings[coin] = {
                'shares': shares,
                'entry_price': simulated_fill,
                'entry_date': date
            }
        trades.append(_trade_record(
            date, coin, 'rebalance_buy', expected_fill, simulated_fill, shares,
            fee, slippage, slippage_pct, adv_participation, execution_mode,
            execution_details.get(coin),
            {'cash_remaining': cash}
        ))

    return holdings, cash, trades, total_fees, total_slippage


def run_variant_backtest(entry_top=10, exit_top=20, trailing_stop=True, rebalance_freq='weekly', momentum_mode='absolute', regime_filter_mode='btc_200dma', position_sizing_mode=POSITION_SIZING_MODE, use_breadth_scaling=USE_BREADTH_SCALING, exposure_scaling_mode=None, momentum_lookback=30, breadth_full_threshold=0.70, trailing_stop_pct=0.25, execution_mode=EXECUTION_MODE, start_date=START_DATE, end_date=END_DATE, save_diagnostics=False):
    """
    Run a parameterized variant backtest.
    
    Args:
        save_diagnostics (bool): If True, save momentum scores and rankings to CSV
    """
    # Load data
    if exposure_scaling_mode is None:
        exposure_scaling_mode = 'breadth_100dma_scaling' if use_breadth_scaling else 'no_scaling'

    coins = [s.split('/')[0] for s in REAL_SYMBOLS] if DATA_SOURCE == 'real' else MOCK_COINS
    data = load_ohlcv_data(coins, use_real=(DATA_SOURCE == 'real'))

    # Get universe
    universe = get_universe(data)

    # Dates
    dates = pd.date_range(start_date, end_date, freq='D')

    # Regime filter: BTC data
    btc_close = data[REGIME_ASSET]['close']
    btc_sma_200 = sma(btc_close, REGIME_PERIOD)
    btc_sma_50 = sma(btc_close, 50)
    btc_momentum_50_200 = pd.DataFrame({
        'sma_50': btc_sma_50,
        'sma_200': btc_sma_200
    })

    available_btc_dates = dates.intersection(btc_close.index)
    if len(available_btc_dates) == 0:
        empty_indexed = pd.DataFrame(columns=['value']).rename_axis('date')
        empty_trades = pd.DataFrame()
        return {
            'equity_curve': empty_indexed.copy(),
            'trades': empty_trades,
            'holdings': pd.DataFrame(columns=['holdings', 'value']).rename_axis('date'),
            'diagnostics': pd.DataFrame().rename_axis('date'),
            'participation_debug': pd.DataFrame(),
            'btc_equity': empty_indexed.copy(),
            'eth_equity': empty_indexed.copy(),
            'summary_diagnostics': {
                'data_source': DATA_SOURCE,
                'num_assets_tested': len(universe),
                'start_date': str(start_date),
                'end_date': str(end_date),
                'date_range': f'{start_date} to {end_date}',
                'avg_exposure': 0,
                'time_in_cash': 0,
                'annualized_turnover': 0,
                'total_fees': 0,
                'total_slippage': 0
            }
        }

    # Benchmarks
    first_btc_date = available_btc_dates[0]
    btc_start = btc_close.loc[first_btc_date]
    eth_start = data['ETH']['close'].loc[first_btc_date] if 'ETH' in data and first_btc_date in data['ETH'].index else 100
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
    latest_breadth = None
    latest_alt_participation = None
    latest_target_exposure = 1.0
    participation_debug = []

    rebalance_dates = _build_rebalance_dates(start_date, end_date, rebalance_freq)

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
            current_prices, execution_prices, average_daily_dollar_volume, execution_details = _execution_context(
                data,
                universe,
                date,
                execution_mode=execution_mode
            )

            portfolio_value = cash + sum(
                holdings[coin]['shares'] * current_prices.get(coin, holdings[coin]['entry_price'])
                for coin in holdings
            )

            ranked = rank_coins(universe, data, date, momentum_mode=momentum_mode, signal_period=momentum_lookback)
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
                    if current_price < highest * (1 - trailing_stop_pct):
                        exit_coins.append(coin)

            # Execute exits
            for coin in exit_coins:
                if coin not in holdings:
                    continue
                shares = holdings[coin]['shares']
                entry_date = holdings[coin]['entry_date']
                expected_fill = current_prices.get(coin, holdings[coin]['entry_price'])
                simulated_fill = execution_prices.get(coin, expected_fill)
                notional = shares * simulated_fill
                fee = notional * TRADING_FEE
                adv = average_daily_dollar_volume.get(coin, 0)
                adv_participation = notional / adv if adv > 0 else 0
                slippage_pct = _liquidity_slippage_pct(notional, adv)
                slippage = notional * slippage_pct
                net_proceeds = notional - fee - slippage
                cash += net_proceeds
                total_fees += fee
                total_slippage += slippage
                holding_days = (date - entry_date).days
                avg_holding_periods.append(holding_days)
                all_trades.append(_trade_record(
                    date, coin, 'exit', expected_fill, simulated_fill, shares,
                    fee, slippage, slippage_pct, adv_participation, execution_mode,
                    execution_details.get(coin),
                    {'net_proceeds': net_proceeds, 'holding_days': holding_days}
                ))
                del holdings[coin]

            target_coins = [coin for coin in target_coins if coin not in exit_coins]
            target_weights = calculate_position_weights(target_coins, data, date, sizing_mode=position_sizing_mode)
            if exposure_scaling_mode != 'no_scaling':
                latest_breadth = calculate_market_breadth(universe, data, date)
                latest_alt_participation = calculate_alt_participation(universe, data, date, btc_asset=REGIME_ASSET)
                latest_target_exposure = target_exposure_for_mode(
                    latest_breadth,
                    latest_alt_participation,
                    exposure_scaling_mode,
                    breadth_full_threshold=breadth_full_threshold
                )
                target_weights = scale_position_weights(target_weights, latest_target_exposure)
            else:
                latest_breadth = None
                latest_alt_participation = None
                latest_target_exposure = 1.0
            participation_debug.append({
                'date': date,
                'exposure_scaling_mode': exposure_scaling_mode,
                'breadth_pct': latest_breadth * 100 if latest_breadth is not None else None,
                'alt_participation_pct': latest_alt_participation * 100 if latest_alt_participation is not None else None,
                'target_exposure': latest_target_exposure,
                'momentum_lookback': momentum_lookback,
                'breadth_full_threshold': breadth_full_threshold,
                'trailing_stop_pct': trailing_stop_pct,
                'selected_coins': '|'.join(target_coins),
                'target_weights': target_weights.copy(),
                'portfolio_value': portfolio_value
            })
            holdings, cash, rebalance_trades, fees, slippage = _rebalance_portfolio(
                holdings,
                target_weights,
                current_prices,
                portfolio_value,
                cash,
                date,
                execution_prices=execution_prices,
                average_daily_dollar_volume=average_daily_dollar_volume,
                execution_details=execution_details,
                execution_mode=execution_mode
            )
            total_fees += fees
            total_slippage += slippage
            all_trades.extend(rebalance_trades)

        current_prices = {}
        for coin in holdings:
            if coin in data and date in data[coin].index:
                current_prices[coin] = data[coin]['close'].loc[date]
            else:
                current_prices[coin] = holdings[coin]['entry_price']
        portfolio_value = cash + sum(holdings[coin]['shares'] * current_prices.get(coin, holdings[coin]['entry_price']) for coin in holdings)
        invested_value = sum(holdings[coin]['shares'] * current_prices.get(coin, holdings[coin]['entry_price']) for coin in holdings)
        exposure = invested_value / portfolio_value if portfolio_value > 0 else 0

        equity_curve.append({'date': date, 'value': portfolio_value})
        holdings_snapshot = {coin: holdings[coin]['shares'] * current_prices.get(coin, holdings[coin]['entry_price']) for coin in holdings}
        holdings_history.append({'date': date, 'holdings': holdings_snapshot, 'value': portfolio_value})
        diagnostics.append({
            'date': date,
            'regime_active': regime_active,
            'breadth': latest_breadth,
            'alt_participation': latest_alt_participation,
            'target_exposure': latest_target_exposure,
            'exposure': exposure,
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
    participation_debug_df = pd.DataFrame(participation_debug)
    btc_df = pd.DataFrame(btc_equity).set_index('date')
    eth_df = pd.DataFrame(eth_equity).set_index('date')

    n_years = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days / 365.25
    avg_positions = diagnostics_df['n_positions'].mean()
    avg_exposure = diagnostics_df['exposure'].mean() if 'exposure' in diagnostics_df else 0
    time_in_cash = (diagnostics_df['exposure'] <= 1e-6).mean() if 'exposure' in diagnostics_df else 0
    rebalance_count = len(rebalance_dates)
    total_trade_notional = trades_df['trade_notional'].sum() if not trades_df.empty and 'trade_notional' in trades_df else 0
    avg_equity = equity_df['value'].mean() if not equity_df.empty else 0
    annualized_turnover = total_trade_notional / avg_equity / n_years if n_years > 0 and avg_equity > 0 else 0
    avg_turnover_per_rebalance = total_trade_notional / avg_equity / rebalance_count if rebalance_count > 0 and avg_equity > 0 else 0
    avg_holding_period = sum(avg_holding_periods) / len(avg_holding_periods) if avg_holding_periods else 0

    summary_diagnostics = {
        'data_source': DATA_SOURCE,
        'num_assets_tested': len(universe),
        'start_date': str(start_date),
        'end_date': str(end_date),
        'date_range': f'{start_date} to {end_date}',
        'survivorship_bias': True,
        'survivorship_note': 'Using static universe of current top coins',
        'avg_positions_held': avg_positions,
        'avg_exposure': avg_exposure,
        'time_in_cash': time_in_cash,
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
        'participation_debug': participation_debug_df,
        'btc_equity': btc_df,
        'eth_equity': eth_df,
        'summary_diagnostics': summary_diagnostics,
        'final_holdings': holdings.copy(),
        'final_cash': cash,
        'final_portfolio_value': equity_df['value'].iloc[-1] if not equity_df.empty else STARTING_CAPITAL
    }


def run_backtest():
    return run_variant_backtest(entry_top=TOP_N, exit_top=EXIT_TOP_N, trailing_stop=True, rebalance_freq=REBALANCE_FREQ, momentum_mode=MOMENTUM_MODE, regime_filter_mode=REGIME_FILTER_MODE, position_sizing_mode=POSITION_SIZING_MODE, use_breadth_scaling=USE_BREADTH_SCALING)


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


def compare_sizing():
    """
    Compare sizing mode performance for absolute momentum under the BTC 200DMA regime.
    """
    sizing_configs = [
        {
            'name': 'equal_weight_top5',
            'position_sizing_mode': 'equal_weight',
            'entry_top': 5
        },
        {
            'name': 'inverse_volatility_top5',
            'position_sizing_mode': 'inverse_volatility',
            'entry_top': 5
        },
        {
            'name': 'equal_weight_top10',
            'position_sizing_mode': 'equal_weight',
            'entry_top': 10
        },
        {
            'name': 'inverse_volatility_top10',
            'position_sizing_mode': 'inverse_volatility',
            'entry_top': 10
        }
    ]

    rows = []
    from performance import calculate_performance

    for config in sizing_configs:
        results = run_variant_backtest(
            entry_top=config['entry_top'],
            exit_top=15,
            trailing_stop=True,
            rebalance_freq='weekly',
            momentum_mode='absolute',
            regime_filter_mode='btc_200dma',
            position_sizing_mode=config['position_sizing_mode']
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
            'position_sizing_mode': config['position_sizing_mode'],
            'entry_top': config['entry_top'],
            'strategy_cagr': metrics['Strategy CAGR'],
            'strategy_max_drawdown': metrics['Strategy Max Drawdown'],
            'strategy_sharpe': metrics['Strategy Sharpe'],
            'total_trades': metrics['Total Trades'],
            'annualized_turnover': metrics['Annualized Turnover'],
            'total_fees': metrics['Total Fees'],
            'total_slippage': metrics['Total Slippage'],
            'final_equity': results['equity_curve']['value'].iloc[-1] if not results['equity_curve'].empty else 0,
            'avg_positions_held': results['summary_diagnostics'].get('avg_positions_held', 0),
            'avg_holding_period': results['summary_diagnostics'].get('avg_holding_period', 0)
        })

    return pd.DataFrame(rows)


def compare_exposure():
    """
    Compare baseline inverse-volatility top 5 against breadth-scaled exposure.
    """
    exposure_configs = [
        {
            'name': 'baseline_inverse_volatility_top5',
            'use_breadth_scaling': False
        },
        {
            'name': 'breadth_scaled_inverse_volatility_top5',
            'use_breadth_scaling': True
        }
    ]

    rows = []
    from performance import calculate_performance

    for config in exposure_configs:
        results = run_variant_backtest(
            entry_top=5,
            exit_top=15,
            trailing_stop=True,
            rebalance_freq='weekly',
            momentum_mode='absolute',
            regime_filter_mode='btc_200dma',
            position_sizing_mode='inverse_volatility',
            use_breadth_scaling=config['use_breadth_scaling']
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
            'use_breadth_scaling': config['use_breadth_scaling'],
            'strategy_cagr': metrics['Strategy CAGR'],
            'strategy_max_drawdown': metrics['Strategy Max Drawdown'],
            'strategy_sharpe': metrics['Strategy Sharpe'],
            'total_trades': metrics['Total Trades'],
            'avg_exposure_pct': results['summary_diagnostics'].get('avg_exposure', 0) * 100,
            'time_in_cash_pct': results['summary_diagnostics'].get('time_in_cash', 0) * 100,
            'final_equity': results['equity_curve']['value'].iloc[-1] if not results['equity_curve'].empty else 0,
            'turnover': metrics['Annualized Turnover'],
            'total_fees': metrics['Total Fees'],
            'total_slippage': metrics['Total Slippage'],
            'fees_slippage': metrics['Total Fees'] + metrics['Total Slippage']
        })

    return pd.DataFrame(rows)


def compare_participation():
    """
    Compare BTC-led versus broad-alt participation exposure scaling modes.
    """
    exposure_configs = [
        {
            'name': 'no_scaling',
            'exposure_scaling_mode': 'no_scaling'
        },
        {
            'name': 'breadth_100dma_scaling',
            'exposure_scaling_mode': 'breadth_100dma_scaling'
        },
        {
            'name': 'alt_participation_scaling',
            'exposure_scaling_mode': 'alt_participation_scaling'
        },
        {
            'name': 'combined_breadth_and_alt_participation',
            'exposure_scaling_mode': 'combined_breadth_and_alt_participation'
        }
    ]

    coins = [s.split('/')[0] for s in REAL_SYMBOLS] if DATA_SOURCE == 'real' else MOCK_COINS
    data = load_ohlcv_data(coins, use_real=(DATA_SOURCE == 'real'))
    latest_available_date = _latest_available_backtest_date(data)

    rows = []
    debug_frames = []
    from performance import calculate_performance

    for config in exposure_configs:
        results = run_variant_backtest(
            entry_top=5,
            exit_top=15,
            trailing_stop=True,
            rebalance_freq='weekly',
            momentum_mode='absolute',
            regime_filter_mode='btc_200dma',
            position_sizing_mode='inverse_volatility',
            exposure_scaling_mode=config['exposure_scaling_mode'],
            start_date=START_DATE,
            end_date=latest_available_date
        )
        metrics = calculate_performance(
            results['equity_curve'],
            results['trades'],
            results['btc_equity'],
            results['eth_equity'],
            results['summary_diagnostics'],
            start_date=START_DATE,
            end_date=latest_available_date
        )
        rows.append({
            'variant': config['name'],
            'exposure_scaling_mode': config['exposure_scaling_mode'],
            'strategy_cagr': metrics['Strategy CAGR'],
            'strategy_max_drawdown': metrics['Strategy Max Drawdown'],
            'strategy_sharpe': metrics['Strategy Sharpe'],
            'total_trades': metrics['Total Trades'],
            'avg_exposure_pct': results['summary_diagnostics'].get('avg_exposure', 0) * 100,
            'time_in_cash_pct': results['summary_diagnostics'].get('time_in_cash', 0) * 100,
            'final_equity': results['equity_curve']['value'].iloc[-1] if not results['equity_curve'].empty else 0,
            'total_fees': metrics['Total Fees'],
            'total_slippage': metrics['Total Slippage'],
            'fees_slippage': metrics['Total Fees'] + metrics['Total Slippage'],
            'btc_cagr': metrics['BTC CAGR'],
            'btc_max_drawdown': metrics['BTC Max Drawdown'],
            'btc_sharpe': metrics['BTC Sharpe'],
            'eth_cagr': metrics['ETH CAGR'],
            'eth_max_drawdown': metrics['ETH Max Drawdown'],
            'eth_sharpe': metrics['ETH Sharpe']
        })

        debug = results['participation_debug'].copy()
        if not debug.empty:
            debug.insert(0, 'variant', config['name'])
            debug_frames.append(debug)

    debug_df = pd.concat(debug_frames, ignore_index=True) if debug_frames else pd.DataFrame(
        columns=['variant', 'date', 'exposure_scaling_mode', 'breadth_pct', 'alt_participation_pct', 'target_exposure']
    )
    return pd.DataFrame(rows), debug_df


def build_sensitivity_summary(sensitivity_df):
    """Summarize the parameter grid by best headline metrics and median Sharpe."""
    if sensitivity_df.empty:
        return pd.DataFrame()

    summary_rows = []
    selectors = [
        ('best_sharpe_configuration', sensitivity_df['strategy_sharpe'].idxmax()),
        ('best_cagr_configuration', sensitivity_df['strategy_cagr'].idxmax()),
        ('lowest_drawdown_configuration', sensitivity_df['strategy_max_drawdown'].idxmax())
    ]
    config_columns = ['momentum_lookback', 'breadth_threshold_pct', 'trailing_stop_pct', 'entry_top']
    metric_columns = ['strategy_cagr', 'strategy_max_drawdown', 'strategy_sharpe', 'total_trades', 'avg_exposure_pct', 'final_equity']
    for label, idx in selectors:
        row = sensitivity_df.loc[idx]
        summary = {'summary_metric': label}
        for column in config_columns + metric_columns:
            summary[column] = row[column]
        summary_rows.append(summary)

    median_row = {'summary_metric': 'median_sharpe_across_all_tests'}
    for column in config_columns + metric_columns:
        median_row[column] = None
    median_row['strategy_sharpe'] = sensitivity_df['strategy_sharpe'].median()
    summary_rows.append(median_row)
    return pd.DataFrame(summary_rows)


def parameter_sensitivity_results():
    """
    Run a full-factorial sensitivity grid around the current best strategy.
    """
    momentum_lookbacks = [20, 30, 60, 90]
    breadth_thresholds = [0.60, 0.70, 0.80]
    trailing_stops = [0.15, 0.25, 0.35]
    entry_tops = [3, 5, 10]

    coins = [s.split('/')[0] for s in REAL_SYMBOLS] if DATA_SOURCE == 'real' else MOCK_COINS
    data = load_ohlcv_data(coins, use_real=(DATA_SOURCE == 'real'))
    latest_available_date = _latest_available_backtest_date(data)

    rows = []
    from performance import calculate_performance

    for momentum_lookback in momentum_lookbacks:
        for breadth_threshold in breadth_thresholds:
            for trailing_stop_pct in trailing_stops:
                for entry_top in entry_tops:
                    results = run_variant_backtest(
                        entry_top=entry_top,
                        exit_top=max(15, entry_top * 3),
                        trailing_stop=True,
                        rebalance_freq='weekly',
                        momentum_mode='absolute',
                        regime_filter_mode='btc_200dma',
                        position_sizing_mode='inverse_volatility',
                        exposure_scaling_mode='breadth_100dma_scaling',
                        momentum_lookback=momentum_lookback,
                        breadth_full_threshold=breadth_threshold,
                        trailing_stop_pct=trailing_stop_pct,
                        start_date=START_DATE,
                        end_date=latest_available_date
                    )
                    metrics = calculate_performance(
                        results['equity_curve'],
                        results['trades'],
                        results['btc_equity'],
                        results['eth_equity'],
                        results['summary_diagnostics'],
                        start_date=START_DATE,
                        end_date=latest_available_date
                    )
                    rows.append({
                        'momentum_lookback': momentum_lookback,
                        'breadth_threshold_pct': breadth_threshold * 100,
                        'trailing_stop_pct': trailing_stop_pct * 100,
                        'entry_top': entry_top,
                        'strategy_cagr': metrics['Strategy CAGR'],
                        'strategy_max_drawdown': metrics['Strategy Max Drawdown'],
                        'strategy_sharpe': metrics['Strategy Sharpe'],
                        'total_trades': metrics['Total Trades'],
                        'avg_exposure_pct': results['summary_diagnostics'].get('avg_exposure', 0) * 100,
                        'final_equity': results['equity_curve']['value'].iloc[-1] if not results['equity_curve'].empty else 0
                    })

    sensitivity_df = pd.DataFrame(rows)
    return sensitivity_df, build_sensitivity_summary(sensitivity_df)


def _next_rebalance_date(current_date, start_date=START_DATE, rebalance_freq='weekly'):
    """Return the next scheduled rebalance date after the current date."""
    search_end = pd.Timestamp(current_date) + pd.Timedelta(days=60)
    rebalance_dates = _build_rebalance_dates(start_date, search_end, rebalance_freq)
    future_dates = rebalance_dates[rebalance_dates > pd.Timestamp(current_date)]
    if len(future_dates) == 0:
        return None
    return future_dates[0]


def generate_live_signals():
    """
    Generate current production-candidate signals from the latest available data.
    """
    production_params = {
        'entry_top': 5,
        'exit_top': 15,
        'trailing_stop_pct': 0.15,
        'momentum_lookback': 20,
        'position_sizing_mode': 'inverse_volatility',
        'exposure_scaling_mode': 'breadth_100dma_scaling',
        'rebalance_freq': 'weekly',
        'momentum_mode': 'absolute',
        'regime_filter_mode': 'btc_200dma'
    }

    coins = [s.split('/')[0] for s in REAL_SYMBOLS] if DATA_SOURCE == 'real' else MOCK_COINS
    data = load_ohlcv_data(coins, use_real=(DATA_SOURCE == 'real'))
    universe = get_universe(data)
    latest_date = _latest_available_backtest_date(data)

    btc_close = data[REGIME_ASSET]['close']
    btc_sma_200 = sma(btc_close, REGIME_PERIOD)
    btc_sma_50 = sma(btc_close, 50)
    btc_momentum_50_200 = pd.DataFrame({
        'sma_50': btc_sma_50,
        'sma_200': btc_sma_200
    })
    btc_regime_active = bool(_check_regime(
        latest_date,
        production_params['regime_filter_mode'],
        btc_close,
        btc_sma_200,
        btc_momentum_50_200
    ))

    scores = get_momentum_scores(
        universe,
        data,
        latest_date,
        momentum_mode=production_params['momentum_mode'],
        signal_period=production_params['momentum_lookback']
    )
    score_by_coin = dict(scores)
    ranked = [coin for coin, _ in sorted(scores, key=lambda item: item[1], reverse=True)]
    selected_coins = ranked[:production_params['entry_top']]

    pre_exposure_weights = calculate_position_weights(
        selected_coins,
        data,
        latest_date,
        sizing_mode=production_params['position_sizing_mode']
    )
    breadth = calculate_market_breadth(universe, data, latest_date)
    breadth_target_exposure = target_exposure_for_mode(
        breadth,
        None,
        production_params['exposure_scaling_mode']
    )
    target_exposure = breadth_target_exposure
    if not btc_regime_active:
        target_exposure = 0.0
    target_weights = scale_position_weights(pre_exposure_weights, target_exposure)

    backtest_results = run_variant_backtest(
        entry_top=production_params['entry_top'],
        exit_top=production_params['exit_top'],
        trailing_stop=True,
        rebalance_freq=production_params['rebalance_freq'],
        momentum_mode=production_params['momentum_mode'],
        regime_filter_mode=production_params['regime_filter_mode'],
        position_sizing_mode=production_params['position_sizing_mode'],
        exposure_scaling_mode=production_params['exposure_scaling_mode'],
        momentum_lookback=production_params['momentum_lookback'],
        trailing_stop_pct=production_params['trailing_stop_pct'],
        start_date=START_DATE,
        end_date=latest_date
    )
    final_holdings = backtest_results.get('final_holdings', {})
    current_prices = {}
    for coin, df in data.items():
        available_prices = df['close'].loc[:latest_date]
        if not available_prices.empty:
            current_prices[coin] = available_prices.iloc[-1]
    final_portfolio_value = backtest_results.get('final_portfolio_value', STARTING_CAPITAL)
    final_cash = backtest_results.get('final_cash', STARTING_CAPITAL)
    cash_allocation = max(0.0, 1.0 - sum(target_weights.values()))
    current_cash_allocation = final_cash / final_portfolio_value if final_portfolio_value > 0 else 1.0
    next_rebalance = _next_rebalance_date(latest_date, START_DATE, production_params['rebalance_freq'])
    next_rebalance_value = str(next_rebalance.date()) if next_rebalance is not None else None

    rows = []
    for rank, coin in enumerate(selected_coins, start=1):
        current_price = current_prices.get(coin)
        holding = final_holdings.get(coin)
        if holding:
            entry_date = holding['entry_date']
            highest_since_entry = data[coin]['close'].loc[entry_date:latest_date].max()
            trailing_stop_level = highest_since_entry * (1 - production_params['trailing_stop_pct'])
            held_value = holding['shares'] * current_price if current_price is not None else 0
            current_weight = held_value / final_portfolio_value if final_portfolio_value > 0 else 0
            holding_status = 'held'
        else:
            trailing_stop_level = current_price * (1 - production_params['trailing_stop_pct']) if current_price is not None else None
            current_weight = 0
            holding_status = 'new_or_not_held'

        rows.append({
            'date': latest_date.date(),
            'rank': rank,
            'coin': coin,
            'selected': True,
            'momentum_score': score_by_coin.get(coin),
            'current_price': current_price,
            'pre_exposure_weight': pre_exposure_weights.get(coin, 0),
            'target_weight': target_weights.get(coin, 0),
            'current_weight': current_weight,
            'holding_status': holding_status,
            'breadth_pct': breadth * 100,
            'breadth_regime_status': 'full' if breadth_target_exposure == 1.0 else 'half' if breadth_target_exposure == 0.5 else 'cash',
            'target_exposure': target_exposure,
            'target_cash_allocation': cash_allocation,
            'current_cash_allocation': current_cash_allocation,
            'btc_regime_active': btc_regime_active,
            'regime_filter_state': 'active' if btc_regime_active else 'inactive',
            'trailing_stop_level': trailing_stop_level,
            'next_rebalance_date': next_rebalance_value
        })

    signals_df = pd.DataFrame(rows)
    snapshot = {
        'as_of_date': str(latest_date.date()),
        'strategy': 'production_candidate',
        'parameters': production_params,
        'selected_coins': selected_coins,
        'target_exposure': target_exposure,
        'cash_allocation': cash_allocation,
        'current_cash_allocation': current_cash_allocation,
        'btc_regime_active': btc_regime_active,
        'regime_filter_state': 'active' if btc_regime_active else 'inactive',
        'breadth_pct': breadth * 100,
        'breadth_regime_status': 'full' if breadth_target_exposure == 1.0 else 'half' if breadth_target_exposure == 0.5 else 'cash',
        'next_rebalance_date': next_rebalance_value,
        'portfolio_value': final_portfolio_value,
        'cash': final_cash,
        'positions': [
            {
                'coin': coin,
                'target_weight': float(target_weights.get(coin, 0)),
                'current_weight': float(signals_df.loc[signals_df['coin'] == coin, 'current_weight'].iloc[0]),
                'trailing_stop_level': float(signals_df.loc[signals_df['coin'] == coin, 'trailing_stop_level'].iloc[0])
            }
            for coin in selected_coins
        ]
    }
    log_row = {
        'run_timestamp': pd.Timestamp.utcnow().isoformat(),
        'as_of_date': str(latest_date.date()),
        'selected_coins': '|'.join(selected_coins),
        'target_exposure': target_exposure,
        'cash_allocation': cash_allocation,
        'current_cash_allocation': snapshot['current_cash_allocation'],
        'breadth_pct': breadth * 100,
        'btc_regime_active': btc_regime_active,
        'regime_filter_state': snapshot['regime_filter_state'],
        'next_rebalance_date': snapshot['next_rebalance_date']
    }
    return signals_df, snapshot, pd.DataFrame([log_row])


def _parse_coin_set(value):
    if not isinstance(value, str) or not value:
        return set()
    return set(value.split('|'))


def _signal_stability_pct(previous_coins, current_coins):
    """Percentage of the previous signal basket that remains in the current basket."""
    previous_coins = set(previous_coins)
    current_coins = set(current_coins)
    if not previous_coins and not current_coins:
        return 100.0
    if not previous_coins:
        return 0.0
    return len(previous_coins & current_coins) / len(previous_coins) * 100


def _portfolio_overlap_pct(previous_weights, current_weights):
    """Weighted overlap between two rebalance target portfolios."""
    previous_weights = previous_weights or {}
    current_weights = current_weights or {}
    denominator = max(sum(previous_weights.values()), sum(current_weights.values()))
    if denominator <= 0:
        return 100.0
    coins = set(previous_weights) | set(current_weights)
    overlap = sum(min(previous_weights.get(coin, 0), current_weights.get(coin, 0)) for coin in coins)
    return overlap / denominator * 100


def build_forward_test_analytics(participation_debug, trades):
    """Build rebalance-to-rebalance forward-testing analytics."""
    if participation_debug.empty:
        return pd.DataFrame()

    trades_by_date = trades.groupby('date') if not trades.empty and 'date' in trades else {}
    rows = []
    previous_coins = set()
    previous_weights = {}
    previous_exposure = None
    for _, row in participation_debug.sort_values('date').iterrows():
        date = row['date']
        current_coins = _parse_coin_set(row.get('selected_coins'))
        current_weights = row.get('target_weights') if isinstance(row.get('target_weights'), dict) else {}
        if hasattr(trades_by_date, 'groups') and date in trades_by_date.groups:
            day_trades = trades_by_date.get_group(date)
        else:
            day_trades = pd.DataFrame()
        trade_notional = day_trades['trade_notional'].sum() if not day_trades.empty and 'trade_notional' in day_trades else 0.0
        portfolio_value = row.get('portfolio_value', 0)
        turnover = trade_notional / portfolio_value if portfolio_value else 0.0
        exit_trades = day_trades[day_trades['holding_days'].notna()] if not day_trades.empty and 'holding_days' in day_trades else pd.DataFrame()
        avg_holding_days = exit_trades['holding_days'].mean() if not exit_trades.empty else None
        target_exposure = row.get('target_exposure', 0)
        rows.append({
            'date': date,
            'signal_stability_pct': _signal_stability_pct(previous_coins, current_coins),
            'turnover': turnover,
            'avg_holding_duration_on_exits': avg_holding_days,
            'target_exposure': target_exposure,
            'exposure_regime_transition': previous_exposure is not None and target_exposure != previous_exposure,
            'portfolio_overlap_pct': _portfolio_overlap_pct(previous_weights, current_weights)
        })
        previous_coins = current_coins
        previous_weights = current_weights
        previous_exposure = target_exposure

    return pd.DataFrame(rows)


def execution_analysis_results():
    """
    Compare production-candidate execution assumptions and collect diagnostics.
    """
    execution_modes = ['same_close', 'next_open', 'next_day_vwap_approx']
    rows = []
    execution_frames = []
    analytics_frames = []
    from performance import calculate_performance

    coins = [s.split('/')[0] for s in REAL_SYMBOLS] if DATA_SOURCE == 'real' else MOCK_COINS
    data = load_ohlcv_data(coins, use_real=(DATA_SOURCE == 'real'))
    latest_available_date = _latest_available_backtest_date(data)

    baseline_metrics = None
    baseline_final_equity = None
    for execution_mode in execution_modes:
        results = run_variant_backtest(
            entry_top=5,
            exit_top=15,
            trailing_stop=True,
            rebalance_freq='weekly',
            momentum_mode='absolute',
            regime_filter_mode='btc_200dma',
            position_sizing_mode='inverse_volatility',
            exposure_scaling_mode='breadth_100dma_scaling',
            momentum_lookback=20,
            trailing_stop_pct=0.15,
            execution_mode=execution_mode,
            start_date=START_DATE,
            end_date=latest_available_date
        )
        metrics = calculate_performance(
            results['equity_curve'],
            results['trades'],
            results['btc_equity'],
            results['eth_equity'],
            results['summary_diagnostics'],
            start_date=START_DATE,
            end_date=latest_available_date
        )
        final_equity = results['equity_curve']['value'].iloc[-1] if not results['equity_curve'].empty else STARTING_CAPITAL
        if execution_mode == 'same_close':
            baseline_metrics = metrics
            baseline_final_equity = final_equity
        analytics = build_forward_test_analytics(results['participation_debug'], results['trades'])
        rows.append({
            'execution_mode': execution_mode,
            'strategy_cagr': metrics['Strategy CAGR'],
            'strategy_sharpe': metrics['Strategy Sharpe'],
            'final_equity': final_equity,
            'cagr_impact_vs_same_close': metrics['Strategy CAGR'] - baseline_metrics['Strategy CAGR'] if baseline_metrics else 0.0,
            'sharpe_impact_vs_same_close': metrics['Strategy Sharpe'] - baseline_metrics['Strategy Sharpe'] if baseline_metrics else 0.0,
            'final_equity_impact_vs_same_close': final_equity - baseline_final_equity if baseline_final_equity is not None else 0.0,
            'total_execution_drag': metrics['Total Fees'] + metrics['Total Slippage'],
            'total_fees': metrics['Total Fees'],
            'total_slippage': metrics['Total Slippage'],
            'average_portfolio_overlap_pct': analytics['portfolio_overlap_pct'].mean() if not analytics.empty else 0.0
        })

        trades = results['trades'].copy()
        if not trades.empty:
            trades.insert(0, 'execution_scenario', execution_mode)
            execution_frames.append(trades)

        if not analytics.empty:
            analytics.insert(0, 'execution_scenario', execution_mode)
            analytics_frames.append(analytics)

    summary = pd.DataFrame(rows)
    execution_diagnostics = pd.concat(execution_frames, ignore_index=True) if execution_frames else pd.DataFrame()
    forward_analytics = pd.concat(analytics_frames, ignore_index=True) if analytics_frames else pd.DataFrame()
    avg_slippage = execution_diagnostics.groupby(['execution_scenario', 'coin'])['slippage_pct'].mean().reset_index(name='avg_slippage_pct') if not execution_diagnostics.empty else pd.DataFrame()
    highest_turnover_assets = execution_diagnostics.groupby(['execution_scenario', 'coin'])['trade_notional'].sum().reset_index(name='total_trade_notional') if not execution_diagnostics.empty else pd.DataFrame()
    execution_audit = build_execution_audit(execution_diagnostics)
    return summary, execution_diagnostics, forward_analytics, avg_slippage, highest_turnover_assets, execution_audit


def _is_buy_action(action):
    return action in {'rebalance_buy', 'entry', 'buy'}


def _is_sell_action(action):
    return action in {'rebalance_sell', 'exit', 'sell'}


def build_execution_audit(execution_diagnostics):
    """Compare trade-level fills across execution modes and flag timing issues."""
    if execution_diagnostics.empty:
        return pd.DataFrame()

    diagnostics = execution_diagnostics.copy()
    diagnostics['trade_sequence'] = diagnostics.groupby('execution_scenario').cumcount()
    base = diagnostics[diagnostics['execution_scenario'] == 'same_close'][
        ['trade_sequence', 'coin', 'action', 'expected_fill', 'simulated_fill']
    ].rename(columns={
        'expected_fill': 'same_close_expected_fill',
        'simulated_fill': 'same_close_fill',
        'coin': 'same_close_coin',
        'action': 'same_close_action'
    })

    delayed = diagnostics[diagnostics['execution_scenario'].isin(['next_open', 'next_day_vwap_approx'])].copy()
    audit = delayed.merge(base, on='trade_sequence', how='left')
    audit['same_trade_identity'] = (
        (audit['coin'] == audit['same_close_coin']) &
        (audit['action'] == audit['same_close_action'])
    )
    audit['fill_delta_vs_same_close'] = audit['simulated_fill'] - audit['same_close_fill']
    audit['portfolio_update_before_execution'] = pd.to_datetime(audit['portfolio_update_date']) < pd.to_datetime(audit['execution_date'])
    audit['uses_data_after_signal'] = pd.to_datetime(audit['fill_data_end_date']) > pd.to_datetime(audit['signal_date'])
    audit['future_data_access_assertion_passed'] = pd.to_datetime(audit['fill_data_end_date']) <= pd.to_datetime(audit['execution_date'])
    audit['delayed_execution_improved_fill'] = audit.apply(
        lambda row: (
            (_is_buy_action(row['action']) and row['simulated_fill'] < row['same_close_fill']) or
            (_is_sell_action(row['action']) and row['simulated_fill'] > row['same_close_fill'])
        ) if pd.notna(row['same_close_fill']) else False,
        axis=1
    )
    audit['unrealistic_improvement_flag'] = (
        audit['delayed_execution_improved_fill'] &
        (
            audit['portfolio_update_before_execution'] |
            audit['fill_uses_full_next_day_ohlc']
        )
    )
    columns = [
        'execution_scenario', 'trade_sequence', 'signal_date', 'execution_date',
        'portfolio_update_date', 'fill_data_end_date', 'coin', 'action',
        'same_close_fill', 'expected_fill', 'simulated_fill', 'fill_delta_vs_same_close',
        'same_trade_identity', 'uses_data_after_signal', 'fill_uses_full_next_day_ohlc',
        'portfolio_update_before_execution', 'future_data_access_assertion_passed',
        'delayed_execution_improved_fill', 'unrealistic_improvement_flag',
        'trade_notional', 'slippage_pct', 'adv_participation_pct'
    ]
    return audit[columns]


def get_walkforward_periods(end_date=END_DATE):
    """Return non-overlapping walk-forward crypto market regimes."""
    final_end = str(pd.Timestamp(end_date).date())
    return [
        {
            'period': '2020_2021',
            'start_date': '2020-01-01',
            'end_date': '2021-12-31'
        },
        {
            'period': '2022',
            'start_date': '2022-01-01',
            'end_date': '2022-12-31'
        },
        {
            'period': '2023_onward',
            'start_date': '2023-01-01',
            'end_date': final_end
        }
    ]


def periods_do_not_overlap(periods):
    """Return True when every period starts after the previous period ends."""
    sorted_periods = sorted(periods, key=lambda period: pd.Timestamp(period['start_date']))
    for previous, current in zip(sorted_periods, sorted_periods[1:]):
        if pd.Timestamp(current['start_date']) <= pd.Timestamp(previous['end_date']):
            return False
    return True


def build_walkforward_row(period, results, metrics):
    """Build one walk-forward output row from an independent backtest run."""
    summary = results['summary_diagnostics']
    equity_curve = results['equity_curve']
    btc_equity = results['btc_equity']
    eth_equity = results['eth_equity']
    return {
        'period': period['period'],
        'start_date': period['start_date'],
        'end_date': period['end_date'],
        'strategy_cagr': metrics.get('Strategy CAGR', 0),
        'strategy_max_drawdown': metrics.get('Strategy Max Drawdown', 0),
        'strategy_sharpe': metrics.get('Strategy Sharpe', 0),
        'total_trades': metrics.get('Total Trades', 0),
        'avg_exposure_pct': summary.get('avg_exposure', 0) * 100,
        'time_in_cash_pct': summary.get('time_in_cash', 0) * 100,
        'final_equity': equity_curve['value'].iloc[-1] if not equity_curve.empty else STARTING_CAPITAL,
        'total_fees': metrics.get('Total Fees', 0),
        'total_slippage': metrics.get('Total Slippage', 0),
        'fees_slippage': metrics.get('Total Fees', 0) + metrics.get('Total Slippage', 0),
        'btc_cagr': metrics.get('BTC CAGR', 0),
        'btc_max_drawdown': metrics.get('BTC Max Drawdown', 0),
        'btc_sharpe': metrics.get('BTC Sharpe', 0),
        'btc_final_equity': btc_equity['value'].iloc[-1] if not btc_equity.empty else STARTING_CAPITAL,
        'eth_cagr': metrics.get('ETH CAGR', 0),
        'eth_max_drawdown': metrics.get('ETH Max Drawdown', 0),
        'eth_sharpe': metrics.get('ETH Sharpe', 0),
        'eth_final_equity': eth_equity['value'].iloc[-1] if not eth_equity.empty else STARTING_CAPITAL
    }


def build_walkforward_data_diagnostics(periods, data, universe):
    """Summarize actual data coverage used by each walk-forward period."""
    bounds = _get_data_date_bounds(data)
    latest_available_date = _latest_available_backtest_date(data)
    asset_date_ranges = '; '.join(
        f"{coin}:{asset_bounds['start_date'].date()} to {asset_bounds['end_date'].date()}"
        for coin, asset_bounds in sorted(bounds.items())
    )
    rows = []
    for period in periods:
        configured_start = pd.Timestamp(period['start_date'])
        configured_end = pd.Timestamp(period['end_date'])
        regime_index = pd.DatetimeIndex(data.get(REGIME_ASSET, pd.DataFrame()).index)
        regime_dates = regime_index[(regime_index >= configured_start) & (regime_index <= configured_end)]
        actual_start = regime_dates.min() if len(regime_dates) > 0 else pd.NaT
        actual_end = regime_dates.max() if len(regime_dates) > 0 else pd.NaT

        assets_with_any_data = []
        missing_coverage = []
        for coin in universe:
            coin_bounds = bounds.get(coin)
            if coin_bounds is None:
                missing_coverage.append(f'{coin}:missing_file')
                continue
            has_any_data = coin_bounds['start_date'] <= configured_end and coin_bounds['end_date'] >= configured_start
            if has_any_data:
                assets_with_any_data.append(coin)
            if pd.isna(actual_start) or pd.isna(actual_end):
                missing_coverage.append(f'{coin}:no_regime_dates')
                continue
            coverage_gaps = []
            if coin_bounds['start_date'] > actual_start:
                coverage_gaps.append(f"starts {coin_bounds['start_date'].date()}")
            if coin_bounds['end_date'] < actual_end:
                coverage_gaps.append(f"ends {coin_bounds['end_date'].date()}")
            if coverage_gaps:
                missing_coverage.append(f"{coin}:{', '.join(coverage_gaps)}")

        rows.append({
            'period': period['period'],
            'configured_start_date': period['start_date'],
            'configured_end_date': period['end_date'],
            'actual_start_date': actual_start.date() if not pd.isna(actual_start) else None,
            'actual_end_date': actual_end.date() if not pd.isna(actual_end) else None,
            'asset_count': len(assets_with_any_data),
            'eligible_asset_count': len(universe),
            'loaded_asset_count': len(bounds),
            'latest_available_date': latest_available_date.date(),
            'asset_date_ranges': asset_date_ranges,
            'missing_asset_coverage_count': len(missing_coverage),
            'missing_asset_coverage': '; '.join(missing_coverage)
        })

    return pd.DataFrame(rows)


def walkforward_results():
    """
    Evaluate the current best strategy independently across market regimes.
    """
    coins = [s.split('/')[0] for s in REAL_SYMBOLS] if DATA_SOURCE == 'real' else MOCK_COINS
    data = load_ohlcv_data(coins, use_real=(DATA_SOURCE == 'real'))
    universe = get_universe(data)
    latest_available_date = _latest_available_backtest_date(data)
    periods = get_walkforward_periods(end_date=latest_available_date)
    rows = []
    from performance import calculate_performance

    for period in periods:
        results = run_variant_backtest(
            entry_top=5,
            exit_top=15,
            trailing_stop=True,
            rebalance_freq='weekly',
            momentum_mode='absolute',
            regime_filter_mode='btc_200dma',
            position_sizing_mode='inverse_volatility',
            use_breadth_scaling=True,
            start_date=period['start_date'],
            end_date=period['end_date']
        )
        metrics = calculate_performance(
            results['equity_curve'],
            results['trades'],
            results['btc_equity'],
            results['eth_equity'],
            results['summary_diagnostics'],
            start_date=period['start_date'],
            end_date=period['end_date']
        )
        rows.append(build_walkforward_row(period, results, metrics))

    diagnostics = build_walkforward_data_diagnostics(periods, data, universe)
    return pd.DataFrame(rows), diagnostics


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
