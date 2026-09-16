import io
import json
from urllib.error import HTTPError
from urllib.parse import parse_qs

import pytest

from v3.phase1.binance_admin import prepare_demo_futures_account
from v3.phase1.binance_probe import BinanceCredentials


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


def _account(balance="0", position="0"):
    return {
        "assets": [{"asset": "USDT", "availableBalance": balance, "walletBalance": balance}],
        "positions": [{"symbol": "BTCUSDT", "positionAmt": position}],
    }


def _symbol_config(margin="CROSSED", leverage=20):
    return [{"symbol": "BTCUSDT", "marginType": margin, "leverage": leverage}]


def test_demo_account_preparation_plans_required_changes_without_posting():
    posted = []

    def opener(request, **_kwargs):
        if request.method == "POST":
            posted.append(request.full_url)
        if "/time" in request.full_url:
            return _Response({"serverTime": 1_777_777_777_000})
        if "/fapi/v3/account" in request.full_url:
            return _Response(_account(balance="0"))
        if "/openOrders" in request.full_url:
            return _Response([])
        if "/symbolConfig" in request.full_url:
            return _Response(_symbol_config())
        raise AssertionError(request.full_url)

    result = prepare_demo_futures_account(
        BinanceCredentials("key", "secret"),
        apply_changes=False,
        opener=opener,
    )

    assert result.actions_required == ("set_margin_type_isolated", "set_leverage_2")
    assert result.actions_applied == ()
    assert "Demo Futures USDT available balance is below 300" in result.blocked_reasons
    assert not result.ready_for_phase1_demo_execution
    assert not posted


def test_demo_account_preparation_applies_only_demo_margin_and_leverage_when_flat():
    posted = []
    refreshed = False

    def opener(request, **_kwargs):
        nonlocal refreshed
        if "/time" in request.full_url:
            return _Response({"serverTime": 1_777_777_777_000})
        if "/fapi/v3/account" in request.full_url:
            return _Response(_account(balance="500"))
        if "/openOrders" in request.full_url:
            return _Response([])
        if "/symbolConfig" in request.full_url:
            if refreshed:
                return _Response(_symbol_config(margin="ISOLATED", leverage=2))
            return _Response(_symbol_config())
        if request.method == "POST":
            posted.append((request.full_url, parse_qs(request.data.decode())))
            if "/leverage" in request.full_url:
                refreshed = True
            return _Response({"code": 200, "msg": "success"})
        raise AssertionError(request.full_url)

    result = prepare_demo_futures_account(
        BinanceCredentials("key", "secret"),
        apply_changes=True,
        opener=opener,
    )

    assert result.actions_applied == ("set_margin_type_isolated", "set_leverage_2")
    assert result.ready_for_phase1_demo_execution
    assert [url for url, _payload in posted] == [
        "https://demo-fapi.binance.com/fapi/v1/marginType",
        "https://demo-fapi.binance.com/fapi/v1/leverage",
    ]
    assert posted[0][1]["marginType"] == ["ISOLATED"]
    assert posted[1][1]["leverage"] == ["2"]


def test_demo_account_preparation_refuses_to_change_non_flat_account():
    def opener(request, **_kwargs):
        if request.method == "POST":
            raise AssertionError("POST should not be called when not flat")
        if "/time" in request.full_url:
            return _Response({"serverTime": 1_777_777_777_000})
        if "/fapi/v3/account" in request.full_url:
            return _Response(_account(balance="500", position="0.01"))
        if "/openOrders" in request.full_url:
            return _Response([{"orderId": 1}])
        if "/symbolConfig" in request.full_url:
            return _Response(_symbol_config())
        raise AssertionError(request.full_url)

    result = prepare_demo_futures_account(
        BinanceCredentials("key", "secret"),
        apply_changes=True,
        opener=opener,
    )

    assert "symbol is not flat" in result.blocked_reasons
    assert result.actions_applied == ()


def test_demo_config_client_rejects_non_allowlisted_post_endpoint():
    def opener(_request, **_kwargs):
        raise AssertionError("network should not be reached")

    from v3.phase1.binance_probe import BinanceDemoConfigClient

    client = BinanceDemoConfigClient(BinanceCredentials("key", "secret"), opener=opener)
    with pytest.raises(ValueError, match="POST allowlist"):
        client.post(
            "https://demo-fapi.binance.com",
            "/fapi/v1/order",
            params={"symbol": "BTCUSDT"},
            server_time_path="/fapi/v1/time",
        )


def test_already_isolated_margin_code_is_treated_as_success():
    def opener(request, **_kwargs):
        if "/time" in request.full_url:
            return _Response({"serverTime": 1_777_777_777_000})
        if "/fapi/v3/account" in request.full_url:
            return _Response(_account(balance="500"))
        if "/openOrders" in request.full_url:
            return _Response([])
        if "/symbolConfig" in request.full_url:
            return _Response(_symbol_config(margin="ISOLATED", leverage=20))
        if "/leverage" in request.full_url:
            return _Response({"leverage": 2, "symbol": "BTCUSDT"})
        raise HTTPError(
            request.full_url,
            400,
            "redacted",
            {},
            io.BytesIO(b'{"code":-4046,"msg":"No need to change margin type."}'),
        )

    result = prepare_demo_futures_account(
        BinanceCredentials("key", "secret"),
        apply_changes=True,
        opener=opener,
    )

    assert result.actions_applied == ("set_leverage_2",)
    assert "margin type update failed" not in result.blocked_reasons
