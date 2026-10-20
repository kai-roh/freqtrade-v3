#!/usr/bin/env python3
"""Run fixed candle-scalp hypotheses with isolated passive-execution simulation.

No credentials, exchange account access, runtime deployment or parameter search.
"""

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
from scripts.build_divergence_dataset import sha256  # noqa: E402
from scripts.run_divergence_research import (  # noqa: E402
    END,
    START,
    bootstrap,
    gate_pair,
    load_frozen,
)
from v3.candle_scalp import ScalpingConfig, backtest, prepare_signals  # noqa: E402

STRATEGIES = ("pullback", "range", "breakout")
SIZINGS = ("single", "averaging")
REGIMES = ("normal", "stress")


def load_study(path: Path) -> tuple[dict, dict]:
    manifest = json.loads(path.read_text())
    if sha256(ROOT / manifest["registration"]) != manifest["registration_sha256"]:
        raise ValueError("Scalp registration changed after freeze")
    source = ROOT / manifest["source_manifest"]
    if sha256(source) != manifest["source_manifest_sha256"]:
        raise ValueError("Source data manifest changed after freeze")
    for name, row in manifest["files"].items():
        if sha256(ROOT / row["path"]) != row["sha256"]:
            raise ValueError(f"Scalp input hash mismatch: {name}")
    original, panels = load_frozen(source)
    if manifest["files"] != original["files"]:
        raise ValueError("Study files differ from original frozen dataset")
    if manifest["start"] != START.isoformat() or manifest["end_exclusive"] != END.isoformat():
        raise ValueError("Unregistered evaluation span")
    return manifest, panels


def marked_daily(series: pd.Series) -> pd.Series:
    """A minute closing at midnight belongs to the preceding UTC day."""
    values = series.copy()
    values.index = values.index - pd.Timedelta(nanoseconds=1)
    return values.resample("1D").last()


def worst_dates(bars: pd.DataFrame) -> pd.Series:
    close = bars.close.resample("1D").last()
    returns = close.pct_change()
    returns = returns[(returns.index >= START) & (returns.index < END)]
    # mergesort is stable, so UTC date is the tie-breaker on the sorted input.
    return returns.sort_values(kind="stable").iloc[:10]


