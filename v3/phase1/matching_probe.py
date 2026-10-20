"""One-shot Demo matching-engine acceptance/cancel test, not a trading strategy.

Explicitly separate from carry risk approval: no profitability or Phase 1E claim.
Each durable reservation permits one POST only. Uncertain outcomes block later runs.
"""

import hashlib
import hmac
import json
import re
import ssl
import time
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from urllib.parse import urlencode
from urllib.request import Request
from uuid import uuid4

from .binance_probe import SPOT_DEMO, USDM_DEMO, BinanceReadOnlyClient
from .demo_inspector import DemoInspector
from .http import secure_open

MAX_NOTIONAL = Decimal("180")


def query_terminal(inspector, product, client_id, venue_order_id=None):
    """Allow bounded read-model lag after cancel; never repeat the mutation."""
    prefix = "/api/v3" if product == "spot" else "/fapi/v1"
    for attempt in range(10):
        if venue_order_id is None:
            order = inspector.order(product, client_id)
        else:
            order = inspector.get(
                product, prefix + "/order", {"symbol": "BTCUSDT", "orderId": venue_order_id}
            )
        if order["status"] not in {"NEW", "PARTIALLY_FILLED"} or Decimal(order["executedQty"]) != 0:
            return order
        if attempt < 9:
            time.sleep(0.25)
    return order


def probe_payload(product, instrument, quote, client_id):
    if product not in {"spot", "perp"} or not re.fullmatch(r"v3p[a-f0-9]{29}", client_id):
        raise ValueError("invalid probe identity")
    if instrument["symbol"] != "BTCUSDT" or instrument["status"] != "TRADING":
        raise ValueError("instrument unavailable")
    filters = {r["filterType"]: r for r in instrument["filters"]}
    tick = Decimal(filters["PRICE_FILTER"]["tickSize"])
    step = Decimal(filters["LOT_SIZE"]["stepSize"])
    minimum = filters.get("NOTIONAL", filters.get("MIN_NOTIONAL", {}))
    minimum = Decimal(minimum.get("minNotional", minimum.get("notional", "NaN")))
    bid, ask = Decimal(quote["bidPrice"]), Decimal(quote["askPrice"])
    if any(not v.is_finite() or v <= 0 for v in (tick, step, minimum, bid, ask)) or ask < bid:
        raise ValueError("invalid instrument or quote")
    # Rest 1% away, then cancel immediately; no deliberate fill request.
    raw = bid * Decimal("0.99") if product == "spot" else ask * Decimal("1.01")
    rounding = ROUND_FLOOR if product == "spot" else ROUND_CEILING
    price = (raw / tick).to_integral_value(rounding=rounding) * tick
    quantity = (max(Decimal("15"), minimum * Decimal("1.2")) / price / step).to_integral_value(
        rounding=ROUND_CEILING
    ) * step
    if not minimum <= price * quantity <= MAX_NOTIONAL:
        raise ValueError("probe exceeds bounded Demo notional")
    payload = dict(
        symbol="BTCUSDT",
        side="BUY" if product == "spot" else "SELL",
        type="LIMIT_MAKER" if product == "spot" else "LIMIT",
        quantity=str(quantity),
        price=str(price),
        newClientOrderId=client_id,
    )
    if product == "perp":
        payload["timeInForce"] = "GTX"
    return payload


