# Crypto Momentum Backtesting Project

This project implements a momentum-based trading strategy for cryptocurrencies.

## Strategy Overview

- Universe: Top 100 coins by market cap on Binance spot, excluding stablecoins, minimum $10M daily volume.
- Signal: 30-day momentum (return).
- Rebalancing: Weekly, buy top 10 ranked coins.
- Exits: If coin falls outside top 20 by momentum, or price drops 25% from highest since entry.
- Position sizing: Equal weight, max 10% per coin, max 10 positions.
- Regime filter: Only trade when BTC > 200-day MA.

## Installation

1. Clone or download the project.
2. Install dependencies: `pip install -r requirements.txt`

## Usage

Run the backtest:

```bash
python main.py --mode backtest
```

This will generate CSV outputs: equity_curve.csv, trades.csv, holdings.csv, diagnostics.csv

## Files

- config.py: Configuration parameters
- data_loader.py: Data loading (mock or real)
- universe.py: Universe filtering
- indicators.py: Technical indicators
- strategy.py: Strategy logic
- backtest.py: Backtest simulation
- performance.py: Performance metrics
- main.py: CLI entry
- tests/: Unit tests

## Notes

Currently uses mock data. To use real Binance data, implement _load_binance_data in data_loader.py (requires ccxt and API keys).