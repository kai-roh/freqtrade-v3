"""Read-only Demo account and tracked-order reconciliation."""

from decimal import Decimal

from .binance_probe import SPOT_DEMO, USDM_DEMO, BinanceReadOnlyClient


class DemoInspector:
    def __init__(self, credentials):
        self.client = BinanceReadOnlyClient(credentials, timeout_seconds=5)

    def get(self, leg, path, params=None):
        if leg not in {"spot", "perp"}:
            raise ValueError("unknown Demo leg")
        result = self.client.get(
            SPOT_DEMO if leg == "spot" else USDM_DEMO,
            path,
            signed=True,
            params=params,
            server_time_path="/api/v3/time" if leg == "spot" else "/fapi/v1/time",
        )
        if not result.ok:
            raise ValueError(f"Demo read failed: {result.http_status}/{result.exchange_code}")
        return result.data

    def account(self):
        spot = self.get("spot", "/api/v3/account")
        perp = self.get("perp", "/fapi/v3/account")
        config = self.get("perp", "/fapi/v1/symbolConfig", {"symbol": "BTCUSDT"})
        mode = self.get("perp", "/fapi/v1/positionSide/dual")
        spot_orders = self.get("spot", "/api/v3/openOrders", {"symbol": "BTCUSDT"})
        perp_orders = self.get("perp", "/fapi/v1/openOrders", {"symbol": "BTCUSDT"})
        if not isinstance(spot_orders, list) or not isinstance(perp_orders, list):
            raise ValueError("order snapshot invalid")
        balances = {r["asset"]: Decimal(r["free"]) for r in spot["balances"]}
        positions = [r for r in perp["positions"] if r["symbol"] == "BTCUSDT"]
        configs = [r for r in config if r["symbol"] == "BTCUSDT"]
        if len(configs) != 1 or mode.get("dualSidePosition") is not False:
            raise ValueError("one-way Demo symbol configuration required")
        if any(r.get("positionSide") != "BOTH" for r in positions):
            raise ValueError("ambiguous Demo position snapshot")
        result = dict(
            spot_usdt=balances.get("USDT", Decimal(0)),
            spot_btc=balances.get("BTC", Decimal(0)),
            perp_usdt=Decimal(perp["availableBalance"]),
            perp_qty=sum((Decimal(r["positionAmt"]) for r in positions), Decimal(0)),
            leverage=int(configs[0]["leverage"]),
            margin_type=configs[0]["marginType"].upper(),
            open_orders=spot_orders + perp_orders,
        )
        if not all(value.is_finite() for value in result.values() if isinstance(value, Decimal)):
            raise ValueError("nonfinite account snapshot")
        return result

    def order(self, leg, client_id):
        path = "/api/v3/order" if leg == "spot" else "/fapi/v1/order"
        return self.get(leg, path, {"symbol": "BTCUSDT", "origClientOrderId": client_id})

    def fills(self, leg, order_id):
        path = "/api/v3/myTrades" if leg == "spot" else "/fapi/v1/userTrades"
        rows = self.get(leg, path, {"symbol": "BTCUSDT", "orderId": order_id, "limit": 1000})
        if not isinstance(rows, list) or len(rows) >= 1000:
            raise ValueError("trade query incomplete; pagination/reconciliation required")
        return [r for r in rows if str(r["orderId"]) == str(order_id)]