def mutate_demo(credentials, product, method, payload, *, opener=secure_open):
    """Fixed Demo endpoints and methods; no arbitrary URL, transfers or bulk cancels."""
    if product not in {"spot", "perp"} or method not in {"POST", "DELETE"}:
        raise ValueError("unsupported Demo operation")
    if payload.get("symbol") != "BTCUSDT":
        raise ValueError("only BTCUSDT probe permitted")
    client_id = payload.get("newClientOrderId" if method == "POST" else "origClientOrderId", "")
    if not re.fullmatch(r"v3p[a-f0-9]{29}", client_id):
        raise ValueError("only probe-owned client IDs permitted")
    if method == "POST":
        allowed = {"symbol", "side", "type", "quantity", "price", "newClientOrderId"}
        if product == "perp":
            allowed.add("timeInForce")
        if set(payload) != allowed:
            raise ValueError("unexpected order field")
        if (payload["side"], payload["type"], payload.get("timeInForce")) != (
            ("BUY", "LIMIT_MAKER", None) if product == "spot" else ("SELL", "LIMIT", "GTX")
        ):
            raise ValueError("only post-only probe entry is permitted")
        q, p = Decimal(payload["quantity"]), Decimal(payload["price"])
        if any(not v.is_finite() or v <= 0 for v in (q, p)) or q * p > MAX_NOTIONAL:
            raise ValueError("probe notional invalid")
    elif set(payload) != {"symbol", "origClientOrderId"}:
        raise ValueError("only an individual probe cancel is permitted")
    base, prefix = (SPOT_DEMO, "/api/v3") if product == "spot" else (USDM_DEMO, "/fapi/v1")
    clock = BinanceReadOnlyClient(opener=opener).get(base, prefix + "/time")
    if not clock.ok or type(clock.data.get("serverTime")) is not int:
        raise ValueError("Demo clock unavailable")
    params = dict(payload, timestamp=clock.data["serverTime"], recvWindow=5000)
    body = urlencode(params)
    signature = hmac.new(credentials.api_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    request = Request(
        base + prefix + "/order",
        method=method,
        data=(body + "&signature=" + signature).encode(),
        headers={
            "X-MBX-APIKEY": credentials.api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with opener(request, timeout=5, context=ssl.create_default_context()) as response:
        return json.loads(response.read())


def run_matching_probe(credentials, connection, *, product, source_sha, image_digest):
    """Call from a tagged immutable image; caller supplies its verified deployment IDs."""
    if not re.fullmatch(r"[a-f0-9]{40}", source_sha) or not re.fullmatch(
        r"sha256:[a-f0-9]{64}", image_digest
    ):
        raise ValueError("pinned source and image required")
    if product not in {"spot", "perp"}:
        raise ValueError("invalid product")
    # Session lock spans read checks, reservation, submission, cancellation and final read.
    with connection.transaction():
        if not connection.execute("SELECT pg_try_advisory_lock(31092027)").fetchone()[0]:
            raise ValueError("another probe owns the Demo execution lock")
    try:
        with connection.transaction():
            if connection.execute(
                "SELECT 1 FROM demo_matching_probes WHERE state <> 'CANCELED' LIMIT 1"
            ).fetchone():
                raise ValueError("unresolved probe blocks new orders")
            if connection.execute("SELECT 1 FROM order_commands WHERE active LIMIT 1").fetchone():
                raise ValueError("strategy commands already active")
            if connection.execute(
                "SELECT 1 FROM fill_event_inbox WHERE status <> 'APPLIED' LIMIT 1"
            ).fetchone():
                raise ValueError("unresolved fills block probe")
        inspector = DemoInspector(credentials)
        account = inspector.account()
        if account["open_orders"] or account["perp_qty"] != 0:
            raise ValueError("Demo account must have no BTC orders and flat futures")
        if account["margin_type"] != "ISOLATED" or not 1 <= account["leverage"] <= 2:
            raise ValueError("isolated margin and at most 2x required")
        if min(account["spot_usdt"], account["perp_usdt"]) < MAX_NOTIONAL * Decimal("1.01"):
            raise ValueError("both Demo wallets must be prefunded")
        base, prefix = (SPOT_DEMO, "/api/v3") if product == "spot" else (USDM_DEMO, "/fapi/v1")
        reader = BinanceReadOnlyClient()
        info = reader.get(base, prefix + "/exchangeInfo", params={"symbol": "BTCUSDT"})
        quote = reader.get(base, prefix + "/ticker/bookTicker", params={"symbol": "BTCUSDT"})
        if not info.ok or not quote.ok:
            raise ValueError("market preflight unavailable")
        instrument = next(r for r in info.data["symbols"] if r["symbol"] == "BTCUSDT")
        client_id = "v3p" + uuid4().hex[:29]
        payload = probe_payload(product, instrument, quote.data, client_id)
        with connection.transaction():
            connection.execute(
                "INSERT INTO demo_matching_probes(id,source_sha,image_digest,product,payload,state) "
                "VALUES (%s,%s,%s,%s,%s::jsonb,'RESERVED')",
                (client_id, source_sha, image_digest, product, json.dumps(payload)),
            )
        errors = []
        venue_order_id = None
        accepted_client_ids = {client_id}
        try:
            acknowledgment = mutate_demo(credentials, product, "POST", payload)
            if (
                acknowledgment.get("clientOrderId") == client_id
                and acknowledgment.get("symbol") == "BTCUSDT"
            ):
                venue_order_id = str(acknowledgment["orderId"])
        except Exception as exc:
            errors.append(type(exc).__name__)  # Never retry uncertain submission.
        finally:
            # Cancel by our precommitted ID even if the POST response was lost.
            try:
                with connection.transaction():
                    connection.execute(
                        "UPDATE demo_matching_probes SET state='CANCEL_PENDING',updated_at=clock_timestamp() WHERE id=%s",
                        (client_id,),
                    )
            except Exception as exc:
                errors.append(type(exc).__name__)
            try:
                cancellation = mutate_demo(
                    credentials,
                    product,
                    "DELETE",
                    {"symbol": "BTCUSDT", "origClientOrderId": client_id},
                )
                # Spot cancellation can replace clientOrderId with a cancel ID.
                # Bind that ID to our original ID and immutable venue order ID.
                if cancellation.get("symbol") == "BTCUSDT" and (
                    cancellation.get("origClientOrderId") == client_id
                    or (product == "perp" and cancellation.get("clientOrderId") == client_id)
                ):
                    cancel_order_id = str(cancellation["orderId"])
                    if venue_order_id is not None and venue_order_id != cancel_order_id:
                        raise ValueError("cancel order identity mismatch")
                    venue_order_id = cancel_order_id
                    accepted_client_ids.add(cancellation["clientOrderId"])
            except Exception as exc:
                errors.append(type(exc).__name__)
        report = {
            "client_order_id": client_id,
            "product": product,
            "errors": errors,
            "matching_engine_post_attempts": 1,
            "strategy_started": False,
            "passed": False,
        }
        if venue_order_id is not None:
            report["venue_order_id"] = venue_order_id
        try:
            order = query_terminal(inspector, product, client_id, venue_order_id)
            if (
                order["symbol"] != "BTCUSDT"
                or order["clientOrderId"] not in accepted_client_ids
                or order["side"] != payload["side"]
                or (venue_order_id is not None and str(order["orderId"]) != venue_order_id)
            ):
                raise ValueError("order identity mismatch")
            if Decimal(order["origQty"]) != Decimal(payload["quantity"]) or Decimal(
                order["price"]
            ) != Decimal(payload["price"]):
                raise ValueError("order payload mismatch")
            report.update(
                venue_order_id=str(order["orderId"]),
                status=order["status"],
                executed_quantity=order["executedQty"],
                quantity=payload["quantity"],
                price=payload["price"],
            )
            after = inspector.account()
            report["account_unchanged"] = (
                after["spot_btc"] == account["spot_btc"]
                and after["perp_qty"] == 0
                and not after["open_orders"]
            )
            report["passed"] = (
                order["status"] == "CANCELED"
                and Decimal(order["executedQty"]) == 0
                and report["account_unchanged"]
            )
        except Exception as exc:
            errors.append(type(exc).__name__)
        with connection.transaction():
            connection.execute(
                "UPDATE demo_matching_probes SET state=%s,report=%s::jsonb,updated_at=clock_timestamp() WHERE id=%s",
                ("CANCELED" if report["passed"] else "BLOCKED", json.dumps(report), client_id),
            )
        return report
    finally:
        with connection.transaction():
            connection.execute("SELECT pg_advisory_unlock(31092027)")


def reconcile_matching_probe(credentials, connection, client_id):
    """Resolve a stored probe using GET only, retaining its initial failed report."""
    from psycopg.rows import dict_row

    with connection.transaction(), connection.cursor(row_factory=dict_row) as cursor:
        row = cursor.execute(
            "SELECT * FROM demo_matching_probes WHERE id=%s FOR UPDATE", (client_id,)
        ).fetchone()
        if not row:
            raise ValueError("unknown probe")
        if row["state"] == "CANCELED":
            return row["report"]
        inspector = DemoInspector(credentials)
        venue_id = row["report"].get("venue_order_id")
        order = query_terminal(inspector, row["product"], client_id, venue_id)
        payload = row["payload"]
        if order["symbol"] != "BTCUSDT" or order["side"] != payload["side"]:
            raise ValueError("reconciliation identity mismatch")
        if venue_id is not None:
            if str(order["orderId"]) != str(venue_id):
                raise ValueError("reconciliation venue identity mismatch")
        elif order["clientOrderId"] != client_id:
            raise ValueError("reconciliation client identity mismatch")
        if Decimal(order["origQty"]) != Decimal(payload["quantity"]) or Decimal(
            order["price"]
        ) != Decimal(payload["price"]):
            raise ValueError("reconciliation payload mismatch")
        account = inspector.account()
        if (
            order["status"] != "CANCELED"
            or Decimal(order["executedQty"]) != 0
            or account["open_orders"]
            or account["perp_qty"] != 0
        ):
            raise ValueError("probe still unresolved; do not submit another order")
        report = dict(
            row["report"],
            initial_report=row["report"],
            passed=True,
            status="CANCELED",
            executed_quantity=order["executedQty"],
            venue_order_id=str(order["orderId"]),
            reconciled_read_only=True,
        )
        cursor.execute(
            "UPDATE demo_matching_probes SET state='CANCELED',report=%s::jsonb,updated_at=clock_timestamp() WHERE id=%s",
            (json.dumps(report), client_id),
        )
        return report
