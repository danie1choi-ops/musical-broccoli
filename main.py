# main.py - CLI entry point for the crypto momentum backtesting project

import argparse
import json
import os
import pandas as pd
from backtest import run_backtest, compare_variants, compare_regimes, compare_sizing, compare_exposure, compare_participation, parameter_sensitivity_results, generate_live_signals, execution_analysis_results, walkforward_results
from performance import calculate_performance
from data_loader import download_binance_data
from config import EQUITY_CURVE_CSV, TRADES_CSV, HOLDINGS_CSV, DIAGNOSTICS_CSV, DATA_SOURCE, REAL_SYMBOLS, START_DATE, END_DATE

def main():
    parser = argparse.ArgumentParser(description='Crypto Momentum Backtest')
    parser.add_argument('--mode', choices=['backtest', 'download-data', 'compare-variants', 'compare-regimes', 'compare-sizing', 'compare-exposure', 'compare-participation', 'sensitivity', 'signals', 'execution-analysis', 'walkforward'], default='backtest', help='Mode to run')
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

    elif args.mode == 'compare-participation':
        print("Comparing BTC dominance and alt participation exposure modes...")
        comparison, debug = compare_participation()
        os.makedirs('outputs', exist_ok=True)
        path = os.path.join('outputs', 'participation_comparison.csv')
        debug_path = os.path.join('outputs', 'participation_debug.csv')
        comparison.to_csv(path, index=False)
        debug.to_csv(debug_path, index=False)
        print(f"Participation comparison saved to {path}")
        print(f"Participation debug saved to {debug_path}")
        print("\nComparison Results:")
        print(comparison.to_string())

    elif args.mode == 'sensitivity':
        print("Running parameter sensitivity tests...")
        sensitivity, summary = parameter_sensitivity_results()
        os.makedirs('outputs', exist_ok=True)
        path = os.path.join('outputs', 'parameter_sensitivity.csv')
        summary_path = os.path.join('outputs', 'sensitivity_summary.csv')
        sensitivity.to_csv(path, index=False)
        summary.to_csv(summary_path, index=False)
        print(f"Parameter sensitivity saved to {path}")
        print(f"Sensitivity summary saved to {summary_path}")
        print("\nSensitivity Summary:")
        print(summary.to_string())

    elif args.mode == 'signals':
        print("Generating live signals...")
        signals, snapshot, log = generate_live_signals()
        os.makedirs('outputs', exist_ok=True)
        signals_path = os.path.join('outputs', 'current_signals.csv')
        snapshot_path = os.path.join('outputs', 'portfolio_snapshot.json')
        log_path = os.path.join('outputs', 'live_signal_log.csv')
        signals.to_csv(signals_path, index=False)
        with open(snapshot_path, 'w') as f:
            json.dump(snapshot, f, indent=2, default=str)
        log.to_csv(log_path, mode='a', header=not os.path.exists(log_path), index=False)
        print(f"Current signals saved to {signals_path}")
        print(f"Portfolio snapshot saved to {snapshot_path}")
        print(f"Live signal log appended to {log_path}")
        print("\nCurrent Signals:")
        print(signals.to_string())

    elif args.mode == 'execution-analysis':
        print("Running execution realism and forward-test analytics...")
        summary, execution_diagnostics, forward_analytics, avg_slippage, highest_turnover_assets, execution_audit = execution_analysis_results()
        os.makedirs('outputs', exist_ok=True)
        summary_path = os.path.join('outputs', 'execution_summary.csv')
        diagnostics_path = os.path.join('outputs', 'execution_diagnostics.csv')
        analytics_path = os.path.join('outputs', 'forward_test_analytics.csv')
        audit_path = os.path.join('outputs', 'execution_audit.csv')
        avg_slippage_path = os.path.join('outputs', 'average_slippage_by_coin.csv')
        turnover_assets_path = os.path.join('outputs', 'highest_turnover_assets.csv')
        summary.to_csv(summary_path, index=False)
        execution_diagnostics.to_csv(diagnostics_path, index=False)
        forward_analytics.to_csv(analytics_path, index=False)
        execution_audit.to_csv(audit_path, index=False)
        avg_slippage.to_csv(avg_slippage_path, index=False)
        highest_turnover_assets.to_csv(turnover_assets_path, index=False)
        print(f"Execution summary saved to {summary_path}")
        print(f"Execution diagnostics saved to {diagnostics_path}")
        print(f"Forward-test analytics saved to {analytics_path}")
        print(f"Execution audit saved to {audit_path}")
        print("\nExecution Summary:")
        print(summary.to_string())
        if not execution_audit.empty:
            print("\nExecution Audit Flags:")
            print(execution_audit[['execution_scenario', 'portfolio_update_before_execution', 'fill_uses_full_next_day_ohlc', 'unrealistic_improvement_flag']].sum(numeric_only=True).to_string())
        if not avg_slippage.empty:
            print("\nAverage Slippage By Coin:")
            print(avg_slippage.to_string())
        if not highest_turnover_assets.empty:
            print("\nHighest Turnover Assets:")
            print(highest_turnover_assets.sort_values('total_trade_notional', ascending=False).head(20).to_string())

    elif args.mode == 'walkforward':
        print("Running walk-forward robustness evaluation...")
        comparison, diagnostics = walkforward_results()
        os.makedirs('outputs', exist_ok=True)
        path = os.path.join('outputs', 'walkforward_results.csv')
        diagnostics_path = os.path.join('outputs', 'walkforward_data_diagnostics.csv')
        comparison.to_csv(path, index=False)
        diagnostics.to_csv(diagnostics_path, index=False)
        print(f"Walk-forward results saved to {path}")
        print(f"Walk-forward data diagnostics saved to {diagnostics_path}")
        print("\nWalk-forward Results:")
        print(comparison.to_string())
        print("\nData Diagnostics:")
        print(diagnostics.to_string())

if __name__ == '__main__':
    main()
