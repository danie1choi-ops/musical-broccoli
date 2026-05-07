# strategy.py - Module for strategy logic: ranking, entries, exits, portfolio weights

import pandas as pd
from indicators import momentum, relative_momentum, realized_volatility
from config import SIGNAL_PERIOD, TOP_N, EXIT_TOP_N, STOP_LOSS_PCT, MAX_WEIGHT_PER_COIN, MAX_POSITIONS, MAX_POSITION_SIZE

def get_momentum_scores(universe, data, date, momentum_mode='absolute'):
    """
    Calculate momentum scores for all coins as of the given date.
    
    Uses data up to date-1 to avoid look-ahead bias.
    
    Args:
        universe (list): List of eligible coins
        data (dict): OHLCV data
        date (pd.Timestamp): Date for ranking
        momentum_mode (str): 'absolute' or 'relative' (relative to BTC)
    
    Returns:
        list: List of tuples (coin, momentum_score)
    """
    scores = []
    for coin in universe:
        if coin not in data:
            continue
        close_prices = data[coin]['close']
        # Use data up to date - 1 day
        available_data = close_prices.loc[:date].iloc[:-1] if len(close_prices.loc[:date]) > 1 else close_prices.loc[:date]
        if len(available_data) < SIGNAL_PERIOD + 1:
            continue
        
        if momentum_mode == 'relative':
            if 'BTC' not in data:
                continue
            btc_prices = data['BTC']['close']
            btc_available = btc_prices.loc[:date].iloc[:-1] if len(btc_prices.loc[:date]) > 1 else btc_prices.loc[:date]
            if len(btc_available) < SIGNAL_PERIOD + 1:
                continue
            mom = relative_momentum(available_data, btc_available, SIGNAL_PERIOD).iloc[-1]
        else:  # absolute
            mom = momentum(available_data, SIGNAL_PERIOD).iloc[-1]
        
        scores.append((coin, mom))
    
    return scores


def rank_coins(universe, data, date, momentum_mode='absolute'):
    """
    Rank coins by momentum as of the given date.

    Uses data up to date-1 to avoid look-ahead bias.
    
    Args:
        universe (list): List of eligible coins
        data (dict): OHLCV data
        date (pd.Timestamp): Date for ranking
        momentum_mode (str): 'absolute' or 'relative' (relative to BTC)
    
    Returns:
        list: Ranked list of coins (best to worst momentum)
    """
    scores = get_momentum_scores(universe, data, date, momentum_mode)
    # Sort by momentum descending
    scores.sort(key=lambda x: x[1], reverse=True)
    return [coin for coin, _ in scores]


def calculate_position_weights(target_coins, data, date, sizing_mode='equal_weight', vol_period=30, max_position_size=MAX_POSITION_SIZE):
    """
    Calculate target position weights for selected coins.

    Args:
        target_coins (list): Coins selected for entry
        data (dict): OHLCV data
        date (pd.Timestamp): Current date
        sizing_mode (str): 'equal_weight' or 'inverse_volatility'
        vol_period (int): Lookback for volatility calculation
        max_position_size (float): Maximum allowed weight per coin

    Returns:
        dict: Coin weights that sum to <= 1.0
    """
    if sizing_mode == 'equal_weight':
        n = len(target_coins)
        if n == 0:
            return {}
        weight = min(1.0 / n, max_position_size)
        return {coin: weight for coin in target_coins}

    if sizing_mode == 'inverse_volatility':
        raw_weights = {}
        for coin in target_coins:
            if coin not in data or date not in data[coin].index:
                continue
            prices = data[coin]['close']
            available = prices.loc[:date].iloc[:-1] if len(prices.loc[:date]) > 1 else prices.loc[:date]
            if len(available) < vol_period + 1:
                continue
            vol_series = realized_volatility(available, vol_period)
            if vol_series.empty:
                continue
            vol = vol_series.iloc[-1]
            if pd.isna(vol) or vol <= 0:
                continue
            raw_weights[coin] = 1.0 / vol

        if not raw_weights:
            return {}

        capped_weights = {coin: min(weight, max_position_size) for coin, weight in raw_weights.items()}
        total_weight = sum(capped_weights.values())
        if total_weight == 0:
            return {}
        if total_weight > 1.0:
            scale = 1.0 / total_weight
            capped_weights = {coin: weight * scale for coin, weight in capped_weights.items()}
        return capped_weights

    return {}


def get_target_positions(ranked_coins, current_positions, data, date):
    """
    Determine target positions based on ranking and exit rules.

    Args:
        ranked_coins (list): Coins ranked by momentum
        current_positions (dict): Current holdings {coin: entry_info}
        data (dict): OHLCV data
        date (pd.Timestamp): Current date

    Returns:
        dict: Target weights {coin: weight}
    """
    # Top N for entry
    top_coins = ranked_coins[:TOP_N]

    # Check exit rules for current positions
    to_exit = []
    for coin, entry_info in current_positions.items():
        entry_date = entry_info['date']
        entry_price = entry_info['price']
        highest_since_entry = data[coin]['close'].loc[entry_date:date].max()

        # Exit rule 1: falls outside top EXIT_TOP_N
        if coin not in ranked_coins[:EXIT_TOP_N]:
            to_exit.append(coin)
            continue

        # Exit rule 2: price falls 25% from highest since entry
        current_price = data[coin]['close'].loc[date]
        if current_price < highest_since_entry * (1 - STOP_LOSS_PCT):
            to_exit.append(coin)

    # New positions: top_coins not already held or exited
    target_coins = [coin for coin in top_coins if coin not in current_positions or coin not in to_exit]

    # Limit to MAX_POSITIONS
    target_coins = target_coins[:MAX_POSITIONS]

    # Equal weight, but cap at MAX_WEIGHT_PER_COIN
    n_positions = len(target_coins)
    if n_positions == 0:
        return {}

    weight = min(1.0 / n_positions, MAX_WEIGHT_PER_COIN)
    # Adjust if sum exceeds 1, but since max 10 positions, 0.1 each = 1.0

    target_weights = {coin: weight for coin in target_coins}
    return target_weights

def update_positions(current_positions, target_weights, data, date):
    """
    Update positions: enter new, exit old.

    Args:
        current_positions (dict): Current {coin: {'date': entry_date, 'price': entry_price}}
        target_weights (dict): Target {coin: weight}
        data (dict): Data
        date (pd.Timestamp): Date

    Returns:
        dict: New positions, list: trades (entries/exits)
    """
    trades = []
    new_positions = {}

    # Exits: positions not in target
    for coin in current_positions:
        if coin not in target_weights:
            exit_price = data[coin]['close'].loc[date]
            trades.append({
                'date': date,
                'coin': coin,
                'action': 'exit',
                'price': exit_price,
                'weight': 0
            })

    # Entries: new in target
    for coin, weight in target_weights.items():
        if coin not in current_positions:
            entry_price = data[coin]['close'].loc[date]
            new_positions[coin] = {'date': date, 'price': entry_price}
            trades.append({
                'date': date,
                'coin': coin,
                'action': 'entry',
                'price': entry_price,
                'weight': weight
            })
        else:
            new_positions[coin] = current_positions[coin]

    return new_positions, trades