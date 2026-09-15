#!/usr/bin/env python3
"""Run one durable Demo carry engineering episode, including timed automatic exit.

This is a synthetic engineering trigger, NOT approval of a profitable strategy.
No mainnet credentials, transfers, or unbounded replacement. Closing dust below
the Spot minimum order is settled as an audited owned residual, never sold or hidden.
"""

import argparse
import asyncio
import json
import math
import os
import sys
import time
import traceback
from datetime import UTC, datetime, timedelta
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg  # noqa: E402

from v3.phase1.action_risk import ActionRiskService  # noqa: E402
from v3.phase1.binance_probe import BinanceReadOnlyClient, load_dotenv_credentials  # noqa: E402
from v3.phase1.demo_collector import stream_quote_row  # noqa: E402
from v3.phase1.demo_inspector import DemoInspector  # noqa: E402
from v3.phase1.demo_node import DemoNode  # noqa: E402
from v3.phase1.engineering_entry import submit_engineering_entry  # noqa: E402
from v3.phase1.episode_coordinator import manage_episode_once  # noqa: E402
from v3.phase1.episode_lifecycle import settle_episode_residual  # noqa: E402
from v3.phase1.episode_plan import EpisodeLimits  # noqa: E402
from v3.phase1.fill_inbox import DurableFillInbox  # noqa: E402
from v3.phase1.node_smoke import _private_native_logs  # noqa: E402
from v3.phase1.notifications import Phase1Notification, send_phase1_telegram  # noqa: E402
from v3.phase1.observations import capture_binance_carry_market_observation  # noqa: E402
from v3.phase1.position_gateway import account_execution_lock  # noqa: E402
from v3.phase1.postgres import PostgresPhase1Ledger, apply_migrations  # noqa: E402
from v3.phase1.rest_recovery import recover_tracked_order  # noqa: E402
from v3.reproducibility import (  # noqa: E402
    NO_MODEL_ARTIFACT_SHA256,
    RunManifest,
    TimeRange,
    sha256_file,
)


