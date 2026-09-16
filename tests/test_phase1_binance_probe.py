import io
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError

import pytest

from v3.phase1.binance_probe import (
    SPOT_DEMO,
    USDM_DEMO,
    BinanceCredentials,
    BinanceReadOnlyClient,
    fee_snapshot_from_probe,
    load_dotenv_credentials,
    probe_phase1_binance,
)


class _Response:
    def __init__(self, data, status=200):
        self.status = status
        self._payload = json.dumps(data).encode()

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def _fixture_opener(request, **_kwargs):
    url = request.full_url
    if url.endswith("/ping"):
        return _Response({})
    if "/time" in url:
        return _Response({"serverTime": 1_777_777_777_000})
    if "exchangeInfo" in url:
        return _Response(
            {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "status": "TRADING",
                        "baseAsset": "BTC",
                        "quoteAsset": "USDT",
                        "filters": [
                            {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                            {
                                "filterType": "LOT_SIZE",
                                "minQty": "0.00001",
                                "stepSize": "0.00001",
                            },
                            {"filterType": "MIN_NOTIONAL", "minNotional": "5"},
                        ],
                    }
                ]
            }
        )
    if "premiumIndex" in url:
        return _Response(
            {
                "symbol": "BTCUSDT",
                "lastFundingRate": "0.0001",
                "nextFundingTime": 1_777_780_000_000,
                "time": 1_777_777_777_000,
            }
        )
    if "bookTicker" in url:
        return _Response(
            {
                "symbol": "BTCUSDT",
                "bidPrice": "100000.00",
                "askPrice": "100001.00",
            }
        )
    if "account/commission" in url:
        return _Response(
            {
                "standardCommission": {"maker": "0.001", "taker": "0.001"},
                "discount": {
                    "enabledForAccount": True,
                    "enabledForSymbol": True,
                    "discount": "0.75",
                },
            }
        )
    if "commissionRate" in url:
        return _Response({"makerCommissionRate": "0.0002", "takerCommissionRate": "0.0005"})
    if "symbolConfig" in url:
        return _Response(
            [
                {
                    "symbol": "BTCUSDT",
                    "marginType": "CROSSED",
                    "leverage": 5,
                    "isAutoAddMargin": False,
                    "maxNotionalValue": "1000000",
                }
            ]
        )
    if "/api/v3/account" in url:
        return _Response(
            {
                "canTrade": True,
                "accountType": "SPOT",
                "permissions": ["SPOT"],
                "balances": [{"asset": "USDT", "free": "secret-balance"}],
                "uid": 123456,
            }
        )
    if "/fapi/v3/account" in url:
        return _Response(
            {
                "canTrade": True,
                "multiAssetsMargin": False,
                "assets": [{"asset": "USDT", "walletBalance": "secret-balance"}],
            }
        )
    raise AssertionError(f"unexpected URL: {url}")


def test_read_only_client_rejects_any_non_allowlisted_endpoint():
    client = BinanceReadOnlyClient(opener=_fixture_opener)

    with pytest.raises(ValueError, match="allowlist"):
        client.get(SPOT_DEMO, "/api/v3/order", signed=False)


def test_probe_records_fees_and_configuration_without_balances_or_secrets():
    result = probe_phase1_binance(
        mainnet_credentials=BinanceCredentials("live-key", "live-secret"),
        demo_credentials=BinanceCredentials("demo-key", "demo-secret"),
        classify_mainnet_credentials_on_demo=False,
        location="fixture",
        captured_at=datetime(2026, 9, 3, tzinfo=UTC),
        opener=_fixture_opener,
    )

    assert result["conclusion"] == {
        "dedicated_demo_credentials_valid": True,
        "dedicated_demo_credentials_valid_on_mainnet": False,
        "demo_authenticated_integration_ready": True,
        "mainnet_credentials_valid": True,
        "orders_remain_disabled": True,
    }
    assert result["mainnet_read_only"]["spot_commission"]["standard_maker_bps"] == "10.000"
    assert result["mainnet_read_only"]["usdm_commission"]["taker_bps"] == "5.0000"
    assert result["mainnet_read_only"]["usdm_symbol_config"]["leverage"] == 5
    encoded = json.dumps(result)
    assert "live-key" not in encoded
    assert "demo-secret" not in encoded
    assert "secret-balance" not in encoded
    assert "123456" not in encoded


