"""Korean stock tick size (호가단위) table.

KRX price-dependent tick sizes for order price rounding.
Prices must be multiples of the tick size for the given price level.
"""

import math

# (price_threshold, tick_size) — sorted ascending
# If price < threshold, use the corresponding tick_size
_TICK_TABLE = [
    (2_000, 1),
    (5_000, 5),
    (20_000, 10),
    (50_000, 50),
    (200_000, 100),
    (500_000, 500),
    (float("inf"), 1_000),
]


def get_tick_size(price: float) -> int:
    """Get the tick size for a given price level."""
    for threshold, tick in _TICK_TABLE:
        if price < threshold:
            return tick
    return 1_000


def round_to_tick(price: float, direction: str = "down") -> int:
    """Round a price to the nearest valid tick.

    Args:
        price: Raw price to round.
        direction: "down" for buy orders (conservative), "up" for sell orders.

    Returns:
        Price rounded to valid tick size.
    """
    tick = get_tick_size(price)
    if direction == "up":
        return int(math.ceil(price / tick) * tick)
    return int(math.floor(price / tick) * tick)


def is_valid_price(price: float) -> bool:
    """Check if a price is a valid multiple of its tick size."""
    tick = get_tick_size(price)
    return price % tick == 0