async def execute(args, runtimes):
    policy_path = Path("configs/phase1-engineering.json")
    policy = json.loads(policy_path.read_text())
    if policy["environment"] != "demo" or policy["real_capital"] or policy["economic_approval"]:
        raise ValueError("Demo engineering policy required")
    if policy["maximum_episodes"] != 1 or not policy["synthetic_trigger"]:
        raise ValueError("only one explicit engineering episode is authorized")
    started = datetime.fromisoformat(args.started_at).astimezone(UTC)
    manifest = RunManifest(
        os.environ["PHASE1_BUILD_SOURCE_SHA"],
        os.environ["PHASE1_IMAGE_DIGEST"],
        sha256_file(Path("uv.lock")),
        sha256_file(policy_path),
        NO_MODEL_ARTIFACT_SHA256,
        "demo-engineering:" + started.isoformat(),
        TimeRange(started, started + timedelta(seconds=1)),
        started,
    )
    manifest.assert_deployable()
    credentials = load_dotenv_credentials(args.credentials_env_file, "BINANCE_DEMO")
    if credentials is None:
        raise ValueError("dedicated Demo credentials required")
    telegram = {}
    for line in args.credentials_env_file.read_text().splitlines():
        name, sep, value = line.partition("=")
        if sep and name.strip() in {"TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"}:
            telegram[name.strip()] = value.strip().strip("\"'")

    history = []

    async def report(kind, detail):
        event = dict(at=datetime.now(UTC).isoformat(), kind=kind, **detail)
        history.append(event)
        args.output.write_text(
            json.dumps(
                dict(
                    environment="demo",
                    economic_approval=False,
                    manifest=manifest.to_dict(),
                    events=history,
                ),
                indent=2,
            )
            + "\n"
        )
        await asyncio.to_thread(
            send_phase1_telegram,
            Phase1Notification(
                kind,
                "데모 자동 캐리 실행",
                "합성 진입·자동 헤지·시간 청산; 수익성 검증 아님",
                datetime.now(UTC),
                detail,
            ),
            token=telegram.get("TELEGRAM_TOKEN", ""),
            chat_id=telegram.get("TELEGRAM_CHAT_ID", ""),
        )

    observation = await asyncio.to_thread(
        capture_binance_carry_market_observation, BinanceReadOnlyClient()
    )
    spot, perp = observation.spot_instrument, observation.perp_instrument
    dsn = os.environ["PHASE1_DATABASE_DSN"]
    with (
        psycopg.connect(dsn, autocommit=True) as control,
        psycopg.connect(dsn, autocommit=True) as stream,
        ActionRiskService() as risk,
    ):
        apply_migrations(control)
        # Dedicated process-lifetime ownership, separate from per-order/account locks.
        if not control.execute("SELECT pg_try_advisory_lock(31092029)").fetchone()[0]:
            raise ValueError("Demo auto runner already active")
        if args.resume_intent:
            if not args.previous_manifest:
                raise ValueError("explicit previous manifest required for close-only takeover")
            with account_execution_lock(control), control.transaction():
                row = control.execute(
                    "SELECT i.run_manifest_id,i.state,b.close_requested_at FROM intents i "
                    "JOIN episode_baselines b ON b.intent_id=i.id WHERE i.id=%s FOR UPDATE",
                    (args.resume_intent,),
                ).fetchone()
                if (
                    not row
                    or row[0] != args.previous_manifest
                    or row[2] is None
                    or row[1] not in {"ABORTING", "RECONCILING", "RECONCILIATION_BLOCKED"}
                ):
                    raise ValueError("only an explicitly identified closing episode can transfer")
                control.execute(
                    "UPDATE episode_baselines SET evidence=evidence || %s::jsonb WHERE intent_id=%s",
                    (
                        json.dumps(
                            {
                                "close_only_takeover": {
                                    "from_manifest": row[0],
                                    "to_manifest": manifest.to_dict(),
                                    "at": datetime.now(UTC).isoformat(),
                                }
                            }
                        ),
                        args.resume_intent,
                    ),
                )
                control.execute(
                    "UPDATE intents SET run_manifest_id=%s WHERE id=%s",
                    (manifest.manifest_id, args.resume_intent),
                )
        ledger = PostgresPhase1Ledger(stream)
        for instrument in (spot, perp):
            ledger.add_instrument_snapshot(instrument.to_postgres_row())
        snapshots = {s.instrument_id: s.id for s in (spot, perp)}
        last_quote = dict.fromkeys(snapshots, float("-inf"))
        inbox = DurableFillInbox(stream)
        fills = []

        def quote_sink(canonical, quote):
            if time.monotonic() - last_quote[canonical] >= 1:
                ledger.add_quote_observation(stream_quote_row(snapshots[canonical], quote))
                last_quote[canonical] = time.monotonic()

        def fill_sink(event):
            receipt = inbox.receive(event)
            if inbox.process(receipt) != "APPLIED":
                raise ValueError("fill quarantine requires review")
            fills.append(
                dict(
                    instrument=str(event.instrument_id),
                    quantity=str(event.last_qty),
                    price=str(event.last_px),
                    side=event.order_side.name,
                )
            )

        runtime = DemoNode(
            credentials, fill_sink=fill_sink, quote_sink=quote_sink, loop=asyncio.get_running_loop()
        )
        runtimes.append(runtime)
        inspector = DemoInspector(credentials)

        def market():
            sq, pq = (runtime.strategy.quotes[s.instrument_id] for s in (spot, perp))
            return (
                EpisodeLimits(
                    spot.lot_size,
                    perp.lot_size,
                    spot.minimum_notional,
                    perp.minimum_notional,
                    sq.bid,
                    sq.ask,
                    pq.bid,
                    pq.ask,
                ),
                (math.ceil(sq.gap_ms()), math.ceil(pq.gap_ms())),
                time.time_ns(),
            )

        class SnapshotInspector:
            def account(self):
                return account

            def __getattr__(self, name):
                return getattr(inspector, name)

        try:
            await runtime.start()
            await report(
                "start",
                dict(status="RUNNING", strategy_started=True, hold_seconds=policy["hold_seconds"]),
            )
            existing = control.execute(
                "SELECT id FROM intents WHERE run_manifest_id=%s", (manifest.manifest_id,)
            ).fetchall()
            if len(existing) > 1:
                raise ValueError("ambiguous engineering episode")
            if existing:
                intent_id = str(existing[0][0])
            else:
                if args.resume_intent:
                    raise ValueError("close-only takeover must never create an entry")
                account = await asyncio.to_thread(inspector.account)
                limits, gaps, ns = market()
                # Exact Spot lot. Independent risk rechecks fee-adjusted hedge headroom.
                qty = (
                    Decimal(policy["target_leg_usdt"]) / limits.spot_ask / spot.lot_size
                ).to_integral_value(rounding=ROUND_FLOOR) * spot.lot_size
                entry = submit_engineering_entry(
                    connection=control,
                    runtime=runtime,
                    risk_service=risk,
                    manifest=manifest,
                    account=account,
                    limits=limits,
                    quantity=qty,
                    price=limits.spot_ask,
                    receive_gap_ms=gaps,
                    observed_ns=ns,
                    hold_seconds=policy["hold_seconds"],
                )
                await report("trade", entry)
                if "intent_id" not in entry:
                    raise ValueError("engineering entry denied")
                intent_id = entry["intent_id"]
            deadline = time.monotonic() + policy["maximum_run_seconds"]
            failures = 0
            while time.monotonic() < deadline:
                await asyncio.sleep(2)
                while fills:
                    await report("trade", {"fill_confirmed": True, **fills.pop(0)})
                if (
                    runtime.strategy.failure
                    or not runtime.node.kernel.exec_engine.check_connected()
                ):
                    raise ValueError(
                        "stream disconnected or durable callback failed; no new orders"
                    )
                commands = control.execute(
                    "SELECT c.id FROM order_commands c JOIN order_dispatches d ON d.command_id=c.id "
                    "WHERE c.intent_id=%s",
                    (intent_id,),
                ).fetchall()
                blocked = False
                for command in commands:
                    result = await asyncio.to_thread(
                        recover_tracked_order, control, inspector, str(command[0])
                    )
                    if result["status"] != "APPLIED":
                        blocked = True
                        break
                if blocked:
                    failures += 1
                    if failures >= 3:
                        raise ValueError("three read-only recovery failures; entry will not replay")
                    continue
                failures = 0
                account = await asyncio.to_thread(inspector.account)
                result = manage_episode_once(
                    connection=control,
                    inspector=SnapshotInspector(),
                    runtime=runtime,
                    risk_service=risk,
                    manifest=manifest,
                    intent_id=intent_id,
                    market_evidence=market,
                )
                if result.get("command_id"):
                    await report("trade", result)
                elif result.get("status") == "CLOSED":
                    await report("stop", result | {"completed_episode": True})
                    return
                elif result.get("status") == "DUST_REMAINS":
                    # Matched-with-dust may hold until the deadline. Closing dust is
                    # settled as an audited owned residual only when futures are flat
                    # and no bounded order could still sell it; it is never sold
                    # below lot size and never hidden as flat.
                    closing = control.execute(
                        "SELECT close_requested_at IS NOT NULL FROM episode_baselines WHERE intent_id=%s",
                        (intent_id,),
                    ).fetchone()[0]
                    if closing:
                        limits, _, _ = market()
                        account = await asyncio.to_thread(inspector.account)
                        settled = settle_episode_residual(
                            control, intent_id=intent_id, account=account, limits=limits
                        )
                        await report(
                            "stop",
                            result | settled | {"completed_episode": True, "exact_flat": False},
                        )
                        return
                elif result.get("status") not in {"WAIT"}:
                    await report("error", result)
                    raise ValueError("management action blocked; no replacement submitted")
            raise ValueError("bounded run deadline exceeded; inventory requires reconciliation")
        except Exception as exc:
            await report(
                "error",
                dict(
                    error_type=type(exc).__name__,
                    error_frames=[
                        dict(file=Path(f.filename).name, line=f.lineno, function=f.name)
                        for f in traceback.extract_tb(exc.__traceback__)
                    ],
                    new_entries_halted=True,
                ),
            )
            raise
        finally:
            await runtime.stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-env-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--started-at", required=True, help="Stable run identity; reuse on restart")
    parser.add_argument(
        "--resume-intent", help="Explicit close-only version takeover; no new entry"
    )
    parser.add_argument("--previous-manifest")
    parser.add_argument("--execute-demo-auto", action="store_true", required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    loop, runtimes = asyncio.new_event_loop(), []
    try:
        with _private_native_logs():
            loop.run_until_complete(execute(args, runtimes))
        return 0
    except Exception:
        return 2
    finally:
        for runtime in runtimes:
            runtime.dispose()
        loop.close()


if __name__ == "__main__":
    raise SystemExit(main())
