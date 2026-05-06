import os
import unittest
from backtest import compare_variants

class TestVariantComparison(unittest.TestCase):

    def test_compare_variants_returns_dataframe(self):
        df = compare_variants()
        self.assertEqual(len(df), 5)
        expected_columns = {
            'variant', 'strategy_cagr', 'strategy_max_drawdown', 'strategy_sharpe',
            'total_trades', 'annualized_turnover', 'total_fees', 'total_slippage',
            'final_equity', 'btc_cagr', 'btc_max_drawdown', 'eth_cagr', 'eth_max_drawdown'
        }
        self.assertTrue(expected_columns.issubset(set(df.columns)))

    def test_compare_variants_saves_csv(self):
        df = compare_variants()
        os.makedirs('outputs', exist_ok=True)
        path = os.path.join('outputs', 'variant_comparison.csv')
        df.to_csv(path, index=False)
        self.assertTrue(os.path.exists(path))

if __name__ == '__main__':
    unittest.main()
