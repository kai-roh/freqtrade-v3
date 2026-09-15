"""Independent approval for bounded Demo hedge and liquidation-of-owned-position actions.

This is NOT an entry/economic approval. Receive-gap is explicitly a transport
freshness guard; it does not replace or measure Spot exchange quote age.
"""

from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import time
from dataclasses import dataclass
from decimal import Decimal

from .episode_plan import EpisodeActionType, EpisodeLimits, EpisodeSnapshot, plan_episode_action


def payload_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class ActionApproval:
    approved: bool
    reason: str
    request_hash: str


def evaluate_action(payload: dict) -> ActionApproval:
    digest = payload_hash(payload)
    try:
        if payload["environment"] != "demo" or payload["real_capital"] is not False:
            raise ValueError("Demo only")
        if payload["live_orders"] is not False:
            raise ValueError("Mainnet authorization forbidden")
        if payload["freshness_basis"] != "local_receive_gap":
            raise ValueError("explicit receive-gap basis required")
        if payload["account_reconciled"] is not True:
            raise ValueError("account reconciliation required")
        elapsed = (time.time_ns() - payload["observed_ns"]) / 1_000_000
        if not 0 <= elapsed <= 2000:
            raise ValueError("action observation expired")
        gaps = payload["receive_gap_ms"]
        if len(gaps) != 2 or any(
            type(gap) is not int or gap < 0 or gap + elapsed > 2000 for gap in gaps
        ):
            raise ValueError("quote transport stale")
        if payload.get("purpose") == "demo_engineering_entry":
            return _evaluate_engineering_entry(payload, digest)
        snapshot = EpisodeSnapshot(**payload["snapshot"])
        limits = EpisodeLimits(**payload["limits"])
        action = plan_episode_action(snapshot, limits)
        if action.action not in {
            EpisodeActionType.HEDGE_PERP_SELL,
            EpisodeActionType.CLOSE_PERP_BUY,
            EpisodeActionType.CLOSE_SPOT_SELL,
        }:
            raise ValueError("no permitted position action")
        if (
            payload["action"] != action.action.value
            or Decimal(payload["quantity"]) != action.quantity
        ):
            raise ValueError("requested action does not match confirmed inventory")
        if payload["reduce_only"] is not action.reduce_only:
            raise ValueError("reduce-only mismatch")
        quantity, price = Decimal(payload["quantity"]), Decimal(payload["price"])
        if not price.is_finite() or price <= 0:
            raise ValueError("invalid action price")
        if action.action == EpisodeActionType.HEDGE_PERP_SELL and quantity * price > Decimal("300"):
            raise ValueError("action exceeds bounded Demo notional")
        reference = (
            limits.perp_ask
            if action.action == EpisodeActionType.CLOSE_PERP_BUY
            else limits.spot_bid
            if action.action == EpisodeActionType.CLOSE_SPOT_SELL
            else limits.perp_bid
        )
        # IOC execution must remain within 10 bps of the observed opposite quote.
        if abs(price / reference - 1) > Decimal("0.001"):
            raise ValueError("IOC price exceeds slippage cap")
        leverage = Decimal(payload["perp_leverage"])
        if not leverage.is_finite() or not 1 <= leverage <= 2:
            raise ValueError("invalid observed leverage")
        if payload["margin_type"] != "ISOLATED":
            raise ValueError("isolated margin required")
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        return ActionApproval(False, str(exc), digest)
    return ActionApproval(True, "confirmed-inventory Demo action only", digest)


def _evaluate_engineering_entry(payload, digest):
    """Explicit synthetic-trigger lane; never claims economic entry approval."""
    from decimal import ROUND_FLOOR

    limits = EpisodeLimits(**payload["limits"])
    qty, price = Decimal(payload["quantity"]), Decimal(payload["price"])
    account = payload["account"]
    leverage = Decimal(account["leverage"])
    if not qty.is_finite() or not price.is_finite() or qty <= 0 or price <= 0:
        raise ValueError("invalid engineering entry")
    if (
        payload.get("economic_approval") is not False
        or payload.get("synthetic_trigger") is not True
    ):
        raise ValueError("engineering trigger must be explicitly non-economic")
    if payload.get("action") != "spot_buy_ioc" or payload.get("reduce_only") is not False:
        raise ValueError("engineering entry is Spot buy only")
    if account["open_orders"] or Decimal(account["perp_qty"]) != 0:
        raise ValueError("engineering entry requires flat futures and no open orders")
    if account["margin_type"] != "ISOLATED" or not 1 <= leverage <= 2:
        raise ValueError("engineering entry requires isolated leverage <=2")
    if not 30 <= payload["hold_seconds"] <= 900:
        raise ValueError("engineering holding bound is 30..900 seconds")
    if qty % limits.spot_lot_size or qty * price > 300:
        raise ValueError("engineering entry size exceeds lot or 300 USDT cap")
    if abs(price / limits.spot_ask - 1) > Decimal("0.001"):
        raise ValueError("engineering entry exceeds 10 bps price cap")
    hedge = (qty * Decimal("0.999") / limits.perp_lot_size).to_integral_value(
        rounding=ROUND_FLOOR
    ) * limits.perp_lot_size
    if (
        qty * price < 3 * limits.spot_min_notional
        or hedge * limits.perp_bid < 3 * limits.perp_min_notional
    ):
        raise ValueError("entry and fee-adjusted hedge require 3x minimum headroom")
    for field, required in (
        ("spot_usdt", qty * price * Decimal("1.02")),
        ("perp_usdt", qty * limits.perp_ask / leverage * Decimal("1.02")),
    ):
        value = Decimal(account[field])
        if not value.is_finite() or value < required:
            raise ValueError("engineering wallet buffer insufficient")
    return ActionApproval(
        True, "synthetic Demo infrastructure entry, not economic approval", digest
    )


def _worker(channel):
    try:
        channel.send("ready")
        while True:
            message = channel.recv()
            if message is None:
                return
            channel.send(evaluate_action(message))
    except (EOFError, OSError):
        return
    finally:
        channel.close()


class ActionRiskService:
    """A separate process with no credentials, database, or order transport."""

    def __init__(self):
        context = mp.get_context("spawn")
        self.channel, child = context.Pipe()
        self.process = context.Process(target=_worker, args=(child,), daemon=True)
        self.process.start()
        child.close()
        self.closed = False
        if not self.channel.poll(5) or self.channel.recv() != "ready":
            self.close()
            raise ValueError("action risk service failed to start")

    def evaluate(self, payload: dict) -> ActionApproval:
        digest = payload_hash(payload)
        if self.closed or not self.process.is_alive():
            return ActionApproval(False, "action risk service unavailable", digest)
        try:
            self.channel.send(payload)
            if not self.channel.poll(1.0):
                self.close()
                return ActionApproval(False, "action risk timeout", digest)
            result = self.channel.recv()
            if not isinstance(result, ActionApproval) or result.request_hash != digest:
                self.close()
                return ActionApproval(False, "action risk response mismatch", digest)
            return result
        except (EOFError, OSError):
            self.close()
            return ActionApproval(False, "action risk communication failed", digest)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.channel.close()
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=1)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
