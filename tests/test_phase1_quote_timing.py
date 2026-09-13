import pytest

from v3.phase1.quote_timing import binance_quote_age_ms


def test_spot_adapter_fallback_is_not_zero_latency_evidence():
    from nautilus_trader.adapters.binance.common.schemas.market import BinanceQuoteData
    from nautilus_trader.model.identifiers import InstrumentId

    raw = {"s": "BTCUSDT", "u": 1, "b": "100", "B": "1", "a": "101", "A": "1"}
    parsed = BinanceQuoteData(**raw).parse_to_quote_tick(
        InstrumentId.from_str("BTCUSDT.BINANCE_SPOT_DEMO"), ts_init=1_000_000_000
    )
    assert parsed.ts_event == parsed.ts_init  # Pinned adapter synthesizes this.
    assert binance_quote_age_ms(raw, received_at_ns=parsed.ts_init) is None


def test_real_futures_timestamp_age_rounds_up():
    assert binance_quote_age_ms({"T": 1000}, received_at_ns=1_010_000_001) == 11


@pytest.mark.parametrize("timestamp", [True, "1000", -1, 0, 2000])
def test_invalid_or_future_timestamp_never_becomes_a_valid_sample(timestamp):
    with pytest.raises(ValueError):
        binance_quote_age_ms({"T": timestamp}, received_at_ns=1_000_000_000)
