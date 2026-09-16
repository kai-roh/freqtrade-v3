#!/usr/bin/env python3
"""Read Binance USD-M public filters for the Phase 2 universe and judge implementability.

Public GET only: mainnet exchangeInfo for MIN_NOTIONAL, LOT_SIZE and PRICE_FILTER,
and the Demo bookTicker mid as the reference price for the notional floor check.
No credentials, no orders, no writes anywhere but the output file.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from v3.phase1.binance_probe import USDM_DEMO, USDM_LIVE, BinanceReadOnlyClient  # noqa: E402
from v3.phase2.implementability import UNIVERSE, SymbolFilters, evaluate_universe  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    client = BinanceReadOnlyClient()
    info = client.get(USDM_LIVE, "/fapi/v1/exchangeInfo")
    if not info.ok:
        raise SystemExit(f"exchangeInfo failed: {info.http_status}")
    symbols = {row["symbol"]: row for row in info.data["symbols"]}
    filters = []
    raw = {}
    for base in UNIVERSE:
        symbol = f"{base}USDT"
        row = symbols[symbol]
        by_type = {f["filterType"]: f for f in row["filters"]}
        quote = client.get(USDM_DEMO, "/fapi/v1/ticker/bookTicker", params={"symbol": symbol})
        if not quote.ok:
            raise SystemExit(f"bookTicker failed for {symbol}")
        price = (Decimal(quote.data["bidPrice"]) + Decimal(quote.data["askPrice"])) / 2
        raw[symbol] = {
            "status": row["status"],
            "onboardDate": row.get("onboardDate"),
            "MIN_NOTIONAL": by_type["MIN_NOTIONAL"]["notional"],
            "LOT_SIZE.stepSize": by_type["LOT_SIZE"]["stepSize"],
            "PRICE_FILTER.tickSize": by_type["PRICE_FILTER"]["tickSize"],
            "reference_price_demo_mid": str(price),
        }
        filters.append(
            SymbolFilters(
                symbol,
                by_type["MIN_NOTIONAL"]["notional"],
                by_type["LOT_SIZE"]["stepSize"],
                by_type["PRICE_FILTER"]["tickSize"],
                price,
                status=row["status"],
            )
        )
    result = evaluate_universe(filters)
    result["captured_at"] = datetime.now(UTC).isoformat()
    result["sources"] = {
        "filters": f"{USDM_LIVE}/fapi/v1/exchangeInfo",
        "reference_price": f"{USDM_DEMO}/fapi/v1/ticker/bookTicker (mid)",
        "maintenance_margin_rate": "assumed 1% (leverageBracket needs credentials); "
        "2x isolated distance ~49% exceeds the 20% floor by a wide margin",
    }
    result["raw_filters"] = raw
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    for k, block in result["by_legs_per_side"].items():
        print(f"k={k} feasible={block['basket_feasible']} admissible={block['admissible_symbols']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
