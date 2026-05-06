# momentum_diagnostics.py - Debug relative momentum implementation

import pandas as pd
from data_loader import load_ohlcv_data
from universe import get_universe
from indicators import momentum, relative_momentum
from config import MOCK_COINS, REAL_SYMBOLS, DATA_SOURCE, START_DATE, END_DATE, SIGNAL_PERIOD

# Load data
coins = [s.split('/')[0] for s in REAL_SYMBOLS] if DATA_SOURCE == 'real' else MOCK_COINS
data = load_ohlcv_data(coins, use_real=(DATA_SOURCE == 'real'))
universe = get_universe(data)

print(f"Data source: {DATA_SOURCE}")
print(f"Universe size: {len(universe)}")
print(f"Universe: {universe[:10]}")
print(f"BTC in data: {'BTC' in data}")
print(f"BTC in universe: {'BTC' in universe}")

# Pick a sample date during backtest period
sample_date = pd.Timestamp('2021-06-15')
print(f"\nSample date: {sample_date}")

# Check BTC data availability
if 'BTC' in data:
    btc_data = data['BTC']['close'].loc[:sample_date]
    print(f"BTC data available up to sample date: {len(btc_data)} days")
    btc_available = btc_data.iloc[:-1] if len(btc_data) > 1 else btc_data
    if len(btc_available) >= SIGNAL_PERIOD + 1:
        btc_mom = momentum(btc_available, SIGNAL_PERIOD).iloc[-1]
        print(f"BTC 30-day momentum: {btc_mom:.6f}")
    else:
        print(f"ERROR: Not enough BTC data ({len(btc_available)} vs {SIGNAL_PERIOD + 1} needed)")
else:
    print("ERROR: BTC not in data!")

# Test absolute vs relative momentum for sample coins
debug_results = []
for i, coin in enumerate(universe[:10]):
    if coin not in data:
        continue
    
    close_prices = data[coin]['close'].loc[:sample_date]
    available_data = close_prices.iloc[:-1] if len(close_prices) > 1 else close_prices
    
    if len(available_data) < SIGNAL_PERIOD + 1:
        print(f"{coin}: Not enough data ({len(available_data)})")
        continue
    
    # Calculate absolute momentum
    abs_mom = momentum(available_data, SIGNAL_PERIOD).iloc[-1]
    
    # Calculate relative momentum
    btc_prices = data['BTC']['close'].loc[:sample_date]
    btc_available = btc_prices.iloc[:-1] if len(btc_prices) > 1 else btc_prices
    
    if len(btc_available) < SIGNAL_PERIOD + 1:
        rel_mom = None
        print(f"{coin}: Cannot calculate relative momentum (BTC data issue)")
    else:
        rel_mom = relative_momentum(available_data, btc_available, SIGNAL_PERIOD).iloc[-1]
    
    debug_results.append({
        'coin': coin,
        'absolute_momentum': abs_mom,
        'relative_momentum': rel_mom,
        'difference': rel_mom - abs_mom if rel_mom is not None else None,
        'data_length': len(available_data)
    })
    print(f"{coin:6} - abs: {abs_mom:8.6f}, rel: {rel_mom:8.6f}, diff: {rel_mom - abs_mom if rel_mom is not None else 'N/A':8.6f}")

# Save debug results
debug_df = pd.DataFrame(debug_results)
debug_df.to_csv('outputs/momentum_debug_sample.csv', index=False)
print(f"\nDebug results saved to outputs/momentum_debug_sample.csv")

# Check rankings
print("\n=== ABSOLUTE MOMENTUM RANKING ===")
abs_ranks = sorted(debug_results, key=lambda x: x['absolute_momentum'], reverse=True)
for i, item in enumerate(abs_ranks):
    print(f"{i+1:2}. {item['coin']:6} - {item['absolute_momentum']:8.6f}")

print("\n=== RELATIVE MOMENTUM RANKING ===")
rel_ranks = sorted(debug_results, key=lambda x: x['relative_momentum'] if x['relative_momentum'] is not None else float('-inf'), reverse=True)
for i, item in enumerate(rel_ranks):
    rel_val = item['relative_momentum'] if item['relative_momentum'] is not None else None
    print(f"{i+1:2}. {item['coin']:6} - {rel_val if rel_val is not None else 'N/A':8.6f}")

# Check if rankings are identical
abs_order = [item['coin'] for item in abs_ranks]
rel_order = [item['coin'] for item in rel_ranks if item['relative_momentum'] is not None]
identical = abs_order[:len(rel_order)] == rel_order
print(f"\nRankings identical: {identical}")
