#!/usr/bin/env python3
"""Run the registered minute-divergence study; writes local research artifacts only."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_divergence_dataset import sha256, validate_bars  # noqa: E402
from v3.divergence import DivergenceConfig, backtest, prepare_signals  # noqa: E402

START = pd.Timestamp("2025-10-01", tz="UTC")
END = pd.Timestamp("2026-10-01", tz="UTC")


def aggregate(bars: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if minutes == 1:
        return bars.copy()
    if minutes != 5:
        raise ValueError("Only registered 1m/5m variants are allowed")
    grouped = bars.resample("5min", closed="left", label="left")
    result = grouped.agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    if not (grouped.size() == 5).all():
        raise ValueError("Incomplete five-minute bar")
    return result


def load_frozen(manifest_path: Path) -> tuple[dict, dict]:
    manifest = json.loads(manifest_path.read_text())
    if manifest["registration_sha256"] != sha256(ROOT / manifest["registration"]):
        raise ValueError("Registration changed after dataset freeze")
    panels = {}
    for symbol in ("BTC", "ETH"):
        parts = {}
        for kind in ("bars", "funding_rate", "mark"):
            record = manifest["files"][f"{symbol}/{kind}"]
            path = ROOT / record["path"]
            if sha256(path) != record["sha256"]:
                raise ValueError(f"Frozen dataset hash mismatch: {symbol}/{kind}")
            frame = pd.read_feather(path)
            if kind == "bars":
                validate_bars(frame, "2025-09-01", "2026-10-01")
            frame.index = pd.DatetimeIndex(pd.to_datetime(frame.pop("date"), utc=True)).as_unit(
                "ns"
            )
            if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
                raise ValueError(f"Invalid index: {symbol}/{kind}")
            parts[kind] = frame
        funding = parts["funding_rate"][["open"]].rename(columns={"open": "funding_rate"})
        # Hour open timestamp +1h is when that mark close first becomes known.
        mark = parts["mark"].close.copy()
        mark.index = mark.index + pd.Timedelta(hours=1)
        funding["mark_price"] = mark.reindex(funding.index)
        funding = funding[(funding.index >= START) & (funding.index < END)]
        expected = pd.date_range(START, END, inclusive="left", freq="8h")
        if (
            not funding.index.equals(expected.as_unit("ns"))
            or not np.isfinite(funding.to_numpy()).all()
        ):
            raise ValueError(f"Funding/mark coverage missing: {symbol}")
        panels[symbol] = (parts["bars"], funding)
    return manifest, panels


def bootstrap(daily: pd.Series) -> dict:
    """Circular seven-day blocks; preserves short-range daily dependence."""
    values = daily.to_numpy()
    rng = np.random.default_rng(42)
    starts = rng.integers(0, len(values), size=(2000, int(np.ceil(len(values) / 7))))
    indices = (starts[:, :, None] + np.arange(7)) % len(values)
    means = values[indices.reshape(2000, -1)[:, : len(values)]].mean(axis=1)
    lower, upper = np.quantile(means, [0.025, 0.975])
    return {
        "mean_daily_pnl": float(values.mean()),
        "lower_95": float(lower),
        "upper_95": float(upper),
        "samples": 2000,
        "block_days": 7,
        "seed": 42,
    }


def summarize(results: dict, prepared: dict) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    equity = sum(result.equity.equity for result in results.values()).rename("equity")
    trade_parts = [
        result.trades.assign(symbol=symbol)
        for symbol, result in results.items()
        if len(result.trades)
    ]
    trades = pd.concat(trade_parts, ignore_index=True) if trade_parts else pd.DataFrame()
    # Equity is timestamped at candle CLOSE; midnight belongs to the preceding day.
    daily_close = equity.copy()
    daily_close.index = daily_close.index - pd.Timedelta(nanoseconds=1)
    daily_close = daily_close.resample("1D").last()
    daily_pnl = daily_close.diff()
    daily_pnl.iloc[0] = daily_close.iloc[0] - 1000
    losses = -trades.loc[trades.net_pnl < 0, "net_pnl"].sum() if len(trades) else 0
    gains = trades.loc[trades.net_pnl > 0, "net_pnl"].sum() if len(trades) else 0
    profit_factor = float(gains / losses) if losses > 0 else None
    peak_values = np.maximum.accumulate(np.r_[1000, equity.to_numpy()])
    dd = np.r_[1000, equity.to_numpy()] / peak_values - 1
    monthly = daily_pnl.groupby(daily_pnl.index.strftime("%Y-%m")).sum()
    fold_edges = pd.date_range(START, END, freq="2MS")
    folds = {
        f"{left:%Y-%m}..{right - pd.Timedelta(days=1):%Y-%m}": float(
            daily_pnl[(daily_pnl.index >= left) & (daily_pnl.index < right)].sum()
        )
        for left, right in zip(fold_edges[:-1], fold_edges[1:], strict=True)
    }
    positive_by_asset = {
        symbol: float(result.trades.loc[result.trades.net_pnl > 0, "net_pnl"].sum())
        if len(result.trades)
        else 0.0
        for symbol, result in results.items()
    }
    concentration = float(max(positive_by_asset.values()) / gains) if gains > 0 else 1.0
    diagnostics = {
        symbol: {
            "entry_signals": int(frame.entry_signal.sum()),
            "low_pivots": int(frame.low_confirmed.sum()),
            "uptrend_bars": int(frame.trend.sum()),
            "volume_ok_bars": int(frame.volume_ok.sum()),
        }
        for symbol, frame in prepared.items()
    }
    summary = {
        "initial_equity": 1000,
        "final_equity": float(equity.iloc[-1]),
        "net_pnl": float(equity.iloc[-1] - 1000),
        "return_pct": float((equity.iloc[-1] / 1000 - 1) * 100),
        "max_drawdown_pct": float(-dd.min() * 100),
        "trades": len(trades),
        "win_rate": float((trades.net_pnl > 0).mean()) if len(trades) else 0,
        "profit_factor": profit_factor,
        "positive_folds": sum(v > 0 for v in folds.values()),
        "positive_profit_concentration": concentration,
        "monthly_pnl": monthly.to_dict(),
        "two_month_pnl": folds,
        "bootstrap": bootstrap(daily_pnl),
        "per_symbol": {s: r.summary for s, r in results.items()},
        "signals": diagnostics,
        "no_trade_pnl": 0.0,
        "funding_pnl": sum(r.summary["funding_pnl"] for r in results.values()),
        "skipped_signals": sum(r.summary["skipped_signals"] for r in results.values()),
    }
    if len(trades):
        if not np.isclose(trades.net_pnl.sum(), summary["net_pnl"], atol=1e-8):
            raise ValueError("Trade ledger does not reconcile to final portfolio equity")
        summary["fees"] = float(trades.entry_fee.sum() + trades.exit_fee.sum())
        for key in ("price_pnl", "slippage_cost"):
            if key in trades:
                summary[key] = float(trades[key].sum())
        summary["exit_reasons"] = trades.exit_reason.value_counts().to_dict()
    return summary, trades, pd.DataFrame({"equity": daily_close, "pnl": daily_pnl})


def gate_pair(normal: dict, stress: dict) -> dict:
    gates = {
        "at_least_100_trades": min(normal["trades"], stress["trades"]) >= 100,
        "both_costs_positive": min(normal["net_pnl"], stress["net_pnl"]) > 0,
        "both_pf_at_least_1_15": all(
            s["profit_factor"] is not None and s["profit_factor"] >= 1.15 for s in (normal, stress)
        ),
        "both_mdd_at_most_10pct": max(normal["max_drawdown_pct"], stress["max_drawdown_pct"]) <= 10,
        "both_at_least_4_positive_folds": min(normal["positive_folds"], stress["positive_folds"])
        >= 4,
        "both_concentration_at_most_80pct": max(
            normal["positive_profit_concentration"], stress["positive_profit_concentration"]
        )
        <= 0.8,
        "normal_bootstrap_lower_positive": normal["bootstrap"]["lower_95"] > 0,
    }
    decision = (
        "INSUFFICIENT_TRADES"
        if not gates["at_least_100_trades"]
        else "RESEARCH_ONLY_PASS"
        if all(gates.values())
        else "STOP_NO_EDGE"
    )
    return {"decision": decision, "gates": {key: bool(value) for key, value in gates.items()}}


def write_report(payload: dict, path: Path) -> None:
    lines = [
        "# RSI divergence scalp — retrospective backtest",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "Research only. Fixed rules; no parameter search, no exchange orders or MA200 changes.",
        "Evaluation: 2025-10-01 through 2026-09-30 UTC; September 2025 warmup excluded.",
        "Capital: 1,000 USDT; 500 per asset, no leverage amplification. All cells shown.",
        "",
        "| Variant | Cost | Net USDT | Return | Trades | Win rate | PF | MDD | Positive slices |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, result in payload["results"].items():
        timeframe, cost = name.split("/")
        pf = f"{result['profit_factor']:.3f}" if result["profit_factor"] is not None else "n/a"
        lines.append(
            f"| {timeframe} | {cost} | {result['net_pnl']:.2f} | {result['return_pct']:.2f}% | "
            f"{result['trades']} | {result['win_rate']:.1%} | {pf} | "
            f"{result['max_drawdown_pct']:.2f}% | {result['positive_folds']}/6 |"
        )
    for timeframe, gate in payload["decisions"].items():
        lines += ["", f"## {timeframe}: {gate['decision']}", ""]
        lines += [
            f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in gate["gates"].items()
        ]
    for name, result in payload["results"].items():
        lines += ["", f"## {name}", "", "| Asset | Net USDT | Trades |", "|---|---:|---:|"]
        for asset, row in result["per_symbol"].items():
            lines.append(f"| {asset} | {row['net_pnl']:.2f} | {row['trades']} |")
        lines += [
            "",
            f"Funding P&L: {result['funding_pnl']:.4f}; fees: {result.get('fees', 0):.4f}; "
            f"slippage cost: {result.get('slippage_cost', 0):.4f} USDT.",
            f"Skipped entry signals (price/risk/lot constraints): {result['skipped_signals']}.",
            "Signals while already holding are ignored; these are not included in skips.",
            f"Daily mean P&L bootstrap 95%: [{result['bootstrap']['lower_95']:.4f}, "
            f"{result['bootstrap']['upper_95']:.4f}] USDT/day.",
            "",
            "Monthly marked P&L (USDT): "
            + "; ".join(f"{k}: {v:.2f}" for k, v in result["monthly_pnl"].items()),
            "",
            "Two-month marked P&L (USDT): "
            + "; ".join(f"{k}: {v:.2f}" for k, v in result["two_month_pnl"].items()),
        ]
    lines += [
        "",
        "## Interpretation and limits",
        "",
        "The no-trade control earns 0. The source's 100% win claim is not an assumption.",
        "This is one mechanical RSI interpretation; the source leaves indicator, pivots, stops and supply-zone exits undefined.",
        "All periods are development data, including dates previously examined at hourly resolution. Stability slices are not an independent holdout.",
        "Normal cost is 14bps and stress is 20bps round-trip (5bps fee plus 2/5bps slippage each side).",
        "Targets are taker executions on touch; OHLC cannot prove actual liquidity, latency or maker fills. Both-hit bars choose stop first.",
        "MDD uses bar-close marked equity, not tick-level or liquidation-engine marks. Futures contract prices mark intrabar P&L; funding uses prior hourly mark closes.",
        "Static current-style lot/notional assumptions are not reconstructed historical exchange rules. Small-account rounding materially affects results.",
        "Separate per-asset sleeves prevent capital reuse; no leverage amplification, averaging down, or compounding. Liquidations are not modeled.",
        "A negative result rejects these fixed rules; it does not establish that every divergence strategy fails.",
        "No live deployment follows automatically, even if a research gate passes.",
        "",
        "## Reproduction",
        "",
        "```bash",
        ".venv/bin/python scripts/build_divergence_dataset.py",
        ".venv/bin/python scripts/run_divergence_research.py",
        "```",
        "",
        "Inputs and registration are SHA256-verified before simulation. summary.json records source hashes, manifest and rules.",
        "Official dataset/schema: https://github.com/binance/binance-public-data",
        "",
    ]
    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=ROOT / "evidence/divergence/data-manifest.json"
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research_results/divergence")
    args = parser.parse_args()
    manifest, panels = load_frozen(args.manifest)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    sources = {
        name: sha256(ROOT / name)
        for name in (
            "v3/divergence.py",
            "scripts/run_divergence_research.py",
            "scripts/build_divergence_dataset.py",
        )
    }
    git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "git_sha": git_sha,
        "source_sha256": sources,
        "manifest_sha256": sha256(args.manifest),
        "registration_sha256": manifest["registration_sha256"],
        "development_only": True,
        "results": {},
        "decisions": {},
        "config": {},
    }
    for minutes in (1, 5):
        prepared = {}
        for symbol, (bars, _) in panels.items():
            signals = prepare_signals(aggregate(bars, minutes))
            prepared[symbol] = signals[(signals.index >= START) & (signals.index < END)]
        for cost, slip in (("normal", 2.0), ("stress", 5.0)):
            results = {}
            for symbol, signals in prepared.items():
                cfg = DivergenceConfig(
                    slippage_bps=slip, min_notional=100 if symbol == "BTC" else 20
                )
                results[symbol] = backtest(signals, cfg, panels[symbol][1], prepared=True)
                payload["config"][f"{minutes}m/{cost}/{symbol}"] = asdict(cfg)
            summary, trades, daily = summarize(results, prepared)
            name = f"{minutes}m/{cost}"
            payload["results"][name] = summary
            if len(trades):
                trades.to_csv(args.output_dir / f"trades-{minutes}m-{cost}.csv", index=False)
            daily.to_csv(args.output_dir / f"daily-{minutes}m-{cost}.csv")
            print(
                json.dumps(
                    {
                        "cell": name,
                        "trades": summary["trades"],
                        "net_pnl": summary["net_pnl"],
                        "pf": summary["profit_factor"],
                    }
                ),
                flush=True,
            )
        payload["decisions"][f"{minutes}m"] = gate_pair(
            payload["results"][f"{minutes}m/normal"], payload["results"][f"{minutes}m/stress"]
        )
    (args.output_dir / "summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    write_report(payload, args.output_dir / "REPORT.md")
    print(json.dumps(payload["decisions"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
