from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from v3.phase1.observations import capture_mainnet_public_funding

NOW = datetime(2026, 9, 9, 1, tzinfo=UTC)


class FundingFixture:
    def __init__(self, times, info=None):
        self.times = times
        self.info = info or []

    def get(self, base, path, **kwargs):
        assert base == "https://fapi.binance.com"
        assert not kwargs.get("signed")
        data = (
            self.info
            if path.endswith("fundingInfo")
            else [
                {
                    "symbol": "BTCUSDT",
                    "fundingRate": "0.0001",
                    "fundingTime": int(t.timestamp() * 1000),
                }
                for t in self.times
            ]
        )
        return SimpleNamespace(data=data)


def test_funding_interval_requires_two_observed_uniform_gaps():
    result = capture_mainnet_public_funding(
        FundingFixture(
            [
                NOW - timedelta(hours=17),
                NOW - timedelta(hours=9),
                NOW - timedelta(hours=1),
            ]
        ),
        symbol="BTCUSDT",
        clock=lambda: NOW,
    )
    assert result.funding_interval_minutes == 480
    assert result.source == "fundingRate_history"


def test_insufficient_history_does_not_invent_eight_hour_interval():
    result = capture_mainnet_public_funding(
        FundingFixture([NOW - timedelta(hours=1)]), symbol="BTCUSDT", clock=lambda: NOW
    )
    assert result.funding_interval_minutes is None


@pytest.mark.parametrize("offset", [1, -30])
def test_future_or_stale_funding_is_rejected(offset):
    latest = NOW + timedelta(hours=offset)
    with pytest.raises(ValueError, match="future|stale"):
        capture_mainnet_public_funding(
            FundingFixture(
                [
                    latest - timedelta(hours=16),
                    latest - timedelta(hours=8),
                    latest,
                ]
            ),
            symbol="BTCUSDT",
            clock=lambda: NOW,
        )
