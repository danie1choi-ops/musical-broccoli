# universe.py - Module for defining the trading universe

from config import UNIVERSE_SIZE, EXCLUDE_STABLES, MIN_DAILY_VOLUME, STABLES, MOCK_MARKET_CAPS

def get_universe(coins_data, market_caps=MOCK_MARKET_CAPS, stables=STABLES):
    """
    Filter the universe to eligible coins based on criteria.

    Args:
        coins_data (dict): Dictionary of coin OHLCV data
        market_caps (dict): Dictionary of coin market caps
        stables (list): List of stablecoin symbols to exclude

    Returns:
        list: List of eligible coin symbols
    """
    eligible = []

    for coin in coins_data.keys():
        # Exclude stablecoins
        if EXCLUDE_STABLES and coin in stables:
            continue

        # Check minimum daily volume
        avg_volume = coins_data[coin]['volume'].mean()
        if avg_volume < MIN_DAILY_VOLUME:
            continue

        # Get market cap
        cap = market_caps.get(coin, 0)
        eligible.append((coin, cap))

    # Sort by market cap descending and take top UNIVERSE_SIZE
    eligible.sort(key=lambda x: x[1], reverse=True)
    universe = [coin for coin, _ in eligible[:UNIVERSE_SIZE]]

    return universe