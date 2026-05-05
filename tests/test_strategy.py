# tests/test_strategy.py - Unit tests for strategy module

import unittest
import pandas as pd
from strategy import rank_coins
from indicators import momentum

class TestStrategy(unittest.TestCase):

    def setUp(self):
        # Mock data
        dates = pd.date_range('2020-01-01', '2020-02-15', freq='D')
        self.data = {
            'BTC': pd.DataFrame({'close': [100 + i for i in range(len(dates))]}, index=dates),
            'ETH': pd.DataFrame({'close': [50 + i*0.5 for i in range(len(dates))]}, index=dates)
        }
        self.universe = ['BTC', 'ETH']
        self.date = pd.Timestamp('2020-02-15')

    def test_rank_coins(self):
        ranked = rank_coins(self.universe, self.data, self.date)
        # BTC has higher momentum (constant increase vs half)
        self.assertEqual(ranked[0], 'BTC')
        self.assertEqual(ranked[1], 'ETH')

if __name__ == '__main__':
    unittest.main()