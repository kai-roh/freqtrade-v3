import json
import os
from decimal import Decimal
from urllib.parse import parse_qs
from uuid import uuid4

import pytest

from v3.phase1.binance_probe import BinanceCredentials
from v3.phase1.matching_probe import mutate_demo, probe_payload, run_matching_probe

CLIENT = "v3p" + "a" * 29


def instrument(minimum="5"):
    return {
        "symbol": "BTCUSDT",
        "status": "TRADING",
        "filters": [
            {"filterType": "PRICE_FILTER", "tickSize": "0.1"},
            {"filterType": "LOT_SIZE", "stepSize": "0.00001"},
            {"filterType": "MIN_NOTIONAL", "minNotional": minimum},
        ],
    }


@pytest.mark.parametrize("product", ["spot", "perp"])
def test_bounded_post_only_payload(product):
    payload = probe_payload(
        product, instrument(), {"bidPrice": "60000", "askPrice": "60001"}, CLIENT
    )
    assert Decimal(payload["quantity"]) * Decimal(payload["price"]) <= 180
    assert payload["side"] == ("BUY" if product == "spot" else "SELL")
    assert payload["type"] == ("LIMIT_MAKER" if product == "spot" else "LIMIT")
    assert (
        (Decimal(payload["price"]) < 60000)
        if product == "spot"
        else (Decimal(payload["price"]) > 60001)
    )


def test_large_minimum_refuses_order():
    with pytest.raises(ValueError, match="bounded"):
        probe_payload("perp", instrument("200"), {"bidPrice": "60000", "askPrice": "60001"}, CLIENT)


@pytest.mark.parametrize(
    "product,method,payload",
    [
        ("mainnet", "POST", {}),
        ("spot", "PUT", {}),
        ("spot", "DELETE", {"symbol": "BTCUSDT", "origClientOrderId": "foreign"}),
        ("spot", "POST", {"symbol": "ETHUSDT"}),
    ],
)
def test_invalid_request_never_reaches_transport(product, method, payload):
    with pytest.raises(ValueError):
        mutate_demo(
            BinanceCredentials("fixture", "fixture"),
            product,
            method,
            payload,
            opener=lambda *a, **kw: pytest.fail("transport must not be called"),
        )


def test_real_order_endpoint_is_demo_only_and_signed():
    requests = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def read(self):
            return json.dumps({"serverTime": 1234567}).encode()

    def opener(request, **kwargs):
        requests.append(request)
        return Response()

    payload = probe_payload(
        "spot", instrument(), {"bidPrice": "60000", "askPrice": "60001"}, CLIENT
    )
    mutate_demo(BinanceCredentials("fixture", "fixture"), "spot", "POST", payload, opener=opener)
    assert requests[-1].full_url == "https://demo-api.binance.com/api/v3/order"
    assert requests[-1].method == "POST"
    assert "signature" in parse_qs(requests[-1].data.decode())


@pytest.mark.parametrize("uncertain", [False, True])
def test_reservation_survives_unknown_submission_and_never_retries(monkeypatch, uncertain):
    import psycopg
    from psycopg import sql

    from v3.phase1 import matching_probe as module
    from v3.phase1.postgres import apply_migrations

    dsn = os.environ.get("PHASE1_TEST_DATABASE_DSN")
    if not dsn:
        pytest.skip("PHASE1_TEST_DATABASE_DSN not set")
    schema = "test_probe_" + uuid4().hex
    calls = []
    payloads = []

    class Inspector:
        def __init__(self, *_args):
            pass

        def account(self):
            return {
                "open_orders": [],
                "perp_qty": Decimal(0),
                "spot_btc": Decimal(0),
                "margin_type": "ISOLATED",
                "leverage": 2,
                "spot_usdt": Decimal(1000),
                "perp_usdt": Decimal(1000),
            }

        def order(self, product, client):
            if uncertain:
                raise TimeoutError()
            p = payloads[0]
            return dict(
                symbol="BTCUSDT",
                clientOrderId=client,
                side=p["side"],
                origQty=p["quantity"],
                price=p["price"],
                orderId=123,
                status="CANCELED",
                executedQty="0",
            )

        def get(self, product, path, params):
            assert params == {"symbol": "BTCUSDT", "orderId": "123"}
            return self.order(product, "cancel-id")

    class Reader:
        def get(self, base, path, **kwargs):
            from types import SimpleNamespace

            return SimpleNamespace(
                ok=True,
                data={"symbols": [instrument()]}
                if path.endswith("exchangeInfo")
                else {"bidPrice": "60000", "askPrice": "60001"},
            )

    monkeypatch.setattr(module, "DemoInspector", Inspector)
    monkeypatch.setattr(module, "BinanceReadOnlyClient", Reader)
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        try:
            apply_migrations(connection)

            def mutate(credentials, product, method, payload):
                calls.append(method)
                if method == "POST":
                    payloads.append(payload)
                    assert (
                        connection.execute("SELECT state FROM demo_matching_probes").fetchone()[0]
                        == "RESERVED"
                    )
                    if uncertain:
                        raise TimeoutError()
                    return {
                        "symbol": "BTCUSDT",
                        "clientOrderId": payload["newClientOrderId"],
                        "orderId": 123,
                    }
                if not uncertain:
                    return {
                        "symbol": "BTCUSDT",
                        "origClientOrderId": payload["origClientOrderId"],
                        "clientOrderId": "cancel-id",
                        "orderId": 123,
                    }
                return {}

            monkeypatch.setattr(module, "mutate_demo", mutate)
            report = run_matching_probe(
                None,
                connection,
                product="spot",
                source_sha="a" * 40,
                image_digest="sha256:" + "b" * 64,
            )
            assert calls == ["POST", "DELETE"]
            assert report["passed"] is (not uncertain)
            if uncertain:
                with pytest.raises(ValueError, match="unresolved probe"):
                    run_matching_probe(
                        None,
                        connection,
                        product="spot",
                        source_sha="a" * 40,
                        image_digest="sha256:" + "b" * 64,
                    )
                assert calls == ["POST", "DELETE"]
        finally:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
