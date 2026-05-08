# tests/test_execution_realism.py - Unit tests for execution realism helpers

import unittest
import pandas as pd
from backtest import _execution_fill_details, _execution_fill_price, _liquidity_slippage_pct, _portfolio_overlap_pct


class TestExecutionRealism(unittest.TestCase):

    def test_slippage_scales_with_liquidity_participation(self):
        low_participation = _liquidity_slippage_pct(
            notional=1_000,
            average_daily_dollar_volume=1_000_000,
            min_slippage=0.0001,
            max_slippage=0.01,
            impact_factor=0.10
        )
        high_participation = _liquidity_slippage_pct(
            notional=100_000,
            average_daily_dollar_volume=1_000_000,
            min_slippage=0.0001,
            max_slippage=0.01,
            impact_factor=0.10
        )
        self.assertGreater(high_participation, low_participation)

    def test_execution_delay_changes_fills(self):
        dates = pd.date_range('2024-01-01', periods=2, freq='D')
        data = {
            'BTC': pd.DataFrame({
                'open': [100, 120],
                'high': [110, 140],
                'low': [90, 100],
                'close': [105, 130],
                'volume': [1, 1]
            }, index=dates)
        }
        same_expected, same_fill = _execution_fill_price(data, 'BTC', dates[0], 'same_close')
        next_expected, next_fill = _execution_fill_price(data, 'BTC', dates[0], 'next_open')
        vwap_expected, vwap_fill = _execution_fill_price(data, 'BTC', dates[0], 'next_day_vwap_approx')

        self.assertEqual(same_expected, 105)
        self.assertEqual(same_fill, 105)
        self.assertEqual(next_expected, 105)
        self.assertEqual(next_fill, 120)
        self.assertEqual(vwap_expected, 105)
        self.assertEqual(vwap_fill, 122.5)

    def test_execution_details_prevent_future_data_beyond_execution_timestamp(self):
        dates = pd.date_range('2024-01-01', periods=3, freq='D')
        data = {
            'BTC': pd.DataFrame({
                'open': [100, 120, 200],
                'high': [110, 140, 220],
                'low': [90, 100, 180],
                'close': [105, 130, 210],
                'volume': [1, 1, 1]
            }, index=dates)
        }
        details = _execution_fill_details(data, 'BTC', dates[0], 'next_day_vwap_approx')
        self.assertEqual(details['signal_date'], dates[0])
        self.assertEqual(details['execution_date'], dates[1])
        self.assertEqual(details['fill_data_end_date'], dates[1])
        self.assertLessEqual(details['fill_data_end_date'], details['execution_date'])
        self.assertTrue(details['fill_uses_full_next_day_ohlc'])

    def test_overlap_calculations_are_correct(self):
        previous_weights = {'BTC': 0.25, 'ETH': 0.25, 'SOL': 0.25}
        current_weights = {'ETH': 0.20, 'SOL': 0.10, 'DOGE': 0.20}
        overlap = _portfolio_overlap_pct(previous_weights, current_weights)
        self.assertAlmostEqual(overlap, 40.0)


if __name__ == '__main__':
    unittest.main()
