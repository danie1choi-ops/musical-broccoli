# Regime Filter & Momentum Mode Implementation

## Overview

This document describes the implementation of advanced strategy features:
- **Relative Momentum**: Compare coin momentum against BTC momentum
- **Regime Filters**: Multiple methods to identify market regimes for trading
- **Extended Variant Testing**: Compare 10 different strategy configurations

## New Configuration Options

### `MOMENTUM_MODE`
- `'absolute'`: Use absolute momentum ranking (default)
- `'relative'`: Use momentum relative to BTC (coin_momentum - BTC_momentum)

### `REGIME_FILTER_MODE`
- `'btc_200dma'`: Only trade when BTC > 200-day moving average (default)
- `'dual_trend'`: Only trade when BTC > 200DMA AND 50DMA > 200DMA
- `'btc_90d_positive'`: Only trade when BTC 90-day return > 0%

## Implementation Details

### Regime Check Logic

The regime is only checked at rebalance dates. The strategy only enters/exits when regime is active.

**btc_200dma Mode:**
```
regime_active = BTC_price > BTC_200DMA
```

**dual_trend Mode:**
```
regime_active = (BTC_price > BTC_200DMA) AND (BTC_50DMA > BTC_200DMA)
```

**btc_90d_positive Mode:**
```
regime_active = (BTC_price / BTC_price_90d_ago) - 1 > 0
```

### Momentum Calculation

**Absolute Momentum (default):**
```
momentum = (price_today / price_30d_ago) - 1
```

**Relative Momentum:**
```
relative_momentum = coin_momentum - BTC_momentum
```

## Usage

### Command Line

```bash
# Single backtest with current config
python3 main.py --mode backtest

# Compare all 10 regime/momentum configurations
python3 main.py --mode compare-regimes

# Compare 5 entry/exit/rebalance variants
python3 main.py --mode compare-variants

# Download fresh data
python3 main.py --mode download-data
```

### Configuration

Edit `config.py` to select:

```python
MOMENTUM_MODE = 'absolute'  # or 'relative'
REGIME_FILTER_MODE = 'btc_200dma'  # or 'dual_trend' or 'btc_90d_positive'
```

### Programmatic Usage

```python
from backtest import run_variant_backtest, compare_regimes

# Run a single configuration
results = run_variant_backtest(
    entry_top=10,
    exit_top=20,
    trailing_stop=True,
    rebalance_freq='weekly',
    momentum_mode='relative',
    regime_filter_mode='dual_trend'
)

# Compare all 10 configurations
comparison_df = compare_regimes()
comparison_df.to_csv('outputs/regime_comparison.csv')
```

## Variant Matrix (10 configurations)

The `compare_regimes()` function tests:

| Momentum | Regime Filter | Rebalance | Entry |
|----------|---------------|-----------|-------|
| absolute | btc_200dma | weekly | top 10 |
| absolute | btc_200dma | weekly | top 5 |
| absolute | btc_200dma | monthly | top 10 |
| absolute | dual_trend | weekly | top 10 |
| absolute | btc_90d_positive | weekly | top 10 |
| relative | btc_200dma | weekly | top 10 |
| relative | btc_200dma | weekly | top 5 |
| relative | btc_200dma | monthly | top 10 |
| relative | dual_trend | weekly | top 10 |
| relative | btc_90d_positive | weekly | top 10 |

Exit threshold: 2x entry_top (e.g., exit_top=20 for entry_top=10)
Trailing stop: 25% from entry high (consistent across all variants)

## Output Files

### Single Backtest (`--mode backtest`)
- `outputs/equity_curve.csv`: Daily portfolio value
- `outputs/trades.csv`: All entry/exit trades with fees and slippage
- `outputs/holdings.csv`: Portfolio holdings by date
- `outputs/diagnostics.csv`: Regime activity, cash levels, positions
- `outputs/btc_equity.csv`: BTC benchmark equity curve
- `outputs/eth_equity.csv`: ETH benchmark equity curve

