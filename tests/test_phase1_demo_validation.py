import io
import json
from urllib.error import HTTPError
from urllib.parse import parse_qs
from urllib.request import Request

import pytest

from v3.phase1.binance_probe import BinanceCredentials
from v3.phase1.demo_validation import RejectRedirects, validate_test_order


class Response:
    status = 200

    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return json.dumps(self.data).encode()


@pytest.mark.parametrize(
    "product,host,path,order_type",
    [
        ("spot", "https://demo-api.binance.com", "/api/v3/order/test", "LIMIT_MAKER"),
        ("usdm", "https://demo-fapi.binance.com", "/fapi/v1/order/test", "LIMIT"),
    ],
)
def test_validation_can_only_send_to_demo_test_endpoint(product, host, path, order_type):
    requests = []

    def opener(request, **kwargs):
        requests.append(request)
        if request.full_url.endswith("/time"):
            return Response({"serverTime": 123456789})
        assert request.full_url == host + path
        assert request.get_method() == "POST"
        fields = parse_qs(request.data.decode())
        assert fields["symbol"] == ["BTCUSDT"]
        assert fields["type"] == [order_type]
        assert "signature" in fields
        if product == "usdm":
            assert fields["timeInForce"] == ["GTX"]
        return Response({})

    result = validate_test_order(
        BinanceCredentials("key", "secret"),
        product=product,
        quantity="0.003",
        price="100000",
        opener=opener,
    )
    assert result["ok"]
    assert len(requests) == 2


def test_validation_rejects_redirect_before_credentials_can_cross_hosts():
    handler = RejectRedirects()
    with pytest.raises(HTTPError, match="redirect forbidden"):
        handler.redirect_request(
            Request("https://demo-api.binance.com/api/v3/order/test"),
            None,
            302,
            "redirect",
            {},
            "https://api.binance.com/api/v3/order",
        )


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "0"])
def test_invalid_quantity_makes_no_network_requests(value):
    def opener(*args, **kwargs):
        raise AssertionError("no request expected")

    with pytest.raises(ValueError):
        validate_test_order(
            BinanceCredentials("key", "secret"),
            product="spot",
            quantity=value,
            price="100000",
            opener=opener,
        )


def test_validation_error_is_redacted_and_never_retried():
    calls = []

    def opener(request, **kwargs):
        if request.full_url.endswith("/time"):
            return Response({"serverTime": 123})
        calls.append(request)
        raise HTTPError(
            request.full_url,
            401,
            "private-key",
            {},
            io.BytesIO(b'{"code":-2015,"msg":"private-secret"}'),
        )

    result = validate_test_order(
        BinanceCredentials("key", "secret"),
        product="usdm",
        quantity="0.003",
        price="100000",
        opener=opener,
    )
    assert result == {"ok": False, "http_status": 401, "exchange_code": -2015}
    assert len(calls) == 1


def test_unexpected_success_payload_does_not_pass_validation():
    def opener(request, **kwargs):
        return Response(
            {"serverTime": 123} if request.full_url.endswith("/time") else {"code": -2015}
        )

    result = validate_test_order(
        BinanceCredentials("key", "secret"),
        product="spot",
        quantity="0.003",
        price="100000",
        opener=opener,
    )
    assert not result["ok"]


def test_usdm_validation_response_is_not_a_real_fill():
    def opener(request, **kwargs):
        if request.full_url.endswith("/time"):
            return Response({"serverTime": 123})
        return Response(
            {
                "symbol": "BTCUSDT",
                "type": "LIMIT",
                "side": "SELL",
                "timeInForce": "GTX",
                "origQty": "0.003",
                "executedQty": "0",
                "orderId": 1234,
            }
        )

    result = validate_test_order(
        BinanceCredentials("key", "secret"),
        product="usdm",
        quantity="0.003",
        price="100000",
        opener=opener,
    )
    assert result["ok"]
    assert result["validation_order_response"]
    assert "orderId" not in result


def test_usdm_empty_template_is_inconclusive_even_with_http_200():
    def opener(request, **kwargs):
        if request.full_url.endswith("/time"):
            return Response({"serverTime": 123})
        return Response(
            {
                "symbol": "",
                "side": "",
                "type": "",
                "origQty": "",
                "executedQty": "",
                "timeInForce": "",
                "status": "",
            }
        )

    result = validate_test_order(
        BinanceCredentials("key", "secret"),
        product="usdm",
        quantity="0.003",
        price="100000",
        opener=opener,
    )
    assert not result["ok"]
    assert result["reason"] == "unverified_response_shape"
