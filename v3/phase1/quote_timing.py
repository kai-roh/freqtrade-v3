"""Quote timestamp provenance before Nautilus replaces absent timestamps."""

from collections.abc import Mapping


def binance_quote_age_ms(payload: Mapping, *, received_at_ns: int) -> int | None:
    """Use raw Binance bookTicker T only, never the adapter's fallback ts_event.

    None is deliberately not a sample for a venue-age SLA. This function neither
    measures receive-gap freshness nor authorizes trading on a missing timestamp.
    """
    if type(received_at_ns) is not int or received_at_ns <= 0:
        raise ValueError("positive receive timestamp is required")
    timestamp = payload.get("T")
    if timestamp is None:
        return None
    if type(timestamp) is not int or timestamp <= 0:
        raise ValueError("invalid exchange quote timestamp")
    elapsed = received_at_ns - timestamp * 1_000_000
    if elapsed < 0:
        raise ValueError("future exchange quote timestamp; check clock synchronization")
    return (elapsed + 999_999) // 1_000_000  # Conservative millisecond ceiling.