def test_http_error_records_only_status_and_exchange_code():
    def rejecting_opener(request, **_kwargs):
        if "/time" in request.full_url:
            return _Response({"serverTime": 1_777_777_777_000})
        raise HTTPError(
            request.full_url,
            401,
            "contains-sensitive-human-message",
            {},
            io.BytesIO(b'{"code":-2015,"msg":"Invalid API-key"}'),
        )

    client = BinanceReadOnlyClient(BinanceCredentials("key", "secret"), opener=rejecting_opener)
    result = client.get(
        SPOT_DEMO,
        "/api/v3/account",
        signed=True,
        server_time_path="/api/v3/time",
    )

    assert result.status_dict() == {"ok": False, "http_status": 401, "exchange_code": -2015}
    assert "sensitive" not in json.dumps(result.status_dict())


def test_mainnet_cross_check_can_never_promote_demo_credentials():
    result = probe_phase1_binance(
        mainnet_credentials=BinanceCredentials("live-key", "live-secret"),
        demo_credentials=None,
        classify_mainnet_credentials_on_demo=True,
        location="fixture",
        captured_at=datetime(2026, 9, 3, tzinfo=UTC),
        opener=_fixture_opener,
    )

    assert result["demo"]["credential_source"] == "mainnet_cross_check"
    assert result["demo"]["authentication"]["spot_account"]["ok"]
    assert not result["conclusion"]["dedicated_demo_credentials_valid"]
    assert not result["conclusion"]["demo_authenticated_integration_ready"]


def test_demo_named_mainnet_key_is_detected_without_promotion():
    def environment_opener(request, **kwargs):
        url = request.full_url
        is_demo_account = url.startswith((SPOT_DEMO, USDM_DEMO)) and "/account" in url
        if is_demo_account:
            raise HTTPError(
                url,
                401,
                "redacted",
                {},
                io.BytesIO(b'{"code":-2015,"msg":"Invalid API-key"}'),
            )
        return _fixture_opener(request, **kwargs)

    result = probe_phase1_binance(
        mainnet_credentials=None,
        demo_credentials=BinanceCredentials("misissued-live-key", "live-secret"),
        classify_mainnet_credentials_on_demo=False,
        classify_demo_credentials_on_mainnet=True,
        location="fixture",
        captured_at=datetime(2026, 9, 3, tzinfo=UTC),
        opener=environment_opener,
    )

    assert result["demo"]["credential_environment"] == "mainnet"
    assert result["demo"]["mainnet_cross_check"]["spot_account"]["ok"]
    assert result["demo"]["mainnet_cross_check"]["usdm_account"]["ok"]
    assert result["conclusion"]["dedicated_demo_credentials_valid_on_mainnet"]
    assert not result["conclusion"]["dedicated_demo_credentials_valid"]
    assert not result["conclusion"]["demo_authenticated_integration_ready"]


def test_fee_snapshot_is_derived_without_optional_bnb_discount():
    result = probe_phase1_binance(
        mainnet_credentials=BinanceCredentials("live-key", "live-secret"),
        demo_credentials=None,
        classify_mainnet_credentials_on_demo=False,
        location="fixture",
        captured_at=datetime(2026, 9, 3, tzinfo=UTC),
        opener=_fixture_opener,
    )

    snapshot = fee_snapshot_from_probe(result, maximum_age_hours=24)

    assert snapshot["spot_maker_bps"] == "10.000"
    assert snapshot["perp_maker_bps"] == "2.0000"
    assert snapshot["normal_entry_cost_bps"] == "12.0000"
    assert snapshot["normal_round_trip_cost_bps"] == "24.0000"
    assert snapshot["bnb_discount_available"] is True
    assert snapshot["bnb_discount_applied"] is False


def test_dotenv_loader_does_not_expand_or_return_unrelated_secrets(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "BINANCE_API_KEY='key-value'\n"
        'BINANCE_API_SECRET="secret-value"\n'
        "TELEGRAM_TOKEN=must-not-load\n"
    )

    credentials = load_dotenv_credentials(env_file, "BINANCE")

    assert credentials == BinanceCredentials("key-value", "secret-value")
    assert load_dotenv_credentials(env_file, "BINANCE_DEMO") is None
