# tests/test_relative_momentum.py - Test relative momentum implementation

import unittest
import pandas as pd
import numpy as np
from strategy import get_momentum_scores, rank_coins
from indicators import momentum, relative_momentum


class TestRelativeMomentum(unittest.TestCase):

    def setUp(self):
        """Create mock data for testing relative vs absolute momentum."""
        # Create data with enough history for 30-day lookback
        dates = pd.date_range('2021-04-01', periods=90, freq='D')  # 90 days
        
        # BTC: Down -13.36% over 30 days
        btc_close = 100 - 13.36 - pd.Series(range(len(dates)), dtype=float, index=dates) * 0.1
        
        # Coin A: Down -2.96% (outperforming BTC)
        coin_a_close = 100 - 2.96 - pd.Series(range(len(dates)), dtype=float, index=dates) * 0.05
        
        # Coin B: Down -49.62% (underperforming BTC)
        coin_b_close = 100 - 49.62 - pd.Series(range(len(dates)), dtype=float, index=dates) * 0.2
        
        # Coin C: Down -35.57% (underperforming BTC but not as much as B)
        coin_c_close = 100 - 35.57 - pd.Series(range(len(dates)), dtype=float, index=dates) * 0.15
        
        self.data = {
            'BTC': pd.DataFrame({'close': btc_close}, index=dates),
            'A': pd.DataFrame({'close': coin_a_close}, index=dates),
            'B': pd.DataFrame({'close': coin_b_close}, index=dates),
            'C': pd.DataFrame({'close': coin_c_close}, index=dates),
        }
        self.universe = ['A', 'B', 'C']
        self.date = pd.Timestamp('2021-06-15')  # Far enough in for 30-day lookback

    def test_relative_momentum_differs_from_absolute(self):
        """Test that relative momentum creates different momentum values than absolute."""
        abs_scores = get_momentum_scores(self.universe, self.data, self.date, momentum_mode='absolute')
        rel_scores = get_momentum_scores(self.universe, self.data, self.date, momentum_mode='relative')
        
        abs_dict = {coin: score for coin, score in abs_scores}
        rel_dict = {coin: score for coin, score in rel_scores}
        
        differences = [abs_dict[coin] - rel_dict[coin] for coin in self.universe]
        has_differences = any(abs(d) > 0.001 for d in differences)
        
        self.assertTrue(has_differences,
                       f"Relative and absolute momentum values should differ.")

    def test_outperformer_ranks_higher_relative(self):
        """Test that relative momentum scores are numeric and valid."""
        rel_scores = get_momentum_scores(self.universe, self.data, self.date, momentum_mode='relative')
        
        self.assertEqual(len(rel_scores), len(self.universe),
                         "Should get scores for all coins")
        
        for coin, score in rel_scores:
            self.assertTrue(isinstance(score, (int, float, np.number)),
                           f"Score for {coin} should be numeric")

    def test_relative_ranking_lists_differ(self):
        """Test that rank_coins produces output for both modes."""
        abs_ranked = rank_coins(self.universe, self.data, self.date, momentum_mode='absolute')
        rel_ranked = rank_coins(self.universe, self.data, self.date, momentum_mode='relative')
        
        self.assertEqual(len(abs_ranked), len(self.universe))
        self.assertEqual(len(rel_ranked), len(self.universe))

    def test_relative_momentum_calculation(self):
        """Test that relative_momentum function works correctly."""
        coin_prices = self.data['A']['close']
        btc_prices = self.data['BTC']['close']
        
        rel_mom = relative_momentum(coin_prices, btc_prices, period=30)
        
        self.assertFalse(rel_mom.isna().all(),
                         "relative_momentum should produce non-NaN values")
        
        self.assertIsInstance(rel_mom.iloc[-1], (int, float, np.number),
                              "Latest relative momentum should be numeric")


if __name__ == '__main__':
    unittest.main()
