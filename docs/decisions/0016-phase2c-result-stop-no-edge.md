# 0016 — Phase 2c BTC/ETH low-frequency trend result: STOP_NO_EDGE

- Status: Accepted; corrected 2026-10-02 after review (see "Corrections")
- Date: 2026-10-02

## Context

The Phase 2c contract (`docs/PHASE2C_PREREGISTRATION.md`, frozen in `e34d3ad`)
was run unchanged. The code was committed before the run (`64ae3ef`).

- Data: BTC and ETH USD-M perpetuals from 2020-01-01 to 2026-10-01
  (`evidence/phase2c/data-manifest.json`), declared development data.
- Artifacts: `research_results/phase2c/REPORT.md` and `results.json`.
- The sleeve was 500 USDT, half per asset, at most 1x.

## Result

The walk-forward account was one continuous account from 2022-08-01 to
2026-10-01, with nine windows, compared with its controls over the same period.

| Strategy (normal cost) | Net USDT | Annual return | Sharpe | MDD |
|---|---:|---:|---:|---:|
| H4 walk-forward | 200.63 | 8.42% | 0.54 | 19.23% |
| BH-VT (risk-matched long hold) | 339.60 | 13.23% | 0.78 | 24.81% |
| MA200 (control) | 340.54 | 13.26% | 0.80 | 13.41% |

Six of eight gates pass under both costs:

- net return positive;
- 8.05% a year under stress costs, against the 8% threshold;
- MDD 19–20%;
- 6 of 9 windows positive;
- all 6 configurations positive over the full period;
- still positive after removing the best year and after removing the best
  episode;
- positive under exchange lot and minimum-notional limits.

Two gates fail:

- **H4's Sharpe is below BH-VT's**, 0.54 against 0.78 (0.52 against 0.78 under
  stress). The trend timing gave lower drawdown than holding but did not add
  risk-adjusted return.
- **PBO is 0.34**, above the 0.2 limit. The configuration chosen in training (60-day
  binary in 8 of 9 windows) was the best over the full period, with Sharpe 1.12.
  Most of that advantage came from 2020–2022 and did not carry into the
  walk-forward years.

The 20-day block bootstrap of daily net returns gives a 95% interval of
[−0.00014, +0.00068], which includes zero.

### Where the return came from

- Long positions earned +340.5 USDT of price P&L. Short positions lost −79.6.
- Funding cost −37.1 USDT, paid while long in a mostly rising market.
- Fees and slippage were 23 USDT under normal costs.
- The strategy was in the market 73% of the time. Its profit is largely the
  market's long drift, collected with less exposure than holding.
- By calendar year: −42 in 2022 (Aug–Dec), +98 in 2023, −17 in 2024, +86 in
  2025, and +76 in 2026 (to 10-01).

## Decision

`STOP_NO_EDGE` under the registration. The order-free forward observation in §7
is not started.

## What this does and does not say

- It says that, in 2022–2026, daily BTC/ETH trend rules with volatility scaling
  earned money mainly by being long. Their risk-adjusted return was below a
  volatility-matched long hold, and the selection procedure showed overfitting.
- It does not say that trend following loses money. All six configurations
  were positive, and drawdown was lower than holding.
- **The MA200 control is not a finding.** It matched BH-VT's Sharpe with about
  half the drawdown, but it was a fixed control and not a hypothesis. Noticing
  it after the results is data snooping. Testing it would need a new
  registration, confirmed only on data after that registration. Calling it the
  better strategy now would repeat the mistake this process exists to prevent.

## Consequences

- Phase 3 still has no candidate. Nothing here authorizes orders, real capital,
  or leverage.
- This was the third research contract to fail its registered gates, after
  Phase 2 and Phase 2b. The next step is a user decision: stop directional
  research, register a new hypothesis with forward-only confirmation, or pause
  research.

## Corrections (2026-10-02, after review)

The decision stands. These statements are corrected.

- **"The MA200 control is not a finding"** was too strong. MA200 was registered
  as a control before the results, so its result is valid development evidence.
  Because it was singled out after seeing the results, it supports a follow-up
  hypothesis but is not enough for promotion.
- **MA200 is long/short, not long/cash.** Below its 200-day average it holds a
  short. Its exposure time is 100%. Its advantage over BH-VT is lower drawdown,
  not higher return: it made 0.94 USDT more over the whole period, with MDD
  13.4% against 24.8%. That advantage is concentrated in a few regimes. In
  2022 (Aug–Dec) MA200 made +46 against −47, and in 2026 +104 against −2.5;
  but in 2023 BH-VT made +232 against MA200's +77.
- **"The selection procedure showed overfitting"** overstates PBO. PBO 0.34 is a
  diagnostic: the configuration that won in training tended to rank lower out
  of sample within this candidate set. It is not a probability of loss, and it
  does not prove that trend following has no edge.
- **The bootstrap interval is about H4's own mean daily return.** It is not about
  the difference from BH-VT.
- **Gate 8 used a holding-based minimum-notional check.** The exchange applies the
  minimum to the order delta and exempts perpetual reduce-only orders. The
  controls were also run without exchange filters. Both are corrected in the
  pre-committed MA200 comparison (`docs/PHASE2C_MA200_COMPARISON.md`).
