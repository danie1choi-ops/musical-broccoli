# main.py - CLI entry point for the crypto momentum backtesting project

import argparse
import pandas as pd
from backtest import run_backtest
from performance import calculate_performance
from data_loader import download_binance_data
from config import EQUITY_CURVE_CSV, TRADES_CSV, HOLDINGS_CSV, DIAGNOSTICS_CSV, DATA_SOURCE, REAL_SYMBOLS, START_DATE, END_DATE

def main():
    parser = argparse.ArgumentParser(description='Crypto Momentum Backtest')
    parser.add_argument('--mode', choices=['backtest', 'download-data'], default='backtest', help='Mode to run')
    args = parser.parse_args()

    if args.mode == 'download-data':
        print("Downloading Binance data...")
        download_binance_data(REAL_SYMBOLS, START_DATE, END_DATE)
        print("Download complete.")

    elif args.mode == 'backtest':
        print("Running backtest...")
        results = run_backtest()

        # Calculate performance
        metrics = calculate_performance(results['equity_curve'], results['trades'], results['btc_equity'], results['eth_equity'], results['summary_diagnostics'])
        if DATA_SOURCE == 'mock':
            print("WARNING: mock data — results are structural only, not strategy evidence.")
        print("Performance Metrics:")
        for key, value in metrics.items():
            if 'CAGR' in key or 'Drawdown' in key or 'Sharpe' in key:
                print(f"{key}: {value:.4f}")
            else:
                print(f"{key}: {value}")

        # Print diagnostics
        print("\nDiagnostics:")
        for key, value in results['summary_diagnostics'].items():
            print(f"{key}: {value}")

        # Save CSVs
        results['equity_curve'].to_csv(EQUITY_CURVE_CSV)
        results['trades'].to_csv(TRADES_CSV, index=False)
        results['holdings'].to_csv(HOLDINGS_CSV)
        results['diagnostics'].to_csv(DIAGNOSTICS_CSV)
        results['btc_equity'].to_csv('btc_equity.csv')
        results['eth_equity'].to_csv('eth_equity.csv')

        print(f"Results saved to {EQUITY_CURVE_CSV}, {TRADES_CSV}, {HOLDINGS_CSV}, {DIAGNOSTICS_CSV}, btc_equity.csv, eth_equity.csv")

if __name__ == '__main__':
    main()