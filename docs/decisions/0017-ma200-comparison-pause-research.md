# 0017 — Fixed MA200 comparison: PAUSE_RESEARCH (implementability at a 500 USDT sleeve)

- Status: Accepted
- Date: 2026-10-02

## Context

After Decision 0016, a review asked whether the MA200 control is worth an
order-free forward observation. Two conditions were set: it had to be compared
against a spot hold, and real order constraints had to be checked. The plan
`docs/PHASE2C_MA200_COMPARISON.md` and its five criteria were committed before
the spot data and the code (`76345aa`). The code was committed before the run
(`98a3c34`).

Two corrections came with it:

- The constrained mode now applies the minimum notional to each order delta.
  Perpetual reduce-only orders are exempt, and spot orders are not.
- The recorded Phase 2c run is reproduced exactly with
  `--legacy-holding-min-notional`.

Everything here is diagnosis on development data that has been seen before.
Output: `research_results/phase2c/ma200-comparison/`.

## Result (2022-08-01 to 2026-10-01, 500 USDT sleeve, constrained mode)

| Normal cost | Net USDT | Annual return | Sharpe | MDD | Worst year | Orders/yr |
|---|---:|---:|---:|---:|---:|---:|
| MA200 (perpetual, long/short) | 318.21 | 12.53% | 0.76 | 14.32% | −5.33 | 21.6 |
| BH-VT spot | 423.44 | 15.84% | 0.93 | 22.60% | −46.11 | 8.9 |
| BH-VT perpetual | 340.90 | 13.27% | 0.81 | 22.39% | −44.35 | 7.7 |

Criteria against the spot hold, the same under both costs:

| Criterion | Result |
|---|---|
| C1 keeps at least 70% of the hold's net | Pass (75%) |
| C2 MDD at most 2/3 of the hold's | Pass (14.3% against a limit of 15.1%) |
| C3 return/MDD at least the hold's | Pass (0.88 against 0.70) |
| C4 worst calendar year at least the hold's | Pass (−5.3 against −46.1) |
| C5 skipped orders at most 10% of attempts | **Fail** (234 of 322, 73%) |

Pre-committed verdict: **PAUSE_RESEARCH**.

### What the C5 failure is

- All 234 skips are BTC. ETH had none.
- The BTC perpetual lot is 0.001 BTC, worth 16–126 USDT over the period
  (median 64). A BTC position capped at 250 USDT therefore has only two to four
  possible sizes.
- Volatility-scaled adjustments of at least 50 USDT often fall below one lot. The
  same order is then attempted again every day, which raised attempts from 87
  (ideal) to 322.
- The economic effect is modest. Constrained MA200 made 318 USDT against 340 in
  ideal mode, and its MDD was 14.3% against 13.4%. The failure is that at this
  sleeve the BTC position cannot follow the rule it is meant to test.
- For information only, and not used for the verdict: at a 1,000 USDT sleeve the
  skips are 3 of 99.

### What the comparison shows

- MA200 does what a risk overlay should. Against the spot hold, it kept 75% of
  the return with about 63% of the drawdown, and its worst year was −5 against
  −46.
- It does not earn more. The spot hold had the higher Sharpe (0.93 against 0.76)
  and 105 USDT more profit. The difference is in the regimes: the hold made +255
  in 2023 against MA200's +58. MA200 made its money in 2022 and 2026, when
  falling markets put it short.
- MA200 changed direction 33 times on BTC and 25 times on ETH in 4.2 years. That
  is frequent whipsaw around the average, not a handful of regime calls.
- The spot hold beat the perpetual hold by about 80 USDT, mainly through funding
  (−70 USDT on perpetuals). Perpetuals are an expensive way to hold long.
- With the corrected order rule, Phase 2c H4's constrained walk-forward is still
  positive: 184.9 USDT normal and 177.8 stress. Gate 8 still passes, and the
  Phase 2c verdict is unchanged.

## Decision

1. Under the pre-committed plan, no forward observation is registered and
   research pauses. No new strategy family is added now.
2. Going beyond this verdict would be an explicit user decision, recorded as a
   departure from the plan. Examples are observing MA200 with a larger sleeve
   or with a different BTC instrument. Moving to a 1,000 USDT sleeve would put
   the whole account into directional exposure. That is a capital decision, not
   a research detail.
3. Nothing here authorizes orders, real capital, or leverage.

## Lessons

- Implementability has to be checked at the order level and at the planned
  sleeve before any rule is tuned. At this capital, BTC perpetual lots are too
  coarse for volatility-scaled sizing.
- For long exposure, spot is the reference. Funding made the perpetual hold
  about 80 USDT worse over four years.