### Variant Comparison (`--mode compare-variants`)
- `outputs/variant_comparison.csv`: Metrics for 5 baseline variants

### Regime Comparison (`--mode compare-regimes`)
- `outputs/regime_relative_strength_comparison.csv`: Metrics for all 10 momentum/regime combinations

## Metrics in Comparison Output

Each variant includes:
- **variant**: Configuration name
- **momentum_mode**: 'absolute' or 'relative'
- **regime_filter**: Filter mode used
- **rebalance_freq**: 'weekly' or 'monthly'
- **entry_top**: Number of coins in portfolio
- **strategy_cagr**: Compound annual return %
- **strategy_max_drawdown**: Peak-to-trough decline %
- **strategy_sharpe**: Risk-adjusted return (annualized)
- **total_trades**: Number of entry+exit trades
- **annualized_turnover**: Portfolio turnover per year
- **total_fees**: Total fees paid ($)
- **total_slippage**: Total slippage costs ($)
- **final_equity**: Portfolio value on END_DATE ($)
- **avg_holding_period**: Average days positions held
- **avg_positions_held**: Average number of active positions
- **btc_cagr**: Bitcoin buy-hold CAGR %
- **btc_max_drawdown**: Bitcoin max drawdown %
- **eth_cagr**: Ethereum buy-hold CAGR %
- **eth_max_drawdown**: Ethereum max drawdown %

## Architecture

### New Functions

**indicators.py:**
- `relative_momentum(coin_prices, btc_prices, period)`: Calculate relative momentum

**strategy.py:**
- `rank_coins(..., momentum_mode='absolute')`: Support for momentum mode parameter

**backtest.py:**
- `_check_regime(date, regime_mode, btc_close, btc_sma, btc_momentum_50_200)`: Regime checking logic
- `run_variant_backtest(..., momentum_mode='absolute', regime_filter_mode='btc_200dma')`: Enhanced variant runner
- `compare_regimes()`: Generate all 10 regime combinations

**main.py:**
- Added `--mode compare-regimes` CLI option

## Testing

All features are tested with:
- `tests/test_exit_logic.py`: New tests for regime filters and momentum modes
- `tests/test_strategy.py`: Momentum ranking (existing)
- `tests/test_variant_comparison.py`: Variant CSV output (existing)

Run tests with:
```bash
python3 -m pytest tests/ -v
```

## Implementation Notes

1. **Regime is only checked at rebalance dates**, not daily. This reduces noise and improves transaction efficiency.

2. **Exit logic now properly uses exit_top parameter**: Holdings outside the top `exit_top` ranked coins are exited.

3. **Relative momentum requires BTC data**: Strategies using relative momentum will skip rankings if BTC data is unavailable.

4. **50DMA is computed dynamically**: For dual_trend mode, 50DMA is calculated on-the-fly (not pre-cached).

5. **Trailing stop remains consistent**: All variants use 25% trailing stop from entry high (when enabled).

6. **Average holding period is tracked**: Each exit records the days held, enabling analysis of holding periods by variant.

## Known Limitations

1. **Survivorship bias**: The strategy uses a static universe of current top 100 coins. Historical data doesn't account for coins that no longer exist or have been delisted.

2. **Single regime per date**: Once regime becomes inactive, all positions are exited at next rebalance (no gradual exit).

3. **Look-ahead bias prevention**: Ranking uses data up to date-1 to prevent using today's price.

4. **Market hours assumption**: Backtests assume fills at daily close prices with fixed slippage/fees.

## Future Enhancements

- [ ] Dynamic universe selection (survivorship bias fix)
- [ ] Intraday regime checks
- [ ] Adaptive position sizing based on regime strength
- [ ] Additional regime filters (macro indicators, VIX, etc.)
- [ ] Regime-weighted entry weights
- [ ] Position exit acceleration during regime changes
