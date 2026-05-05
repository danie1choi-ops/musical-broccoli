# main.py - CLI entry point for the crypto momentum backtesting project

import argparse
import pandas as pd
from backtest import run_backtest
from performance import calculate_performance
from config import EQUITY_CURVE_CSV, TRADES_CSV, HOLDINGS_CSV, DIAGNOSTICS_CSV

def main():
    parser = argparse.ArgumentParser(description='Crypto Momentum Backtest')
    parser.add_argument('--mode', choices=['backtest'], default='backtest', help='Mode to run')
    args = parser.parse_args()

    if args.mode == 'backtest':
        print("Running backtest...")
        results = run_backtest()

        # Calculate performance
        metrics = calculate_performance(results['equity_curve'], results['trades'])
        print("Performance Metrics:")
        for key, value in metrics.items():
            print(f"{key}: {value:.4f}")

        # Save CSVs
        results['equity_curve'].to_csv(EQUITY_CURVE_CSV)
        results['trades'].to_csv(TRADES_CSV, index=False)
        results['holdings'].to_csv(HOLDINGS_CSV)
        results['diagnostics'].to_csv(DIAGNOSTICS_CSV)

        print(f"Results saved to {EQUITY_CURVE_CSV}, {TRADES_CSV}, {HOLDINGS_CSV}, {DIAGNOSTICS_CSV}")

if __name__ == '__main__':
    main()