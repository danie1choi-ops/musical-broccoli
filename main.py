# main.py - CLI entry point for the crypto momentum backtesting project

import argparse
import os
import pandas as pd
from backtest import run_backtest, compare_variants, compare_regimes, compare_sizing, compare_exposure
from performance import calculate_performance
from data_loader import download_binance_data
from config import EQUITY_CURVE_CSV, TRADES_CSV, HOLDINGS_CSV, DIAGNOSTICS_CSV, DATA_SOURCE, REAL_SYMBOLS, START_DATE, END_DATE

def main():
    parser = argparse.ArgumentParser(description='Crypto Momentum Backtest')
    parser.add_argument('--mode', choices=['backtest', 'download-data', 'compare-variants', 'compare-regimes', 'compare-sizing', 'compare-exposure'], default='backtest', help='Mode to run')
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
        os.makedirs('outputs', exist_ok=True)
        results['equity_curve'].to_csv(os.path.join('outputs', EQUITY_CURVE_CSV))
        results['trades'].to_csv(os.path.join('outputs', TRADES_CSV), index=False)
        results['holdings'].to_csv(os.path.join('outputs', HOLDINGS_CSV))
        results['diagnostics'].to_csv(os.path.join('outputs', DIAGNOSTICS_CSV))
        results['btc_equity'].to_csv(os.path.join('outputs', 'btc_equity.csv'))
        results['eth_equity'].to_csv(os.path.join('outputs', 'eth_equity.csv'))

        print(f"Results saved to outputs/{EQUITY_CURVE_CSV}, outputs/{TRADES_CSV}, outputs/{HOLDINGS_CSV}, outputs/{DIAGNOSTICS_CSV}, outputs/btc_equity.csv, outputs/eth_equity.csv")

    elif args.mode == 'compare-variants':
        print("Comparing variants...")
        comparison = compare_variants()
        os.makedirs('outputs', exist_ok=True)
        path = os.path.join('outputs', 'variant_comparison.csv')
        comparison.to_csv(path, index=False)
        print(f"Variant comparison saved to {path}")

    elif args.mode == 'compare-regimes':
        print("Comparing regime filters and momentum modes...")
        comparison = compare_regimes()
        os.makedirs('outputs', exist_ok=True)
        path = os.path.join('outputs', 'regime_relative_strength_comparison.csv')
        comparison.to_csv(path, index=False)
        print(f"Regime comparison saved to {path}")
        print("\nComparison Results:")
        print(comparison.to_string())

    elif args.mode == 'compare-sizing':
        print("Comparing position sizing modes...")
        comparison = compare_sizing()
        os.makedirs('outputs', exist_ok=True)
        path = os.path.join('outputs', 'sizing_comparison.csv')
        comparison.to_csv(path, index=False)
        print(f"Sizing comparison saved to {path}")
        print("\nComparison Results:")
        print(comparison.to_string())

    elif args.mode == 'compare-exposure':
        print("Comparing exposure scaling modes...")
        comparison = compare_exposure()
        os.makedirs('outputs', exist_ok=True)
        path = os.path.join('outputs', 'exposure_comparison.csv')
        comparison.to_csv(path, index=False)
        print(f"Exposure comparison saved to {path}")
        print("\nComparison Results:")
        print(comparison.to_string())

if __name__ == '__main__':
    main()
