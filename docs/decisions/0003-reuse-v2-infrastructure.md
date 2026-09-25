# 0003 — Reuse the retired V2 infrastructure for a fail-closed V3 test

- Status: Accepted
- Date: 2026-08-10

## Context

V2 is retired after 194 closed dry-run trades and a cumulative loss of 183.8396 USDT. There are no open V2 trades. The host, localhost API tunnel, restart policy, and health monitoring remain useful and do not depend on the rejected V2 strategy or FreqAI models.

Milestone 1 still blocks classifier work and paper trading of the rejected deterministic policies. The user explicitly requested that V2 stop completely, its data be backed up, and V3 take over the existing server infrastructure for testing.

## Decision

Stop and remove the V2 container after creating and validating a server-local full backup. V3 then reuses:

- container identity `freqtrade_kai`;
- localhost API binding `127.0.0.1:8080`;
- `restart: unless-stopped` and the existing health-check pattern;
- the existing API and exchange environment values, copied without exposing them.

V3 does not reuse the V2 trade database, models, predictions, strategy, logs, or market-data directory. It continues with `tradesv3_v3.sqlite`, `V3ShadowStrategy`, and the V3 project path.

## Safety boundary

The runtime starts in `dry_run` mode, at fixed 50 USDT stake and 1x leverage. `V3ShadowStrategy` emits zero long and short entries. This is an infrastructure/API/health test only; it is not evidence that a trading strategy passed research gates.

Classifier implementation, non-zero entry signals, and live capital remain blocked by Decision 0002.
