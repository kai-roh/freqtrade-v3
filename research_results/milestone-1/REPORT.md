# Milestone 1 Research Report

- generated_at: `2026-08-10T01:50:01Z`
- decision: **STOP_BEFORE_CLASSIFIER**
- normal cost: `20.0 bps`
- stress cost: `30.0 bps`

## Portfolio promotion results

| Candidate | Side | Trades | PF normal | EV normal | MDD normal | Positive folds | Pair concentration | Stress pass | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| no_trade | long | 0 | 0.000 | 0.000000 | 0.000% | 0 | 1.000 | FAIL | REJECT |
| no_trade | short | 0 | 0.000 | 0.000000 | 0.000% | 0 | 1.000 | FAIL | REJECT |
| trend_pullback | long | 314 | 0.491 | -0.002046 | 65.738% | 0 | 1.000 | FAIL | REJECT |
| trend_pullback | short | 223 | 0.611 | -0.001605 | 37.039% | 0 | 1.000 | FAIL | REJECT |
| volatility_breakout | long | 447 | 0.576 | -0.001916 | 93.025% | 0 | 1.000 | FAIL | REJECT |
| volatility_breakout | short | 424 | 0.666 | -0.001563 | 69.994% | 0 | 1.000 | FAIL | REJECT |

## Component diagnostics

| Candidate | Pair | Side | Trades | PF normal | EV normal | MDD normal | Positive folds | Stress pass | Decision |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| no_trade | BTC/USDT:USDT | long | 0 | 0.000 | 0.000000 | 0.000% | 0 | FAIL | REJECT |
| no_trade | BTC/USDT:USDT | short | 0 | 0.000 | 0.000000 | 0.000% | 0 | FAIL | REJECT |
| no_trade | ETH/USDT:USDT | long | 0 | 0.000 | 0.000000 | 0.000% | 0 | FAIL | REJECT |
| no_trade | ETH/USDT:USDT | short | 0 | 0.000 | 0.000000 | 0.000% | 0 | FAIL | REJECT |
| trend_pullback | BTC/USDT:USDT | long | 127 | 0.499 | -0.001665 | 22.245% | 1 | FAIL | REJECT |
| trend_pullback | BTC/USDT:USDT | short | 105 | 0.670 | -0.001118 | 11.736% | 0 | FAIL | REJECT |
| trend_pullback | ETH/USDT:USDT | long | 187 | 0.488 | -0.002305 | 44.277% | 0 | FAIL | REJECT |
| trend_pullback | ETH/USDT:USDT | short | 118 | 0.574 | -0.002039 | 26.279% | 0 | FAIL | REJECT |
| volatility_breakout | BTC/USDT:USDT | long | 274 | 0.433 | -0.002442 | 66.917% | 0 | FAIL | REJECT |
| volatility_breakout | BTC/USDT:USDT | short | 189 | 0.534 | -0.002081 | 41.700% | 0 | FAIL | REJECT |
| volatility_breakout | ETH/USDT:USDT | long | 173 | 0.777 | -0.001083 | 28.077% | 2 | FAIL | REJECT |
| volatility_breakout | ETH/USDT:USDT | short | 235 | 0.764 | -0.001145 | 32.660% | 1 | FAIL | REJECT |

## Interpretation

Classifier research is allowed only when a same-side BTC/ETH portfolio passes both normal and stress cost gates, including the 50% pair-contribution limit. Component rows are diagnostics only. Parameters are selected independently inside each training fold and are never selected on its validation rows.

Machine-learning implementation remains blocked unless at least one deterministic portfolio is promoted. Passing this report still does not authorize live trading.
