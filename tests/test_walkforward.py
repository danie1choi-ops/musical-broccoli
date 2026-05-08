# tests/test_walkforward.py - Unit tests for walk-forward robustness evaluation

import unittest
import pandas as pd
from backtest import get_walkforward_periods, periods_do_not_overlap, build_walkforward_row
from performance import calculate_performance


class TestWalkforwardEvaluation(unittest.TestCase):

    def test_periods_do_not_overlap(self):
        periods = get_walkforward_periods(end_date='2023-12-31')
        self.assertTrue(periods_do_not_overlap(periods))
        for previous, current in zip(periods, periods[1:]):
            self.assertLess(pd.Timestamp(previous['end_date']), pd.Timestamp(current['start_date']))

    def test_metrics_are_calculated_independently_per_regime(self):
        dates = pd.to_datetime(['2020-01-01', '2021-01-01'])
        equity = pd.DataFrame({'value': [10000, 20000]}, index=dates)
        empty_trades = pd.DataFrame()
        summary = {'total_fees': 0, 'total_slippage': 0, 'annualized_turnover': 0}

        one_year = calculate_performance(
            equity,
            empty_trades,
            equity,
            equity,
            summary,
            start_date='2020-01-01',
            end_date='2021-01-01'
        )
        two_year = calculate_performance(
            equity,
            empty_trades,
            equity,
            equity,
            summary,
            start_date='2020-01-01',
            end_date='2022-01-01'
        )

        self.assertGreater(one_year['Strategy CAGR'], two_year['Strategy CAGR'])
        self.assertAlmostEqual(one_year['Strategy CAGR'], 1.0, places=2)

    def test_benchmark_comparisons_are_correct(self):
        dates = pd.to_datetime(['2020-01-01', '2021-01-01'])
        strategy = pd.DataFrame({'value': [10000, 15000]}, index=dates)
        btc = pd.DataFrame({'value': [10000, 20000]}, index=dates)
        eth = pd.DataFrame({'value': [10000, 5000]}, index=dates)
        summary = {
            'avg_exposure': 0.5,
            'time_in_cash': 0.25,
            'total_fees': 10,
            'total_slippage': 5,
            'annualized_turnover': 1.2
        }
        metrics = calculate_performance(
            strategy,
            pd.DataFrame(),
            btc,
            eth,
            summary,
            start_date='2020-01-01',
            end_date='2021-01-01'
        )
        row = build_walkforward_row(
            {'period': 'test', 'start_date': '2020-01-01', 'end_date': '2021-01-01'},
            {
                'equity_curve': strategy,
                'btc_equity': btc,
                'eth_equity': eth,
                'summary_diagnostics': summary
            },
            metrics
        )

        self.assertAlmostEqual(row['btc_cagr'], 1.0, places=2)
        self.assertAlmostEqual(row['eth_cagr'], -0.5, places=2)
        self.assertEqual(row['btc_final_equity'], 20000)
        self.assertEqual(row['eth_final_equity'], 5000)
        self.assertEqual(row['fees_slippage'], 15)


if __name__ == '__main__':
    unittest.main()
