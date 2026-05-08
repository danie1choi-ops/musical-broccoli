# config.py - Configuration parameters for the crypto momentum backtesting project

# Exchange and universe settings
EXCHANGE = 'binance'
UNIVERSE_SIZE = 100
EXCLUDE_STABLES = True
MIN_DAILY_VOLUME = 10_000_000  # $10M

# Timeframe and rebalancing
TIMEFRAME = '1d'
REBALANCE_FREQ = 'weekly'  # Rebalance every week

# Signal parameters
SIGNAL_PERIOD = 30  # 30-day momentum

# Strategy parameters
TOP_N = 5  # Buy top 5 ranked coins
EXIT_TOP_N = 15  # Exit if falls outside top 15
STOP_LOSS_PCT = 0.25  # 25% stop loss from highest close since entry
MAX_WEIGHT_PER_COIN = 0.25  # Max 25% per coin
MAX_POSITIONS = 5  # Max 5 positions for the current baseline

# Regime filter
REGIME_ASSET = 'BTC'
REGIME_PERIOD = 200  # 200-day MA

# Momentum mode: "absolute" or "relative" (relative = coin_mom - BTC_mom)
MOMENTUM_MODE = 'absolute'

# Regime filter mode: "btc_200dma", "dual_trend", "btc_90d_positive"
REGIME_FILTER_MODE = 'btc_200dma'

# Backtest dates
START_DATE = '2020-01-01'
END_DATE = '2023-01-01'

# Trading costs
TRADING_FEE = 0.001  # 0.10% per trade
SLIPPAGE = 0.001  # 0.10% per trade
EXECUTION_MODE = 'same_close'  # 'same_close', 'next_open', or 'next_day_vwap_approx'
MIN_SLIPPAGE = 0.0005  # 0.05% minimum modeled slippage
MAX_SLIPPAGE = 0.01  # 1.00% maximum modeled slippage
SLIPPAGE_IMPACT_FACTOR = 0.10  # 1% ADV participation -> 0.10% slippage before caps
ADV_LOOKBACK_DAYS = 30

# Portfolio
STARTING_CAPITAL = 10000
POSITION_SIZING_MODE = 'inverse_volatility'  # 'equal_weight' or 'inverse_volatility'
MAX_POSITION_SIZE = 0.25  # Maximum position size per coin for sizing rules
USE_BREADTH_SCALING = False  # Scale exposure using percentage of coins above their 100DMA

# Data source
DATA_SOURCE = 'real'  # 'real' or 'mock'

# Real data symbols (Binance spot)
REAL_SYMBOLS = [
    'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'ADA/USDT', 'SOL/USDT', 'DOT/USDT',
    'DOGE/USDT', 'AVAX/USDT', 'LTC/USDT', 'MATIC/USDT', 'ALGO/USDT', 'VET/USDT',
    'ICP/USDT', 'FIL/USDT', 'TRX/USDT', 'ETC/USDT', 'XLM/USDT', 'THETA/USDT',
    'FTT/USDT', 'HBAR/USDT'
]

# Output files
EQUITY_CURVE_CSV = 'equity_curve.csv'
TRADES_CSV = 'trades.csv'
HOLDINGS_CSV = 'holdings.csv'
DIAGNOSTICS_CSV = 'diagnostics.csv'

# Mock data settings
MOCK_COINS = ['BTC', 'ETH', 'BNB', 'ADA', 'SOL', 'DOT', 'DOGE', 'AVAX', 'LTC', 'MATIC',
               'ALGO', 'VET', 'ICP', 'FIL', 'TRX', 'ETC', 'XLM', 'THETA', 'FTT', 'HBAR']  # 20 coins for mock
STABLES = ['USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'USDP', 'FRAX', 'LUSD', 'GUSD', 'USD']

# Mock market caps (in billions USD, approximate)
MOCK_MARKET_CAPS = {
    'BTC': 500,
    'ETH': 300,
    'BNB': 50,
    'ADA': 20,
    'SOL': 15,
    'DOT': 10,
    'DOGE': 8,
    'AVAX': 7,
    'LTC': 6,
    'MATIC': 5,
    'ALGO': 4,
    'VET': 3,
    'ICP': 2.5,
    'FIL': 2,
    'TRX': 1.5,
    'ETC': 1,
    'XLM': 0.8,
    'THETA': 0.5,
    'FTT': 0.3,
    'HBAR': 0.2
}
