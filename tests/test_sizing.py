# tests/test_sizing.py - Unit tests for sizing mode behavior

import unittest
import pandas as pd
from strategy import calculate_position_weights

class TestSizingModes(unittest.TestCase):

    def setUp(self):
        dates = pd.date_range('2020-01-01', periods=35, freq='D')
        self.data = {
            'LOW_VOL': pd.DataFrame({'close': [100 + 0.1 * i for i in range(len(dates))]}, index=dates),
            'HIGH_VOL': pd.DataFrame({'close': [100 if i % 2 == 0 else 10000 for i in range(len(dates))]}, index=dates),
            'MISSING_VOL': pd.DataFrame({'close': [100] * 15}, index=dates[:15])
        }
        self.date = dates[-1]

    def test_inverse_volatility_weights_sum_to_one_or_less(self):
        weights = calculate_position_weights(['LOW_VOL', 'HIGH_VOL'], self.data, self.date, sizing_mode='inverse_volatility')
        self.assertLessEqual(sum(weights.values()), 1.0)
        self.assertTrue(all(weight > 0 for weight in weights.values()))

    def test_higher_volatility_coins_receive_lower_weights(self):
        weights = calculate_position_weights(['LOW_VOL', 'HIGH_VOL'], self.data, self.date, sizing_mode='inverse_volatility')
        self.assertIn('LOW_VOL', weights)
        self.assertIn('HIGH_VOL', weights)
        self.assertGreater(weights['LOW_VOL'], weights['HIGH_VOL'])

    def test_max_position_cap_works(self):
        # Create low-vol coins with near-zero volatility to force cap behavior
        dates = pd.date_range('2020-01-01', periods=35, freq='D')
        data = {
            'COIN1': pd.DataFrame({'close': [100 + 1 * i for i in range(len(dates))]}, index=dates),
            'COIN2': pd.DataFrame({'close': [100 + 1 * i for i in range(len(dates))]}, index=dates),
            'COIN3': pd.DataFrame({'close': [100 + 1 * i for i in range(len(dates))]}, index=dates),
            'COIN4': pd.DataFrame({'close': [100 + 1 * i for i in range(len(dates))]}, index=dates),
            'COIN5': pd.DataFrame({'close': [100 + 1 * i for i in range(len(dates))]}, index=dates)
        }
        weights = calculate_position_weights(['COIN1', 'COIN2', 'COIN3', 'COIN4', 'COIN5'], data, dates[-1], sizing_mode='inverse_volatility')
        self.assertTrue(weights)
        self.assertLessEqual(max(weights.values()), 0.25)
        self.assertLessEqual(sum(weights.values()), 1.0)

if __name__ == '__main__':
    unittest.main()
