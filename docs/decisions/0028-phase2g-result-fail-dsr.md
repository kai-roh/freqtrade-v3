# 0028 — Phase 2g result: T1 taker-flow ensemble FAIL on the deflated Sharpe only

- Status: Accepted
- Date: 2026-10-20 (KST)

## Result

T1 was evaluated once on 2024-01-01..2026-09-29. Results are in
`research_results/phase2g/validation-results.json`.

| | Total | CAGR | Sharpe | MDD |
|---|---|---|---|---|
| T1 | +380.6% | 77% | 1.86 | 21% |
| T1 at double cost | +293.2% | 65% | 1.65 | 22% |
| BTC hold | +92.9% | | 0.75 | 53% |
| BTC/ETH hold | +57.4% | | 0.57 | 60% |

| Sub-period | T1 | BTC |
|---|---|---|
| 2024 (up) | +47.5%, Sharpe 1.56 | +115.8% |
| 2025-01..2026-09 (down) | +250.0%, Sharpe 2.14 | −19.6% |

| Gate | Result |
|---|---|
| V1 positive, Sharpe ≥ 0.5 | Pass |
| V2 positive in both sub-periods | Pass |
| V3 positive at double cost | Pass |
| V4 MDD below BTC (21% vs 53%) | Pass |
| V5 DSR ≥ 0.95 at M=188 | **Fail (0.84)** |

Verdict under the registration: **`FAIL`**. The validation window is now spent.

## Diagnostics (after the verdict; they do not change it)

- **The DSR failure comes from the trial-Sharpe dispersion.** The 66 Phase 2f
  configurations ranged from −1.47 to 1.83 in annual Sharpe. At M=188, that
  dispersion puts the expected best-by-chance Sharpe above two. T1's full-period
  Sharpe, 1.86 over 2020-07..2026-09, does not clear it.
- **Funding is about half the return.** With funding set to zero, the validation
  total is +188.8% with Sharpe 1.32. The strategy is long names with persistent taker
  buying. In squeezes, those names pay longs very large negative funding. On
  2025-08-05, for example, MYXUSDT's hourly funding hit the −2% cap for most of the
  day. These entries were checked against the raw archive files and are real.
- **The return is concentrated.** Weekly returns were positive in 65% of 144 weeks.
  Without the best 10 weeks, the validation log return falls from 1.57 to 0.17,
  about +18%. The largest symbol contributions were 2025–26 small-cap squeezes:
  LAB, ZEC, SIREN, and WLD.
- **The long side earned most of the return.** Long legs alone made +180% and short
  legs alone +29%.

## Consequences

- T1 is not promoted on historical evidence. No historical window remains for a
  clean confirmation. Any further check must use data after 2026-10-20.
- Because T1 uses only public daily archive data, it can be evaluated forward on
  that data without running anything on the server. Executing it on Demo would
  additionally test fills, and would need user approval.
