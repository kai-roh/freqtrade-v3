# Milestone 1 Research Report

- generated_at: `2026-09-15T10:30:00Z`
- decision: **STOP_BEFORE_CLASSIFIER**
- normal cost: `20.0 bps`
- stress cost: `30.0 bps`

## Portfolio promotion results

| Candidate | Side | Trades | PF normal | EV normal | MDD normal | Positive folds | Pair concentration | Stress pass | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| no_trade | long | 0 | 0.000 | 0.000000 | 0.000% | 0 | 1.000 | FAIL | REJECT |
| no_trade | short | 0 | 0.000 | 0.000000 | 0.000% | 0 | 1.000 | FAIL | REJECT |
| trend_pullback | long | 307 | 0.515 | -0.000093 | 2.966% | 0 | 1.000 | FAIL | REJECT |
| trend_pullback | short | 254 | 0.563 | -0.000083 | 2.244% | 0 | 1.000 | FAIL | REJECT |
| volatility_breakout | long | 415 | 0.572 | -0.000082 | 3.527% | 0 | 1.000 | FAIL | REJECT |
| volatility_breakout | short | 382 | 0.554 | -0.000102 | 4.243% | 1 | 1.000 | FAIL | REJECT |

## Component diagnostics

| Candidate | Pair | Side | Trades | PF normal | EV normal | MDD normal | Positive folds | Stress pass | Decision |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| no_trade | BTC/USDT:USDT | long | 0 | 0.000 | 0.000000 | 0.000% | 0 | FAIL | REJECT |
| no_trade | BTC/USDT:USDT | short | 0 | 0.000 | 0.000000 | 0.000% | 0 | FAIL | REJECT |
| no_trade | ETH/USDT:USDT | long | 0 | 0.000 | 0.000000 | 0.000% | 0 | FAIL | REJECT |
| no_trade | ETH/USDT:USDT | short | 0 | 0.000 | 0.000000 | 0.000% | 0 | FAIL | REJECT |
| trend_pullback | BTC/USDT:USDT | long | 110 | 0.510 | -0.000083 | 0.983% | 1 | FAIL | REJECT |
| trend_pullback | BTC/USDT:USDT | short | 120 | 0.562 | -0.000069 | 0.884% | 0 | FAIL | REJECT |
| trend_pullback | ETH/USDT:USDT | long | 197 | 0.518 | -0.000098 | 1.983% | 0 | FAIL | REJECT |
| trend_pullback | ETH/USDT:USDT | short | 134 | 0.564 | -0.000096 | 1.398% | 0 | FAIL | REJECT |
| volatility_breakout | BTC/USDT:USDT | long | 270 | 0.471 | -0.000088 | 2.380% | 0 | FAIL | REJECT |
| volatility_breakout | BTC/USDT:USDT | short | 160 | 0.471 | -0.000107 | 1.809% | 0 | FAIL | REJECT |
| volatility_breakout | ETH/USDT:USDT | long | 145 | 0.703 | -0.000071 | 1.388% | 1 | FAIL | REJECT |
| volatility_breakout | ETH/USDT:USDT | short | 222 | 0.602 | -0.000099 | 2.449% | 1 | FAIL | REJECT |

## Interpretation

Classifier research is allowed only when a same-side BTC/ETH portfolio passes both normal and stress cost gates, including the 50% pair-contribution limit. Component rows are diagnostics only. Parameters are selected independently inside each training fold and are never selected on its validation rows.

Machine-learning implementation remains blocked unless at least one deterministic portfolio is promoted. Passing this report still does not authorize live trading.
