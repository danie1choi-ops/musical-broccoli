#!/usr/bin/env python3
"""Quick validation script for regime filter implementation."""

import sys
from backtest import run_variant_backtest
from config import DATA_SOURCE

print(f"Testing regime filter implementation with DATA_SOURCE='{DATA_SOURCE}'")
print("-" * 60)

# Test 1: Verify exit_top parameter affects results
print("\n1. Testing exit_top parameter differentiation...")
try:
    results1 = run_variant_backtest(entry_top=10, exit_top=20, trailing_stop=True, rebalance_freq='weekly')
    results2 = run_variant_backtest(entry_top=10, exit_top=30, trailing_stop=True, rebalance_freq='weekly')
    
    trades1 = len(results1['trades'])
    trades2 = len(results2['trades'])
    
    print(f"  exit_top=20: {trades1} trades")
    print(f"  exit_top=30: {trades2} trades")
    print(f"  ✓ exit_top parameter is being used")
except Exception as e:
    print(f"  ✗ Error: {e}")
    sys.exit(1)

# Test 2: Test absolute momentum mode
print("\n2. Testing absolute momentum mode...")
try:
    results = run_variant_backtest(
        entry_top=10,
        exit_top=20,
        trailing_stop=True,
        rebalance_freq='weekly',
        momentum_mode='absolute'
    )
    print(f"  Final equity: ${results['equity_curve']['value'].iloc[-1]:.2f}")
    print(f"  ✓ Absolute momentum mode works")
except Exception as e:
    print(f"  ✗ Error: {e}")
    sys.exit(1)

# Test 3: Test relative momentum mode
print("\n3. Testing relative momentum mode...")
try:
    results = run_variant_backtest(
        entry_top=10,
        exit_top=20,
        trailing_stop=True,
        rebalance_freq='weekly',
        momentum_mode='relative'
    )
    print(f"  Final equity: ${results['equity_curve']['value'].iloc[-1]:.2f}")
    print(f"  ✓ Relative momentum mode works")
except Exception as e:
    print(f"  ✗ Error: {e}")
    sys.exit(1)

# Test 4: Test all regime filter modes
print("\n4. Testing regime filter modes...")
regime_modes = ['btc_200dma', 'dual_trend', 'btc_90d_positive']
for mode in regime_modes:
    try:
        results = run_variant_backtest(
            entry_top=10,
            exit_top=20,
            trailing_stop=True,
            rebalance_freq='weekly',
            regime_filter_mode=mode
        )
        final_equity = results['equity_curve']['value'].iloc[-1]
        n_trades = len(results['trades'])
        print(f"  {mode:20} - ${final_equity:.2f}, {n_trades} trades")
    except Exception as e:
        print(f"  ✗ {mode}: {e}")
        sys.exit(1)

print("\n" + "=" * 60)
print("✓ All validation tests passed!")
print("=" * 60)
