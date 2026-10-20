# Phase 2b H3 episode trace

- source: Stage A fold 0 validation, rule `H3 W=168h k=3`, cost `normal`
- replay matches recorded fold decomposition: **True**

## Totals over the traced legs (USDT)

| Price P&L | Funding realized | Funding expected at entry | Costs | Net |
|---:|---:|---:|---:|---:|
| -6.622 | 0.421 | 0.804 | 0.477 | -6.678 |

## Episode 1: 2026-02-05T01:00 → 2026-02-05T16:00 (15 h)

Net over its legs -4.670 USDT (equity change from the first held hour, which excludes entry costs: -4.610).

| Leg | Side | Entry | Exit | Exit by | Score at entry (bp) | Underlying | Price P&L | Funding exp. | Funding real. | Costs | Net |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| BTC | short | 02-05T01:00 | 02-05T16:00 | taker_risk | 0.24 | -7.40% | 3.698 | 0.002 | -0.002 | 0.056 | 3.639 |
| SOL | long | 02-05T01:00 | 02-05T16:00 | taker_risk | -1.56 | -7.80% | -3.899 | 0.015 | 0.001 | 0.056 | -3.954 |
| BNB | short | 02-05T01:00 | 02-05T16:00 | taker_risk | 0.04 | -5.37% | 2.687 | 0.000 | 0.000 | 0.057 | 2.630 |
| XRP | long | 02-05T01:00 | 02-05T16:00 | taker_risk | -0.45 | -13.02% | -6.510 | 0.004 | -0.002 | 0.053 | -6.566 |
| DOGE | long | 02-05T01:00 | 02-05T16:00 | taker_risk | -0.53 | -9.06% | -4.530 | 0.005 | 0.002 | 0.055 | -4.584 |
| LINK | short | 02-05T01:00 | 02-05T16:00 | taker_risk | 0.43 | -8.43% | 4.217 | 0.004 | 0.004 | 0.056 | 4.164 |

- Short basket ['BTC', 'BNB', 'LINK']: price 10.602, funding 0.001. Long basket ['SOL', 'XRP', 'DOGE']: price -14.939, funding 0.000.
- Price P&L path: after 24 h -4.337, after 5 days -4.337, low -4.337 at 02-05T16:00, end -4.337.
- Leg counts unequal for 0 of 16 hours (price P&L in those hours 0.000); max |long − short| notional 3.7 USDT, mean -1.4.
- 30-day beta to BTC at entry: BTC 1.00, SOL 1.29, BNB 0.86, XRP 1.21, DOGE 1.37, LINK 1.32. Net beta-weighted notional (long − short) +35.0 USDT.
- Market over the episode: equal-weight universe -8.55%, BTC -7.40%.

## Episode 2: 2026-02-07T01:00 → 2026-02-21T02:00 (337 h)

Net over its legs -2.008 USDT (equity change from the first held hour, which excludes entry costs: -1.948).

| Leg | Side | Entry | Exit | Exit by | Score at entry (bp) | Underlying | Price P&L | Funding exp. | Funding real. | Costs | Net |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| BTC | short | 02-07T01:00 | 02-14T01:00 | maker | -0.08 | -1.22% | 0.611 | -0.009 | -0.026 | 0.020 | 0.566 |
| ETH | long | 02-07T01:00 | 02-21T01:00 | maker | -0.56 | -3.95% | -1.977 | 0.115 | 0.073 | 0.020 | -1.924 |
| SOL | long | 02-07T01:00 | 02-21T01:00 | maker | -2.13 | -2.44% | -1.220 | 0.436 | 0.196 | 0.020 | -1.043 |
| XRP | long | 02-07T01:00 | 02-21T01:00 | maker | -0.74 | -2.42% | -1.211 | 0.153 | 0.129 | 0.020 | -1.101 |
| LINK | short | 02-07T01:00 | 02-21T01:00 | maker | 0.37 | +0.80% | -0.402 | 0.076 | 0.051 | 0.020 | -0.371 |
| BNB | short | 02-07T01:00 | 02-21T02:00 | taker_fallback | 0.01 | -3.83% | 1.914 | 0.002 | -0.003 | 0.044 | 1.867 |

- Short basket ['BTC', 'LINK', 'BNB']: price 2.123, funding 0.021. Long basket ['ETH', 'SOL', 'XRP']: price -4.408, funding 0.398.
- Price P&L path: after 24 h 0.870, after 5 days -1.154, low -2.708 at 02-13T02:00, end -2.284.
- Leg counts unequal for 169 of 338 hours (price P&L in those hours -2.882); max |long − short| notional 59.0 USDT, mean 25.3.
- 30-day beta to BTC at entry: BTC 1.00, ETH 1.26, SOL 1.24, XRP 1.16, LINK 1.19, BNB 0.86. Net beta-weighted notional (long − short) +30.8 USDT.
- Market over the episode: equal-weight universe -0.88%, BTC -2.86%.

## Minimum-hold lock

| Leg | Side | Kept by lock from | Lock ends | Final exit | Price P&L while locked | Funding while locked |
|---|---|---|---|---|---:|---:|
| BTC | short | 02-10T00:00 | 02-12T01:00 | 02-14T01:00 | 1.916 | -0.011 |
| ETH | long | 02-10T00:00 | 02-12T01:00 | 02-21T01:00 | -3.580 | 0.034 |

## Blocked decisions while holding

| Decision | Spread (bp) | Held after |
|---|---:|---|
| 02-14T00:00 | 0.91 | short ['BNB', 'LINK'] / long ['ETH', 'SOL', 'XRP'] |
| 02-15T00:00 | 0.87 | short ['BNB', 'LINK'] / long ['ETH', 'SOL', 'XRP'] |
| 02-16T00:00 | 0.73 | short ['BNB', 'LINK'] / long ['ETH', 'SOL', 'XRP'] |
| 02-17T00:00 | 0.70 | short ['BNB', 'LINK'] / long ['ETH', 'SOL', 'XRP'] |
| 02-18T00:00 | 0.66 | short ['BNB', 'LINK'] / long ['ETH', 'SOL', 'XRP'] |
| 02-19T00:00 | 0.63 | short ['BNB', 'LINK'] / long ['ETH', 'SOL', 'XRP'] |
| 02-20T00:00 | 0.54 | short ['BNB', 'LINK'] / long ['ETH', 'SOL', 'XRP'] |

## Daily stop

- 2026-02-05T16:00: equity 195.604 vs day start 200.000
