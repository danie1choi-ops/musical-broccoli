# relative_strength_debug.py - Debug relative strength implementation

import pandas as pd
from data_loader import load_ohlcv_data
from universe import get_universe
from indicators import momentum, relative_momentum
from strategy import get_momentum_scores
from config import MOCK_COINS, REAL_SYMBOLS, DATA_SOURCE, START_DATE, END_DATE, SIGNAL_PERIOD

# Load data
coins = [s.split('/')[0] for s in REAL_SYMBOLS] if DATA_SOURCE == 'real' else MOCK_COINS
data = load_ohlcv_data(coins, use_real=(DATA_SOURCE == 'real'))
universe = get_universe(data)

print(f"Data source: {DATA_SOURCE}")
print(f"Universe size: {len(universe)}")
print(f"Sample date: 2021-06-15")

# Pick a sample date during backtest period
sample_date = pd.Timestamp('2021-06-15')

# Get momentum scores using both modes
abs_scores = get_momentum_scores(universe, data, sample_date, momentum_mode='absolute')
rel_scores = get_momentum_scores(universe, data, sample_date, momentum_mode='relative')

# Create dictionaries for easier lookup
abs_dict = {coin: score for coin, score in abs_scores}
rel_dict = {coin: score for coin, score in rel_scores}

# Collect diagnostics for all coins
debug_results = []

for coin in universe:
    if coin not in data or coin == 'BTC':
        continue
    
    close_prices = data[coin]['close'].loc[:sample_date]
    available_data = close_prices.iloc[:-1] if len(close_prices) > 1 else close_prices
    
    if len(available_data) < SIGNAL_PERIOD + 1:
        continue
    
    btc_prices = data['BTC']['close'].loc[:sample_date]
    btc_available = btc_prices.iloc[:-1] if len(btc_prices) > 1 else btc_prices
    
    if len(btc_available) < SIGNAL_PERIOD + 1:
        continue
    
    # Get price levels
    coin_close_today = available_data.iloc[-1]
    coin_close_30d_ago = available_data.iloc[-31] if len(available_data) > 30 else available_data.iloc[0]
    btc_close_today = btc_available.iloc[-1]
    btc_close_30d_ago = btc_available.iloc[-31] if len(btc_available) > 30 else btc_available.iloc[0]
    
    # Calculate components
    coin_return = (coin_close_today / coin_close_30d_ago) - 1
    btc_return = (btc_close_today / btc_close_30d_ago) - 1
    coin_btc_ratio_today = coin_close_today / btc_close_today
    coin_btc_ratio_30d = coin_close_30d_ago / btc_close_30d_ago
    ratio_return = (coin_btc_ratio_today / coin_btc_ratio_30d) - 1
    
    # Get scores from our functions
    abs_mom = abs_dict.get(coin, None)
    rel_mom = rel_dict.get(coin, None)
    
    debug_results.append({
        'coin': coin,
        'coin_close_today': coin_close_today,
        'btc_close_today': btc_close_today,
        'coin_btc_ratio': coin_btc_ratio_today,
        'coin_return_30d': coin_return,
        'btc_return_30d': btc_return,
        'relative_strength_ratio': coin_return / btc_return if abs(btc_return) > 0.001 else None,
        'ratio_momentum': ratio_return,
        'absolute_momentum': abs_mom,
        'relative_momentum': rel_mom,
        'data_points': len(available_data)
    })

debug_df = pd.DataFrame(debug_results)
debug_df = debug_df.sort_values('absolute_momentum', ascending=False).reset_index(drop=True)
debug_df.to_csv('outputs/relative_strength_debug.csv', index=False)
print(f"Debug results saved to outputs/relative_strength_debug.csv")

# Print comparison
print("\n=== SAMPLE DATA (sorted by absolute momentum) ===")
print(debug_df[['coin', 'coin_return_30d', 'btc_return_30d', 'relative_strength_ratio', 
                 'absolute_momentum', 'relative_momentum']].head(15).to_string())

# Check ranking differences
print("\n=== ABSOLUTE MOMENTUM RANKING (top 10) ===")
abs_ranked = sorted(debug_results, key=lambda x: x['absolute_momentum'], reverse=True)
for i, item in enumerate(abs_ranked[:10]):
    print(f"{i+1:2}. {item['coin']:6} - {item['absolute_momentum']:8.6f}")

print("\n=== RELATIVE MOMENTUM RANKING (top 10) ===")
rel_ranked = sorted(debug_results, key=lambda x: x['relative_momentum'], reverse=True)
for i, item in enumerate(rel_ranked[:10]):
    print(f"{i+1:2}. {item['coin']:6} - {item['relative_momentum']:8.6f}")

# Check if rankings are different
abs_order = [item['coin'] for item in abs_ranked[:10]]
rel_order = [item['coin'] for item in rel_ranked[:10]]
identical = abs_order == rel_order
print(f"\nTop 10 rankings identical: {identical}")

if not identical:
    print("\nCoins that changed position:")
    for coin in abs_order:
        abs_pos = abs_order.index(coin) + 1
        rel_pos = rel_order.index(coin) + 1 if coin in rel_order else None
        if rel_pos and abs_pos != rel_pos:
            print(f"  {coin}: abs #{abs_pos} → rel #{rel_pos}")