def portfolio_summary(
    results: dict, signals: dict
) -> tuple[dict, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    equity = sum(result.equity.equity for result in results.values())
    exposure = sum(result.equity.exposure for result in results.values())
    filled_bound = sum(result.equity.filled_notional_peak for result in results.values())
    if equity.isna().any() or exposure.isna().any():
        raise ValueError("Per-asset equity indices do not align")
    initial = sum(result.summary["initial_equity"] for result in results.values())
    if initial != 1000:
        raise ValueError("Registered portfolio capital is 1,000 USDT")
    trades = (
        pd.concat(
            [r.trades.assign(symbol=s) for s, r in results.items() if len(r.trades)],
            ignore_index=True,
        )
        if any(len(r.trades) for r in results.values())
        else pd.DataFrame()
    )
    fills = (
        pd.concat(
            [r.fills.assign(symbol=s) for s, r in results.items() if len(r.fills)],
            ignore_index=True,
        )
        if any(len(r.fills) for r in results.values())
        else pd.DataFrame()
    )
    daily_equity = marked_daily(equity)
    daily_pnl = daily_equity.diff()
    daily_pnl.iloc[0] = daily_equity.iloc[0] - initial
    daily_exposure = exposure.copy()
    daily_exposure.index = daily_exposure.index - pd.Timedelta(nanoseconds=1)
    daily = pd.DataFrame(
        {
            "equity": daily_equity,
            "pnl": daily_pnl,
            "mean_exposure": daily_exposure.resample("1D").mean(),
            "max_exposure": daily_exposure.resample("1D").max(),
        }
    )
    filled_daily = filled_bound.copy()
    filled_daily.index = filled_daily.index - pd.Timedelta(nanoseconds=1)
    daily["filled_notional_bound"] = filled_daily.resample("1D").max()
    daily["add_fills"] = 0
    if len(fills):
        add_times = pd.to_datetime(fills.loc[fills.kind == "add", "timestamp"], utc=True)
        counts = pd.Series(1, index=pd.DatetimeIndex(add_times)).resample("1D").sum()
        daily["add_fills"] = counts.reindex(daily.index, fill_value=0).astype(int)
    gain_by_asset = {
        s: float(r.trades.loc[r.trades.net_pnl > 0, "net_pnl"].sum()) if len(r.trades) else 0.0
        for s, r in results.items()
    }
    gains = sum(gain_by_asset.values())
    losses = float(-trades.loc[trades.net_pnl < 0, "net_pnl"].sum()) if len(trades) else 0.0
    values = np.r_[initial, equity.to_numpy()]
    mdd = float(-(values / np.maximum.accumulate(values) - 1).min() * 100)
    monthly = daily.pnl.groupby(daily.index.strftime("%Y-%m")).sum()
    edges = pd.date_range(START, END, freq="2MS")
    slices = {
        f"{left:%Y-%m}..{right - pd.Timedelta(days=1):%Y-%m}": float(
            daily.loc[(daily.index >= left) & (daily.index < right), "pnl"].sum()
        )
        for left, right in zip(edges[:-1], edges[1:], strict=True)
    }
    summary = {
        "initial_equity": initial,
        "final_equity": float(equity.iloc[-1]),
        "net_pnl": float(equity.iloc[-1] - initial),
        "return_pct": float((equity.iloc[-1] / initial - 1) * 100),
        "max_drawdown_pct": mdd,
        "trades": len(trades),
        "win_rate": float((trades.net_pnl > 0).mean()) if len(trades) else 0.0,
        "profit_factor": gains / losses if losses > 0 else None,
        "positive_profit_concentration": max(gain_by_asset.values()) / gains if gains else 1.0,
        "positive_folds": sum(v > 0 for v in slices.values()),
        "monthly_pnl": monthly.to_dict(),
        "two_month_pnl": slices,
        "bootstrap": bootstrap(daily.pnl),
        "no_trade_pnl": 0.0,
        "max_exposure": float(exposure.max()),
        "max_filled_notional_bound": float(filled_bound.max()),
        "mean_exposure": float(exposure.mean()),
        "worst_campaign": float(trades.net_pnl.min()) if len(trades) else 0.0,
        "max_holding_minutes": float(trades.holding_minutes.max()) if len(trades) else 0.0,
        "entry_fills": int((fills.kind == "entry").sum()) if len(fills) else 0,
        "add_fills": int((fills.kind == "add").sum()) if len(fills) else 0,
        "per_symbol": {s: r.summary for s, r in results.items()},
        "signals": {
            s: int(frame.loc[(frame.index >= START) & (frame.index < END), "entry_signal"].sum())
            for s, frame in signals.items()
        },
    }
    for key in ("price_pnl", "fees", "slippage_cost", "funding_pnl"):
        summary[key] = float(trades[key].sum()) if len(trades) else 0.0
    if len(trades):
        summary["exit_reasons"] = trades.exit_reason.value_counts().to_dict()
    if not np.isclose(
        summary["net_pnl"], float(trades.net_pnl.sum()) if len(trades) else 0, atol=1e-8
    ):
        raise ValueError("Campaign ledger does not reconcile to final portfolio equity")
    if not np.isclose(
        summary["net_pnl"],
        summary["price_pnl"] - summary["fees"] - summary["slippage_cost"] + summary["funding_pnl"],
        atol=1e-8,
    ):
        raise ValueError("Price/cost decomposition does not reconcile")
    if not np.isclose(daily.pnl.sum(), summary["net_pnl"], atol=1e-8):
        raise ValueError("Marked daily P&L does not reconcile")
    return summary, trades, fills, daily


def stress_diagnostic(daily: pd.DataFrame, trades: pd.DataFrame, dates: pd.Series) -> list[dict]:
    output = []
    for date, market_return in dates.items():
        row = daily.loc[date]
        if len(trades):
            times = pd.to_datetime(trades.exit_time, utc=True)
            closed = trades.loc[(times >= date) & (times < date + pd.Timedelta(days=1))]
            realized = float(closed.net_pnl.sum())
        else:
            realized = 0.0
        output.append(
            {
                "date": date.strftime("%Y-%m-%d"),
                "btc_daily_return_pct": float(market_return * 100),
                "marked_pnl": float(row.pnl),
                "closed_campaign_pnl": realized,
                "add_fills": int(row.add_fills),
                "max_exposure": float(row.max_exposure),
                "filled_notional_bound": float(row.filled_notional_bound),
            }
        )
    return output


def paired_comparison(single: pd.DataFrame, averaging: pd.DataFrame) -> dict:
    if not single.index.equals(averaging.index):
        raise ValueError("Paired daily dates differ")
    difference = averaging.pnl - single.pnl
    return {
        "net_pnl_difference": float(difference.sum()),
        "bootstrap_daily_difference": bootstrap(difference),
        "single_mean_exposure": float(single.mean_exposure.mean()),
        "averaging_mean_exposure": float(averaging.mean_exposure.mean()),
        "equal_risk_comparison": False,
    }


def write_report(payload: dict, path: Path) -> None:
    lines = [
        "# Candle scalp — three hypotheses and bounded averaging",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "Fixed retrospective study, 2025-10-01..2026-09-30 UTC, BTC/ETH USD-M perpetuals.",
        "1,000 USDT split500/500; 30m signals and completed1h/4h trend, minute execution only.",
        "Initial entry budget200 in BOTH variants; averaging may add150+150, capped500 per asset.",
        "Campaign stop-risk budget5 USDT; fixed stop,4h timeout, daily/sleeve protection. No leverage escalation.",
        "This is a mechanical interpretation, not a reproduction of discretionary news/chart judgments.",
        "",
        "| Strategy | Sizing | Execution | Net USDT | Trades | Win rate | PF | MDD | Add fills |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, result in payload["results"].items():
        strategy, sizing, regime = name.split("/")
        pf = f"{result['profit_factor']:.3f}" if result["profit_factor"] is not None else "n/a"
        lines.append(
            f"| {strategy} | {sizing} | {regime} | {result['net_pnl']:.2f} | {result['trades']} | "
            f"{result['win_rate']:.1%} | {pf} | {result['max_drawdown_pct']:.2f}% | {result['add_fills']} |"
        )
    lines += ["", "## Research gates", ""]
    for variant, decision in payload["decisions"].items():
        failed = ", ".join(k for k, v in decision["gates"].items() if not v)
        lines.append(f"- **{variant}: {decision['decision']}**. Failed: {failed or 'none'}.")
    lines += [
        "",
        "## Does bounded averaging improve the single entry?",
        "",
        "Same first entry budget, but averaging consumes additional capital and risk; this is NOT an equal-risk superiority test.",
        "Difference = averaging minus single, including all no-trade days. Bootstrap is descriptive, not new-data confirmation.",
        "",
        "| Strategy/cost | Net difference USDT | Daily difference95% CI | Single mean exposure | Averaging mean exposure |",
        "|---|---:|---|---:|---:|",
    ]
    for name, paired in payload["paired"].items():
        ci = paired["bootstrap_daily_difference"]
        lines.append(
            f"| {name} | {paired['net_pnl_difference']:.2f} | [{ci['lower_95']:.4f}, {ci['upper_95']:.4f}] | "
            f"{paired['single_mean_exposure']:.2f} | {paired['averaging_mean_exposure']:.2f} |"
        )
    for name, result in payload["results"].items():
        lines += [
            "",
            f"## {name}",
            "",
            f"Price P&L {result['price_pnl']:.4f} − fees {result['fees']:.4f} − slippage {result['slippage_cost']:.4f} "
            f"+ funding {result['funding_pnl']:.4f} = net {result['net_pnl']:.4f} USDT.",
            f"Worst campaign {result['worst_campaign']:.4f}; maximum holding {result['max_holding_minutes']:.0f}min; "
            f"minute-close peak/mean exposure {result['max_exposure']:.2f}/{result['mean_exposure']:.2f} USDT; "
            f"within-minute filled-notional portfolio bound {result['max_filled_notional_bound']:.2f} USDT.",
            f"Entry/add fills {result['entry_fills']}/{result['add_fills']}; exits {json.dumps(result.get('exit_reasons', {}), sort_keys=True)}.",
            "Monthly marked P&L: "
            + "; ".join(f"{k}: {v:.2f}" for k, v in result["monthly_pnl"].items()),
            "Two-month marked P&L: "
            + "; ".join(f"{k}: {v:.2f}" for k, v in result["two_month_pnl"].items()),
            "",
            "| Asset | Net USDT | Campaigns | Diagnostics |",
            "|---|---:|---:|---|",
        ]
        for symbol, row in result["per_symbol"].items():
            lines.append(
                f"| {symbol} | {row['net_pnl']:.2f} | {row['trades']} | "
                f"{json.dumps(row.get('diagnostics', {}), sort_keys=True)} |"
            )
        lines += [
            "",
            "Worst10 BTC daily-return dates, selected ex post for a disclosed stress diagnostic:",
            "",
            "| UTC date | BTC return | Marked portfolio P&L | Adds | Minute-close peak / filled-notional bound |",
            "|---|---:|---:|---:|---:|",
        ]
        for row in result["worst_market_days"]:
            lines.append(
                f"| {row['date']} | {row['btc_daily_return_pct']:.2f}% | {row['marked_pnl']:.2f} | "
                f"{row['add_fills']} | {row['max_exposure']:.2f} / {row['filled_notional_bound']:.2f} |"
            )
    lines += [
        "",
        "## Limits",
        "",
        "All data are retrospective development data, already used for prior candidate research. No prospective holdout or tuned winner.",
        "Passive fills require strict trade-through2bps normal/5bps stress; mere touches do not fill. Placement rejects crossing limits using minute-open proxy.",
        "A post-only order's actual queue, acceptance, latency and fills cannot be reconstructed from OHLC. These are deliberately explicit simulation assumptions.",
        "Maker fees2bps each side; safety exits taker5bps plus2/5bps adverse slippage. Stress changes both fill eligibility and taker slippage, so trade samples can differ.",
        "The entry/add minute cannot take profit; stops win ambiguous bars; pending adds can prevent assuming a same-minute target fill. Gaps can exceed stop budgets.",
        "Not every claimed scalp is represented: no real-time news or social popularity data, no other coins, no unbounded martingale or rising leverage.",
        "Daily/weekly candle context is descriptive; it was not used to fit filters. Twelve-hour context was not added as another fitted filter.",
        "The unit steps/minimum notionals are static modeling assumptions. MDD and mean/peak marked exposure use minute-close marks, not tick-level liquidation risk.",
        "Filled-notional bound retains same-minute round trips; it sums each asset's within-minute maximum cost notional and can overstate synchronized portfolio exposure. Campaign max_exposure is an OHLC high-price envelope, not observed tick exposure.",
        "A pass authorizes research consideration only, never automatic paper/Demo/live execution. Existing MA200 operation remains unchanged.",
        "",
        "## Reproduction",
        "",
        "```bash",
        ".venv/bin/python scripts/run_candle_scalp_research.py",
        "```",
        "",
        "study-manifest.json locks registration, source minute/funding/mark hashes. summary.json locks source code hashes and all12 configs/results.",
        "CSV artifacts contain complete campaign/fill ledgers and daily marked-equity paths.",
        "",
    ]
    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=ROOT / "evidence/candle-scalp/study-manifest.json"
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "research_results/candle-scalp")
    args = parser.parse_args()
    manifest, panels = load_study(args.manifest)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    source_names = (
        "v3/candle_scalp.py",
        "scripts/run_candle_scalp_research.py",
        "scripts/run_divergence_research.py",
        "scripts/build_divergence_dataset.py",
        "v3/divergence.py",
    )
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "git_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_sha256": {name: sha256(ROOT / name) for name in source_names},
        "manifest_sha256": sha256(args.manifest),
        "registration_sha256": manifest["registration_sha256"],
        "development_only": True,
        "results": {},
        "decisions": {},
        "paired": {},
        "config": {},
    }
    dates = worst_dates(panels["BTC"][0])
    for strategy in STRATEGIES:
        signals = {symbol: prepare_signals(bars, strategy) for symbol, (bars, _) in panels.items()}
        dailies = {}
        for sizing in SIZINGS:
            for regime in REGIMES:
                results = {}
                for symbol, (bars, funding) in panels.items():
                    cfg = ScalpingConfig(
                        strategy=strategy,
                        averaging=sizing == "averaging",
                        stress=regime == "stress",
                        min_notional=100 if symbol == "BTC" else 20,
                    )
                    minute = bars.loc[(bars.index >= START) & (bars.index < END)]
                    results[symbol] = backtest(minute, signals[symbol], cfg, funding)
                    payload["config"][f"{strategy}/{sizing}/{regime}/{symbol}"] = asdict(cfg)
                summary, trades, fills, daily = portfolio_summary(results, signals)
                summary["worst_market_days"] = stress_diagnostic(daily, trades, dates)
                name = f"{strategy}/{sizing}/{regime}"
                payload["results"][name] = summary
                dailies[f"{sizing}/{regime}"] = daily
                slug = name.replace("/", "-")
                trades.to_csv(args.output_dir / f"campaigns-{slug}.csv", index=False)
                fills.to_csv(args.output_dir / f"fills-{slug}.csv", index=False)
                daily.to_csv(args.output_dir / f"daily-{slug}.csv")
                print(
                    json.dumps(
                        {
                            "cell": name,
                            "trades": summary["trades"],
                            "net_pnl": summary["net_pnl"],
                            "win_rate": summary["win_rate"],
                            "adds": summary["add_fills"],
                        }
                    ),
                    flush=True,
                )
            payload["decisions"][f"{strategy}/{sizing}"] = gate_pair(
                payload["results"][f"{strategy}/{sizing}/normal"],
                payload["results"][f"{strategy}/{sizing}/stress"],
            )
        for regime in REGIMES:
            payload["paired"][f"{strategy}/{regime}"] = paired_comparison(
                dailies[f"single/{regime}"], dailies[f"averaging/{regime}"]
            )
    (args.output_dir / "summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    write_report(payload, args.output_dir / "REPORT.md")
    print(json.dumps(payload["decisions"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
