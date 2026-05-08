# tests/test_exposure_scaling.py - Unit tests for breadth-based exposure scaling

import unittest
import pandas as pd
from strategy import calculate_market_breadth, exposure_scale_from_breadth, calculate_alt_participation, exposure_scale_from_alt_participation, target_exposure_for_mode, scale_position_weights


class TestExposureScaling(unittest.TestCase):

    def test_exposure_scaling_works_correctly(self):
        weights = {'BTC': 0.25, 'ETH': 0.25, 'SOL': 0.25, 'BNB': 0.25}
        scaled = scale_position_weights(weights, 0.50)
        self.assertEqual(scaled, {'BTC': 0.125, 'ETH': 0.125, 'SOL': 0.125, 'BNB': 0.125})

        self.assertEqual(exposure_scale_from_breadth(0.71), 1.0)
        self.assertEqual(exposure_scale_from_breadth(0.70), 0.50)
        self.assertEqual(exposure_scale_from_breadth(0.50), 0.50)
        self.assertEqual(exposure_scale_from_breadth(0.49), 0.0)

    def test_exposure_never_exceeds_100_percent(self):
        scaled = scale_position_weights({'BTC': 0.80, 'ETH': 0.80}, 1.50)
        self.assertLessEqual(sum(scaled.values()), 1.0)

    def test_cash_mode_activates_below_breadth_threshold(self):
        weights = {'BTC': 0.25, 'ETH': 0.25}
        scaled = scale_position_weights(weights, exposure_scale_from_breadth(0.25))
        self.assertEqual(scaled, {})

    def test_market_breadth_calculates_percent_above_100dma(self):
        dates = pd.date_range('2020-01-01', periods=101, freq='D')
        data = {
            'ABOVE': pd.DataFrame({'close': [100] * 100 + [120]}, index=dates),
            'BELOW': pd.DataFrame({'close': [100] * 100 + [80]}, index=dates),
            'MISSING': pd.DataFrame({'close': [100] * 50}, index=dates[:50])
        }
        breadth = calculate_market_breadth(['ABOVE', 'BELOW', 'MISSING'], data, dates[-1])
        self.assertEqual(breadth, 0.5)

    def test_alt_participation_percentage_calculation_is_correct(self):
        dates = pd.date_range('2020-01-01', periods=91, freq='D')
        data = {
            'BTC': pd.DataFrame({'close': [100] * 90 + [110]}, index=dates),
            'ALT_WIN': pd.DataFrame({'close': [100] * 90 + [130]}, index=dates),
            'ALT_LOSE': pd.DataFrame({'close': [100] * 90 + [105]}, index=dates),
            'ALT_MISSING': pd.DataFrame({'close': [100] * 30}, index=dates[:30])
        }
        participation = calculate_alt_participation(
            ['BTC', 'ALT_WIN', 'ALT_LOSE', 'ALT_MISSING'],
            data,
            dates[-1]
        )
        self.assertEqual(participation, 0.5)

    def test_alt_participation_exposure_thresholds_work_correctly(self):
        self.assertEqual(exposure_scale_from_alt_participation(0.70), 1.0)
        self.assertEqual(exposure_scale_from_alt_participation(0.69), 0.5)
        self.assertEqual(exposure_scale_from_alt_participation(0.50), 0.5)
        self.assertEqual(exposure_scale_from_alt_participation(0.49), 0.0)

    def test_combined_mode_uses_lower_exposure(self):
        self.assertEqual(
            target_exposure_for_mode(0.80, 0.40, 'combined_breadth_and_alt_participation'),
            0.0
        )
        self.assertEqual(
            target_exposure_for_mode(0.40, 0.80, 'combined_breadth_and_alt_participation'),
            0.0
        )
        self.assertEqual(
            target_exposure_for_mode(0.60, 0.80, 'combined_breadth_and_alt_participation'),
            0.5
        )


if __name__ == '__main__':
    unittest.main()
